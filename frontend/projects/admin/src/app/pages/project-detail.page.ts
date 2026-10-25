import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { BuildingOut, FloorIn, FloorOut, ProjectOut, UnitformaApi, problemMessage } from 'api-client';

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
          </span>
        </div>
      }
      @if (error()) { <p class="uf-error">{{ error() }}</p> }

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
  styles: `.uf-form-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }`,
})
export class ProjectDetailPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly project = signal<ProjectOut | null>(null);
  readonly buildings = signal<BuildingOut[]>([]);
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
    } catch (e) {
      this.error.set(problemMessage(e));
    }
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
