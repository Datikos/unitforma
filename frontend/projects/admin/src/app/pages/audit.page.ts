import { DatePipe, JsonPipe } from '@angular/common';
import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatTableModule } from '@angular/material/table';
import { AuditOut, UnitformaApi, problemMessage } from 'api-client';

@Component({
  selector: 'uf-audit-page',
  imports: [MatTableModule, MatButtonModule, DatePipe, JsonPipe],
  template: `
    <div class="uf-page">
      @if (error()) { <p class="uf-error">{{ error() }}</p> }
      <table mat-table [dataSource]="items()" class="uf-table">
        <ng-container matColumnDef="at"><th mat-header-cell *matHeaderCellDef>When</th><td mat-cell *matCellDef="let a">{{ a.at | date: 'medium' }}</td></ng-container>
        <ng-container matColumnDef="actor"><th mat-header-cell *matHeaderCellDef>Actor</th><td mat-cell *matCellDef="let a">{{ a.actor_role }}</td></ng-container>
        <ng-container matColumnDef="what"><th mat-header-cell *matHeaderCellDef>Action</th><td mat-cell *matCellDef="let a">{{ a.entity_type }} · {{ a.action }}</td></ng-container>
        <ng-container matColumnDef="change"><th mat-header-cell *matHeaderCellDef>Change</th><td mat-cell *matCellDef="let a"><code class="uf-json">{{ a.after | json }}</code></td></ng-container>
        <tr mat-header-row *matHeaderRowDef="cols"></tr>
        <tr mat-row *matRowDef="let row; columns: cols"></tr>
      </table>
      <div><span class="uf-muted">{{ items().length }} of {{ total() }}</span>
        @if (items().length < total()) { <button mat-button (click)="more()">Load more</button> }
      </div>
    </div>
  `,
  styles: `.uf-json { font-size: 0.75rem; white-space: pre-wrap; word-break: break-all; }`,
})
export class AuditPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly items = signal<AuditOut[]>([]);
  readonly total = signal(0);
  readonly error = signal<string | null>(null);
  readonly cols = ['at', 'actor', 'what', 'change'];

  constructor() {
    toObservable(this.tenantId).subscribe(() => void this.load(true));
  }

  async load(reset = false): Promise<void> {
    try {
      const page = await this.api.listAudit(this.tenantId(), 50, reset ? 0 : this.items().length);
      this.items.set(reset ? page.items : [...this.items(), ...page.items]);
      this.total.set(page.total);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  more(): Promise<void> {
    return this.load(false);
  }
}
