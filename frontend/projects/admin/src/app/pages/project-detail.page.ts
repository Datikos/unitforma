import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  BuildingOut,
  BuildingUpdate,
  ElevationCandidateOut,
  FloorIn,
  FloorOut,
  BlockProposalOut,
  FloorProposalOut,
  ProjectOut,
  ProposedFloorOut,
  RegulatoryImportOut,
  UnitformaApi,
  problemMessage,
} from 'api-client';
import {
  EmptyStateComponent,
  Fact,
  FactsComponent,
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
  dayOf,
  whenShort,
} from 'ui';
import { ProjectContext } from '../core/project-context';

interface PortalFields {
  construction_status: string;
  completion: string;
  terms: string;
  elevation_sheet_id: string;
}
import { DialogsService } from '../ui/dialogs.service';
import { ToastService } from '../ui/toast.service';

/** Project overview: header facts, permit (ADR-0007), structure of buildings and floors (plan §3.5). */
@Component({
  selector: 'uf-project-detail-page',
  imports: [
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatButtonModule,
    MatCheckboxModule,
    RouterLink,
    NgIcon,
    PageHeaderComponent,
    SectionCardComponent,
    StatusChipComponent,
    FactsComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      @let p = project();
      <uf-page-header
        [title]="p?.name ?? 'Project'"
        icon="lucideLayoutDashboard"
        [kicker]="p ? p.slug : null"
        [facts]="facts()"
      >
        <ng-container actions>
          @if (p) {
            <button mat-stroked-button [disabled]="busy()" (click)="toggleArchive(p)">
              <ng-icon
                [name]="p.status === 'archived' ? 'lucideArchiveRestore' : 'lucideArchive'"
              />
              {{ p.status === 'archived' ? 'Reactivate' : 'Archive' }}
            </button>
          }
          <a mat-stroked-button routerLink="documents"
            ><ng-icon name="lucideFileText" /> Documents</a
          >
          <a mat-stroked-button routerLink="inventory"><ng-icon name="lucideTable" /> Inventory</a>
          <a mat-flat-button routerLink="publish"><ng-icon name="lucideRocket" /> Publish</a>
        </ng-container>
      </uf-page-header>
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }

      <div class="uf-stats">
        <div class="uf-stat">
          <span class="uf-stat__label">Buildings</span
          ><span class="uf-stat__value">{{ realBuildings().length }}</span
          ><span class="uf-stat__hint">{{ placedCount() }} placed on the site plan</span>
        </div>
        <div class="uf-stat">
          <span class="uf-stat__label">Floors</span
          ><span class="uf-stat__value">{{ floorCount() }}</span
          ><span class="uf-stat__hint">across all buildings</span>
        </div>
        <div class="uf-stat">
          <span class="uf-stat__label">Currency</span
          ><span class="uf-stat__value">{{ p?.currency ?? '—' }}</span
          ><span class="uf-stat__hint">code pattern {{ p?.code_pattern ?? '—' }}</span>
        </div>
      </div>

      @if (permit(); as r) {
        <uf-section-card
          title="Building permit"
          icon="lucideScrollText"
          [summary]="(r['application_no'] || r['external_id']) + ' · ' + (r['status'] || '')"
          storageKey="project-permit"
        >
          <div actions>
            @if (latestImport(); as j) {
              @if (importStalled()) {
                <uf-status-chip
                  domain="regulatory_import"
                  value="failed"
                  label="Import stalled"
                  tooltip="The worker did not report back; Check registry starts a fresh import"
                />
              } @else {
                <uf-status-chip domain="regulatory_import" [value]="j.status" />
              }
            }
          </div>
          <uf-facts [facts]="permitFacts(r)" />
          @if (latestImport(); as j) {
            <p class="uf-small">
              <span class="uf-muted">Last import {{ when(j.started_at || j.created_at) }}</span>
              @if (j.status === 'done') {
                · {{ count(j, 'imported') }} files imported, {{ count(j, 'existing') }} already
                present, {{ count(j, 'skipped') }} skipped, {{ count(j, 'failed') }} failed
              }
              @if (j.error) {
                <span class="uf-error"> · {{ j.error }}</span>
              }
            </p>
            @if (count(j, 'failed')) {
              <ul class="uf-muted uf-small">
                @for (f of failed(j); track f['attached_file_id']) {
                  <li>{{ f['file_name'] }}: {{ f['error'] }}</li>
                }
              </ul>
            }
            @if (importStalled()) {
              <p class="uf-hint">
                This import has been "running" for more than 20 minutes: the worker never reported
                back (a restart or a crash). "Check registry for new files" closes it and starts a
                fresh one; files already here are kept.
              </p>
            } @else if (j.status === 'importing') {
              <p class="uf-hint">
                The worker is downloading the drawings. They appear under Documents within a minute
                and propose floors from their level markers.
              </p>
            }
          }
          @if (heights(); as h) {
            <p class="uf-hint">
              Permit heights: {{ h.above ?? '—' }} m above 0.00, {{ h.below ?? '—' }} m below. Use
              them when you generate floors below (for example 4 floors of about 3.5 m above ground
              and one basement).
            </p>
          }
          <div class="uf-actions">
            <a mat-stroked-button routerLink="documents"
              ><ng-icon name="lucideFileText" /> Documents</a
            >
            <button
              mat-stroked-button
              [disabled]="busy() || importRunning()"
              (click)="refreshPermit()"
            >
              <ng-icon name="lucideRefreshCw" /> Check registry for new files
            </button>
            <a mat-button [href]="str(r['public_page'])" target="_blank" rel="noopener"
              ><ng-icon name="lucideExternalLink" /> Registry page</a
            >
            <span class="uf-hint"
              >Fetches the permit again and imports only files that are not here yet.</span
            >
          </div>
        </uf-section-card>
      }

      <uf-section-card
        title="Add building"
        icon="lucidePlus"
        summary="code and optional name"
        storageKey="project-add-building"
        [open]="realBuildings().length === 0"
      >
        <div class="uf-form-row">
          <mat-form-field appearance="outline" subscriptSizing="dynamic" class="code"
            ><mat-label>Code</mat-label
            ><input
              matInput
              [(ngModel)]="code"
              name="code"
              placeholder="A"
              (keyup.enter)="addBuilding()"
          /></mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Name</mat-label
            ><input
              matInput
              [(ngModel)]="bname"
              name="bname"
              placeholder="Block A"
              (keyup.enter)="addBuilding()"
          /></mat-form-field>
          <button mat-flat-button [disabled]="busy() || !code.trim()" (click)="addBuilding()">
            Add
          </button>
          <span class="uf-hint"
            >The code appears in unit codes ({{ p?.code_pattern ?? 'A-3-01' }}) and on the
            portal.</span
          >
        </div>
      </uf-section-card>

      @for (b of realBuildings(); track b.id) {
        <uf-section-card
          [title]="b.code + (b.name ? ' · ' + b.name : '')"
          icon="lucideBuilding2"
          [count]="floorsOf(b).length"
          [summary]="floorSummary(b)"
          [storageKey]="'project-building-' + b.id"
        >
          <div actions class="uf-actions">
            <uf-status-chip domain="building.placement" [value]="b.placement_status" />
            <a mat-button routerLink="placement"><ng-icon name="lucideMap" /> Place</a>
            <button mat-button [disabled]="busy()" (click)="deleteBuilding(b)">
              <ng-icon name="lucideTrash2" /> Delete
            </button>
          </div>
          @if (proposalFor(b); as pr) {
            @if (pr.split_level && !asOneBuilding()[b.id]) {
              <div class="proposal">
                <p class="uf-small">
                  <strong>Split-level blocks: {{ blocksOf(pr).length }}</strong> drawn side by side
                  on {{ pr.sheets_with_markers }} sheets.
                  <span class="uf-muted"
                    >Each column of level markers on the plan sheets is a block with its own
                    storeys. Blocks become separate buildings, as the sheets' regions and the 3D
                    model expect; edit the codes first. The sheets then get one floor suggestion per
                    block.</span
                  >
                  <a class="uf-link" (click)="setOneBuilding(b, true)"
                    >Treat as one building instead</a
                  >
                </p>
                <div class="blocks">
                  @for (blk of blocksOf(pr); track blk.code) {
                    <div class="block">
                      <mat-form-field appearance="outline" subscriptSizing="dynamic" class="code">
                        <mat-label>Building code</mat-label>
                        <input
                          matInput
                          [ngModel]="blockCode(b, blk)"
                          (ngModelChange)="setBlockCode(b, blk, $event)"
                          [name]="'blk-' + b.id + blk.code"
                        />
                      </mat-form-field>
                      <span class="uf-hint"
                        >column at {{ (blk.column_x * 100).toFixed(0) }} % of the sheet width ·
                        {{ blk.sheets }} sheets</span
                      >
                      <table class="uf-plain floors">
                        <thead>
                          <tr>
                            <th>Level</th>
                            <th>Name</th>
                            <th class="uf-num">Elevation (m)</th>
                            <th class="uf-num">Height (m)</th>
                          </tr>
                        </thead>
                        <tbody>
                          @for (f of blk.floors; track f.level) {
                            <tr>
                              <td class="uf-num">{{ f.level }}</td>
                              <td>{{ f.display_name }}</td>
                              <td class="uf-num">
                                {{ f.elevation_m >= 0 ? '+' : '' }}{{ f.elevation_m }}
                              </td>
                              <td class="uf-num">{{ f.height_m ?? '—' }}</td>
                            </tr>
                          }
                        </tbody>
                      </table>
                    </div>
                  }
                </div>
                <div class="uf-actions">
                  <mat-checkbox
                    [checked]="removeSource()[b.id] ?? true"
                    (change)="setRemoveSource(b, $event.checked)"
                    [disabled]="busy()"
                  >
                    Remove building {{ b.code }} afterwards (only possible while it has no units)
                  </mat-checkbox>
                  <button mat-flat-button [disabled]="busy()" (click)="acceptBlocks(b, pr)">
                    <ng-icon name="lucideBuilding2" /> Create {{ blocksOf(pr).length }} buildings
                    with their floors
                  </button>
                </div>
              </div>
            } @else {
              <div class="proposal">
                @if (pr.split_level) {
                  <p class="uf-small">
                    <a class="uf-link" (click)="setOneBuilding(b, false)"
                      >Back to {{ blocksOf(pr).length }} blocks</a
                    >
                  </p>
                }
                <p class="uf-small">
                  <strong>Floors proposed from the drawings</strong> ·
                  {{ pr.floors.length }} storeys on {{ pr.sheets_with_markers }} sheets.
                  <span class="uf-muted"
                    >Level markers such as +3.20 on the plan sheets, one storey per marker height;
                    heights are the distance to the next storey
                    @if (pr.roof['elevation_m']) {
                      , the top one to the roof at +{{ pr.roof['elevation_m'] }}
                    }
                    . Existing floors are kept; "fills elevation" completes a floor you generated.
                    Three markers 1 m apart on one sheet are split-level blocks drawn side by side:
                    accept only one block's storeys here, or model the blocks as separate
                    buildings.</span
                  >
                </p>
                <table class="uf-plain floors">
                  <thead>
                    <tr>
                      <th></th>
                      <th>Level</th>
                      <th>Name</th>
                      <th class="uf-num">Elevation (m)</th>
                      <th class="uf-num">Height (m)</th>
                      <th>Status</th>
                      <th class="uf-num">Sheets</th>
                    </tr>
                  </thead>
                  <tbody>
                    @for (f of pr.floors; track f.level) {
                      <tr [class.uf-muted]="f.status === 'existing'">
                        <td>
                          <mat-checkbox
                            [checked]="isPicked(b, f)"
                            [disabled]="f.status === 'existing' || busy()"
                            (change)="togglePick(b, f, $event.checked)"
                          />
                        </td>
                        <td class="uf-num">{{ f.level }}</td>
                        <td>{{ f.display_name }}</td>
                        <td class="uf-num">
                          {{ f.elevation_m >= 0 ? '+' : '' }}{{ f.elevation_m }}
                        </td>
                        <td class="uf-num">{{ f.height_m ?? '—' }}</td>
                        <td>
                          <span
                            class="uf-chip"
                            [class.uf-tone-good]="f.status === 'new'"
                            [class.uf-tone-warning]="f.status === 'update'"
                            >{{ statusLabel(f.status) }}</span
                          >
                        </td>
                        <td class="uf-num" [title]="f.markers.join(', ')">{{ f.sheets }}</td>
                      </tr>
                    }
                  </tbody>
                </table>
                @if (pr.unmatched_existing.length) {
                  <p class="uf-hint">
                    Floors without a marker in the drawings, left as they are:
                    @for (u of pr.unmatched_existing; track u['floor_id']) {
                      {{ u['display_name'] }}
                    }
                  </p>
                }
                <div class="uf-actions">
                  <button
                    mat-flat-button
                    [disabled]="busy() || !pickedCount(b)"
                    (click)="acceptProposal(b, pr)"
                  >
                    <ng-icon name="lucideLayers" /> Accept {{ pickedCount(b) }} floor(s)
                  </button>
                </div>
              </div>
            }
          }
          <div class="uf-form-row">
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="num"
              ><mat-label>Lowest level</mat-label
              ><input
                matInput
                type="number"
                [(ngModel)]="from[b.id]"
                [name]="'from' + b.id"
                placeholder="-1"
            /></mat-form-field>
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="num"
              ><mat-label>Highest level</mat-label
              ><input
                matInput
                type="number"
                [(ngModel)]="to[b.id]"
                [name]="'to' + b.id"
                placeholder="12"
            /></mat-form-field>
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="num"
              ><mat-label>Floor height (m)</mat-label
              ><input
                matInput
                type="number"
                step="0.01"
                [(ngModel)]="height[b.id]"
                [name]="'h' + b.id"
                placeholder="3.3"
            /></mat-form-field>
            <button mat-stroked-button [disabled]="busy()" (click)="generateFloors(b)">
              <ng-icon name="lucideLayers" />
              {{ floorsOf(b).length ? 'Regenerate floors' : 'Generate floors' }}
            </button>
            @if (floorsOf(b).length) {
              <span class="uf-hint"
                >Regenerating replaces the floor list; floors with mapped units cannot be
                removed.</span
              >
            }
          </div>
          @if (floorsOf(b).length) {
            <table class="uf-plain floors">
              <thead>
                <tr>
                  <th>Level</th>
                  <th>Name</th>
                  <th class="uf-num">Height (m)</th>
                </tr>
              </thead>
              <tbody>
                @for (f of floorsOf(b); track f.id) {
                  <tr>
                    <td class="uf-num">{{ f.level }}</td>
                    <td>{{ f.display_name }}</td>
                    <td class="uf-num">{{ f.height_m ?? '—' }}</td>
                  </tr>
                }
              </tbody>
            </table>
            <p class="uf-hint">
              Accepting floors re-runs the page → floor suggestions on the sheets that were
              processed before; open Documents, then a sheet, to confirm them.
            </p>
          } @else {
            <p class="uf-muted uf-small">
              No floors yet. Generate them above; negative levels become basements (B1), 0 is
              Ground.
            </p>
          }
          <div class="portal">
            <h4 class="portal__title"><ng-icon name="lucideGlobe" /> Shown to buyers</h4>
            <div class="uf-form-row">
              <mat-form-field appearance="outline" subscriptSizing="dynamic"
                ><mat-label>Construction status</mat-label
                ><select
                  matNativeControl
                  [(ngModel)]="pf(b).construction_status"
                  [name]="'cs' + b.id"
                >
                  <option value="">Not stated</option>
                  <option value="planned">Planned</option>
                  <option value="under_construction">Under construction</option>
                  <option value="completed">Completed</option>
                </select></mat-form-field
              >
              <mat-form-field appearance="outline" subscriptSizing="dynamic"
                ><mat-label>Completion</mat-label
                ><input
                  matInput
                  [(ngModel)]="pf(b).completion"
                  [name]="'completion' + b.id"
                  maxlength="80"
                  placeholder="e.g. December 2026"
              /></mat-form-field>
              <mat-form-field appearance="outline" subscriptSizing="dynamic" class="elev-pick"
                ><mat-label>Elevation drawing (floor picker)</mat-label
                ><select
                  matNativeControl
                  [(ngModel)]="pf(b).elevation_sheet_id"
                  [name]="'elev' + b.id"
                >
                  <option value="">None: floor list and 3D only</option>
                  @for (c of candidatesOf(b); track c.sheet_id) {
                    <option [value]="c.sheet_id">
                      {{ c.document_title }}, page {{ c.page_no }} · {{ c.matched_floors }} of
                      {{ c.floors }} floors matched
                    </option>
                  }
                </select></mat-form-field
              >
            </div>
            @if (candidateOf(b); as c) {
              <figure class="elev">
                @if (c.raster_url) {
                  <img [src]="c.raster_url" alt="Elevation drawing preview" />
                }
                <figcaption class="uf-hint">
                  @if (c.matched_floors >= 2) {
                    {{ c.matched_floors }} floor bands from the level markers; buyers tap a band to
                    open that floor.
                  } @else {
                    Fewer than two floors match this sheet's level markers; the portal keeps the
                    floor list. Check the floors' elevations.
                  }
                </figcaption>
              </figure>
            } @else if (!candidatesOf(b).length) {
              <p class="uf-hint">
                No section or elevation sheet with level markers under this building yet. Upload the
                facade drawing as a document of this building.
              </p>
            }
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="wide"
              ><mat-label>Terms for this building</mat-label
              ><textarea
                matInput
                rows="3"
                [(ngModel)]="pf(b).terms"
                [name]="'terms' + b.id"
                maxlength="4000"
                placeholder="Handover specification, payment options, mortgage partners; empty = the project default from Publish"
              ></textarea>
            </mat-form-field>
            <div class="uf-actions">
              <button mat-flat-button [disabled]="busy()" (click)="savePortal(b)">
                <ng-icon name="lucideGlobe" /> Save
              </button>
              <span class="uf-hint">Buyers see it after the next publication.</span>
            </div>
          </div>
        </uf-section-card>
      } @empty {
        <uf-empty-state
          icon="lucideBuilding2"
          title="No buildings yet"
          text="Add a building above. Floors are what sheets, units and the 3D model attach to."
        />
      }

      @if (p) {
        <uf-section-card
          title="Archive or delete"
          icon="lucideTriangleAlert"
          summary="archive keeps everything; delete is permanent"
          storageKey="project-danger"
          [open]="false"
        >
          <p class="uf-hint">
            Archive hides the project from the projects list and changes nothing else; Reactivate
            brings it back. Delete removes the project with its buildings, units, documents, files
            and publications; the audit log keeps who did it. Both are refused while the portal is
            published: unpublish first. Delete needs the tenant admin role and the slug typed in.
          </p>
          <div class="uf-actions">
            <button mat-stroked-button [disabled]="busy()" (click)="toggleArchive(p)">
              <ng-icon
                [name]="p.status === 'archived' ? 'lucideArchiveRestore' : 'lucideArchive'"
              />
              {{ p.status === 'archived' ? 'Reactivate' : 'Archive' }}
            </button>
            <button mat-stroked-button [disabled]="busy()" (click)="deleteProject(p)">
              <ng-icon name="lucideTrash2" /> Delete project permanently
            </button>
          </div>
        </uf-section-card>
      }
    </div>
  `,
  styles: `
    .proposal {
      margin: 0 0 0.75rem;
      padding: 0.75rem;
      border: 1px solid #fcd34d;
      border-radius: var(--uf-radius, 8px);
      background: #fffbeb;
      display: grid;
      gap: 0.5rem;
    }
    .code {
      width: 8rem;
    }
    .blocks {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(18rem, 1fr));
      gap: 0.75rem;
    }
    .block {
      display: grid;
      gap: 0.35rem;
      padding: 0.5rem;
      border: 1px solid var(--uf-border, #e5e7eb);
      border-radius: var(--uf-radius, 8px);
      background: #fff;
    }
    .num {
      width: 10rem;
    }
    .floors {
      max-width: 36rem;
    }
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
    .portal {
      display: grid;
      gap: 0.5rem;
      margin-top: 0.75rem;
      padding-top: 0.75rem;
      border-top: 1px solid var(--uf-border);
    }
    .portal__title {
      margin: 0;
      font-size: 0.95rem;
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }
    .elev-pick {
      min-width: 260px;
    }
    .elev {
      margin: 0;
      display: grid;
      gap: 0.25rem;
    }
    .elev img {
      max-width: min(100%, 520px);
      border: 1px solid var(--uf-border);
      border-radius: 8px;
      background: #fff;
    }
    .wide {
      width: 100%;
    }
  `,
})
export class ProjectDetailPage {
  private readonly api = inject(UnitformaApi);
  private readonly ctx = inject(ProjectContext);
  private readonly toast = inject(ToastService);
  private readonly dialogs = inject(DialogsService);
  private readonly router = inject(Router);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly project = signal<ProjectOut | null>(null);
  readonly buildings = signal<BuildingOut[]>([]);
  readonly realBuildings = computed(() => this.buildings().filter((b) => b.kind === 'building'));
  readonly floorCount = computed(() =>
    this.realBuildings().reduce((a, b) => a + (b.floors?.length ?? 0), 0),
  );
  readonly placedCount = computed(
    () => this.realBuildings().filter((b) => b.placement_status === 'confirmed').length,
  );
  /** Permit summary stored on the project (ADR-0007 Decision 4), when it was imported from one. */
  readonly permit = computed(() => {
    const r = this.project()?.regulatory as Record<string, unknown> | undefined;
    return r && r['source'] === 'tasge' ? r : null;
  });
  readonly imports = signal<RegulatoryImportOut[]>([]);
  /** Floor proposals per building (ADR-0010); hidden when every storey already exists. */
  readonly proposals = signal<Record<string, FloorProposalOut>>({});
  private readonly picks = signal<Record<string, Set<number>>>({});
  /** Split-level blocks (ADR-0014): edited codes, the "one building" switch, the remove-source choice. */
  readonly blockCodes = signal<Record<string, string>>({});
  readonly asOneBuilding = signal<Record<string, boolean>>({});
  readonly removeSource = signal<Record<string, boolean>>({});
  readonly latestImport = computed(() => this.imports()[0] ?? null);
  /** "importing" for over 20 minutes means a lost worker (ADR-0016 #8); the next refresh closes it. */
  readonly importStalled = computed(() => {
    const j = this.latestImport();
    if (!j || j.status !== 'importing') return false;
    const started = new Date(j.started_at || j.created_at).getTime();
    return Date.now() - started > 20 * 60 * 1000;
  });
  readonly importRunning = computed(
    () => this.latestImport()?.status === 'importing' && !this.importStalled(),
  );
  readonly heights = computed(() => {
    const p = this.latestImport()?.permit as Record<string, unknown> | undefined;
    const h = (p?.['heights'] ?? null) as {
      above_zero_m?: number | null;
      below_zero_m?: number | null;
    } | null;
    return h ? { above: h.above_zero_m ?? null, below: h.below_zero_m ?? null } : null;
  });
  readonly facts = computed<HeaderFact[]>(() => {
    const p = this.project();
    if (!p) return [];
    const addr = (p.address ?? {}) as Record<string, unknown>;
    return [
      { domain: 'project', status: p.status },
      ...(typeof addr['line'] === 'string'
        ? [{ icon: 'lucideMapPin', value: String(addr['line']) }]
        : []),
      ...(this.permit()
        ? [
            {
              icon: 'lucideScrollText',
              label: 'Permit',
              value: String(this.permit()!['application_no'] ?? ''),
            },
          ]
        : []),
    ];
  });
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  /** Sections and elevations per building that can become its floor picker (ADR-0014). */
  readonly candidates = signal<Record<string, ElevationCandidateOut[]>>({});
  /** Portal fields per building as edited (ADR-0014 Decisions 1 and 3). */
  portalForms: Record<string, PortalFields> = {};
  code = '';
  bname = '';
  from: Record<string, number> = {};
  to: Record<string, number> = {};
  height: Record<string, number> = {};
  when = whenShort;

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
      this.ctx.set(p);
      this.buildings.set(b);
      const props = await Promise.all(
        b
          .filter((x) => x.kind === 'building')
          .map(async (x) => [x.id, await this.api.floorProposal(this.tenantId(), x.id)] as const),
      );
      const map: Record<string, FloorProposalOut> = {};
      const picks: Record<string, Set<number>> = {};
      for (const [id, pr] of props) {
        if (pr.floors.some((f) => f.status !== 'existing')) {
          map[id] = pr;
          picks[id] = new Set(pr.floors.filter((f) => f.status !== 'existing').map((f) => f.level));
        }
      }
      this.proposals.set(map);
      this.picks.set(picks);
      this.portalForms = {};
      const real = b.filter((x) => x.kind === 'building');
      const cands = await Promise.all(
        real.map((x) => this.api.elevationCandidates(this.tenantId(), x.id).catch(() => [])),
      );
      this.candidates.set(Object.fromEntries(real.map((x, i) => [x.id, cands[i]])));
      const reg = p.regulatory as Record<string, unknown>;
      this.imports.set(
        reg?.['source'] === 'tasge'
          ? await this.api.listRegulatoryImports(this.tenantId(), this.projectId())
          : [],
      );
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  permitFacts(r: Record<string, unknown>): Fact[] {
    return [
      { label: 'Permit', value: String(r['application_no'] ?? r['external_id'] ?? '') },
      { label: 'Status', value: this.str(r['status']) },
      { label: 'Decided', value: dayOf(this.str(r['decided_at'])) },
      { label: 'Address', value: this.str(r['address']) },
      { label: 'Parcels', value: this.codes(r).join(', ') },
    ];
  }

  str(v: unknown): string {
    return typeof v === 'string' ? v : '';
  }

  codes(r: Record<string, unknown>): string[] {
    return Array.isArray(r['cadastral_codes']) ? (r['cadastral_codes'] as string[]) : [];
  }

  count(j: RegulatoryImportOut, key: string): number {
    return j.counts?.[key] ?? 0;
  }

  failed(j: RegulatoryImportOut): Record<string, unknown>[] {
    const f = j.stats?.['failed'];
    return Array.isArray(f) ? (f as Record<string, unknown>[]) : [];
  }

  proposalFor(b: BuildingOut): FloorProposalOut | null {
    return this.proposals()[b.id] ?? null;
  }

  isPicked(b: BuildingOut, f: ProposedFloorOut): boolean {
    return f.status === 'existing' || (this.picks()[b.id]?.has(f.level) ?? false);
  }

  togglePick(b: BuildingOut, f: ProposedFloorOut, on: boolean): void {
    this.picks.update((m) => {
      const set = new Set(m[b.id] ?? []);
      if (on) set.add(f.level);
      else set.delete(f.level);
      return { ...m, [b.id]: set };
    });
  }

  pickedCount(b: BuildingOut): number {
    return this.picks()[b.id]?.size ?? 0;
  }

  statusLabel(status: string): string {
    return { new: 'new', update: 'fills elevation', existing: 'already there' }[status] ?? status;
  }

  blocksOf(pr: FloorProposalOut): BlockProposalOut[] {
    return pr.blocks ?? [];
  }

  setOneBuilding(b: BuildingOut, on: boolean): void {
    this.asOneBuilding.update((m) => ({ ...m, [b.id]: on }));
  }

  setRemoveSource(b: BuildingOut, on: boolean): void {
    this.removeSource.update((m) => ({ ...m, [b.id]: on }));
  }

  blockCode(b: BuildingOut, blk: BlockProposalOut): string {
    return this.blockCodes()[b.id + '/' + blk.code] ?? blk.code;
  }

  setBlockCode(b: BuildingOut, blk: BlockProposalOut, code: string): void {
    this.blockCodes.update((m) => ({ ...m, [b.id + '/' + blk.code]: code }));
  }

  /** One building per block with its floors; the source building goes when asked and empty. */
  async acceptBlocks(b: BuildingOut, pr: FloorProposalOut): Promise<void> {
    const remove = this.removeSource()[b.id] ?? true;
    await this.run(async () => {
      const out = await this.api.acceptBlocks(this.tenantId(), b.id, {
        delete_source: remove,
        blocks: this.blocksOf(pr).map((blk) => ({
          code: this.blockCode(b, blk).trim(),
          name: `Block ${this.blockCode(b, blk).trim()}`,
          floors: blk.floors.map((f) => ({
            level: f.level,
            display_name: f.display_name,
            elevation_m: String(f.elevation_m),
            height_m: f.height_m != null ? String(f.height_m) : null,
          })),
        })),
      });
      this.toast.ok(
        `${out.buildings.length} buildings created${out.source_removed ? `, ${b.code} removed` : ''}; sheet suggestions are being refreshed`,
      );
    });
  }

  /** Accept through the floors endpoint that exists; existing levels are updated, nothing is deleted. */
  async acceptProposal(b: BuildingOut, pr: FloorProposalOut): Promise<void> {
    const picked = this.picks()[b.id] ?? new Set<number>();
    const floors: FloorIn[] = pr.floors
      .filter((f) => f.status !== 'existing' && picked.has(f.level))
      .map((f) => ({
        level: f.level,
        display_name: f.display_name,
        elevation_m: String(f.elevation_m),
        height_m: f.height_m != null ? String(f.height_m) : null,
      }));
    if (!floors.length) return;
    await this.run(() => this.api.setFloors(this.tenantId(), b.id, floors));
    this.toast.ok(`${floors.length} floor(s) accepted; sheet suggestions are being refreshed`);
  }

  floorsOf(b: BuildingOut): FloorOut[] {
    return b.floors ?? [];
  }

  pf(b: BuildingOut): PortalFields {
    return (this.portalForms[b.id] ??= {
      construction_status: b.construction_status ?? '',
      completion: b.completion ?? '',
      terms: b.terms ?? '',
      elevation_sheet_id: b.elevation_sheet_id ?? '',
    });
  }

  candidatesOf(b: BuildingOut): ElevationCandidateOut[] {
    return this.candidates()[b.id] ?? [];
  }

  candidateOf(b: BuildingOut): ElevationCandidateOut | null {
    const id = this.pf(b).elevation_sheet_id;
    return (id && this.candidatesOf(b).find((c) => c.sheet_id === id)) || null;
  }

  /** Empty strings clear the field: the API treats an explicit null as "clear" (ADR-0014 Decision 3). */
  async savePortal(b: BuildingOut): Promise<void> {
    const f = this.pf(b);
    await this.run(async () => {
      await this.api.updateBuilding(this.tenantId(), b.id, {
        construction_status: (f.construction_status ||
          null) as BuildingUpdate['construction_status'],
        completion: f.completion.trim() || null,
        terms: f.terms.trim() || null,
        elevation_sheet_id: f.elevation_sheet_id || null,
        version: b.version,
      });
      this.toast.ok(`Building ${b.code} saved. Publish a new version to show it to buyers.`);
    });
  }

  floorSummary(b: BuildingOut): string {
    const f = this.floorsOf(b);
    if (!f.length) return 'no floors yet';
    const lv = f.map((x) => x.level);
    return `levels ${Math.min(...lv)} to ${Math.max(...lv)}`;
  }

  async refreshPermit(): Promise<void> {
    await this.run(async () => {
      await this.api.refreshPermit(this.tenantId(), this.projectId());
      this.toast.ok('Registry checked; new files are being imported');
    });
  }

  async addBuilding(): Promise<void> {
    if (!this.code.trim()) return;
    await this.run(async () => {
      await this.api.createBuilding(this.tenantId(), this.projectId(), {
        code: this.code.trim(),
        name: this.bname || null,
        kind: 'building',
        sort_order: 0,
      });
      this.toast.ok(`Building ${this.code.trim()} added`);
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
      floors.push({
        level: lvl,
        display_name: lvl < 0 ? `B${-lvl}` : lvl === 0 ? 'Ground' : String(lvl),
        height_m: h ? String(h) : null,
      });
    }
    await this.run(async () => {
      await this.api.setFloors(this.tenantId(), b.id, floors);
      this.toast.ok(`${floors.length} floors set on ${b.code}`);
    });
  }

  /** Archive keeps every row and file (ADR-0012 Decision 1); the backend refuses it while published. */
  async toggleArchive(p: ProjectOut): Promise<void> {
    const archive = p.status !== 'archived';
    if (archive) {
      const ok = await this.dialogs.confirm({
        title: `Archive ${p.name}?`,
        message:
          'The project leaves the projects list; nothing is deleted and Reactivate brings it back.',
        confirmLabel: 'Archive',
        icon: 'lucideArchive',
      });
      if (!ok) return;
    }
    await this.run(async () => {
      await this.api.updateProject(this.tenantId(), this.projectId(), {
        status: archive ? 'archived' : 'active',
        version: p.version,
      });
      this.toast.ok(archive ? `${p.name} archived` : `${p.name} reactivated`);
    });
  }

  /** Only an empty building goes; the backend answers 409 with the unit count otherwise. */
  async deleteBuilding(b: BuildingOut): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: `Delete building ${b.code}?`,
      message:
        'Its floors and 3D models are removed; documents filed under it stay with the project. ' +
        'A building with units cannot be deleted.',
      confirmLabel: 'Delete',
      tone: 'bad',
      icon: 'lucideTrash2',
    });
    if (!ok) return;
    await this.run(async () => {
      await this.api.deleteBuilding(this.tenantId(), b.id);
      this.toast.ok(`Building ${b.code} deleted`);
    });
  }

  /** Tenant admin only, typed slug, never while published (ADR-0012 Decision 4). */
  async deleteProject(p: ProjectOut): Promise<void> {
    const typed = await this.dialogs.prompt({
      title: `Delete ${p.name} permanently?`,
      message:
        `Type the slug "${p.slug}" to confirm. Buildings, units, documents, files and ` +
        'publications are removed; the audit log keeps a record. This cannot be undone.',
      label: 'Project slug',
      placeholder: p.slug,
      required: true,
      confirmLabel: 'Delete permanently',
    });
    if (typed === null) return;
    if (typed.trim() !== p.slug) {
      this.error.set(`The slug does not match (${p.slug}); nothing was deleted`);
      return;
    }
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.deleteProject(this.tenantId(), this.projectId(), p.slug);
      this.toast.ok(`${p.name} deleted`);
      await this.router.navigate(['/t', this.tenantId(), 'projects']);
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
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
