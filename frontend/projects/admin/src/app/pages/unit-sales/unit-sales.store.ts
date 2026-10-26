import { Injectable, OnDestroy, computed, inject, signal } from '@angular/core';
import {
  BoundaryOut,
  InventoryRow,
  MediaOut,
  MediaUpdate,
  PaymentPlanOut,
  PromotionOut,
  RendersOut,
  SalesChanges,
  SalesHistoryOut,
  SheetOut,
  UnitformaApi,
  problemMessage,
} from 'api-client';
import { httpStatus, problemBody } from '../../sales/sales-format';
import { DialogsService } from '../../ui/dialogs.service';
import { ToastService } from '../../ui/toast.service';
import {
  Form,
  FormKey,
  MediaKind,
  blankForm,
  changedKeys,
  currentBoundary,
  diffChanges,
  formFrom,
  perM2,
  planOf,
  timelineOf,
} from './unit-sales.model';

/** State and API calls of one unit's commercial page; provided by the page, shared with its cards. */
@Injectable()
export class UnitSalesStore implements OnDestroy {
  private readonly api = inject(UnitformaApi);
  private readonly dialogs = inject(DialogsService);
  private readonly toast = inject(ToastService);
  private tenantId = '';
  private projectId = '';
  private unitId = '';

  readonly row = signal<InventoryRow | null>(null);
  readonly plans = signal<PaymentPlanOut[]>([]);
  readonly promotions = signal<PromotionOut[]>([]);
  readonly media = signal<MediaOut[]>([]);
  /** Generated 3D plan renders and the tenant's daily cap (ADR-0017). */
  readonly renders = signal<RendersOut | null>(null);
  /** Every unit of the project, for the floor plan colours and the same-floor and same-layout links. */
  readonly allRows = signal<InventoryRow[]>([]);
  /** Units of the same floor: the plan card's links and the partner choice of a joined render (ADR-0017 E4). */
  readonly neighbours = computed(() => {
    const r = this.row();
    return r
      ? this.allRows().filter((x) => x.floor_id === r.floor_id && x.unit_id !== r.unit_id)
      : [];
  });
  /** Units sharing the layout code (they show this unit's public media until they get their own). */
  readonly layoutMates = computed(() => {
    const r = this.row();
    return r?.layout
      ? this.allRows().filter((x) => x.layout === r.layout && x.unit_id !== r.unit_id)
      : [];
  });
  private readonly planBase = signal<{
    unitId: string;
    sheet: SheetOut;
    boundaries: BoundaryOut[];
  } | null>(null);
  /** The floor plan around this unit, coloured by availability; null without a current outline. */
  readonly plan = computed(() => {
    const b = this.planBase();
    return b ? planOf(b.unitId, b.sheet, b.boundaries, this.allRows()) : null;
  });
  /** Live price per m² from the typed price, before saving. */
  readonly perM2 = computed(() => {
    const r = this.row();
    return r ? perM2(this.form(), r) : null;
  });
  private pollTimer: ReturnType<typeof setTimeout> | null = null;
  readonly history = signal<SalesHistoryOut | null>(null);
  readonly preview = signal<Record<string, unknown> | null>(null);
  readonly areaDefs = signal<{ key: string; label?: string }[]>([]);
  readonly conflict = signal<InventoryRow | null>(null);
  readonly pending = signal<SalesChanges>({});
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly form = signal<Form>(blankForm());
  reason = '';
  confirmZero = false;

  readonly timeline = computed(() => timelineOf(this.history()));
  readonly conflictKeys = computed(() => Object.keys(this.pending()));
  readonly hasOverrides = computed(
    () => Object.keys(this.row()?.public_field_overrides ?? {}).length > 0,
  );
  readonly changed = computed<Set<FormKey>>(() => {
    const r = this.row();
    return new Set(r ? changedKeys(this.form(), r) : []);
  });
  readonly dirtyCount = computed(() => this.changed().size);
  readonly planName = computed(
    () => this.plans().find((p) => p.id === this.form().payment_plan_id)?.name ?? null,
  );
  readonly promotionNames = computed(() =>
    this.promotions()
      .filter((p) => this.form().promotion_ids.includes(p.id))
      .map((p) => p.name),
  );

  init(tenantId: string, projectId: string, unitId: string): void {
    this.tenantId = tenantId;
    this.projectId = projectId;
    if (unitId !== this.unitId) this.planBase.set(null);
    this.unitId = unitId;
  }

  set<K extends FormKey>(key: K, value: Form[K]): void {
    this.form.update((f) => ({ ...f, [key]: value }));
  }

  isChanged(key: FormKey): boolean {
    return this.changed().has(key);
  }

  async load(): Promise<void> {
    try {
      const [row, plans, promos, media, history, preview, settings, renders] = await Promise.all([
        this.api.getUnitSales(this.tenantId, this.unitId),
        this.api.listPaymentPlans(this.tenantId, this.projectId),
        this.api.listPromotions(this.tenantId, this.projectId),
        this.api.listMedia(this.tenantId, this.unitId),
        this.api.unitSalesHistory(this.tenantId, this.unitId),
        this.api.unitPublicPreview(this.tenantId, this.unitId),
        this.api.getSalesSettings(this.tenantId, this.projectId),
        this.api.listRenders(this.tenantId, this.unitId),
      ]);
      this.plans.set(plans);
      this.promotions.set(promos);
      this.media.set(media);
      this.setRenders(renders);
      void this.api
        .inventory(this.tenantId, this.projectId)
        .then((rows) => this.allRows.set(rows))
        .catch(() => this.allRows.set([]));
      if (this.planBase()?.unitId !== this.unitId) void this.loadPlan();
      this.history.set(history);
      this.preview.set(preview);
      this.areaDefs.set(settings.area_definitions as { key: string; label?: string }[]);
      this.setRow(row);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  /** The unit's current outline, its sheet and the other outlines on it; silent when there is none. */
  private async loadPlan(): Promise<void> {
    const unitId = this.unitId;
    try {
      const unit = await this.api.getUnit(this.tenantId, unitId);
      const b = currentBoundary(unit.boundaries ?? []);
      if (!b) {
        if (unitId === this.unitId) this.planBase.set(null);
        return;
      }
      const [sheet, boundaries] = await Promise.all([
        this.api.getSheet(this.tenantId, b.sheet_id),
        this.api.listBoundaries(this.tenantId, b.sheet_id),
      ]);
      if (unitId === this.unitId) this.planBase.set({ unitId, sheet, boundaries });
    } catch {
      if (unitId === this.unitId) this.planBase.set(null);
    }
  }

  private setRow(row: InventoryRow): void {
    this.row.set(row);
    this.form.set(formFrom(row));
    this.reason = '';
    this.confirmZero = false;
  }

  reset(): void {
    const r = this.row();
    if (r) this.setRow(r);
  }

  async save(): Promise<void> {
    const r = this.row();
    if (!r) return;
    let changes: SalesChanges;
    try {
      changes = diffChanges(this.form(), r);
    } catch (e) {
      this.error.set((e as Error).message);
      return;
    }
    await this.send(changes, r.version);
  }

  private async send(changes: SalesChanges, version: number): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.updateUnitSales(this.tenantId, this.unitId, {
        ...changes,
        version,
        reason: this.reason || null,
        confirm_zero_price: this.confirmZero,
      });
      this.conflict.set(null);
      this.pending.set({});
      this.toast.ok('Saved');
      await this.load();
    } catch (e) {
      const body = problemBody(e);
      if (httpStatus(e) === 409 && body?.['current']) {
        this.pending.set(changes);
        this.conflict.set(body['current'] as InventoryRow);
      } else {
        this.error.set(problemMessage(e));
      }
    } finally {
      this.busy.set(false);
    }
  }

  saveOnTop(): Promise<void> {
    const c = this.conflict();
    return c ? this.send(this.pending(), c.version) : Promise.resolve();
  }

  discardMine(): void {
    const c = this.conflict();
    if (c) this.setRow(c);
    this.conflict.set(null);
    this.pending.set({});
  }

  togglePublic(key: string, value: boolean): Promise<void> {
    const r = this.row()!;
    return this.send(
      {
        public_fields: {
          ...r.public_field_overrides,
          [key]: value,
        } as SalesChanges['public_fields'],
      },
      r.version,
    );
  }

  clearOverrides(): Promise<void> {
    return this.send({ public_fields: {} }, this.row()!.version);
  }

  async upload(file: File, kind: MediaKind, isPublic: boolean, ai: boolean): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const intent = await this.api.createMedia(this.tenantId, this.unitId, {
        file_name: file.name,
        content_type: file.type || 'application/octet-stream',
        byte_size: file.size,
        kind,
        is_public: isPublic,
        is_ai_generated: ai,
      });
      await this.api.uploadToPresignedUrl(intent.upload_url, file, file.type);
      await this.api.completeMedia(this.tenantId, intent.media.id);
      this.toast.ok(`${file.name} uploaded`);
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  // --- generated 3D plan renders (ADR-0017 Decision 3) ---------------------------------------
  private setRenders(r: RendersOut): void {
    this.renders.set(r);
    if (this.pollTimer) clearTimeout(this.pollTimer);
    this.pollTimer = null;
    if (r.items.some((i) => i.status === 'queued' || i.status === 'running')) {
      this.pollTimer = setTimeout(() => void this.loadRenders(), 4000);
    }
  }

  async loadRenders(): Promise<void> {
    try {
      const r = await this.api.listRenders(this.tenantId, this.unitId);
      const before = this.renders();
      this.setRenders(r);
      // a render that just finished also changed the media list
      if (before && before.items.some((i) => i.status === 'queued' || i.status === 'running')) {
        if (!r.items.some((i) => i.status === 'queued' || i.status === 'running')) {
          this.media.set(await this.api.listMedia(this.tenantId, this.unitId));
        }
      }
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  async requestRender(note: string, withUnitId: string | null = null): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.requestRender(this.tenantId, this.unitId, {
        note: note.trim() || null,
        with_unit_id: withUnitId,
      });
      this.toast.ok('Render requested; it appears below when the model answers');
      await this.loadRenders();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  async approveRender(id: string): Promise<void> {
    this.busy.set(true);
    try {
      await this.api.approveRender(this.tenantId, id);
      this.toast.ok('Approved: public with the next publication, shared by layout code');
      await Promise.all([this.loadRenders(), this.load()]);
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  async rejectRender(id: string): Promise<void> {
    this.busy.set(true);
    try {
      await this.api.rejectRender(this.tenantId, id);
      await Promise.all([this.loadRenders(), this.load()]);
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  ngOnDestroy(): void {
    if (this.pollTimer) clearTimeout(this.pollTimer);
    this.pollTimer = null;
  }

  async patchMedia(m: MediaOut, body: Omit<MediaUpdate, 'version'>): Promise<void> {
    try {
      await this.api.updateMedia(this.tenantId, m.id, { ...body, version: m.version });
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  async move(i: number, delta: number): Promise<void> {
    const ids = this.media().map((m) => m.id);
    [ids[i], ids[i + delta]] = [ids[i + delta], ids[i]];
    try {
      this.media.set(await this.api.reorderMedia(this.tenantId, this.unitId, ids));
      this.preview.set(await this.api.unitPublicPreview(this.tenantId, this.unitId));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  async remove(m: MediaOut): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: `Delete ${m.file_name}?`,
      message: 'The file is removed from this unit and from the next publication.',
      confirmLabel: 'Delete',
      tone: 'bad',
      icon: 'lucideTrash2',
    });
    if (!ok) return;
    try {
      await this.api.deleteMedia(this.tenantId, m.id);
      this.toast.ok(`${m.file_name} deleted`);
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }
}
