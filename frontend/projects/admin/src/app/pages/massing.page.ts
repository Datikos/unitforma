import { DecimalPipe, SlicePipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { MassingOut, UnitformaApi, problemMessage } from 'api-client';
import { MassingUnitInfo, MassingViewerComponent } from 'viewer-3d';

interface MassingStats {
  units?: number;
  triangles?: number;
  bytes?: number;
  units_skipped_uncalibrated?: number;
  buildings_unplaced?: string[];
}

/** Internal viewer for the generated massing model (plan §14 Phase 2 exit: "massing GLB appears in an internal viewer"). */
@Component({
  selector: 'uf-massing-page',
  imports: [DecimalPipe, SlicePipe, MatCardModule, MatButtonModule, MatFormFieldModule, MatSelectModule, RouterLink, MassingViewerComponent],
  template: `
    <div class="uf-page">
      <div class="uf-page-header">
        <h2>3D massing</h2>
        <span>
          <a mat-stroked-button [routerLink]="['..']">Back to project</a>
          <button mat-flat-button [disabled]="busy()" (click)="regenerate()">Regenerate</button>
        </span>
      </div>
      @if (error()) { <p class="uf-error">{{ error() }}</p> }
      <div class="uf-toolbar">
        <mat-form-field appearance="outline">
          <mat-label>Floor</mat-label>
          <mat-select [value]="floor()" (valueChange)="floor.set($event)">
            <mat-option [value]="null">All floors</mat-option>
            @for (l of levels(); track l) { <mat-option [value]="l">Level {{ l }}</mat-option> }
          </mat-select>
        </mat-form-field>
        @if (model(); as m) {
          <span class="uf-muted">
            {{ m.status }} · {{ m.created_at | slice: 0 : 16 }}
            @if (stats().units !== undefined) { · {{ stats().units }} units · {{ stats().triangles }} triangles · {{ (stats().bytes ?? 0) / 1024 | number: '1.0-0' }} kB }
            @if (stats().units_skipped_uncalibrated) { · {{ stats().units_skipped_uncalibrated }} unit(s) skipped (sheet not calibrated) }
            @if (stats().buildings_unplaced?.length) { · unplaced: {{ stats().buildings_unplaced!.join(', ') }} }
          </span>
          @if (m.error) { <span class="uf-error">{{ m.error }}</span> }
        }
        @if (picked(); as u) { <span class="uf-chip">{{ u.building_code }} · {{ u.code }} · {{ u.unit_type }} · level {{ u.floor_level }}</span> }
      </div>
      <uf-massing-viewer [src]="model()?.glb_url ?? null" [floorLevel]="floor()" [selectedUnitId]="picked()?.unit_id ?? null" (unitPicked)="picked.set($event)" (loadedUnits)="units.set($event)" />
    </div>
  `,
  styles: `
    .uf-toolbar { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .uf-chip { padding: 0.2rem 0.5rem; border-radius: 4px; background: #fef3c7; }
  `,
})
export class MassingPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly model = signal<MassingOut | null>(null);
  readonly units = signal<MassingUnitInfo[]>([]);
  readonly floor = signal<number | null>(null);
  readonly picked = signal<MassingUnitInfo | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly levels = computed(() => [...new Set(this.units().map((u) => u.floor_level))].sort((a, b) => a - b));
  readonly stats = computed(() => (this.model()?.stats ?? {}) as MassingStats);

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  async load(): Promise<MassingOut | null> {
    try {
      const m = await this.api.getMassing(this.tenantId(), this.projectId());
      this.model.set(m);
      return m;
    } catch (e) {
      const status = (e as { status?: number }).status;
      if (status === 404) {
        this.model.set(null);
        this.error.set('No massing model yet: approve a mapped sheet or click Regenerate.');
      } else {
        this.error.set(problemMessage(e));
      }
      return null;
    }
  }

  /** Queue a rebuild and poll until the worker replaces the current model (or 60 s pass). */
  async regenerate(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    const before = this.model()?.id ?? null;
    try {
      await this.api.regenerateMassing(this.tenantId(), this.projectId());
      for (let i = 0; i < 30; i++) {
        await new Promise((r) => setTimeout(r, 2000));
        const m = await this.load();
        if (m && m.id !== before && m.status !== 'generating') return;
      }
      this.error.set('The worker has not produced a new model yet; reload later.');
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
