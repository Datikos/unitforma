import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { BoundaryOut, BuildingOut, SheetOut, SuggestionOut, UnitOut, UnitformaApi, problemMessage } from 'api-client';
import { PlanMode, PlanPolygon, PlanViewerComponent, Point, Ring } from 'plan-viewer';

/** Sheet mapping editor: floor assignment, calibration, unit boundaries, vector suggestions, review (plan §13.1 steps 3–5). */
@Component({
  selector: 'uf-sheet-page',
  imports: [FormsModule, DecimalPipe, MatCardModule, MatFormFieldModule, MatInputModule, MatSelectModule, MatButtonModule, MatButtonToggleModule, RouterLink, PlanViewerComponent],
  template: `
    <div class="uf-page">
      <div class="uf-page-header">
        <h2>Sheet @if (sheet(); as s) { page {{ s.page_no }} }</h2>
        <a mat-stroked-button [routerLink]="['../../documents']">Documents</a>
      </div>
      @if (error()) { <p class="uf-error">{{ error() }}</p> }
      @if (sheet(); as s) {
        <div class="uf-toolbar">
          <mat-form-field appearance="outline" class="uf-floor">
            <mat-label>Floor</mat-label>
            <mat-select [value]="s.floor_id" (valueChange)="assign($event)">
              <mat-option [value]="null">— not assigned —</mat-option>
              @for (f of floors(); track f.id) { <mat-option [value]="f.id">{{ f.label }}</mat-option> }
            </mat-select>
          </mat-form-field>
          @if (s.suggested_floor_id && !s.floor_id) { <span class="uf-muted">Suggested: {{ floorLabel(s.suggested_floor_id) }}</span> }
          <mat-button-toggle-group [value]="mode()" (valueChange)="mode.set($event)">
            <mat-button-toggle value="view">View</mat-button-toggle>
            <mat-button-toggle value="calibrate">Calibrate</mat-button-toggle>
            <mat-button-toggle value="draw" [disabled]="!s.floor_id">Draw unit</mat-button-toggle>
          </mat-button-toggle-group>
          <button mat-stroked-button [disabled]="busy() || !s.floor_id" (click)="suggest()">Suggest boundaries</button>
          <span class="uf-muted">
            @if (pxPerMetre(); as ppm) { {{ ppm | number: '1.0-0' }} px/m @if (s.calibration_status === 'inherited') { (inherited) } } @else { not calibrated }
            · {{ hintsText() }}
          </span>
          <span class="uf-spacer"></span>
          <button mat-flat-button [disabled]="busy() || draftCount() === 0" (click)="approve()">Approve {{ draftCount() }} draft unit(s)</button>
        </div>
        @if (mode() === 'calibrate') {
          <mat-card appearance="outlined"><mat-card-content class="uf-form-row">
            <span>Click two points of a known distance, then enter it:</span>
            <mat-form-field appearance="outline"><mat-label>Distance (m)</mat-label><input matInput type="number" step="0.01" [(ngModel)]="distance" name="distance" /></mat-form-field>
            <button mat-stroked-button [disabled]="!calibPts() || !distance" (click)="calibrate()">Apply</button>
          </mat-card-content></mat-card>
        }
        @if (mode() === 'draw') {
          <mat-card appearance="outlined"><mat-card-content class="uf-form-row">
            <span>Click the corners of the unit; double-click or Enter to close.</span>
            <mat-form-field appearance="outline"><mat-label>Type</mat-label>
              <mat-select [(ngModel)]="unitType" name="unitType"><mat-option value="apartment">Apartment</mat-option><mat-option value="commercial">Commercial</mat-option><mat-option value="parking">Parking</mat-option><mat-option value="storage">Storage</mat-option></mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline"><mat-label>Code (optional)</mat-label><input matInput [(ngModel)]="code" name="code" placeholder="auto" /></mat-form-field>
            <mat-form-field appearance="outline"><mat-label>Label on drawing</mat-label><input matInput [(ngModel)]="label" name="label" /></mat-form-field>
          </mat-card-content></mat-card>
        }
        @if (candidates().length) {
          <mat-card appearance="outlined"><mat-card-content class="uf-form-row">
            <span>{{ candidates().length }} suggested polygon(s) from the drawing's line work (dashed). Click one to select it.</span>
            @if (selectedCandidate(); as c) {
              <span class="uf-chip">{{ c.label ?? 'unlabelled' }} · {{ c.confidence * 100 | number: '1.0-0' }} %</span>
              <mat-form-field appearance="outline"><mat-label>Type</mat-label>
                <mat-select [(ngModel)]="unitType" name="candType"><mat-option value="apartment">Apartment</mat-option><mat-option value="commercial">Commercial</mat-option><mat-option value="parking">Parking</mat-option><mat-option value="storage">Storage</mat-option></mat-select>
              </mat-form-field>
              <mat-form-field appearance="outline"><mat-label>Code (optional)</mat-label><input matInput [(ngModel)]="code" name="candCode" placeholder="auto" /></mat-form-field>
              <button mat-flat-button [disabled]="busy()" (click)="acceptCandidate(c)">Accept as unit</button>
              <button mat-button [disabled]="busy()" (click)="dismissCandidate(c)">Dismiss</button>
            }
            <button mat-stroked-button [disabled]="busy() || labelledCount() === 0" (click)="acceptLabelled()">Accept all {{ labelledCount() }} labelled</button>
            <button mat-button (click)="candidates.set([])">Clear suggestions</button>
          </mat-card-content></mat-card>
        }
        <uf-plan-viewer
          [src]="s.raster_url ?? null"
          [width]="s.raster_width ?? 1000"
          [height]="s.raster_height ?? 700"
          [polygons]="polygons()"
          [mode]="mode()"
          (polygonDrawn)="onDrawn($event)"
          (calibrationPicked)="calibPts.set($event)"
          (polygonSelected)="onSelected($event)"
        />
        <mat-card appearance="outlined">
          <mat-card-header><mat-card-title>Units on this sheet</mat-card-title></mat-card-header>
          <mat-card-content>
            <table class="uf-units">
              <thead><tr><th>Code</th><th>Type</th><th>Status</th><th>Source</th><th>Measured area</th><th></th></tr></thead>
              <tbody>
                @for (u of units(); track u.id) {
                  <tr [class.uf-selected]="u.id === selectedUnitId()" (click)="selectedUnitId.set(u.id)">
                    <td>{{ u.code }}</td><td>{{ u.unit_type }}</td>
                    <td>{{ u.lifecycle_status }} · {{ u.verification_status }}</td>
                    <td>{{ sourceOf(u) }}</td>
                    <td>@if (measured(u); as a) { {{ a.value_m2 }} m² ({{ a.verification_status }}) } @else { — }</td>
                    <td><button mat-button (click)="relabel(u); $event.stopPropagation()">Relabel</button><button mat-button (click)="remove(u); $event.stopPropagation()">Remove</button></td>
                  </tr>
                } @empty { <tr><td colspan="6" class="uf-muted">No units drawn yet.</td></tr> }
              </tbody>
            </table>
          </mat-card-content>
        </mat-card>
      }
    </div>
  `,
  styles: `
    .uf-toolbar { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .uf-floor { min-width: 220px; }
    .uf-spacer { flex: 1; }
    .uf-form-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .uf-units { width: 100%; border-collapse: collapse; }
    .uf-units th, .uf-units td { text-align: left; padding: 0.4rem 0.5rem; border-bottom: 1px solid #e5e7eb; }
    .uf-units tr { cursor: pointer; }
    .uf-selected { background: rgba(245, 158, 11, 0.12); }
    .uf-chip { padding: 0.2rem 0.5rem; border-radius: 4px; background: #ede9fe; }
  `,
})
export class SheetPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly sheetId = input.required<string>();
  readonly sheet = signal<SheetOut | null>(null);
  readonly buildings = signal<BuildingOut[]>([]);
  readonly boundaries = signal<BoundaryOut[]>([]);
  readonly units = signal<UnitOut[]>([]);
  readonly candidates = signal<SuggestionOut[]>([]);
  readonly selectedCandidateIdx = signal<number | null>(null);
  readonly mode = signal<PlanMode>('view');
  readonly calibPts = signal<[Point, Point] | null>(null);
  readonly selectedUnitId = signal<string | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  distance: number | null = null;
  unitType: 'apartment' | 'commercial' | 'parking' | 'storage' = 'apartment';
  code = '';
  label = '';

  readonly floors = computed(() =>
    this.buildings()
      .filter((b) => b.kind === 'building')
      .flatMap((b) => (b.floors ?? []).map((f) => ({ id: f.id, label: `${b.code} · ${f.display_name} (level ${f.level})` }))),
  );
  readonly polygons = computed<PlanPolygon[]>(() => {
    const byUnit = new Map(this.units().map((u) => [u.id, u]));
    const own: PlanPolygon[] = this.boundaries().map((b) => ({ id: b.unit_id, ring: (b.polygon['ring'] as Ring) ?? [], label: byUnit.get(b.unit_id)?.code ?? b.label ?? '', status: b.status, selected: b.unit_id === this.selectedUnitId() }));
    const cands: PlanPolygon[] = this.candidates().map((c, i) => ({ id: `cand:${i}`, ring: c.ring as Ring, label: c.label ?? '', kind: 'candidate' as const, selected: i === this.selectedCandidateIdx() }));
    return [...own, ...cands];
  });
  readonly selectedCandidate = computed(() => (this.selectedCandidateIdx() === null ? null : this.candidates()[this.selectedCandidateIdx()!] ?? null));
  readonly labelledCount = computed(() => this.candidates().filter((c) => c.label).length);
  readonly draftCount = computed(() => this.boundaries().filter((b) => b.status === 'draft').length);
  readonly hintsText = computed(() => {
    const h = (this.sheet()?.hints ?? {}) as { levels?: string[]; scales?: number[]; apartment_labels?: string[] };
    const parts: string[] = [];
    if (h.levels?.length) parts.push(`levels ${h.levels.join(', ')}`);
    if (h.scales?.length) parts.push(`scale 1:${h.scales.join('/')}`);
    if (h.apartment_labels?.length) parts.push(`${h.apartment_labels.length} apartment labels`);
    return parts.join(' · ') || 'no hints';
  });
  readonly pxPerMetre = computed(() => {
    const c = this.sheet()?.calibration as { m_per_px?: number } | null | undefined;
    return c?.m_per_px ? 1 / c.m_per_px : null;
  });

  constructor() {
    toObservable(this.sheetId).subscribe(() => void this.load());
  }

  floorLabel(id: string): string {
    return this.floors().find((f) => f.id === id)?.label ?? id;
  }

  measured(u: UnitOut) {
    return (u.areas ?? []).find((a) => a.source === 'drawing_measured');
  }

  sourceOf(u: UnitOut): string {
    return (u.boundaries ?? []).find((b) => b.sheet_id === this.sheetId())?.source ?? '';
  }

  async load(): Promise<void> {
    try {
      const [s, b, bounds, units] = await Promise.all([
        this.api.getSheet(this.tenantId(), this.sheetId()),
        this.api.listBuildings(this.tenantId(), this.projectId()),
        this.api.listBoundaries(this.tenantId(), this.sheetId()),
        this.api.listUnits(this.tenantId(), this.projectId()),
      ]);
      this.sheet.set(s);
      this.buildings.set(b);
      this.boundaries.set(bounds);
      const onSheet = new Set(bounds.map((x) => x.unit_id));
      this.units.set(units.filter((u) => onSheet.has(u.id)));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  onSelected(id: string): void {
    if (id.startsWith('cand:')) {
      this.selectedCandidateIdx.set(Number(id.slice(5)));
      this.selectedUnitId.set(null);
    } else {
      this.selectedUnitId.set(id);
      this.selectedCandidateIdx.set(null);
    }
  }

  assign(floorId: string | null): Promise<void> {
    return this.run(() => this.api.assignSheetFloor(this.tenantId(), this.sheetId(), floorId, this.sheet()!.version));
  }

  calibrate(): Promise<void> {
    const pts = this.calibPts();
    if (!pts || !this.distance) return Promise.resolve();
    return this.run(async () => {
      await this.api.calibrateSheet(this.tenantId(), this.sheetId(), { p1: pts[0], p2: pts[1], distance_m: this.distance! }, this.sheet()!.version);
      this.calibPts.set(null);
      this.mode.set('view');
    });
  }

  onDrawn(ring: Ring): Promise<void> {
    return this.run(async () => {
      await this.api.createBoundary(this.tenantId(), this.sheetId(), { ring, unit_type: this.unitType, code: this.code || null, label: this.label || null, source: 'manual' });
      this.code = this.label = '';
    });
  }

  /** Closed loops from the sheet's vectors; polygons already covered by a unit are left out. */
  async suggest(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const all = await this.api.suggestBoundaries(this.tenantId(), this.sheetId());
      const taken = this.boundaries().map((b) => centroidOf(b.polygon['ring'] as Ring));
      const fresh = all.filter((c) => !taken.some((t) => inside(t, c.ring as Ring)));
      this.candidates.set(fresh);
      this.selectedCandidateIdx.set(fresh.length ? 0 : null);
      if (!all.length) this.error.set('No closed loops found in this sheet (scanned or raster-only drawing): draw units manually.');
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  acceptCandidate(c: SuggestionOut): Promise<void> {
    return this.run(async () => {
      await this.api.createBoundary(this.tenantId(), this.sheetId(), { ring: c.ring, unit_type: this.unitType, code: this.code || null, label: c.label ?? null, source: 'vector_suggest' });
      this.code = '';
      this.dismissCandidate(c);
    });
  }

  acceptLabelled(): Promise<void> {
    return this.run(async () => {
      for (const c of this.candidates().filter((x) => x.label)) {
        await this.api.createBoundary(this.tenantId(), this.sheetId(), { ring: c.ring, unit_type: 'apartment', code: null, label: c.label ?? null, source: 'vector_suggest' });
      }
      this.candidates.update((list) => list.filter((x) => !x.label));
      this.selectedCandidateIdx.set(null);
    });
  }

  dismissCandidate(c: SuggestionOut): void {
    this.candidates.update((list) => list.filter((x) => x !== c));
    this.selectedCandidateIdx.set(this.candidates().length ? 0 : null);
  }

  approve(): Promise<void> {
    return this.run(() => this.api.approveSheet(this.tenantId(), this.sheetId()));
  }

  relabel(u: UnitOut): Promise<void> {
    const code = window.prompt(`New code for ${u.code}`, u.code);
    if (!code || code === u.code) return Promise.resolve();
    return this.run(() => this.api.relabelUnit(this.tenantId(), u.id, code, u.version, 'reviewer relabel'));
  }

  remove(u: UnitOut): Promise<void> {
    if (!window.confirm(`Mark ${u.code} as removed? The record and its history are kept.`)) return Promise.resolve();
    return this.run(() => this.api.removeUnit(this.tenantId(), u.id, u.version, 'removed in mapping editor'));
  }

  private async run(fn: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await fn();
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}

function centroidOf(ring: Ring): Point {
  const n = ring.length || 1;
  return [ring.reduce((a, p) => a + p[0], 0) / n, ring.reduce((a, p) => a + p[1], 0) / n];
}

/** Ray-casting point-in-polygon on normalised coordinates. */
function inside(pt: Point, ring: Ring): boolean {
  let hit = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > pt[1] !== yj > pt[1] && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi) hit = !hit;
  }
  return hit;
}
