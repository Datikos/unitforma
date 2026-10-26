import { Injectable, computed, inject, signal } from '@angular/core';
import { GridApi } from 'ag-grid-community';
import {
  BulkResult,
  BulkUpdate,
  InventoryRow,
  LayoutOut,
  PaymentPlanOut,
  PromotionOut,
  SalesChanges,
  SalesSettingsOut,
  SalesUpdate,
  UnitformaApi,
  problemMessage,
} from 'api-client';
import { httpStatus, problemBody } from '../../sales/sales-format';
import { DialogsService } from '../../ui/dialogs.service';
import { ToastService } from '../../ui/toast.service';
import {
  BulkForm,
  ColumnSet,
  Conflict,
  blankBulk,
  bulkChanges,
  buildColumns,
  toChange,
  visibleColumns,
} from './inventory.model';

/** State and API calls of the inventory grid; provided by the page, shared with its cards. */
@Injectable()
export class InventoryStore {
  private readonly api = inject(UnitformaApi);
  private readonly dialogs = inject(DialogsService);
  private readonly toast = inject(ToastService);
  private tenantId = '';
  private projectId = '';
  private grid: GridApi<InventoryRow> | null = null;

  readonly rows = signal<InventoryRow[]>([]);
  readonly plans = signal<PaymentPlanOut[]>([]);
  readonly layouts = signal<LayoutOut[]>([]);
  readonly promotions = signal<PromotionOut[]>([]);
  readonly settings = signal<SalesSettingsOut | null>(null);
  readonly selected = signal<InventoryRow[]>([]);
  readonly columnSet = signal<ColumnSet>('commercial');
  readonly quick = signal('');
  readonly conflict = signal<Conflict | null>(null);
  readonly preview = signal<BulkResult | null>(null);
  readonly busy = signal(false);
  readonly loaded = signal(false);
  readonly error = signal<string | null>(null);
  readonly bulk = signal<BulkForm>(blankBulk());

  readonly priced = computed(
    () => this.rows().filter((r) => r.list_price !== null && r.list_price !== undefined).length,
  );
  readonly published = computed(
    () => this.rows().filter((r) => r.publication_status === 'published').length,
  );
  readonly byAvailability = computed(() => {
    const out: Record<string, number> = {};
    for (const r of this.rows()) out[r.availability] = (out[r.availability] ?? 0) + 1;
    return out;
  });
  readonly conflictKeys = computed(() => Object.keys(this.conflict()?.mine ?? {}));

  init(tenantId: string, projectId: string): void {
    this.tenantId = tenantId;
    this.projectId = projectId;
  }

  attachGrid(api: GridApi<InventoryRow>): void {
    this.grid = api;
    this.refreshColumns();
  }

  private columns() {
    return buildColumns({
      settings: this.settings(),
      plans: () => this.plans(),
      layouts: () => this.layouts().map((l) => l.code),
      onBadPrice: (t) => this.error.set(t),
    });
  }

  private refreshColumns(): void {
    if (!this.grid) return;
    this.grid.setGridOption('columnDefs', this.columns());
    this.applyColumnSet();
  }

  async load(): Promise<void> {
    try {
      const [rows, plans, promos, settings, layouts] = await Promise.all([
        this.api.inventory(this.tenantId, this.projectId),
        this.api.listPaymentPlans(this.tenantId, this.projectId),
        this.api.listPromotions(this.tenantId, this.projectId),
        this.api.getSalesSettings(this.tenantId, this.projectId),
        this.api.listLayouts(this.tenantId, this.projectId).catch(() => [] as LayoutOut[]),
      ]);
      this.plans.set(plans);
      this.layouts.set(layouts);
      this.promotions.set(promos);
      this.settings.set(settings);
      this.rows.set(rows);
      this.selected.set([]);
      this.refreshColumns();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.loaded.set(true);
    }
  }

  setColumns(set: ColumnSet): void {
    this.columnSet.set(set);
    this.applyColumnSet();
  }

  private applyColumnSet(): void {
    if (!this.grid) return;
    const all = (this.grid.getColumns() ?? []).map((c) => c.getColId());
    const visible = visibleColumns(this.columnSet(), all);
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

  onSelection(rows: InventoryRow[]): void {
    this.selected.set(rows);
    this.preview.set(null);
  }

  async onCellChanged(
    field: string,
    data: InventoryRow,
    oldValue: unknown,
    newValue: unknown,
  ): Promise<void> {
    if (oldValue === newValue) return;
    const before = { ...data, [field]: oldValue } as InventoryRow;
    const change = toChange(field, newValue, this.plans());
    if (!change) return;
    await this.save(before, change, {});
  }

  /** Save one change with the row version; handles 409 (conflict card) and the confirm-able 422s. */
  async save(row: InventoryRow, change: SalesChanges, extra: Partial<SalesUpdate>): Promise<void> {
    this.error.set(null);
    try {
      const updated = await this.api.updateUnitSales(this.tenantId, row.unit_id, {
        ...change,
        ...extra,
        version: row.version,
      });
      this.replace(updated);
      this.toast.ok(`${row.code} saved`);
    } catch (e) {
      const body = problemBody(e);
      if (httpStatus(e) === 409 && body?.['current']) {
        const current = body['current'] as InventoryRow;
        this.replace(current);
        this.conflict.set({ code: row.code, mine: change, current });
        return;
      }
      const detail = String(body?.['detail'] ?? '');
      if (httpStatus(e) === 422 && detail.includes('price 0')) {
        const ok = await this.dialogs.confirm({
          title: `Save a price of 0 for ${row.code}?`,
          message: 'A price of 0 is published as a real price. An empty price means "on request".',
          consequence: 'Buyers would see this unit listed at 0.',
          confirmLabel: 'Save 0',
          tone: 'warning',
        });
        if (ok) return this.save(row, change, { ...extra, confirm_zero_price: true });
      }
      if (httpStatus(e) === 422 && detail.includes('requires a reason')) {
        const reason = await this.dialogs.prompt({
          title: `${row.code} is sold`,
          message:
            'Changing the availability of a sold unit needs a reason; it is kept in the unit history.',
          label: 'Reason',
          required: true,
          confirmLabel: 'Save with reason',
        });
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
    const b = this.bulk();
    const changes = bulkChanges(b);
    if (changes === undefined) {
      this.error.set('The bulk price is not a valid amount');
      return;
    }
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
      const res = await this.api.bulkUpdate(this.tenantId, this.projectId, body);
      if (preview) {
        this.preview.set(res);
      } else {
        this.preview.set(null);
        this.toast.ok(`${res.changed_units} unit(s) updated`);
        await this.load();
      }
    } catch (e) {
      const body = problemBody(e);
      if (httpStatus(e) === 409) {
        const stale = (body?.['stale'] as { code: string }[] | undefined) ?? [];
        this.error.set(
          `${stale.length} unit(s) changed meanwhile (${stale
            .map((s) => s.code)
            .slice(0, 8)
            .join(', ')}): the grid was reloaded, review and apply again.`,
        );
        await this.load();
      } else if (body?.['unit_errors']) {
        const errs = body['unit_errors'] as { code?: string; errors: string[] }[];
        this.error.set(
          'Nothing was changed. ' +
            errs
              .slice(0, 5)
              .map((u) => `${u.code ?? ''}: ${u.errors.join('; ')}`)
              .join(' · '),
        );
      } else {
        this.error.set(problemMessage(e));
      }
    } finally {
      this.busy.set(false);
    }
  }

  /** Publication flags of the selected units (reach buyers with the next publication). */
  async setPublication(status: 'published' | 'hidden' | 'unpublished'): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.setUnitPublication(
        this.tenantId,
        this.projectId,
        status,
        this.selected().map((r) => r.unit_id),
      );
      this.toast.ok(
        `${this.selected().length} unit(s) set to "${status === 'published' ? 'public' : status === 'hidden' ? 'link only' : 'not published'}". Buyers see it after the next publication.`,
      );
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  async download(format: 'csv' | 'xlsx', columns: 'internal' | 'public'): Promise<void> {
    try {
      await this.api.downloadInventory(this.tenantId, this.projectId, format, columns);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }
}
