import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { Router, RouterLink } from '@angular/router';
import { CellClassParams, CellValueChangedEvent, ColDef, GridApi, GridOptions, ValueFormatterParams } from 'ag-grid-community';
import { BulkResult, BulkUpdate, InventoryRow, PaymentPlanOut, PromotionOut, SalesChanges, SalesSettingsOut, SalesUpdate, UnitformaApi, problemMessage } from 'api-client';
import { DataGridComponent } from '../grid/data-grid.component';
import { AVAILABILITY, formatPrice, httpStatus, parsePriceInput, problemBody } from '../sales/sales-format';

type ColumnSet = 'commercial' | 'public' | 'internal' | 'all';

interface Conflict {
  code: string;
  mine: SalesChanges;
  current: InventoryRow;
}

const KEEP = '__keep__';
const NONE = '__none__';

/** Columns per set; "all" shows every column. */
const SETS: Record<Exclude<ColumnSet, 'all'>, string[]> = {
  commercial: ['code', 'building_code', 'floor_level', 'unit_type', 'availability', 'list_price', 'currency', 'price_on_request', 'price_per_m2', 'payment_plan_name', 'promotion_names', 'rooms', 'bedrooms'],
  public: ['code', 'building_code', 'floor_level', 'unit_type', 'availability', 'list_price', 'currency', 'price_on_request', 'price_per_m2', 'payment_plan_name', 'promotion_names', 'rooms', 'bedrooms', 'bathrooms', 'orientation', 'public_description', 'media_count', 'publication_status'],
  internal: ['code', 'building_code', 'floor_level', 'availability', 'availability_reason', 'list_price', 'currency', 'internal_notes', 'verification_status', 'publication_status', 'version'],
};

/** Sales inventory grid (plan §6.3, §11.2 "Inventory"): inline edit with optimistic concurrency, bulk edit, export. */
@Component({
  selector: 'uf-inventory-page',
  imports: [FormsModule, RouterLink, MatButtonModule, MatButtonToggleModule, MatCardModule, MatCheckboxModule, MatFormFieldModule, MatInputModule, MatSelectModule, DataGridComponent],
  template: `
    <div class="uf-page">
      <div class="uf-page-header">
        <h2>Inventory</h2>
        <span class="uf-links">
          <a mat-stroked-button routerLink="../imports">Import</a>
          <a mat-stroked-button routerLink="../sales-setup">Plans, promotions &amp; settings</a>
          <button mat-stroked-button (click)="download('xlsx', 'internal')">Export XLSX</button>
          <button mat-stroked-button (click)="download('csv', 'internal')">Export CSV</button>
          <button mat-stroked-button (click)="download('xlsx', 'public')">Export public columns</button>
          <a mat-stroked-button [routerLink]="['..']">Back to project</a>
        </span>
      </div>
      @if (error()) { <p class="uf-error" role="alert">{{ error() }}</p> }
      @if (conflict(); as c) {
        <mat-card appearance="outlined" class="uf-conflict" role="alert">
          <mat-card-content>
            <strong>{{ c.code }} was changed by someone else</strong> while you were editing.
            <div class="uf-diff">
              @for (k of conflictKeys(); track k) {
                <div><span class="uf-muted">{{ k }}</span>: yours <code>{{ show(c.mine, k) }}</code> · current <code>{{ show(c.current, k) }}</code></div>
              }
            </div>
          </mat-card-content>
          <mat-card-actions>
            <button mat-flat-button (click)="reapply(c)">Apply mine on top of the current version</button>
            <button mat-button (click)="conflict.set(null)">Keep the current values</button>
          </mat-card-actions>
        </mat-card>
      }
      <div class="uf-toolbar">
        <mat-form-field appearance="outline" class="uf-search">
          <mat-label>Search</mat-label>
          <input matInput [ngModel]="quick()" (ngModelChange)="setQuick($event)" placeholder="code, plan, notes…" />
        </mat-form-field>
        <mat-button-toggle-group [value]="columnSet()" (valueChange)="setColumns($event)" aria-label="Column set">
          <mat-button-toggle value="commercial">Commercial</mat-button-toggle>
          <mat-button-toggle value="public">Public fields</mat-button-toggle>
          <mat-button-toggle value="internal">Internal</mat-button-toggle>
          <mat-button-toggle value="all">All</mat-button-toggle>
        </mat-button-toggle-group>
        <span class="uf-muted">{{ rows().length }} units · {{ priced() }} priced · {{ selected().length }} selected</span>
      </div>

      @if (selected().length) {
        <mat-card appearance="outlined">
          <mat-card-header><mat-card-title>Bulk edit {{ selected().length }} unit(s)</mat-card-title></mat-card-header>
          <mat-card-content class="uf-form-row">
            <mat-form-field appearance="outline"><mat-label>Availability</mat-label>
              <mat-select [(ngModel)]="bulk.availability" name="bAvail">
                <mat-option [value]="KEEP">— keep —</mat-option>
                @for (a of availability; track a) { <mat-option [value]="a">{{ a }}</mat-option> }
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline"><mat-label>Reason</mat-label><input matInput [(ngModel)]="bulk.reason" name="bReason" placeholder="required to change sold units" /></mat-form-field>
            <mat-form-field appearance="outline" class="uf-num"><mat-label>Set price</mat-label><input matInput [(ngModel)]="bulk.price" name="bPrice" placeholder="keep" /></mat-form-field>
            <mat-form-field appearance="outline" class="uf-num"><mat-label>or adjust %</mat-label><input matInput type="number" [(ngModel)]="bulk.adjust" name="bAdjust" /></mat-form-field>
            <mat-form-field appearance="outline" class="uf-ccy"><mat-label>Currency</mat-label><input matInput [(ngModel)]="bulk.currency" name="bCcy" placeholder="keep" maxlength="3" /></mat-form-field>
            <mat-form-field appearance="outline"><mat-label>Payment plan</mat-label>
              <mat-select [(ngModel)]="bulk.plan" name="bPlan">
                <mat-option [value]="KEEP">— keep —</mat-option>
                <mat-option [value]="NONE">— none —</mat-option>
                @for (p of plans(); track p.id) { <mat-option [value]="p.id">{{ p.name }}</mat-option> }
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline"><mat-label>Promotions</mat-label>
              <mat-select [(ngModel)]="bulk.promotions" name="bPromo" multiple [disabled]="!bulk.setPromotions">
                @for (p of promotions(); track p.id) { <mat-option [value]="p.id">{{ p.name }}</mat-option> }
              </mat-select>
            </mat-form-field>
            <mat-checkbox [(ngModel)]="bulk.setPromotions" name="bSetPromo">Replace promotions</mat-checkbox>
            <mat-checkbox [(ngModel)]="bulk.confirmZero" name="bZero">Allow price 0</mat-checkbox>
          </mat-card-content>
          <mat-card-actions>
            <button mat-stroked-button [disabled]="busy()" (click)="runBulk(true)">Preview</button>
            <button mat-flat-button [disabled]="busy() || !preview()" (click)="runBulk(false)">Apply to {{ selected().length }} unit(s)</button>
            <button mat-button (click)="clearSelection()">Clear selection</button>
          </mat-card-actions>
          @if (preview(); as p) {
            <div class="uf-preview">
              <p>{{ p.changed_units }} of {{ p.units.length }} unit(s) would change.</p>
              <table>
                <thead><tr><th>Unit</th><th>Changes</th></tr></thead>
                <tbody>
                  @for (u of p.units; track u.unit_id) {
                    <tr><td>{{ u.code }}</td><td>@for (c of u.changes; track $index) { <span class="uf-chg">{{ c['field'] }}: {{ c['old'] ?? '∅' }} → {{ c['new'] ?? '∅' }}</span> } @empty { <span class="uf-muted">no change</span> }</td></tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </mat-card>
      }

      <uf-data-grid [options]="gridOptions" [rows]="rows()" (ready)="onReady($event)" />
      <p class="uf-muted uf-legend">
        Click a code to open the unit. Empty price = price on request (never 0). Price per m² is computed from the project's price area type
        @if (settings(); as s) { ({{ s.price_area_type }}) }.
      </p>
    </div>
  `,
  styles: `
    .uf-toolbar { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .uf-search { min-width: 260px; }
    .uf-form-row { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
    .uf-num { width: 130px; }
    .uf-ccy { width: 100px; }
    .uf-links { display: flex; gap: 0.5rem; flex-wrap: wrap; }
    .uf-conflict { border-color: #d97706; background: #fffbeb; }
    .uf-diff { margin-top: 0.5rem; display: grid; gap: 0.25rem; }
    .uf-preview { padding: 0 1rem 1rem; max-height: 280px; overflow: auto; }
    .uf-preview table { border-collapse: collapse; width: 100%; }
    .uf-preview td, .uf-preview th { text-align: left; padding: 0.25rem 0.5rem; border-bottom: 1px solid #e5e7eb; }
    .uf-chg { display: inline-block; margin-right: 0.75rem; }
    .uf-legend { font-size: 0.8rem; }
  `,
})
export class InventoryPage {
  private readonly api = inject(UnitformaApi);
  private readonly router = inject(Router);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly rows = signal<InventoryRow[]>([]);
  readonly plans = signal<PaymentPlanOut[]>([]);
  readonly promotions = signal<PromotionOut[]>([]);
  readonly settings = signal<SalesSettingsOut | null>(null);
  readonly selected = signal<InventoryRow[]>([]);
  readonly columnSet = signal<ColumnSet>('commercial');
  readonly quick = signal('');
  readonly conflict = signal<Conflict | null>(null);
  readonly preview = signal<BulkResult | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly availability = AVAILABILITY;
  readonly KEEP = KEEP;
  readonly NONE = NONE;
  readonly priced = computed(() => this.rows().filter((r) => r.list_price !== null && r.list_price !== undefined).length);
  readonly conflictKeys = computed(() => Object.keys(this.conflict()?.mine ?? {}));
  bulk = { availability: KEEP, reason: '', price: '', adjust: null as number | null, currency: '', plan: KEEP, promotions: [] as string[], setPromotions: false, confirmZero: false };
  private grid: GridApi<InventoryRow> | null = null;

  readonly gridOptions: GridOptions<InventoryRow> = {
    getRowId: (p) => p.data.unit_id,
    rowSelection: { mode: 'multiRow', checkboxes: true, headerCheckbox: true, selectAll: 'filtered' },
    selectionColumnDef: { pinned: 'left', width: 52, suppressHeaderMenuButton: true },
    defaultColDef: { sortable: true, filter: true, resizable: true, minWidth: 90 },
    singleClickEdit: false,
    stopEditingWhenCellsLoseFocus: true,
    undoRedoCellEditing: false,
    tooltipShowDelay: 300,
    onCellValueChanged: (e) => void this.onCellChanged(e),
    onSelectionChanged: (e) => {
      this.selected.set(e.api.getSelectedRows());
      this.preview.set(null);
    },
    onCellClicked: (e) => {
      if (e.colDef.field === 'code' && e.data) void this.router.navigate(['/t', this.tenantId(), 'projects', this.projectId(), 'inventory', e.data.unit_id]);
    },
    columnDefs: [],
  };

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  private columns(): ColDef<InventoryRow>[] {
    const price = (p: ValueFormatterParams<InventoryRow>) => formatPrice(p.value, p.data?.currency) ?? (p.data?.price_on_request ? 'on request' : '—');
    const num = (field: 'rooms' | 'bedrooms' | 'bathrooms', header: string): ColDef<InventoryRow> => ({
      field,
      headerName: header,
      editable: true,
      cellEditor: 'agNumberCellEditor',
      cellEditorParams: { min: 0, max: 100, precision: 0 },
      filter: 'agNumberColumnFilter',
      width: 105,
    });
    const areaKeys = (this.settings()?.area_definitions ?? []).map((a) => (a as { key: string; label?: string }));
    return [
      { field: 'code', headerName: 'Code', pinned: 'left', width: 130, cellClass: 'uf-link', filter: 'agTextColumnFilter' },
      { field: 'building_code', headerName: 'Bldg', width: 90 },
      { field: 'floor_level', headerName: 'Floor', width: 95, filter: 'agNumberColumnFilter' },
      { field: 'unit_type', headerName: 'Type', width: 120 },
      {
        field: 'availability',
        headerName: 'Availability',
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: { values: [...AVAILABILITY] },
        width: 135,
        cellClassRules: {
          'uf-av-available': (p: CellClassParams<InventoryRow>) => p.value === 'available',
          'uf-av-reserved': (p: CellClassParams<InventoryRow>) => p.value === 'reserved',
          'uf-av-sold': (p: CellClassParams<InventoryRow>) => p.value === 'sold',
          'uf-av-withdrawn': (p: CellClassParams<InventoryRow>) => p.value === 'withdrawn',
        },
      },
      { field: 'availability_reason', headerName: 'Availability reason (internal)', editable: true, width: 200 },
      {
        field: 'list_price',
        headerName: 'Price',
        editable: true,
        type: 'rightAligned',
        width: 160,
        valueFormatter: price,
        valueParser: (p) => {
          const v = parsePriceInput(p.newValue);
          if (v === undefined) {
            this.error.set(`"${p.newValue}" is not a price: use digits and at most two decimals`);
            return p.oldValue;
          }
          return v;
        },
        filter: 'agNumberColumnFilter',
        filterValueGetter: (p) => (p.data?.list_price == null ? null : Number(p.data.list_price)),
        comparator: (a, b) => (a == null ? -1 : Number(a)) - (b == null ? -1 : Number(b)),
      },
      { field: 'currency', headerName: 'Ccy', editable: true, width: 85, valueParser: (p) => String(p.newValue ?? '').trim().toUpperCase() || p.oldValue },
      { field: 'price_on_request', headerName: 'On request', editable: true, cellDataType: 'boolean', width: 115 },
      {
        field: 'price_per_m2',
        headerName: 'Price / m²',
        type: 'rightAligned',
        width: 140,
        valueFormatter: (p) => formatPrice(p.value, p.data?.currency) ?? '—',
        tooltipValueGetter: (p) => (p.data?.price_area_m2 ? `per m² ${p.data.price_area_type} (${p.data.price_area_m2} m², ${p.data.price_area_source}, ${p.data.price_area_verified ? 'verified' : 'unverified'})` : `no ${p.data?.price_area_type} area`),
      },
      {
        field: 'payment_plan_name',
        headerName: 'Payment plan',
        editable: true,
        cellEditor: 'agSelectCellEditor',
        cellEditorParams: () => ({ values: ['', ...this.plans().map((p) => p.name)] }),
        width: 170,
      },
      { colId: 'promotion_names', headerName: 'Promotions', valueGetter: (p) => (p.data?.promotion_names ?? []).join(', '), width: 160 },
      num('rooms', 'Rooms'),
      num('bedrooms', 'Bedrooms'),
      num('bathrooms', 'Baths'),
      { field: 'orientation', headerName: 'Orientation', editable: true, width: 120 },
      { field: 'public_description', headerName: 'Public description', editable: true, cellEditor: 'agLargeTextCellEditor', cellEditorPopup: true, width: 240 },
      { field: 'internal_notes', headerName: 'Internal notes', editable: true, cellEditor: 'agLargeTextCellEditor', cellEditorPopup: true, width: 240, headerTooltip: 'Never published' },
      { field: 'verification_status', headerName: 'Verification', width: 125 },
      { field: 'publication_status', headerName: 'Publication', width: 125 },
      ...areaKeys.map((a) => ({
        colId: `area_${a.key}`,
        headerName: `${a.label ?? a.key} m²`,
        valueGetter: (p: { data?: InventoryRow }) => (p.data?.areas?.[a.key] ? Number(p.data.areas[a.key]) : null),
        type: 'rightAligned',
        filter: 'agNumberColumnFilter',
        width: 140,
      }) as ColDef<InventoryRow>),
      { field: 'media_count', headerName: 'Media', width: 95, filter: 'agNumberColumnFilter' },
      { field: 'version', headerName: 'Ver.', width: 80 },
    ];
  }

  onReady(api: GridApi<InventoryRow>): void {
    this.grid = api;
    api.setGridOption('columnDefs', this.columns());
    this.applyColumnSet();
  }

  async load(): Promise<void> {
    try {
      const [rows, plans, promos, settings] = await Promise.all([
        this.api.inventory(this.tenantId(), this.projectId()),
        this.api.listPaymentPlans(this.tenantId(), this.projectId()),
        this.api.listPromotions(this.tenantId(), this.projectId()),
        this.api.getSalesSettings(this.tenantId(), this.projectId()),
      ]);
      this.plans.set(plans);
      this.promotions.set(promos);
      this.settings.set(settings);
      this.rows.set(rows);
      this.selected.set([]);
      if (this.grid) {
        this.grid.setGridOption('columnDefs', this.columns());
        this.applyColumnSet();
      }
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  setColumns(set: ColumnSet): void {
    this.columnSet.set(set);
    this.applyColumnSet();
  }

  private applyColumnSet(): void {
    if (!this.grid) return;
    const all = (this.grid.getColumns() ?? []).map((c) => c.getColId());
    const set = this.columnSet();
    const visible = set === 'all' ? all : all.filter((id) => SETS[set].includes(id) || (set === 'public' && id.startsWith('area_')));
    this.grid.setColumnsVisible(all, false);
    this.grid.setColumnsVisible(visible, true);
  }

  setQuick(v: string): void {
    this.quick.set(v);
    this.grid?.setGridOption('quickFilterText', v);
  }

  clearSelection(): void {
    this.grid?.deselectAll();
  }

  show(obj: object, key: string): string {
    const v = (obj as Record<string, unknown>)[key];
    if (v === null || v === undefined || v === '') return '∅';
    return Array.isArray(v) ? v.join(', ') : String(v);
  }

  /** Grid cell → API change. Returns null when the column is not editable through the API. */
  private toChange(field: string, value: unknown): SalesChanges | null {
    switch (field) {
      case 'payment_plan_name': {
        const plan = this.plans().find((p) => p.name === value);
        return { payment_plan_id: plan ? plan.id : null };
      }
      case 'list_price':
        return { list_price: (value as string | null) ?? null };
      case 'rooms':
      case 'bedrooms':
      case 'bathrooms':
        return { [field]: value === null || value === undefined || value === '' ? null : Number(value) } as SalesChanges;
      case 'availability':
      case 'availability_reason':
      case 'currency':
      case 'price_on_request':
      case 'orientation':
      case 'public_description':
      case 'internal_notes':
        return { [field]: value === '' ? null : value } as SalesChanges;
      default:
        return null;
    }
  }

  private async onCellChanged(e: CellValueChangedEvent<InventoryRow>): Promise<void> {
    const field = e.colDef.field as string;
    if (!e.data || e.oldValue === e.newValue) return;
    const before = { ...e.data, [field]: e.oldValue } as InventoryRow;
    const change = this.toChange(field, e.newValue);
    if (!change) return;
    await this.save(before, change, {});
  }

  /** Save one change with the row version; handles 409 (conflict banner) and the confirm-able 422s. */
  private async save(row: InventoryRow, change: SalesChanges, extra: Partial<SalesUpdate>): Promise<void> {
    this.error.set(null);
    try {
      const updated = await this.api.updateUnitSales(this.tenantId(), row.unit_id, { ...change, ...extra, version: row.version });
      this.replace(updated);
    } catch (e) {
      const body = problemBody(e);
      if (httpStatus(e) === 409 && body?.['current']) {
        const current = body['current'] as InventoryRow;
        this.replace(current);
        this.conflict.set({ code: row.code, mine: change, current });
        return;
      }
      const detail = String(body?.['detail'] ?? '');
      if (httpStatus(e) === 422 && detail.includes('price 0') && window.confirm(`Save a price of 0 for ${row.code}?`)) {
        return this.save(row, change, { ...extra, confirm_zero_price: true });
      }
      if (httpStatus(e) === 422 && detail.includes('requires a reason')) {
        const reason = window.prompt(`${row.code} is sold. Why does its availability change?`);
        if (reason) return this.save(row, change, { ...extra, reason });
      }
      this.replace(row); // revert the cell
      this.error.set(`${row.code}: ${problemMessage(e)}`);
    }
  }

  reapply(c: Conflict): Promise<void> {
    this.conflict.set(null);
    return this.save(c.current, c.mine, {});
  }

  private replace(row: InventoryRow): void {
    this.grid?.applyTransaction({ update: [row] });
    this.rows.update((rows) => rows.map((r) => (r.unit_id === row.unit_id ? row : r)));
  }

  async runBulk(preview: boolean): Promise<void> {
    const changes: SalesChanges = {};
    const b = this.bulk;
    if (b.availability !== KEEP) changes.availability = b.availability as InventoryRow['availability'];
    if (b.price.trim()) {
      const p = parsePriceInput(b.price);
      if (p === undefined) {
        this.error.set('The bulk price is not a valid amount');
        return;
      }
      changes.list_price = p;
    }
    if (b.currency.trim()) changes.currency = b.currency.trim().toUpperCase();
    if (b.plan !== KEEP) changes.payment_plan_id = b.plan === NONE ? null : b.plan;
    if (b.setPromotions) changes.promotion_ids = b.promotions;
    const body: BulkUpdate = {
      items: this.selected().map((r) => ({ unit_id: r.unit_id, version: r.version })),
      changes,
      price_adjust_percent: b.adjust !== null && !changes.list_price ? String(b.adjust) : null,
      preview,
      reason: b.reason || null,
      confirm_zero_price: b.confirmZero,
    };
    this.busy.set(true);
    this.error.set(null);
    try {
      const res = await this.api.bulkUpdate(this.tenantId(), this.projectId(), body);
      if (preview) {
        this.preview.set(res);
      } else {
        this.preview.set(null);
        await this.load();
      }
    } catch (e) {
      const body = problemBody(e);
      if (httpStatus(e) === 409) {
        const stale = (body?.['stale'] as { code: string }[] | undefined) ?? [];
        this.error.set(`${stale.length} unit(s) changed meanwhile (${stale.map((s) => s.code).slice(0, 8).join(', ')}): the grid was reloaded, review and apply again.`);
        await this.load();
      } else if (body?.['unit_errors']) {
        const errs = body['unit_errors'] as { code?: string; errors: string[] }[];
        this.error.set('Nothing was changed. ' + errs.slice(0, 5).map((u) => `${u.code ?? ''}: ${u.errors.join('; ')}`).join(' · '));
      } else {
        this.error.set(problemMessage(e));
      }
    } finally {
      this.busy.set(false);
    }
  }

  async download(format: 'csv' | 'xlsx', columns: 'internal' | 'public'): Promise<void> {
    try {
      await this.api.downloadInventory(this.tenantId(), this.projectId(), format, columns);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }
}
