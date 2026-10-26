import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  DocumentOut,
  FootprintOut,
  ProjectOut,
  SheetOut,
  SiteFeatureOut,
  SiteFeatureUpdate,
  SiteTransform,
  UnitformaApi,
  problemMessage,
} from 'api-client';
import { PlanMode, PlanPolygon, PlanViewerComponent, Point, PolygonMove, Ring } from 'plan-viewer';
import {
  EmptyStateComponent,
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
  labelOf,
} from 'ui';
import { DialogsService } from '../ui/dialogs.service';
import { ToastService } from '../ui/toast.service';

type Pt = [number, number];

/** A facade drawing assigned to one side of a building (stored on the building, ADR-0016 E3). */
interface FacadeAssign {
  side: number;
  sheet_id: string;
  region: { ring: number[][] } | null;
  flip?: boolean;
}

const FEATURE_KINDS = [
  'garden',
  'road',
  'parking_zone',
  'amenity',
  'common_area',
  'entrance',
  'other',
];
const FEATURE_LABELS: Record<string, string> = {
  garden: 'Garden / green',
  road: 'Road',
  parking_zone: 'Parking zone',
  amenity: 'Amenity (playground, pool, …)',
  common_area: 'Common area',
  entrance: 'Entrance',
  other: 'Other',
};
/** Same hues the portal uses on the plan and in 3D. */
const FEATURE_COLOURS: Record<string, string> = {
  garden: '#6fb86a',
  road: '#8b919a',
  parking_zone: '#9aa1ab',
  amenity: '#5fb2dc',
  common_area: '#c9b58f',
  entrance: '#e8963f',
  other: '#b8b5ae',
};

function apply(t: SiteTransform, p: Pt): Pt {
  const a = ((t.rotation_deg ?? 0) * Math.PI) / 180;
  const c = Math.cos(a);
  const s = Math.sin(a);
  const k = t.scale ?? 1;
  return [(t.tx ?? 0) + k * (c * p[0] - s * p[1]), (t.ty ?? 0) + k * (s * p[0] + c * p[1])];
}

function invert(t: SiteTransform, p: Pt): Pt {
  const a = ((t.rotation_deg ?? 0) * Math.PI) / 180;
  const c = Math.cos(a);
  const s = Math.sin(a);
  const k = t.scale ?? 1;
  const x = (p[0] - (t.tx ?? 0)) / k;
  const y = (p[1] - (t.ty ?? 0)) / k;
  return [c * x + s * y, -s * x + c * y];
}

/**
 * Building placement editor (plan §3.5 site frame, §13.1 step 3a): footprints from the lowest mapped
 * floor are placed on the calibrated site plan by dragging, by numeric inputs or by two-point alignment.
 * The resulting `site_transform` is what the massing generator uses to position each building.
 */
@Component({
  selector: 'uf-placement-page',
  imports: [
    FormsModule,
    DecimalPipe,
    MatButtonModule,
    MatButtonToggleModule,
    MatCheckboxModule,
    MatSlideToggleModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    RouterLink,
    NgIcon,
    PlanViewerComponent,
    PageHeaderComponent,
    StatusChipComponent,
    EmptyStateComponent,
    SectionCardComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="Site placement" icon="lucideMap" [facts]="facts()">
        <ng-container actions
          ><a mat-stroked-button routerLink="../massing"
            ><ng-icon name="lucideBox" /> 3D massing</a
          ></ng-container
        >
      </uf-page-header>
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }
      <p class="uf-hint">
        Put each building footprint on the site plan: position, rotation and scale. The placement
        feeds the portal site view and the 3D massing. A card with unsaved edits is marked until you
        save it.
      </p>
      <div class="uf-toolbar">
        <mat-form-field appearance="outline" class="uf-wide" subscriptSizing="dynamic">
          <mat-label>Site plan sheet</mat-label>
          <mat-select [value]="siteSheetId()" (valueChange)="chooseSiteSheet($event)">
            @for (s of siteSheets(); track s.sheet.id) {
              <mat-option [value]="s.sheet.id"
                >{{ s.doc.title }} · page {{ s.sheet.page_no }}
                @if (s.sheet.calibration_status === 'none') {
                  (not calibrated)
                }
              </mat-option>
            }
          </mat-select>
        </mat-form-field>
        @if (siteSheet(); as s) {
          @if (!metresPerPx()) {
            <a mat-stroked-button [routerLink]="['../sheets', s.id]"
              >Calibrate the site plan first</a
            >
          } @else {
            <span class="uf-muted">{{ 1 / metresPerPx()! | number: '1.0-0' }} px/m</span>
          }
        } @else {
          <span class="uf-hint"
            >Upload a document of kind "Site plan" under Documents and choose its sheet here.</span
          >
        }
        <mat-button-toggle-group
          [value]="mode()"
          (valueChange)="setMode($event)"
          hideSingleSelectionIndicator
          aria-label="Editor mode"
        >
          <mat-button-toggle value="view" title="Pan and zoom; click a footprint to select it"
            ><ng-icon name="lucideMousePointer" /> View</mat-button-toggle
          >
          <mat-button-toggle
            value="move"
            [disabled]="!metresPerPx()"
            title="Drag a footprint to move it"
            ><ng-icon name="lucideMove" /> Drag</mat-button-toggle
          >
          <mat-button-toggle
            value="pick"
            [disabled]="!metresPerPx() || !selected()"
            title="Click a footprint corner, then where it belongs; twice for rotation and scale"
            ><ng-icon name="lucideCompass" /> Two-point align</mat-button-toggle
          >
          <mat-button-toggle
            value="draw"
            [disabled]="!siteSheet() || !featureTarget()"
            title="Outline the selected site feature on the plan"
            ><ng-icon name="lucidePenTool" /> Draw feature</mat-button-toggle
          >
        </mat-button-toggle-group>
        @if (featureTarget(); as ft) {
          <span class="uf-chip uf-tone-warning"
            ><ng-icon name="lucidePenTool" />Outlining {{ featureName(ft) }}: click the corners,
            double-click to close</span
          >
          <button mat-button (click)="cancelDraw()">Cancel</button>
        }
      </div>
      @if (mode() === 'pick') {
        <div class="uf-card uf-form-row">
          <ng-icon name="lucideCompass" class="lead" />
          <span>
            @switch (picks().length) {
              @case (0) {
                Click a corner of the footprint…
              }
              @case (1) {
                …now click where that corner belongs on the site plan.
              }
              @case (2) {
                Translation applied. Click a second footprint corner to also set rotation and scale,
                or switch mode.
              }
              @case (3) {
                …and where that second corner belongs.
              }
            }
          </span>
          <button mat-stroked-button (click)="picks.set([])">Reset points</button>
        </div>
      }
      @if (!siteSheets().length) {
        <uf-empty-state
          icon="lucideMap"
          title="No site plan yet"
          text="Upload a site plan under Documents (kind: Site plan), calibrate its scale in the sheet editor, then choose it above."
        >
          <a mat-flat-button routerLink="../documents">Open Documents</a>
        </uf-empty-state>
      }
      @if (siteSheet(); as sheet) {
        <div class="viewer">
          <uf-plan-viewer
            [src]="sheet.raster_url ?? null"
            [width]="sheet.raster_width ?? 1000"
            [height]="sheet.raster_height ?? 700"
            [polygons]="polygons()"
            [marks]="picks()"
            [mode]="mode()"
            (polygonSelected)="selectedId.set($event)"
            (polygonMoved)="onMoved($event)"
            (pointPicked)="onPick($event)"
            (polygonDrawn)="onFeatureDrawn($event)"
          />
        </div>
      }

      <uf-section-card
        title="Site features"
        icon="lucideMap"
        [count]="features().length"
        summary="gardens, roads, parking, amenities drawn on the site plan; the portal shows them in 2D and 3D"
        storageKey="placement-features"
      >
        <p class="uf-hint">
          Add a feature, then "Draw on plan" and outline it on the site plan above. Public features
          appear on the buyer's site plan and as ground, roads and trees in the 3D view (ADR-0016).
        </p>
        <div class="uf-form-row">
          <mat-form-field appearance="outline" subscriptSizing="dynamic">
            <mat-label>Kind</mat-label>
            <mat-select [(ngModel)]="newFeature.kind" name="nfKind">
              @for (k of featureKinds; track k) {
                <mat-option [value]="k">{{ featureKindLabel(k) }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic">
            <mat-label>Name</mat-label>
            <input
              matInput
              [(ngModel)]="newFeature.name"
              name="nfName"
              placeholder="Courtyard garden"
              (keyup.enter)="addFeature()"
            />
          </mat-form-field>
          <button
            mat-flat-button
            [disabled]="busy() || !newFeature.name.trim()"
            (click)="addFeature()"
          >
            <ng-icon name="lucidePlus" /> Add feature
          </button>
        </div>
        @for (f of features(); track f.id) {
          <div class="feature" [class.is-target]="featureTarget() === f.id">
            <span class="swatch" [style.background]="featureColour(f.kind)"></span>
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="kind">
              <mat-select [value]="f.kind" (valueChange)="patchFeature(f, { kind: $event })">
                @for (k of featureKinds; track k) {
                  <mat-option [value]="k">{{ featureKindLabel(k) }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
            <strong>{{ f.name }}</strong>
            <span class="uf-muted uf-small">{{
              f.polygon?.['ring'] ? 'outlined' : 'not drawn yet'
            }}</span>
            <mat-slide-toggle
              [checked]="f.is_public"
              (change)="patchFeature(f, { is_public: $event.checked })"
              >Public</mat-slide-toggle
            >
            <span class="uf-spacer"></span>
            <button mat-button [disabled]="busy() || !siteSheet()" (click)="drawFeature(f)">
              <ng-icon name="lucidePenTool" /> {{ f.polygon?.['ring'] ? 'Redraw' : 'Draw on plan' }}
            </button>
            @if (f.polygon?.['ring']) {
              <button
                mat-button
                [disabled]="busy()"
                (click)="patchFeature(f, { clear_polygon: true })"
              >
                Clear outline
              </button>
            }
            <button mat-button [disabled]="busy()" (click)="removeFeature(f)">
              <ng-icon name="lucideTrash2" /> Delete
            </button>
          </div>
        } @empty {
          <p class="uf-muted uf-small">No site features yet.</p>
        }
      </uf-section-card>

      <uf-section-card
        title="Facade drawings on the 3D model"
        icon="lucideBuilding"
        [summary]="facadeSummary()"
        storageKey="placement-facades"
      >
        <p class="uf-hint">
          Each building has four sides. Pick the elevation sheet that shows a side, mark the facade
          on it, save, and the 3D massing is rebuilt with the drawing on that side. "Mirrored" flips
          the drawing when the sheet shows the facade from the other direction (ADR-0016).
        </p>
        @if (!elevationSheets().length) {
          <p class="uf-muted uf-small">
            No elevation sheets yet: upload the facades under Documents (kind: Elevations).
          </p>
        }
        @for (f of footprints(); track f.building_id) {
          @if (f.sides?.length) {
            <div class="facades">
              <strong>{{ f.code }} {{ f.name ?? '' }}</strong>
              <table class="uf-plain">
                <thead>
                  <tr>
                    <th>Side</th>
                    <th>Length</th>
                    <th>Elevation sheet</th>
                    <th>Facade area</th>
                    <th>Mirrored</th>
                  </tr>
                </thead>
                <tbody>
                  @for (sd of f.sides; track sideIdx(sd)) {
                    <tr [class.is-target]="isFacadeTarget(f.building_id, sideIdx(sd))">
                      <td>
                        {{ sideLabel(sideIdx(sd)) }}
                        <span class="uf-muted">· {{ sidePos(sd) }} edge on the plan</span>
                      </td>
                      <td class="uf-num">{{ sideLen(sd) }} m</td>
                      <td>
                        <mat-form-field
                          appearance="outline"
                          subscriptSizing="dynamic"
                          class="sheet"
                        >
                          <mat-select
                            [value]="facadeOf(f.building_id, sideIdx(sd))?.sheet_id ?? null"
                            (valueChange)="setFacadeSheet(f.building_id, sideIdx(sd), $event)"
                          >
                            <mat-option [value]="null">— none —</mat-option>
                            @for (e of elevationSheets(); track e.sheet.id) {
                              <mat-option [value]="e.sheet.id"
                                >{{ e.doc.title }} · page {{ e.sheet.page_no }}</mat-option
                              >
                            }
                          </mat-select>
                        </mat-form-field>
                      </td>
                      <td>
                        @if (facadeOf(f.building_id, sideIdx(sd)); as a) {
                          <button
                            mat-button
                            [disabled]="busy()"
                            (click)="markFacade(f.building_id, sideIdx(sd))"
                          >
                            <ng-icon name="lucidePenTool" />
                            {{ a.region ? 'Re-mark' : 'Mark area' }}
                          </button>
                          @if (!a.region) {
                            <span class="uf-muted uf-small">whole sheet</span>
                          }
                        }
                      </td>
                      <td>
                        @if (facadeOf(f.building_id, sideIdx(sd)); as a) {
                          <mat-checkbox
                            [checked]="!!a.flip"
                            (change)="setFacadeFlip(f.building_id, sideIdx(sd), $event.checked)"
                          />
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        }
        @if (facadeTarget(); as ft) {
          <div class="uf-card uf-stack">
            <div class="uf-form-row">
              <ng-icon name="lucidePenTool" class="lead" />
              <span
                >Outline the facade of <strong>{{ sideLabel(ft.side) }}</strong> on this sheet:
                click the corners of the drawn facade (without dimensions and title block),
                double-click to close.</span
              >
              <span class="uf-spacer"></span>
              <button mat-button (click)="facadeTarget.set(null)">Cancel</button>
            </div>
            @if (facadeSheet(); as fs) {
              <div class="viewer viewer--facade">
                <uf-plan-viewer
                  [src]="fs.raster_url ?? null"
                  [width]="fs.raster_width ?? 1000"
                  [height]="fs.raster_height ?? 700"
                  [polygons]="facadePolygons()"
                  mode="draw"
                  (polygonDrawn)="onFacadeDrawn($event)"
                />
              </div>
            }
          </div>
        }
        <div class="uf-actions">
          <button mat-flat-button [disabled]="busy() || !facadesDirty()" (click)="saveFacades()">
            Save facades and rebuild 3D
          </button>
          @if (facadesDirty()) {
            <span class="uf-hint">unsaved facade changes</span>
          }
        </div>
      </uf-section-card>
      <div class="uf-grid3">
        @for (f of footprints(); track f.building_id) {
          <div
            class="uf-card fp"
            [class.is-selected]="f.building_id === selectedId()"
            [class.uf-changed]="dirty()[f.building_id]"
            (click)="selectedId.set(f.building_id)"
          >
            <div class="fp__head">
              <strong>{{ f.code }} {{ f.name ?? '' }}</strong>
              <uf-status-chip domain="building.placement" [value]="f.placement_status" />
            </div>
            <div class="uf-muted uf-small">
              {{ f.floors }} floors · {{ f.height_m }} m
              @if (f.source_floor_level !== null) {
                · footprint from level {{ f.source_floor_level }}
              } @else {
                · no calibrated boundaries yet
              }
            </div>
            <div class="uf-form-row">
              <mat-form-field appearance="outline" class="uf-num" subscriptSizing="dynamic"
                ><mat-label>x (m)</mat-label
                ><input
                  matInput
                  type="number"
                  step="0.1"
                  [ngModel]="tf(f).tx"
                  (ngModelChange)="edit(f, 'tx', $event)"
                  [name]="'tx' + f.building_id"
              /></mat-form-field>
              <mat-form-field appearance="outline" class="uf-num" subscriptSizing="dynamic"
                ><mat-label>y (m)</mat-label
                ><input
                  matInput
                  type="number"
                  step="0.1"
                  [ngModel]="tf(f).ty"
                  (ngModelChange)="edit(f, 'ty', $event)"
                  [name]="'ty' + f.building_id"
              /></mat-form-field>
              <mat-form-field appearance="outline" class="uf-num" subscriptSizing="dynamic"
                ><mat-label>rotation (°)</mat-label
                ><input
                  matInput
                  type="number"
                  step="1"
                  [ngModel]="tf(f).rotation_deg"
                  (ngModelChange)="edit(f, 'rotation_deg', $event)"
                  [name]="'r' + f.building_id"
              /></mat-form-field>
              <mat-form-field appearance="outline" class="uf-num" subscriptSizing="dynamic"
                ><mat-label>scale</mat-label
                ><input
                  matInput
                  type="number"
                  step="0.01"
                  [ngModel]="tf(f).scale"
                  (ngModelChange)="edit(f, 'scale', $event)"
                  [name]="'s' + f.building_id"
              /></mat-form-field>
              <mat-form-field appearance="outline" class="uf-num" subscriptSizing="dynamic"
                ><mat-label>elevation (m)</mat-label
                ><input
                  matInput
                  type="number"
                  step="0.1"
                  [ngModel]="tf(f).elevation"
                  (ngModelChange)="edit(f, 'elevation', $event)"
                  [name]="'e' + f.building_id"
              /></mat-form-field>
            </div>
            <div class="uf-actions">
              <button
                mat-stroked-button
                [disabled]="busy() || !dirty()[f.building_id]"
                (click)="save(f); $event.stopPropagation()"
              >
                Save
              </button>
              <button
                mat-flat-button
                [disabled]="busy() || f.placement_status === 'confirmed' || dirty()[f.building_id]"
                (click)="confirm(f); $event.stopPropagation()"
              >
                <ng-icon name="lucideCircleCheck" /> Confirm placement
              </button>
              @if (dirty()[f.building_id]) {
                <span class="uf-hint">unsaved edits</span>
              }
            </div>
          </div>
        } @empty {
          <uf-empty-state
            icon="lucideBuilding2"
            title="No footprints yet"
            text="A footprint comes from the lowest mapped and calibrated floor of a building. Map a floor plan first."
            [compact]="true"
          />
        }
      </div>
    </div>
  `,
  styles: `
    .uf-wide {
      min-width: 300px;
    }
    .uf-num {
      width: 120px;
    }
    .lead {
      color: var(--uf-primary);
      font-size: 1.25rem;
    }
    .viewer {
      background: var(--uf-surface);
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius);
      overflow: hidden;
    }
    uf-plan-viewer {
      display: block;
      --uf-plan-height: auto;
      --uf-plan-max-height: 75vh;
      --uf-plan-min-height: 320px;
    }
    .feature {
      display: flex;
      gap: 0.5rem;
      align-items: center;
      flex-wrap: wrap;
      padding: 0.3rem 0.5rem;
      border-radius: 6px;
    }
    .feature.is-target {
      background: var(--uf-tone-warning-bg);
    }
    .feature .kind {
      width: 10rem;
    }
    .swatch {
      width: 0.9rem;
      height: 0.9rem;
      border-radius: 3px;
      border: 1px solid rgba(0, 0, 0, 0.15);
    }
    .facades {
      display: grid;
      gap: 0.35rem;
    }
    .facades .sheet {
      min-width: 16rem;
    }
    .facades tr.is-target td {
      background: var(--uf-tone-warning-bg);
    }
    .viewer--facade uf-plan-viewer {
      --uf-plan-max-height: 60vh;
    }
    .fp {
      display: grid;
      gap: 0.5rem;
      cursor: pointer;
      border-radius: var(--uf-radius);
    }
    .fp.is-selected {
      outline: 2px solid var(--uf-primary);
    }
    .fp__head {
      display: flex;
      justify-content: space-between;
      gap: 0.5rem;
      align-items: center;
    }
    mat-button-toggle ng-icon,
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class PlacementPage {
  private readonly api = inject(UnitformaApi);
  private readonly toast = inject(ToastService);
  private readonly dialogs = inject(DialogsService);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly project = signal<ProjectOut | null>(null);
  readonly facts = computed<HeaderFact[]>(() => {
    const f = this.footprints();
    return [
      { label: 'Buildings', value: f.length },
      {
        domain: 'building.placement',
        status: 'confirmed',
        value: `${f.filter((x) => x.placement_status === 'confirmed').length} placed`,
      },
      {
        domain: 'building.placement',
        status: 'unplaced',
        value: `${f.filter((x) => x.placement_status === 'unplaced').length} not placed`,
      },
      ...(this.siteSheet()
        ? [{ domain: 'sheet.calibration' as const, status: this.siteSheet()!.calibration_status }]
        : []),
    ];
  });
  readonly docs = signal<DocumentOut[]>([]);
  readonly siteSheets = signal<{ doc: DocumentOut; sheet: SheetOut }[]>([]);
  readonly siteSheet = signal<SheetOut | null>(null);
  readonly footprints = signal<FootprintOut[]>([]);
  readonly edits = signal<Record<string, SiteTransform>>({});
  readonly dirty = signal<Record<string, boolean>>({});
  readonly selectedId = signal<string | null>(null);
  readonly mode = signal<PlanMode>('view');
  readonly picks = signal<Point[]>([]);
  // site features (ADR-0016 Decision 3)
  readonly features = signal<SiteFeatureOut[]>([]);
  readonly featureTarget = signal<string | null>(null);
  readonly featureKinds = FEATURE_KINDS;
  newFeature: { kind: string; name: string } = { kind: 'garden', name: '' };
  // facade drawings (ADR-0016 Decision 2)
  readonly elevationSheets = signal<{ doc: DocumentOut; sheet: SheetOut }[]>([]);
  readonly facades = signal<Record<string, FacadeAssign[]>>({});
  readonly facadesSaved = signal('');
  readonly facadeTarget = signal<{ building_id: string; side: number } | null>(null);
  readonly facadeSheet = signal<SheetOut | null>(null);
  readonly facadesDirty = computed(() => JSON.stringify(this.facades()) !== this.facadesSaved());
  readonly facadePolygons = computed<PlanPolygon[]>(() => {
    const t = this.facadeTarget();
    const a = t ? this.facadeOf(t.building_id, t.side) : null;
    const ring = a?.region?.ring as Ring | undefined;
    return ring ? [{ id: 'facade', ring, label: 'facade', kind: 'region' as const }] : [];
  });
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  readonly siteSheetId = computed(
    () => (this.project()?.site_frame as { sheet_id?: string } | undefined)?.sheet_id ?? null,
  );
  readonly metresPerPx = computed(() => {
    const s = this.siteSheet();
    const c = s?.calibration as { m_per_px?: number } | null | undefined;
    return c?.m_per_px && s?.raster_width ? c.m_per_px : null;
  });
  readonly selected = computed(
    () => this.footprints().find((f) => f.building_id === this.selectedId()) ?? null,
  );
  readonly polygons = computed<PlanPolygon[]>(() => {
    const m = this.metresPerPx();
    const s = this.siteSheet();
    if (!m || !s?.raster_width || !s.raster_height) return [];
    const feats: PlanPolygon[] = this.features()
      .filter((f) => Array.isArray(f.polygon?.['ring']))
      .map((f) => ({
        id: 'feature:' + f.id,
        ring: f.polygon!['ring'] as Ring,
        label: f.name,
        fill: FEATURE_COLOURS[f.kind] + '55',
        stroke: FEATURE_COLOURS[f.kind],
        selected: this.featureTarget() === f.id,
      }));
    return feats.concat(
      this.footprints()
        .filter((f) => f.ring_m)
        .map((f) => ({
          id: f.building_id,
          ring: (f.ring_m as Ring).map((p) => this.toNorm(apply(this.tf(f), p as Pt))),
          label: f.code,
          kind: 'footprint' as const,
          selected: f.building_id === this.selectedId(),
        })),
    );
  });

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  tf(f: FootprintOut): SiteTransform {
    const e = this.edits()[f.building_id];
    if (e) return e;
    const t = (f.site_transform ?? {}) as Partial<SiteTransform>;
    return {
      tx: t.tx ?? 0,
      ty: t.ty ?? 0,
      rotation_deg: t.rotation_deg ?? 0,
      scale: t.scale ?? 1,
      elevation: t.elevation ?? 0,
    };
  }

  private toNorm(p: Pt): Point {
    const s = this.siteSheet()!;
    const m = this.metresPerPx()!;
    return [p[0] / (m * s.raster_width!), p[1] / (m * s.raster_height!)];
  }

  private toMetres(p: Point): Pt {
    const s = this.siteSheet()!;
    const m = this.metresPerPx()!;
    return [p[0] * m * s.raster_width!, p[1] * m * s.raster_height!];
  }

  async load(): Promise<void> {
    try {
      const [p, d, fp] = await Promise.all([
        this.api.getProject(this.tenantId(), this.projectId()),
        this.api.listDocuments(this.tenantId(), this.projectId()),
        this.api.listFootprints(this.tenantId(), this.projectId()),
      ]);
      this.project.set(p);
      this.docs.set(d);
      this.footprints.set(fp);
      this.edits.set({});
      this.dirty.set({});
      const fac: Record<string, FacadeAssign[]> = {};
      for (const f of fp) fac[f.building_id] = (f.facades ?? []) as unknown as FacadeAssign[];
      this.facades.set(fac);
      this.facadesSaved.set(JSON.stringify(fac));
      this.features.set(await this.api.listSiteFeatures(this.tenantId(), this.projectId()));
      const elevations = d.filter((x) => x.kind === 'elevation' && x.current_revision_id);
      const elists = await Promise.all(
        elevations.map((x) =>
          this.api
            .listSheets(this.tenantId(), x.current_revision_id!)
            .catch(() => [] as SheetOut[]),
        ),
      );
      this.elevationSheets.set(
        elevations.flatMap((doc, i) =>
          elists[i].filter((sh) => sh.raster_url).map((sheet) => ({ doc, sheet })),
        ),
      );
      const sitePlans = d.filter((x) => x.kind === 'site_plan' && x.current_revision_id);
      const lists = await Promise.all(
        sitePlans.map((x) =>
          this.api
            .listSheets(this.tenantId(), x.current_revision_id!)
            .catch(() => [] as SheetOut[]),
        ),
      );
      this.siteSheets.set(sitePlans.flatMap((doc, i) => lists[i].map((sheet) => ({ doc, sheet }))));
      const id = this.siteSheetId();
      this.siteSheet.set(
        id ? await this.api.getSheet(this.tenantId(), id).catch(() => null) : null,
      );
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  async chooseSiteSheet(sheetId: string): Promise<void> {
    const p = this.project();
    if (!p) return;
    await this.run(() =>
      this.api.updateProject(this.tenantId(), this.projectId(), {
        site_frame: { ...(p.site_frame ?? {}), sheet_id: sheetId, north_deg: 0 },
        version: p.version,
      }),
    );
  }

  setMode(m: PlanMode): void {
    this.mode.set(m);
    this.picks.set([]);
    if (m !== 'draw') this.featureTarget.set(null);
  }

  // --- site features
  featureKindLabel(k: string): string {
    return FEATURE_LABELS[k] ?? k;
  }

  featureColour(k: string): string {
    return FEATURE_COLOURS[k] ?? FEATURE_COLOURS['other'];
  }

  featureName(id: string): string {
    return this.features().find((f) => f.id === id)?.name ?? 'feature';
  }

  addFeature(): Promise<void> {
    const name = this.newFeature.name.trim();
    if (!name) return Promise.resolve();
    return this.run(async () => {
      const f = await this.api.createSiteFeature(this.tenantId(), this.projectId(), {
        kind: this.newFeature.kind as SiteFeatureOut['kind'] & string,
        name,
        polygon: null,
        is_public: true,
        sort_order: this.features().length,
      } as never);
      this.newFeature = { kind: this.newFeature.kind, name: '' };
      this.toast.ok(`${f.name} added; draw it on the plan`);
      this.drawFeature(f);
    });
  }

  patchFeature(f: SiteFeatureOut, body: SiteFeatureUpdate): Promise<void> {
    return this.run(async () => {
      await this.api.updateSiteFeature(this.tenantId(), f.id, body);
    });
  }

  async removeFeature(f: SiteFeatureOut): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: `Delete ${f.name}?`,
      message: 'The feature leaves the site plan and the 3D view with the next publication.',
      confirmLabel: 'Delete',
      tone: 'bad',
    });
    if (!ok) return;
    return this.run(async () => {
      await this.api.deleteSiteFeature(this.tenantId(), f.id);
      this.toast.ok(`${f.name} deleted`);
    });
  }

  drawFeature(f: SiteFeatureOut): void {
    this.featureTarget.set(f.id);
    this.mode.set('draw');
    this.picks.set([]);
  }

  cancelDraw(): void {
    this.featureTarget.set(null);
    this.mode.set('view');
  }

  /** A closed outline on the site plan becomes the targeted feature's polygon (sheet-normalised). */
  onFeatureDrawn(ring: Ring): Promise<void> {
    const id = this.featureTarget();
    if (!id) return Promise.resolve();
    this.featureTarget.set(null);
    this.mode.set('view');
    return this.run(async () => {
      await this.api.updateSiteFeature(this.tenantId(), id, { polygon: { ring } });
      this.toast.ok(`${this.featureName(id)} outlined`);
    });
  }

  // --- facades
  sideIdx(sd: Record<string, unknown>): number {
    return Number(sd['index'] ?? 0);
  }

  sideLen(sd: Record<string, unknown>): number {
    return Number(sd['length_m'] ?? 0);
  }

  /** Where the side sits on the floor plan, from its outward normal (clockwise sides, y down). */
  sidePos(sd: Record<string, unknown>): string {
    const [ax, ay] = (sd['a'] as number[]) ?? [0, 0];
    const [bx, by] = (sd['b'] as number[]) ?? [0, 0];
    const nx = by - ay;
    const ny = -(bx - ax);
    if (Math.abs(nx) >= Math.abs(ny)) return nx > 0 ? 'right' : 'left';
    return ny > 0 ? 'bottom' : 'top';
  }

  sideLabel(i: number): string {
    return ['Side 1', 'Side 2', 'Side 3', 'Side 4'][i] ?? `Side ${i + 1}`;
  }

  facadeOf(buildingId: string, side: number): FacadeAssign | null {
    return (this.facades()[buildingId] ?? []).find((a) => a.side === side) ?? null;
  }

  isFacadeTarget(buildingId: string, side: number): boolean {
    const t = this.facadeTarget();
    return !!t && t.building_id === buildingId && t.side === side;
  }

  facadeSummary(): string {
    const n = Object.values(this.facades()).reduce(
      (a, l) => a + l.filter((x) => x.sheet_id).length,
      0,
    );
    return n ? `${n} side${n === 1 ? '' : 's'} assigned` : 'no facade drawings assigned';
  }

  private setFacade(buildingId: string, side: number, patch: Partial<FacadeAssign> | null): void {
    this.facades.update((all) => {
      const list = (all[buildingId] ?? []).filter((a) => a.side !== side);
      const cur = this.facadeOf(buildingId, side);
      if (patch !== null)
        list.push({ side, sheet_id: '', region: null, flip: false, ...(cur ?? {}), ...patch });
      return { ...all, [buildingId]: list.sort((a, b) => a.side - b.side) };
    });
  }

  setFacadeSheet(buildingId: string, side: number, sheetId: string | null): void {
    if (!sheetId) {
      this.setFacade(buildingId, side, null);
      if (this.isFacadeTarget(buildingId, side)) this.facadeTarget.set(null);
      return;
    }
    const cur = this.facadeOf(buildingId, side);
    this.setFacade(buildingId, side, {
      sheet_id: sheetId,
      region: cur?.sheet_id === sheetId ? cur.region : null,
    });
  }

  setFacadeFlip(buildingId: string, side: number, flip: boolean): void {
    this.setFacade(buildingId, side, { flip });
  }

  async markFacade(buildingId: string, side: number): Promise<void> {
    const a = this.facadeOf(buildingId, side);
    if (!a?.sheet_id) return;
    const sheet = this.elevationSheets().find((e) => e.sheet.id === a.sheet_id)?.sheet ?? null;
    this.facadeSheet.set(sheet);
    this.facadeTarget.set({ building_id: buildingId, side });
  }

  onFacadeDrawn(ring: Ring): void {
    const t = this.facadeTarget();
    if (!t) return;
    this.setFacade(t.building_id, t.side, { region: { ring } });
    this.facadeTarget.set(null);
    this.toast.ok(`${this.sideLabel(t.side)} marked; save to rebuild the 3D model`);
  }

  /** Facade choices are stored on each building (ADR-0016 E3); saving queues a massing rebuild. */
  saveFacades(): Promise<void> {
    const fps = this.footprints();
    return this.run(async () => {
      for (const f of fps) {
        const kept = (this.facades()[f.building_id] ?? []).filter((a) => a.sheet_id);
        await this.api.updateBuilding(this.tenantId(), f.building_id, {
          facades: kept.map((a) => ({
            side: a.side,
            sheet_id: a.sheet_id,
            region: a.region,
            flip: !!a.flip,
          })),
          version: f.version,
        });
      }
      await this.api.regenerateMassing(this.tenantId(), this.projectId());
      this.toast.ok('Facades saved; the 3D model is being rebuilt');
      await this.load();
    });
  }

  edit(f: FootprintOut, key: keyof SiteTransform, value: number | string): void {
    const t = { ...this.tf(f), [key]: Number(value) };
    this.edits.update((e) => ({ ...e, [f.building_id]: t }));
    this.dirty.update((d) => ({ ...d, [f.building_id]: true }));
  }

  onMoved(mv: PolygonMove): void {
    const f = this.footprints().find((x) => x.building_id === mv.id);
    if (!f) return;
    const s = this.siteSheet()!;
    const m = this.metresPerPx()!;
    const t = this.tf(f);
    this.edits.update((e) => ({
      ...e,
      [f.building_id]: {
        ...t,
        tx: round(t.tx! + mv.dx * s.raster_width! * m),
        ty: round(t.ty! + mv.dy * s.raster_height! * m),
      },
    }));
    this.dirty.update((d) => ({ ...d, [f.building_id]: true }));
  }

  /** Two-point alignment: pairs (footprint corner → target). One pair translates; two pairs also rotate and scale. */
  onPick(pt: Point): void {
    const f = this.selected();
    if (!f) return;
    const picks = [...this.picks(), pt];
    this.picks.set(picks);
    if (picks.length === 2 || picks.length === 4) {
      const t = this.tf(f);
      const pairs: [Pt, Pt][] = [];
      for (let i = 0; i + 1 < picks.length; i += 2)
        pairs.push([invert(t, this.toMetres(picks[i])), this.toMetres(picks[i + 1])]);
      let next: SiteTransform;
      if (pairs.length === 1) {
        const [l, target] = pairs[0];
        const now = apply(t, l);
        next = {
          ...t,
          tx: round(t.tx! + target[0] - now[0]),
          ty: round(t.ty! + target[1] - now[1]),
        };
      } else {
        const [[l1, b1], [l2, b2]] = pairs;
        const dl: Pt = [l2[0] - l1[0], l2[1] - l1[1]];
        const db: Pt = [b2[0] - b1[0], b2[1] - b1[1]];
        const lenL = Math.hypot(dl[0], dl[1]);
        const lenB = Math.hypot(db[0], db[1]);
        if (lenL < 1e-6 || lenB < 1e-6) return;
        const scale = lenB / lenL;
        const rot = Math.atan2(db[1], db[0]) - Math.atan2(dl[1], dl[0]);
        const c = Math.cos(rot);
        const s = Math.sin(rot);
        next = {
          ...t,
          scale: round(scale, 4),
          rotation_deg: round((rot * 180) / Math.PI, 2),
          tx: round(b1[0] - scale * (c * l1[0] - s * l1[1])),
          ty: round(b1[1] - scale * (s * l1[0] + c * l1[1])),
        };
        this.picks.set([]);
      }
      this.edits.update((e) => ({ ...e, [f.building_id]: next }));
      this.dirty.update((d) => ({ ...d, [f.building_id]: true }));
    }
  }

  save(f: FootprintOut): Promise<void> {
    return this.run(async () => {
      await this.api.updateBuilding(this.tenantId(), f.building_id, {
        site_transform: this.tf(f),
        placement_status: 'draft',
        version: f.version,
      });
      this.toast.ok(`${f.code} placement saved as draft`);
    });
  }

  confirm(f: FootprintOut): Promise<void> {
    return this.run(async () => {
      await this.api.updateBuilding(this.tenantId(), f.building_id, {
        placement_status: 'confirmed',
        version: f.version,
      });
      this.toast.ok(`${f.code} placement confirmed`);
    });
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

function round(v: number, digits = 3): number {
  const k = 10 ** digits;
  return Math.round(v * k) / k;
}
