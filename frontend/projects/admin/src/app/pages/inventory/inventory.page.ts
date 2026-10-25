import { Component, computed, inject, input } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatMenuModule } from '@angular/material/menu';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { GridOptions } from 'ag-grid-community';
import { InventoryRow } from 'api-client';
import { EmptyStateComponent, HeaderFact, PageHeaderComponent, UF_ICONS } from 'ui';
import { DataGridComponent } from '../../grid/data-grid.component';
import { InventoryBulkCardComponent } from './inventory-bulk-card.component';
import { InventoryConflictCardComponent } from './inventory-conflict-card.component';
import { COLUMN_SET_LABELS, ColumnSet } from './inventory.model';
import { InventoryStore } from './inventory.store';

/** Sales inventory grid (plan §6.3, §11.2 "Inventory"): inline edit with optimistic concurrency, bulk edit, export. */
@Component({
  selector: 'uf-inventory-page',
  imports: [
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatButtonToggleModule,
    MatFormFieldModule,
    MatInputModule,
    MatMenuModule,
    NgIcon,
    DataGridComponent,
    PageHeaderComponent,
    EmptyStateComponent,
    InventoryBulkCardComponent,
    InventoryConflictCardComponent,
  ],
  providers: [InventoryStore],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="Inventory & prices" icon="lucideTable" [facts]="facts()">
        <ng-container actions>
          <a mat-stroked-button routerLink="../imports"
            ><ng-icon name="lucideFileSpreadsheet" /> Import prices</a
          >
          <a mat-stroked-button routerLink="../sales-setup"
            ><ng-icon name="lucideHandCoins" /> Plans &amp; promotions</a
          >
          <button mat-stroked-button [matMenuTriggerFor]="exportMenu">
            <ng-icon name="lucideDownload" /> Export
          </button>
          <mat-menu #exportMenu="matMenu">
            <button mat-menu-item (click)="store.download('xlsx', 'internal')">
              XLSX, internal columns
            </button>
            <button mat-menu-item (click)="store.download('csv', 'internal')">
              CSV, internal columns
            </button>
            <button mat-menu-item (click)="store.download('xlsx', 'public')">
              XLSX, public columns
            </button>
          </mat-menu>
        </ng-container>
      </uf-page-header>
      @if (store.error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }
      <uf-inventory-conflict-card />

      @if (store.loaded() && store.rows().length === 0) {
        <uf-empty-state
          icon="lucideTable"
          title="No units to price yet"
          text="Units come from approved sheets. Map a floor plan under Documents, approve it, and the units appear here with their areas."
        >
          <a mat-flat-button routerLink="../documents">Open Documents</a>
        </uf-empty-state>
      } @else {
        <div class="uf-filterbar">
          <mat-form-field appearance="outline" class="search" subscriptSizing="dynamic">
            <ng-icon matPrefix name="lucideSearch" />
            <input
              matInput
              [ngModel]="store.quick()"
              (ngModelChange)="store.setQuick($event)"
              placeholder="Search code, plan, notes…"
              aria-label="Search"
            />
          </mat-form-field>
          <mat-button-toggle-group
            [value]="store.columnSet()"
            (valueChange)="store.setColumns($event)"
            aria-label="Column set"
            hideSingleSelectionIndicator
          >
            @for (s of sets; track s) {
              <mat-button-toggle [value]="s">{{ labels[s] }}</mat-button-toggle>
            }
          </mat-button-toggle-group>
          <span class="uf-count"
            >{{ store.rows().length }} units · {{ store.selected().length }} selected</span
          >
        </div>
        @if (store.selected().length) {
          <uf-inventory-bulk-card />
        }
        <uf-data-grid
          [options]="gridOptions"
          [rows]="store.rows()"
          (ready)="store.attachGrid($event)"
        />
        <p class="uf-hint">
          Click a code to open the unit. Edit a cell and press Enter to save; the row version
          protects against overwriting a colleague. Empty price = price on request, never 0. Price
          per m² uses the project's price area type
          @if (store.settings(); as s) {
            ({{ s.price_area_type }})
          }
          .
        </p>
      }
    </div>
  `,
  styles: `
    .search {
      min-width: 280px;
    }
    .search ng-icon {
      margin: 0 0.25rem 0 0.5rem;
      color: var(--uf-muted);
    }
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class InventoryPage {
  protected readonly store = inject(InventoryStore);
  private readonly router = inject(Router);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly sets: ColumnSet[] = ['commercial', 'public', 'internal', 'all'];
  readonly labels = COLUMN_SET_LABELS;

  readonly facts = computed<HeaderFact[]>(() => {
    const a = this.store.byAvailability();
    return [
      { label: 'Units', value: this.store.rows().length },
      { label: 'Priced', value: this.store.priced() },
      { domain: 'availability', status: 'available', value: `${a['available'] ?? 0} available` },
      { domain: 'availability', status: 'reserved', value: `${a['reserved'] ?? 0} reserved` },
      { domain: 'availability', status: 'sold', value: `${a['sold'] ?? 0} sold` },
      {
        domain: 'unit.publication',
        status: 'published',
        value: `${this.store.published()} public`,
      },
    ];
  });

  readonly gridOptions: GridOptions<InventoryRow> = {
    getRowId: (p) => p.data.unit_id,
    rowSelection: {
      mode: 'multiRow',
      checkboxes: true,
      headerCheckbox: true,
      selectAll: 'filtered',
    },
    selectionColumnDef: { pinned: 'left', width: 52, suppressHeaderMenuButton: true },
    defaultColDef: { sortable: true, filter: true, resizable: true, minWidth: 90 },
    singleClickEdit: false,
    stopEditingWhenCellsLoseFocus: true,
    undoRedoCellEditing: false,
    tooltipShowDelay: 300,
    onCellValueChanged: (e) =>
      void this.store.onCellChanged(e.colDef.field as string, e.data, e.oldValue, e.newValue),
    onSelectionChanged: (e) => this.store.onSelection(e.api.getSelectedRows()),
    onCellClicked: (e) => {
      if (e.colDef.field === 'code' && e.data)
        void this.router.navigate([
          '/t',
          this.tenantId(),
          'projects',
          this.projectId(),
          'inventory',
          e.data.unit_id,
        ]);
    },
    columnDefs: [],
  };

  constructor() {
    toObservable(this.projectId).subscribe(() => {
      this.store.init(this.tenantId(), this.projectId());
      void this.store.load();
    });
  }
}
