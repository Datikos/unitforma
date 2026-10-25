import { SlicePipe } from '@angular/common';
import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { RouterLink } from '@angular/router';
import { LineageOut, UnitOut, UnitformaApi, problemMessage } from 'api-client';

/** Project inventory: units with verification state, areas and the lineage log. */
@Component({
  selector: 'uf-units-page',
  imports: [SlicePipe, MatTableModule, MatButtonModule, RouterLink],
  template: `
    <div class="uf-page">
      <div class="uf-page-header"><h2>Units</h2><a mat-stroked-button [routerLink]="['..']">Back to project</a></div>
      @if (error()) { <p class="uf-error">{{ error() }}</p> }
      <table mat-table [dataSource]="units()" class="uf-table">
        <ng-container matColumnDef="code"><th mat-header-cell *matHeaderCellDef>Code</th><td mat-cell *matCellDef="let u">{{ u.code }}</td></ng-container>
        <ng-container matColumnDef="type"><th mat-header-cell *matHeaderCellDef>Type</th><td mat-cell *matCellDef="let u">{{ u.unit_type }}</td></ng-container>
        <ng-container matColumnDef="status"><th mat-header-cell *matHeaderCellDef>Status</th><td mat-cell *matCellDef="let u">{{ u.lifecycle_status }} · {{ u.verification_status }} · {{ u.publication_status }}</td></ng-container>
        <ng-container matColumnDef="areas"><th mat-header-cell *matHeaderCellDef>Areas</th><td mat-cell *matCellDef="let u">
          @for (a of u.areas; track a.id) { <span class="uf-area">{{ a.area_type }} {{ a.value_m2 }} m² <small>({{ a.source }}, {{ a.verification_status }})</small></span> }
        </td></ng-container>
        <tr mat-header-row *matHeaderRowDef="cols"></tr>
        <tr mat-row *matRowDef="let row; columns: cols"></tr>
      </table>
      <h3>Lineage</h3>
      <ul class="uf-lineage">
        @for (e of lineage(); track e.id) {
          <li><code>{{ e.decided_at | slice: 0 : 16 }}</code> {{ e.event_type }} {{ e.note ?? '' }} <small class="uf-muted">{{ e.from_unit_ids.length }} → {{ e.to_unit_ids.length }}</small></li>
        } @empty { <li class="uf-muted">No lineage events yet.</li> }
      </ul>
    </div>
  `,
  styles: `
    .uf-area { display: inline-block; margin-right: 0.75rem; }
    .uf-lineage { list-style: none; padding: 0; display: grid; gap: 0.25rem; }
  `,
})
export class UnitsPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly units = signal<UnitOut[]>([]);
  readonly lineage = signal<LineageOut[]>([]);
  readonly error = signal<string | null>(null);
  readonly cols = ['code', 'type', 'status', 'areas'];

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  async load(): Promise<void> {
    try {
      const [u, l] = await Promise.all([this.api.listUnits(this.tenantId(), this.projectId()), this.api.projectLineage(this.tenantId(), this.projectId())]);
      this.units.set(u);
      this.lineage.set(l);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }
}
