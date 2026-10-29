import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { BuildingModelOut, BuildingOut, IfcSpaceLinkOut, MassingOut, UnitOut, UnitformaApi, problemMessage } from 'api-client';
import { MassingUnitInfo, MassingViewerComponent } from 'viewer-3d';
import {
  EmptyStateComponent,
  HeaderFact,
  PageHeaderComponent,
  UF_ICONS,
  kb,
  labelOf,
  whenShort,
} from 'ui';
import { ToastService } from '../ui/toast.service';

/** The converter's element groups in words (ADR-0032); IFC class names are shown as they are. */
const DROPPED_LABEL: Record<string, string> = {
  services: 'building services (pipes, ducts, fittings)',
  proxies: 'generic objects (IfcBuildingElementProxy)',
  other: 'other elements',
  IfcBuildingElementPart: 'element skins and parts',
};

/** Space colour in the IFC view by link status: the hues of the status chips (ADR-0036 #D1). */
const LINK_COLOUR: Record<string, string> = {
  confirmed: '#34d399',
  suggested: '#fbbf24',
  unmatched: '#f87171',
  rejected: '#9ca3af',
};

/** The id a space carries in the IFC GLB: its unit once confirmed, else `space:<GlobalId>`. */
export function spaceKey(lk: IfcSpaceLinkOut): string {
  return lk.status === 'confirmed' && lk.unit_id ? lk.unit_id : `space:${lk.ifc_global_id}`;
}

/** The viewer's `unitColors` for the IFC view: every linked space in its status hue. */
export function linkColours(links: IfcSpaceLinkOut[]): Record<string, string> {
  const out: Record<string, string> = {};
  for (const lk of links) {
    const c = LINK_COLOUR[lk.status];
    if (c) out[spaceKey(lk)] = c;
  }
  return out;
}

interface MassingStats {
  units?: number;
  triangles?: number;
  bytes?: number;
  units_draft?: number;
  units_skipped_uncalibrated?: number;
  buildings_unplaced?: string[];
}

/** Internal viewer for the generated massing model (plan §14 Phase 2 exit: "massing GLB appears in an internal viewer"). */
@Component({
  selector: 'uf-massing-page',
  imports: [
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    RouterLink,
    NgIcon,
    MassingViewerComponent,
    PageHeaderComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="3D massing" icon="lucideBox" [facts]="facts()">
        <ng-container actions>
          <a mat-stroked-button routerLink="../placement"
            ><ng-icon name="lucideMap" /> Site placement</a
          >
          <button mat-flat-button [disabled]="busy()" (click)="regenerate()">
            <ng-icon name="lucideRefreshCw" [class.uf-spin]="busy()" />
            {{ busy() ? 'Waiting for the worker…' : 'Regenerate' }}
          </button>
        </ng-container>
      </uf-page-header>
      @if (error(); as e) {
        <div
          class="uf-alert"
          [class.uf-alert--bad]="model()"
          [class.uf-alert--info]="!model()"
          role="alert"
        >
          <ng-icon [name]="model() ? 'lucideCircleX' : 'lucideInfo'" />{{ e }}
        </div>
      }
      @if (model(); as m) {
        <div class="uf-toolbar">
          <mat-form-field appearance="outline" subscriptSizing="dynamic">
            <mat-label>Floor</mat-label>
            <mat-select [value]="floor()" (valueChange)="floor.set($event)">
              <mat-option [value]="null">All floors</mat-option>
              @for (l of levels(); track l) {
                <mat-option [value]="l">Level {{ l }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          @if (stats().units_skipped_uncalibrated) {
            <span class="uf-chip uf-tone-warning"
              ><ng-icon name="lucideRuler" />{{ stats().units_skipped_uncalibrated }} unit(s)
              skipped: sheet not calibrated</span
            >
          }
          @if (stats().buildings_unplaced?.length) {
            <span class="uf-chip uf-tone-warning"
              ><ng-icon name="lucideMapPin" />unplaced:
              {{ stats().buildings_unplaced!.join(', ') }}</span
            >
          }
          @if (m.error) {
            <span class="uf-chip uf-tone-bad">{{ m.error }}</span>
          }
          <span class="uf-spacer"></span>
          @if (picked(); as u) {
            <span class="uf-chip uf-chip--lg uf-tone-info"
              ><ng-icon name="lucideBuilding" />{{ u.building_code }} · {{ u.code }} ·
              {{ labelOf('unit_type', u.unit_type) }} · level {{ u.floor_level }}</span
            >
          } @else {
            <span class="uf-hint">Click a unit in the model to see its code.</span>
          }
        </div>
        <div class="viewer">
          <uf-massing-viewer
            [src]="viewerSrc() ?? m.glb_url ?? null"
            [badge]="viewerBadge()"
            [floorLevel]="floor()"
            [selectedUnitId]="selectedId()"
            [unitColors]="spaceColors()"
            (unitPicked)="onPick($event)"
            (loadedUnits)="units.set($event)"
          />
        </div>
        <p class="uf-hint">
          A schematic model built from the approved floor outlines and the floor heights; buyers see
          it on the portal when their device can load it. Exact geometry needs an IFC export (later
          phase).
        </p>
      }

      <section class="ifc">
        <h3><ng-icon name="lucideBox" /> Architect's model (IFC)</h3>
        <p class="uf-hint">
          Upload an IFC export under a building in Documents; the heavy worker converts it to a model
          with one object per space. Link each space to its unit here: unit ids never change, only
          the link. Confirming an IFC space copies its IFC floor areas onto the unit as unverified
          "ifc_quantity" areas. When the export has no spaces, the approved plan outlines of the
          building's floors become the spaces, placed in the model by matching the lowest floor to
          its storey's slab (ADR-0030); confirming one of those says the alignment is right, no
          areas are copied. Buyers see the IFC model of a building instead of the massing once it
          exists; only confirmed spaces of listed units are clickable for them. In the IFC view each
          space is tinted like its status chip: green confirmed, amber suggested, red unmatched, grey
          not a unit.
        </p>
        <div class="uf-toolbar">
          <mat-form-field appearance="outline" subscriptSizing="dynamic">
            <mat-label>Building</mat-label>
            <mat-select [value]="buildingId()" (valueChange)="selectBuilding($event)">
              @for (b of buildings(); track b.id) {
                <mat-option [value]="b.id">{{ b.code }} {{ b.name ?? '' }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          @if (ifcModel(); as im) {
            <span class="uf-chip" [class.uf-tone-good]="im.status === 'ready'" [class.uf-tone-bad]="im.status === 'failed'">{{ im.status }}</span>
            <span class="uf-chip">{{ im.stats['spaces'] }} spaces · {{ im.stats['triangles'] }} triangles · {{ mb(im.stats['bytes']) }} MB</span>
            <span class="uf-chip uf-tone-good">{{ count(im, 'confirmed') }} confirmed</span>
            <span class="uf-chip uf-tone-warning">{{ count(im, 'suggested') }} suggested</span>
            <span class="uf-chip uf-tone-bad">{{ count(im, 'unmatched') }} unmatched</span>
            <span class="uf-chip">{{ count(im, 'rejected') }} not units</span>
            @if (dropped(im).length) {
              <span class="uf-chip uf-tone-warning">dropped to fit 15 MB: {{ dropped(im).join(', ') }}</span>
            }
            <span class="uf-spacer"></span>
            <button mat-stroked-button [disabled]="view() === 'massing'" (click)="view.set('massing')">Show massing</button>
            <button mat-stroked-button [disabled]="view() === 'ifc' || !im.glb_url" (click)="view.set('ifc')">Show IFC model</button>
            <button mat-stroked-button [disabled]="busy()" (click)="rebuildIfc()">Re-run conversion</button>
            @if (im.error) { <span class="uf-chip uf-tone-bad">{{ im.error }}</span> }
          } @else if (buildingId()) {
            <span class="uf-hint">No IFC model for this building yet. Upload an .ifc file under it in Documents.</span>
          }
        </div>
        @if (ifcModel(); as im) {
          @if (im.status === 'ready' && im.stats['spaces'] === 0) {
            <div class="uf-alert uf-alert--warning">
              <ng-icon name="lucideTriangleAlert" />
              <span>
                The export holds no spaces (IfcSpace), so there is nothing to link to units; the
                building still shows as a model. @if (im.stats['application']) {{{ im.stats['application'] }} wrote it.}
                @if (exportAdvice(im).length === 0) {
                  @if (isArchicad(im)) {
                    Archicad writes a zone as IfcSpace only when zones are inside the exported scope
                    (the zone layers visible, or "Entire project", and element type Zone kept in the
                    IFC translator's Model Filter). Ask the architect to re-export with zones and
                    upload the file as a new revision of the same document.
                  } @else {
                    Ask the architect to export rooms or zones as IfcSpace and upload the file as a
                    new revision of the same document.
                  }
                }
              </span>
            </div>
          }
          @if (im.status === 'ready' && planFit(im); as pf) {
            @if (pf['reason']) {
              <div class="uf-alert uf-alert--warning">
                <ng-icon name="lucideTriangleAlert" />
                <span>
                  No spaces from the plans either: {{ pf['reason'] }}. Approve calibrated unit
                  outlines on this building's floors, then re-run the conversion.
                </span>
              </div>
            } @else {
              <div class="uf-alert uf-alert--info">
                <ng-icon name="lucideLayers" />
                <span>
                  {{ im.stats['spaces_plan'] }} spaces come from the approved plan outlines, placed
                  on the model by floor {{ pf['floor_level'] }} against storey
                  "{{ pf['storey'] ?? '?' }}" ({{ faceLabel(pf) }}@if (pf['scope'] === 'project') {, fitted together with the other blocks' outlines}):
                  rotation {{ pf['rotation_deg'] }}°, overlap {{ pct(pf['iou']) }} on average,
                  the worst level {{ pct(pf['min_coverage']) }} inside. Check the model (Show IFC
                  model, select a row), then confirm: confirming says the alignment is right; no
                  areas are copied.
                </span>
                @if (suggestedPlan() > 0) {
                  <button mat-stroked-button [disabled]="busy()" (click)="confirmPlan()">
                    Confirm all {{ suggestedPlan() }} plan spaces
                  </button>
                }
              </div>
            }
          }
          @if (im.status === 'ready' && exportAdvice(im).length) {
            <div class="uf-alert uf-alert--warning">
              <ng-icon name="lucideSettings" />
              <div>
                <strong>Export settings read from the file</strong> (ADR-0030): what to ask the
                architect to change before the next revision.
                <ul class="uf-advice">
                  @for (a of exportAdvice(im); track a.key) {
                    <li><code>{{ a.name }}: {{ a.value }}</code> — {{ a.advice }}</li>
                  }
                </ul>
              </div>
            </div>
          }
        }
        @if (links().length) {
          <table class="plain">
            <tr><th>Space</th><th>Storey</th><th>Floor</th><th class="num">Net m²</th><th>Unit</th><th>Status</th><th></th></tr>
            @for (lk of links(); track lk.id) {
              <tr [class.sel]="selectedLink()?.id === lk.id" (click)="selectLink(lk)">
                <td>{{ lk.name || lk.ifc_global_id }}@if (lk.long_name) { <span class="uf-hint"> · {{ lk.long_name }}</span> }@if (lk.source === 'plan') { <span class="uf-chip uf-tone-info">from plan</span> }</td>
                <td>{{ lk.storey_name }}@if (lk.storey_elevation_m != null) { <span class="uf-hint"> {{ lk.storey_elevation_m }}</span> }</td>
                <td>{{ lk.floor_level ?? '—' }}</td>
                <td class="num">{{ lk.areas['net_floor_area'] ?? '—' }}</td>
                <td>
                  <mat-form-field appearance="outline" subscriptSizing="dynamic" class="unit">
                    <mat-select [value]="pickUnit[lk.id] ?? lk.unit_id" (valueChange)="pickUnit[lk.id] = $event" [disabled]="busy() || lk.status === 'confirmed'">
                      <mat-option [value]="null">—</mat-option>
                      @for (u of unitsOnFloor(lk); track u.id) { <mat-option [value]="u.id">{{ u.code }}</mat-option> }
                    </mat-select>
                  </mat-form-field>
                  @if (lk.unit_code && lk.status === 'suggested') { <span class="uf-hint">suggested {{ lk.unit_code }}@if (lk.confidence) { · {{ pct(lk.confidence) }} }</span> }
                </td>
                <td><span class="uf-chip" [class.uf-tone-good]="lk.status === 'confirmed'" [class.uf-tone-warning]="lk.status === 'suggested'" [class.uf-tone-bad]="lk.status === 'unmatched'">{{ lk.status === 'rejected' ? 'not a unit' : lk.status }}</span></td>
                <td class="actions">
                  @if (lk.status !== 'confirmed') {
                    <button mat-stroked-button [disabled]="busy() || !(pickUnit[lk.id] ?? lk.unit_id)" (click)="decide(lk, 'confirm'); $event.stopPropagation()">Confirm</button>
                    <button mat-button [disabled]="busy()" (click)="decide(lk, 'reject'); $event.stopPropagation()">Not a unit</button>
                  } @else {
                    <button mat-button [disabled]="busy()" (click)="decide(lk, 'reset'); $event.stopPropagation()">Undo</button>
                  }
                </td>
              </tr>
            }
          </table>
          <p class="uf-hint">Suggestions come from the storey (elevation within 0.3 m of a floor) and the apartment label in the space name. Select a row to highlight the space in the IFC model.</p>
        }
      </section>

      @if (!model() && !busy()) {
        <uf-empty-state
          icon="lucideBox"
          title="No massing model yet"
          text="The model is built from approved sheets with a calibrated scale and placed buildings. Approve a mapped sheet, or click Regenerate."
        >
          <a mat-stroked-button routerLink="../documents">Open Documents</a>
        </uf-empty-state>
      }
    </div>
  `,
  styles: `
    .ifc { margin-top: 1.25rem; display: grid; gap: 0.5rem; }
    .ifc h3 { margin: 0; font-size: 1.05rem; display: flex; align-items: center; gap: 0.35rem; }
    .uf-advice { margin: 6px 0 0; padding-left: 18px; }
    .uf-advice li { margin: 2px 0; }
    .plain { border-collapse: collapse; width: 100%; }
    .plain th, .plain td { padding: 0.25rem 0.5rem; text-align: left; border-bottom: 1px solid var(--uf-border); vertical-align: middle; }
    .plain tr.sel td { background: var(--uf-surface); }
    .num { text-align: right !important; white-space: nowrap; }
    .unit { width: 11rem; }
    .actions { white-space: nowrap; }
    .viewer {
      background: var(--uf-surface);
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius);
      overflow: hidden;
      min-height: 420px;
    }
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class MassingPage {
  private readonly api = inject(UnitformaApi);
  private readonly toast = inject(ToastService);
  readonly labelOf = labelOf;
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly model = signal<MassingOut | null>(null);
  readonly units = signal<MassingUnitInfo[]>([]);
  readonly floor = signal<number | null>(null);
  readonly picked = signal<MassingUnitInfo | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly levels = computed(() =>
    [...new Set(this.units().map((u) => u.floor_level))].sort((a, b) => a - b),
  );
  readonly stats = computed(() => (this.model()?.stats ?? {}) as MassingStats);
  // --- IFC model per building (ADR-0006 Phase C)
  readonly buildings = signal<BuildingOut[]>([]);
  readonly buildingId = signal<string | null>(null);
  readonly ifcModel = signal<BuildingModelOut | null>(null);
  readonly links = signal<IfcSpaceLinkOut[]>([]);
  readonly selectedLink = signal<IfcSpaceLinkOut | null>(null);
  readonly projectUnits = signal<UnitOut[]>([]);
  readonly view = signal<'massing' | 'ifc'>('massing');
  pickUnit: Record<string, string | null> = {};
  readonly viewerSrc = computed(() => (this.view() === 'ifc' ? (this.ifcModel()?.glb_url ?? null) : (this.model()?.glb_url ?? null)));
  readonly viewerBadge = computed(() => (this.view() === 'ifc' ? "Model from the architect's IFC export" : 'Schematic model generated from floor plans — not an architectural model'));
  /** In the IFC view the selected row highlights its space; confirmed spaces carry the unit id. */
  readonly selectedId = computed(() => {
    if (this.view() === 'ifc') {
      const lk = this.selectedLink();
      return lk ? spaceKey(lk) : null;
    }
    return this.picked()?.unit_id ?? null;
  });
  /** In the IFC view every space is tinted by its link status, so the work left shows on the model. */
  readonly spaceColors = computed(() => (this.view() === 'ifc' ? linkColours(this.links()) : null));
  readonly facts = computed<HeaderFact[]>(() => {
    const m = this.model();
    if (!m) return [];
    const s = this.stats();
    return [
      { domain: 'massing', status: m.status },
      { label: 'Built', value: whenShort(m.created_at) },
      ...(s.units !== undefined
        ? [
            { label: 'Units', value: s.units },
            { label: 'Triangles', value: s.triangles ?? 0 },
            { label: 'Size', value: kb(s.bytes) },
          ]
        : []),
    ];
  });

  constructor() {
    toObservable(this.projectId).subscribe(() => {
      void this.load();
      void this.loadBuildings();
    });
  }

  async loadBuildings(): Promise<void> {
    try {
      const [bs, units] = await Promise.all([this.api.listBuildings(this.tenantId(), this.projectId()), this.api.listUnits(this.tenantId(), this.projectId())]);
      const real = bs.filter((b) => b.kind === 'building');
      this.buildings.set(real);
      this.projectUnits.set(units);
      if (real.length && !this.buildingId()) await this.selectBuilding(real[0].id);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  async selectBuilding(id: string | null): Promise<void> {
    this.buildingId.set(id);
    this.selectedLink.set(null);
    this.pickUnit = {};
    if (!id) {
      this.ifcModel.set(null);
      this.links.set([]);
      return;
    }
    try {
      const [m, links] = await Promise.all([this.api.buildingModel(this.tenantId(), id), this.api.listIfcLinks(this.tenantId(), id)]);
      this.ifcModel.set(m);
      this.links.set(links);
      if (!m) this.view.set('massing');
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  mb(v: unknown): string {
    return typeof v === 'number' ? (v / 1048576).toFixed(1) : '?';
  }

  count(m: BuildingModelOut, key: string): number {
    return m.links?.[key] ?? 0;
  }

  /**
   * ADR-0030 Decision 1: one line per translator option that limits what the model can do. The
   * option names are what Archicad 29 writes; other tools produce no lines.
   */
  exportAdvice(m: BuildingModelOut): { key: string; name: string; value: string; advice: string }[] {
    const opts = (m.stats['export_options'] ?? {}) as Record<string, string>;
    const out: { key: string; name: string; value: string; advice: string }[] = [];
    const spaces = Number(m.stats['spaces'] ?? 0);
    const v = (k: string) => (opts[k] ?? '').toLowerCase();
    if (spaces === 0 && v('elements_to_export').startsWith('visible')) {
      out.push({
        key: 'elements_to_export',
        name: 'Elements to export',
        value: opts['elements_to_export'],
        advice:
          'zones on a hidden layer are not exported; ask for "Entire project", or for the zone layers visible in the exported view, with element type Zone kept in the Model Filter.',
      });
    }
    if (v('base_quantities') === 'off') {
      out.push({
        key: 'base_quantities',
        name: 'IFC Base Quantities',
        value: opts['base_quantities'],
        advice:
          'no floor areas in the file, so confirming a space copies nothing onto the unit; ask for On.',
      });
    }
    if (v('material_preservation').startsWith('explode')) {
      out.push({
        key: 'material_preservation',
        name: 'Material Preservation',
        value: opts['material_preservation'],
        advice:
          'every composite wall and slab arrives as separate skins; the model is larger than it needs to be (the skins are kept: they carry the facade colours and the railings); ask for Off.',
      });
    }
    return out;
  }

  faceLabel(pf: Record<string, unknown>): string {
    const f = pf['face'];
    return f === 'slabs' ? 'slab footprint' : f === 'hull' ? 'slab hull' : 'model bounds';
  }

  planFit(m: BuildingModelOut): Record<string, unknown> | null {
    const pf = m.stats['plan_fit'];
    return pf && typeof pf === 'object' ? (pf as Record<string, unknown>) : null;
  }

  readonly suggestedPlan = computed(
    () => this.links().filter((lk) => lk.source === 'plan' && lk.status === 'suggested').length,
  );

  /** ADR-0030 C1: one call confirms every suggested plan space; the GLB is relinked once. */
  async confirmPlan(): Promise<void> {
    const id = this.buildingId();
    if (!id) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const r = await this.api.confirmPlanIfcLinks(this.tenantId(), id);
      this.toast.ok(`${r.confirmed} plan space(s) confirmed`);
      await this.selectBuilding(id); // links and the relinked GLB
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  isArchicad(m: BuildingModelOut): boolean {
    return String(m.stats['application'] ?? '')
      .toLowerCase()
      .includes('archicad');
  }

  dropped(m: BuildingModelOut): string[] {
    const d = m.stats['classes_dropped'];
    return Array.isArray(d) ? (d as string[]).map((g) => DROPPED_LABEL[g] ?? g) : [];
  }

  pct(v: unknown): string {
    const n = typeof v === 'string' ? Number(v) : (v as number | null | undefined);
    return typeof n === 'number' && !Number.isNaN(n) ? `${Math.round(n * 100)} %` : '';
  }

  unitsOnFloor(lk: IfcSpaceLinkOut): UnitOut[] {
    const b = this.buildingId();
    return this.projectUnits().filter((u) => u.building_id === b && (lk.floor_id ? u.floor_id === lk.floor_id : true) && u.lifecycle_status !== 'removed');
  }

  selectLink(lk: IfcSpaceLinkOut): void {
    this.selectedLink.set(lk);
    if (this.ifcModel()?.glb_url) this.view.set('ifc');
  }

  onPick(u: MassingUnitInfo): void {
    this.picked.set(u);
    if (this.view() === 'ifc') {
      const gid = u.unit_id.startsWith('space:') ? u.unit_id.slice(6) : null;
      const lk = this.links().find((l) => (gid ? l.ifc_global_id === gid : l.unit_id === u.unit_id));
      if (lk) this.selectedLink.set(lk);
    }
  }

  async decide(lk: IfcSpaceLinkOut, decision: 'confirm' | 'reject' | 'reset'): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const unitId = decision === 'confirm' ? (this.pickUnit[lk.id] ?? lk.unit_id ?? null) : null;
      const updated = await this.api.decideIfcLink(this.tenantId(), lk.id, { decision, unit_id: unitId });
      this.links.update((list) => list.map((x) => (x.id === lk.id ? updated : x)));
      const id = this.buildingId();
      if (id) this.ifcModel.set(await this.api.buildingModel(this.tenantId(), id)); // the GLB got a new key after relinking
      this.toast.ok(decision === 'confirm' ? `Space ${updated.name ?? ''} confirmed as ${updated.unit_code ?? 'unit'}` : 'Updated');
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  async rebuildIfc(): Promise<void> {
    const id = this.buildingId();
    if (!id) return;
    this.busy.set(true);
    try {
      await this.api.rebuildBuildingModel(this.tenantId(), id);
      this.toast.ok('Conversion queued on the heavy worker; reload in a minute');
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
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
        if (m && m.id !== before && m.status !== 'generating') {
          this.toast.ok('New massing model ready');
          return;
        }
      }
      this.error.set('The worker has not produced a new model yet; reload later.');
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
