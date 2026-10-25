import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { BuildingOut, FloorIn, FloorOut, ProjectOut, RegulatoryImportOut, UnitformaApi, problemMessage } from 'api-client';

/** Project structure: buildings and their floors (plan §3.5). */
@Component({
  selector: 'uf-project-detail-page',
  imports: [FormsModule, MatCardModule, MatFormFieldModule, MatInputModule, MatButtonModule, MatTableModule, RouterLink],
  template: `
    <div class="uf-page">
      @if (project(); as p) {
        <div class="uf-page-header">
          <h2>{{ p.name }}</h2>
          <span class="uf-muted">{{ p.slug }} · {{ p.status }} · {{ p.currency }} · code pattern {{ p.code_pattern }}</span>
          <span class="uf-links">
            <a mat-stroked-button routerLink="documents">Documents</a>
            <a mat-stroked-button routerLink="proposals">Revision diffs</a>
            <a mat-stroked-button routerLink="placement">Site placement</a>
            <a mat-stroked-button routerLink="massing">3D massing</a>
            <a mat-stroked-button routerLink="units">Units</a>
            <a mat-stroked-button routerLink="inventory">Inventory &amp; prices</a>
            <a mat-stroked-button routerLink="publish">Publish</a>
          </span>
        </div>
      }
      @if (error()) { <p class="uf-error">{{ error() }}</p> }

      @if (permit(); as r) {
        <mat-card appearance="outlined" class="permit">
          <mat-card-header>
            <mat-card-title>Building permit {{ r['application_no'] || r['external_id'] }}</mat-card-title>
            <mat-card-subtitle>
              {{ r['status'] }} · decided {{ day(r['decided_at']) }} · {{ r['address'] || '' }}
              @if (codes(r).length) { · parcel {{ codes(r).join(', ') }} }
              · <a [href]="str(r['public_page'])" target="_blank" rel="noopener">registry page</a>
            </mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            @if (latestImport(); as j) {
              <p>
                <strong [class]="'status-' + j.status">{{ importLabel(j) }}</strong>
                <span class="uf-muted"> · fetched {{ (j.started_at || j.created_at).slice(0, 16).replace('T', ' ') }}</span>
                @if (j.status === 'done') {
                  <span class="uf-muted"> · {{ count(j, 'imported') }} files imported, {{ count(j, 'existing') }} already present, {{ count(j, 'skipped') }} skipped, {{ count(j, 'failed') }} failed</span>
                }
                @if (j.error) { <span class="uf-error"> · {{ j.error }}</span> }
              </p>
              @if (count(j, 'failed')) {
                <ul class="uf-muted small">
                  @for (f of failed(j); track f['attached_file_id']) { <li>{{ f['file_name'] }}: {{ f['error'] }}</li> }
                </ul>
              }
              @if (j.status === 'importing') {
                <p class="uf-muted small">The worker is downloading the drawings. Reload this page in a minute; they appear under Documents and propose floors from their level markers.</p>
              }
            }
            @if (heights(); as h) {
              <p class="uf-muted small">Permit heights: {{ h.above ?? '—' }} m above 0.00, {{ h.below ?? '—' }} m below. Use them when you generate floors below (for example 4 floors of about 3.5 m above ground and one basement).</p>
            }
            <div class="uf-form-row">
              <a mat-stroked-button routerLink="documents">Documents</a>
              <button mat-stroked-button [disabled]="busy() || latestImport()?.status === 'importing'" (click)="refreshPermit()">Check registry for new files</button>
              <span class="uf-muted small">Fetches the permit again and imports only files that are not here yet.</span>
            </div>
          </mat-card-content>
        </mat-card>
      }

      <mat-card appearance="outlined">
        <mat-card-header><mat-card-title>Add building</mat-card-title></mat-card-header>
        <mat-card-content class="uf-form-row">
          <mat-form-field appearance="outline"><mat-label>Code</mat-label><input matInput [(ngModel)]="code" name="code" placeholder="A" /></mat-form-field>
          <mat-form-field appearance="outline"><mat-label>Name</mat-label><input matInput [(ngModel)]="bname" name="bname" /></mat-form-field>
          <button mat-flat-button [disabled]="busy()" (click)="addBuilding()">Add</button>
        </mat-card-content>
      </mat-card>

      @for (b of buildings(); track b.id) {
        <mat-card appearance="outlined">
          <mat-card-header>
            <mat-card-title>{{ b.code }} {{ b.name ?? '' }}</mat-card-title>
            <mat-card-subtitle>{{ b.kind }} · placement {{ b.placement_status }} · {{ floorsOf(b).length }} floors</mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            @if (b.kind === 'building') {
              <div class="uf-form-row">
                <mat-form-field appearance="outline"><mat-label>Lowest level</mat-label><input matInput type="number" [(ngModel)]="from[b.id]" [name]="'from' + b.id" /></mat-form-field>
                <mat-form-field appearance="outline"><mat-label>Highest level</mat-label><input matInput type="number" [(ngModel)]="to[b.id]" [name]="'to' + b.id" /></mat-form-field>
                <mat-form-field appearance="outline"><mat-label>Floor height (m)</mat-label><input matInput type="number" step="0.01" [(ngModel)]="height[b.id]" [name]="'h' + b.id" /></mat-form-field>
                <button mat-stroked-button [disabled]="busy()" (click)="generateFloors(b)">Generate floors</button>
              </div>
            }
            @if (floorsOf(b).length) {
              <table mat-table [dataSource]="floorsOf(b)" class="uf-table">
                <ng-container matColumnDef="level"><th mat-header-cell *matHeaderCellDef>Level</th><td mat-cell *matCellDef="let f">{{ f.level }}</td></ng-container>
                <ng-container matColumnDef="name"><th mat-header-cell *matHeaderCellDef>Name</th><td mat-cell *matCellDef="let f">{{ f.display_name }}</td></ng-container>
                <ng-container matColumnDef="height"><th mat-header-cell *matHeaderCellDef>Height (m)</th><td mat-cell *matCellDef="let f">{{ f.height_m ?? '—' }}</td></ng-container>
                <tr mat-header-row *matHeaderRowDef="floorCols"></tr>
                <tr mat-row *matRowDef="let row; columns: floorCols"></tr>
              </table>
            }
          </mat-card-content>
        </mat-card>
      }
    </div>
  `,
  styles: `
    .uf-form-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .small { font-size: 0.85rem; }
    .status-done { color: #047857; }
    .status-importing { color: #b45309; }
    .status-failed { color: #b91c1c; }
  `,
})
export class ProjectDetailPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly project = signal<ProjectOut | null>(null);
  readonly buildings = signal<BuildingOut[]>([]);
  /** Permit summary stored on the project (ADR-0007 Decision 4), when it was imported from one. */
  readonly permit = computed(() => {
    const r = this.project()?.regulatory as Record<string, unknown> | undefined;
    return r && r['source'] === 'tasge' ? r : null;
  });
  readonly imports = signal<RegulatoryImportOut[]>([]);
  readonly latestImport = computed(() => this.imports()[0] ?? null);
  readonly heights = computed(() => {
    const p = this.latestImport()?.permit as Record<string, unknown> | undefined;
    const h = (p?.['heights'] ?? null) as { above_zero_m?: number | null; below_zero_m?: number | null } | null;
    return h ? { above: h.above_zero_m ?? null, below: h.below_zero_m ?? null } : null;
  });
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly floorCols = ['level', 'name', 'height'];
  code = '';
  bname = '';
  from: Record<string, number> = {};
  to: Record<string, number> = {};
  height: Record<string, number> = {};

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  async load(): Promise<void> {
    try {
      const [p, b] = await Promise.all([
        this.api.getProject(this.tenantId(), this.projectId()),
        this.api.listBuildings(this.tenantId(), this.projectId()),
      ]);
      this.project.set(p);
      this.buildings.set(b);
      const reg = p.regulatory as Record<string, unknown>;
      this.imports.set(reg?.['source'] === 'tasge' ? await this.api.listRegulatoryImports(this.tenantId(), this.projectId()) : []);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  day(v: unknown): string {
    return typeof v === 'string' && v ? v.slice(0, 10) : '—';
  }

  str(v: unknown): string {
    return typeof v === 'string' ? v : '';
  }

  codes(r: Record<string, unknown>): string[] {
    return Array.isArray(r['cadastral_codes']) ? (r['cadastral_codes'] as string[]) : [];
  }

  count(j: RegulatoryImportOut, key: string): number {
    return j.counts?.[key] ?? 0;
  }

  failed(j: RegulatoryImportOut): Record<string, unknown>[] {
    const f = j.stats?.['failed'];
    return Array.isArray(f) ? (f as Record<string, unknown>[]) : [];
  }

  importLabel(j: RegulatoryImportOut): string {
    return { importing: 'Import running', done: 'Import finished', failed: 'Import failed', fetched: 'Fetched' }[j.status] ?? j.status;
  }

  async refreshPermit(): Promise<void> {
    await this.run(() => this.api.refreshPermit(this.tenantId(), this.projectId()));
  }

  floorsOf(b: BuildingOut): FloorOut[] {
    return b.floors ?? [];
  }

  async addBuilding(): Promise<void> {
    await this.run(async () => {
      await this.api.createBuilding(this.tenantId(), this.projectId(), { code: this.code, name: this.bname || null, kind: 'building', sort_order: 0 });
      this.code = this.bname = '';
    });
  }

  async generateFloors(b: BuildingOut): Promise<void> {
    const from = Number(this.from[b.id] ?? 0);
    const to = Number(this.to[b.id] ?? 0);
    const h = this.height[b.id];
    if (to < from) {
      this.error.set('Highest level must be ≥ lowest level');
      return;
    }
    const floors: FloorIn[] = [];
    for (let lvl = from; lvl <= to; lvl++) {
      floors.push({ level: lvl, display_name: lvl < 0 ? `B${-lvl}` : lvl === 0 ? 'Ground' : String(lvl), height_m: h ? String(h) : null });
    }
    await this.run(() => this.api.setFloors(this.tenantId(), b.id, floors));
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
