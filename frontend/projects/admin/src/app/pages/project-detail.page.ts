import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  BuildingOut,
  FloorIn,
  FloorOut,
  ProjectOut,
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
              <uf-status-chip domain="regulatory_import" [value]="j.status" />
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
            @if (j.status === 'importing') {
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
              [disabled]="busy() || latestImport()?.status === 'importing'"
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
          } @else {
            <p class="uf-muted uf-small">
              No floors yet. Generate them above; negative levels become basements (B1), 0 is
              Ground.
            </p>
          }
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
    .code {
      width: 8rem;
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
  readonly latestImport = computed(() => this.imports()[0] ?? null);
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

  floorsOf(b: BuildingOut): FloorOut[] {
    return b.floors ?? [];
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
