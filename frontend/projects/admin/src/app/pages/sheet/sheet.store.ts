import { Injectable, computed, inject, signal } from '@angular/core';
import {
  BoundaryOut,
  BuildingOut,
  SheetFloorOut,
  SheetOut,
  SuggestionOut,
  UnitOut,
  UnitformaApi,
  problemMessage,
} from 'api-client';
import { PlanMode, PlanPolygon, Point, Ring } from 'plan-viewer';
import { DialogsService } from '../../ui/dialogs.service';
import { ToastService } from '../../ui/toast.service';
import {
  FloorOption,
  UnitType,
  centroidOf,
  confident,
  duplicateOf,
  hintsText,
  inside,
} from './sheet.model';

/** State and API calls of the sheet mapping editor; provided by the page, shared with its cards. */
@Injectable()
export class SheetStore {
  private readonly api = inject(UnitformaApi);
  private readonly dialogs = inject(DialogsService);
  private readonly toast = inject(ToastService);
  private tenantId = '';
  private projectId = '';
  private sheetId = '';

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
  readonly notice = signal<string | null>(null);
  distance: number | null = null;
  unitType: UnitType = 'apartment';
  code = '';
  label = '';

  /** Local edit of the sheet's floors; saved in one call (PUT /sheets/{id}/floors). */
  readonly draft = signal<SheetFloorOut[]>([]);
  readonly floorsEdited = signal(false);
  readonly regionTarget = signal<string | null>(null);
  drawFloor: string | null = null;

  readonly confirmedFloors = computed(() =>
    (this.sheet()?.floors ?? []).filter((a) => a.status === 'confirmed'),
  );
  readonly hasSuggested = computed(() => this.draft().some((a) => a.status === 'suggested'));
  readonly floorsDirty = computed(() => this.floorsEdited() || this.hasSuggested());
  readonly floors = computed<FloorOption[]>(() =>
    this.buildings()
      .filter((b) => b.kind === 'building')
      .flatMap((b) =>
        (b.floors ?? []).map((f) => ({
          id: f.id,
          label: `${b.code} · ${f.display_name} (level ${f.level})`,
        })),
      ),
  );
  readonly unassignedFloors = computed(() => {
    const taken = new Set(this.draft().map((a) => a.floor_id));
    return this.floors().filter((f) => !taken.has(f.id));
  });
  readonly polygons = computed<PlanPolygon[]>(() => {
    const byUnit = new Map(this.units().map((u) => [u.id, u]));
    const own: PlanPolygon[] = this.boundaries().map((b) => ({
      id: b.unit_id,
      ring: (b.polygon['ring'] as Ring) ?? [],
      label: byUnit.get(b.unit_id)?.code ?? b.label ?? '',
      status: b.status,
      selected: b.unit_id === this.selectedUnitId(),
    }));
    const cands: PlanPolygon[] = this.candidates().map((c, i) => ({
      id: `cand:${i}`,
      ring: c.ring as Ring,
      label: c.label ?? '',
      kind: 'candidate' as const,
      selected: i === this.selectedCandidateIdx(),
    }));
    const regions: PlanPolygon[] = this.draft()
      .filter((a) => a.region?.['ring'])
      .map((a) => ({
        id: `region:${a.floor_id}`,
        ring: a.region!['ring'] as Ring,
        label: this.floorLabel(a.floor_id),
        kind: 'region' as const,
      }));
    return [...regions, ...own, ...cands];
  });
  readonly selectedCandidate = computed(() =>
    this.selectedCandidateIdx() === null
      ? null
      : (this.candidates()[this.selectedCandidateIdx()!] ?? null),
  );
  readonly labelledCount = computed(() => this.candidates().filter(confident).length);
  readonly draftCount = computed(
    () => this.boundaries().filter((b) => b.status === 'draft').length,
  );
  readonly duplicateOf = computed(() => duplicateOf(this.sheet()?.hints));
  readonly hintsText = computed(() => hintsText(this.sheet()?.hints));
  readonly pxPerMetre = computed(() => {
    const c = this.sheet()?.calibration as { m_per_px?: number } | null | undefined;
    return c?.m_per_px ? 1 / c.m_per_px : null;
  });
  /** Set when the calibration came from the file itself (DXF $INSUNITS, ADR-0006). */
  readonly calibrationSource = computed(
    () => (this.sheet()?.calibration as { source?: string } | null | undefined)?.source ?? null,
  );

  init(tenantId: string, projectId: string, sheetId: string): void {
    this.tenantId = tenantId;
    this.projectId = projectId;
    this.sheetId = sheetId;
  }

  floorLabel(id: string): string {
    return this.floors().find((f) => f.id === id)?.label ?? id;
  }

  sourceOf(u: UnitOut): string {
    return (u.boundaries ?? []).find((b) => b.sheet_id === this.sheetId)?.source ?? '';
  }

  async load(): Promise<void> {
    try {
      const [s, b, bounds, units] = await Promise.all([
        this.api.getSheet(this.tenantId, this.sheetId),
        this.api.listBuildings(this.tenantId, this.projectId),
        this.api.listBoundaries(this.tenantId, this.sheetId),
        this.api.listUnits(this.tenantId, this.projectId),
      ]);
      this.sheet.set(s);
      this.draft.set((s.floors ?? []).map((a) => ({ ...a })));
      this.floorsEdited.set(false);
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
      const t = this.selectedCandidate()?.unit_type;
      if (t) this.unitType = t;
      this.selectedUnitId.set(null);
    } else {
      this.selectedUnitId.set(id);
      this.selectedCandidateIdx.set(null);
    }
  }

  setMode(m: PlanMode): void {
    this.regionTarget.set(null);
    this.mode.set(m);
  }

  addFloor(floorId: string | null): void {
    if (!floorId) return;
    this.draft.update((d) => [
      ...d,
      { floor_id: floorId, status: 'confirmed', source: 'manual', region: null, marker: null },
    ]);
    this.floorsEdited.set(true);
  }

  removeFloor(floorId: string): void {
    this.draft.update((d) => d.filter((a) => a.floor_id !== floorId));
    this.floorsEdited.set(true);
  }

  clearRegion(floorId: string): void {
    this.draft.update((d) => d.map((a) => (a.floor_id === floorId ? { ...a, region: null } : a)));
    this.floorsEdited.set(true);
  }

  drawRegion(floorId: string): void {
    this.regionTarget.set(floorId);
    this.mode.set('draw');
  }

  resetFloors(): void {
    this.draft.set((this.sheet()?.floors ?? []).map((a) => ({ ...a })));
    this.floorsEdited.set(false);
    this.regionTarget.set(null);
  }

  /** Every listed floor becomes confirmed, suggestions included. */
  saveFloors(): Promise<void> {
    const floors = this.draft().map((a) => ({
      floor_id: a.floor_id,
      region: a.region ? { ring: a.region['ring'] as number[][] } : null,
    }));
    return this.run(async () => {
      await this.api.setSheetFloors(this.tenantId, this.sheetId, floors, this.sheet()!.version);
      this.toast.ok(
        `${floors.length} floor${floors.length === 1 ? '' : 's'} confirmed on this sheet`,
      );
    });
  }

  calibrate(): Promise<void> {
    const pts = this.calibPts();
    if (!pts || !this.distance) return Promise.resolve();
    return this.run(async () => {
      await this.api.calibrateSheet(
        this.tenantId,
        this.sheetId,
        { p1: pts[0], p2: pts[1], distance_m: this.distance! },
        this.sheet()!.version,
      );
      this.calibPts.set(null);
      this.mode.set('view');
      this.toast.ok('Scale saved');
    });
  }

  onDrawn(ring: Ring): Promise<void> {
    const target = this.regionTarget();
    if (target) {
      this.draft.update((d) =>
        d.map((a) => (a.floor_id === target ? { ...a, region: { ring } } : a)),
      );
      this.floorsEdited.set(true);
      this.regionTarget.set(null);
      this.mode.set('view');
      return Promise.resolve();
    }
    return this.run(async () => {
      await this.api.createBoundary(this.tenantId, this.sheetId, {
        ring,
        unit_type: this.unitType,
        code: this.code || null,
        label: this.label || null,
        source: 'manual',
        floor_id: this.drawFloor,
      });
      this.code = this.label = '';
    });
  }

  /** Closed loops from the sheet's vectors; polygons already covered by a unit are left out. */
  async suggest(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const all = await this.api.suggestBoundaries(this.tenantId, this.sheetId);
      const taken = this.boundaries().map((b) => centroidOf(b.polygon['ring'] as Ring));
      const fresh = all.filter((c) => !taken.some((t) => inside(t, c.ring as Ring)));
      this.candidates.set(fresh);
      this.selectedCandidateIdx.set(fresh.length ? 0 : null);
      if (!all.length)
        this.error.set(
          'No closed loops found in this sheet (scanned or raster-only drawing): draw units manually.',
        );
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  acceptCandidate(c: SuggestionOut): Promise<void> {
    return this.run(async () => {
      await this.api.createBoundary(this.tenantId, this.sheetId, {
        ring: c.ring,
        unit_type: this.unitType,
        code: this.code || null,
        label: c.label ?? null,
        source: 'vector_suggest',
        floor_id: c.floor_id ?? null,
        printed_area_m2: c.printed_area_m2 ?? null,
      });
      this.code = '';
      this.dismissCandidate(c);
    });
  }

  acceptLabelled(): Promise<void> {
    return this.run(async () => {
      const list = this.candidates().filter(confident);
      for (const c of list) {
        await this.api.createBoundary(this.tenantId, this.sheetId, {
          ring: c.ring,
          unit_type: c.unit_type!,
          code: null,
          label: c.label ?? null,
          source: 'vector_suggest',
          floor_id: c.floor_id ?? null,
          printed_area_m2: c.printed_area_m2 ?? null,
        });
      }
      this.candidates.update((all) => all.filter((x) => !confident(x)));
      this.selectedCandidateIdx.set(null);
      this.toast.ok(`${list.length} unit${list.length === 1 ? '' : 's'} created from suggestions`);
    });
  }

  async setExcluded(excluded: boolean, reason?: string): Promise<void> {
    let why: string | null = null;
    if (excluded) {
      why =
        reason ??
        (await this.dialogs.prompt({
          title: 'Exclude this sheet from mapping',
          message:
            'Excluded pages stop proposing floors and units. Say why, so a colleague knows (reprint, detail, schedule).',
          label: 'Reason',
          value: 'not a floor plan',
          required: true,
          confirmLabel: 'Exclude',
        }));
      if (why === null) return;
    }
    return this.run(() =>
      this.api.excludeSheet(this.tenantId, this.sheetId, excluded, why, this.sheet()!.version),
    );
  }

  readPrinted(): Promise<void> {
    return this.run(async () => {
      const r = await this.api.readPrintedAreas(this.tenantId, this.sheetId);
      this.notice.set(
        `Printed areas: ${r.updated} stored, ${r.unchanged} unchanged, ${r.unmatched} unit(s) without a printed area.`,
      );
    });
  }

  dismissCandidate(c: SuggestionOut): void {
    this.candidates.update((list) => list.filter((x) => x !== c));
    this.selectedCandidateIdx.set(this.candidates().length ? 0 : null);
  }

  async approve(): Promise<void> {
    const n = this.draftCount();
    const ok = await this.dialogs.confirm({
      title: `Approve ${n} draft unit${n === 1 ? '' : 's'}?`,
      message:
        'Approval creates permanent unit records. Their identity never changes afterwards; later revisions are matched against them.',
      consequence:
        'The units appear under Units & lineage and in the inventory; the 3D massing is regenerated.',
      confirmLabel: 'Approve',
      icon: 'lucideClipboardCheck',
    });
    if (!ok) return;
    return this.run(async () => {
      await this.api.approveSheet(this.tenantId, this.sheetId);
      this.toast.ok(`${n} unit${n === 1 ? '' : 's'} approved`);
    });
  }

  async relabel(u: UnitOut): Promise<void> {
    const code = await this.dialogs.prompt({
      title: `Relabel ${u.code}`,
      message: 'The unit keeps its id and history; only the code changes.',
      label: 'New code',
      value: u.code,
      required: true,
      confirmLabel: 'Relabel',
    });
    if (!code || code === u.code) return;
    return this.run(() =>
      this.api.relabelUnit(this.tenantId, u.id, code, u.version, 'reviewer relabel'),
    );
  }

  async remove(u: UnitOut): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: `Mark ${u.code} as removed?`,
      message: 'The record and its history are kept; the unit leaves the inventory and the portal.',
      confirmLabel: 'Mark removed',
      tone: 'bad',
    });
    if (!ok) return;
    return this.run(() =>
      this.api.removeUnit(this.tenantId, u.id, u.version, 'removed in mapping editor'),
    );
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
