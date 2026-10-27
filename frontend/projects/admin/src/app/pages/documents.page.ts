import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { BuildingOut, DocumentOut, SheetOut, UnitformaApi, problemMessage } from 'api-client';
import {
  EmptyStateComponent,
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
  kb,
  labelOf,
} from 'ui';
import { parsePages } from '../core/page-ranges';
import { DialogsService } from '../ui/dialogs.service';
import { ToastService } from '../ui/toast.service';

type Kind =
  | 'site_plan'
  | 'floor_plan'
  | 'section'
  | 'elevation'
  | 'render'
  | 'schedule'
  | 'model_ifc'
  | 'model_glb'
  | 'texture'
  | 'permit'
  | 'other'
  | 'unclassified';

/** Kinds a person can choose; model kinds are fixed by the file type (set at upload and by the worker). */
const MODEL_KINDS = new Set<string>(['model_ifc', 'model_glb']);
const KINDS: { value: Kind; label: string }[] = [
  { value: 'site_plan', label: 'Site plan' },
  { value: 'floor_plan', label: 'Floor plans' },
  { value: 'section', label: 'Sections' },
  { value: 'elevation', label: 'Elevations' },
  { value: 'render', label: 'Renders' },
  { value: 'schedule', label: 'Area schedule' },
  { value: 'permit', label: 'Permit document' },
  { value: 'other', label: 'Other' },
];
const KIND_LABELS: Record<string, string> = Object.fromEntries(
  KINDS.map((k) => [k.value, k.label]),
);
KIND_LABELS['model_ifc'] = 'IFC model';
KIND_LABELS['model_glb'] = 'GLB model';
KIND_LABELS['texture'] = 'Texture';
KIND_LABELS['unclassified'] = 'Uncategorized';
const SOURCE_LABELS: Record<string, string> = {
  manual: 'set by you',
  filename: 'guessed from the name',
  content: 'guessed from the content',
  type: 'fixed by the file type',
  pending: 'needs a kind',
};

/**
 * Project documents (plan §13.1 steps 1–2, ADR-0008): upload several files at once, let the
 * platform guess each kind from the name and then from the content, confirm or fix the kind on
 * the card; processing status and sheets per revision.
 */
@Component({
  selector: 'uf-documents-page',
  imports: [
    FormsModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatButtonModule,
    MatButtonToggleModule,
    MatProgressBarModule,
    MatSlideToggleModule,
    RouterLink,
    NgIcon,
    PageHeaderComponent,
    SectionCardComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="Documents" icon="lucideFileText" [facts]="facts()">
        <ng-container actions>
          <a mat-stroked-button routerLink="../proposals"
            ><ng-icon name="lucideGitCompare" /> Revision diffs</a
          >
        </ng-container>
      </uf-page-header>
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }
      <uf-section-card
        [title]="targetDoc ? 'New revision of ' + targetDoc.title : 'Upload files'"
        icon="lucideUpload"
        summary="several files at once; the kind is guessed and confirmed on the card"
        storageKey="documents-upload"
        [open]="docs().length === 0 || !!targetDoc"
      >
        <p class="uf-hint">
          Each file becomes a document named after it. The kind is guessed from the name now and
          from the content after processing; confirm it on the card.
        </p>
        <div class="uf-form-row">
          <mat-form-field appearance="outline"
            ><mat-label>Building (optional, for all files)</mat-label>
            <mat-select [(ngModel)]="buildingId" name="buildingId">
              <mat-option [value]="null">Project level</mat-option>
              @for (b of buildings(); track b.id) {
                <mat-option [value]="b.id">{{ b.code }} {{ b.name ?? '' }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline"
            ><mat-label>Source note</mat-label
            ><input matInput [(ngModel)]="note" name="note" placeholder="Rev C from architect"
          /></mat-form-field>
          <label class="pick" [class.is-busy]="busy()">
            <ng-icon name="lucideFileUp" />
            {{
              selected.length
                ? selected.length + ' file' + (selected.length === 1 ? '' : 's') + ' chosen'
                : 'Choose files…'
            }}
            <input
              type="file"
              #file
              [multiple]="!targetDoc"
              accept="application/pdf,image/png,image/jpeg,.dxf,application/dxf,image/vnd.dxf"
              (change)="onFiles($event)"
              hidden
            />
          </label>
          <button mat-flat-button [disabled]="busy() || !selected.length" (click)="upload()">
            <ng-icon name="lucideUpload" />
            {{
              targetDoc
                ? 'Upload revision'
                : selected.length > 1
                  ? 'Upload ' + selected.length + ' files'
                  : 'Upload'
            }}
          </button>
          @if (targetDoc) {
            <button mat-button (click)="targetDoc = null; selected = []">Cancel</button>
          }
        </div>
        <p class="uf-hint">
          Accepted: PDF and PNG/JPG (plans, renders, schedules) and DXF exported from AutoCAD or
          ArchiCAD (one sheet per layout, scale taken from the drawing units). DWG must be saved as
          DXF first; IFC and GLB are stored but not processed yet. Any 2D source gives the schematic
          3D model; exact 3D needs an IFC export.
        </p>
        @if (progress(); as pr) {
          <p class="uf-small uf-muted">{{ pr.done }} of {{ pr.total }} files · {{ pr.current }}</p>
          <mat-progress-bar
            mode="determinate"
            [value]="((pr.done + pr.fraction) / pr.total) * 100"
          />
        }
      </uf-section-card>

      @if (docs().length) {
        <div class="uf-filterbar">
          <mat-button-toggle-group
            [value]="filter()"
            (change)="filter.set($event.value)"
            aria-label="Filter"
            hideSingleSelectionIndicator
          >
            <mat-button-toggle value="all">All · {{ docs().length }}</mat-button-toggle>
            <mat-button-toggle value="needs"
              >Needs a kind · {{ needsKind().length }}</mat-button-toggle
            >
            <mat-button-toggle value="guessed"
              >Guessed, unconfirmed · {{ guessed().length }}</mat-button-toggle
            >
          </mat-button-toggle-group>
          <mat-form-field appearance="outline" subscriptSizing="dynamic" class="search">
            <ng-icon matPrefix name="lucideSearch" />
            <input
              matInput
              [ngModel]="query()"
              (ngModelChange)="query.set($event)"
              placeholder="Search title or file…"
              aria-label="Search documents"
            />
          </mat-form-field>
          <span class="uf-count">{{ shown().length }} shown</span>
        </div>
      }

      @for (d of shown(); track d.id) {
        <uf-section-card
          [title]="d.title"
          [icon]="kindIcon(d.kind)"
          [summary]="revSummary(d)"
          [storageKey]="'doc-' + d.id"
          [collapsible]="false"
        >
          <div actions class="uf-actions">
            <uf-status-chip
              domain="document.kind"
              [value]="d.kind"
              [tooltip]="labelOf('document.kind_source', d.kind_source)"
            />
            <uf-status-chip domain="document.kind_source" [value]="d.kind_source" />
            @if (d.current_revision; as r) {
              <uf-status-chip domain="document.processing" [value]="r.processing_status" />
            }
            @if (d.kind === 'render' && d.visibility === 'public') {
              <span class="uf-chip uf-tone-good"
                ><ng-icon name="lucideGlobe" />In portal gallery</span
              >
            }
          </div>
          @if (d.current_revision?.processing_error) {
            <div class="uf-alert uf-alert--bad">
              <ng-icon name="lucideCircleX" />{{ d.current_revision?.processing_error }}
            </div>
          }
          @if (d.current_revision?.processing_note; as note) {
            <p class="uf-hint"><ng-icon name="lucideCopy" /> {{ note }}</p>
          }
          <div class="uf-actions">
            @if (isModelKind(d.kind)) {
              <span
                class="uf-chip"
                title="A model is a model by its file type; the kind cannot be changed"
                ><ng-icon name="lucideBox" />{{ kindLabel(d.kind) }}</span
              >
            } @else {
              <mat-form-field appearance="outline" class="kind">
                <mat-label>Kind</mat-label>
                <mat-select
                  [value]="d.kind === 'unclassified' ? null : d.kind"
                  (selectionChange)="setKind(d, $event.value)"
                  [disabled]="busy()"
                >
                  @for (k of kinds; track k.value) {
                    <mat-option [value]="k.value">{{ k.label }}</mat-option>
                  }
                </mat-select>
              </mat-form-field>
            }
            <mat-form-field appearance="outline" class="building">
              <mat-label>Building</mat-label>
              <mat-select
                [value]="d.building_id ?? ''"
                (selectionChange)="setBuilding(d, $event.value || null)"
                [disabled]="busy()"
                aria-label="Building the document is filed under"
              >
                <mat-option value="">Project level</mat-option>
                @for (b of buildings(); track b.id) {
                  <mat-option [value]="b.id">{{ b.code }} {{ b.name ?? '' }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
            @if (d.kind === 'render') {
              <mat-slide-toggle
                [checked]="d.visibility === 'public'"
                [disabled]="busy()"
                (change)="setVisibility(d, $event.checked)"
                >Show in portal gallery</mat-slide-toggle
              >
            }
            @if (isGuessed(d)) {
              <button mat-stroked-button [disabled]="busy()" (click)="setKind(d, d.kind)">
                <ng-icon name="lucideCheck" /> Confirm {{ kindLabel(d.kind) }}
              </button>
            }
            @if (!sheets()[d.id]) {
              <button mat-button (click)="loadSheets(d)">
                <ng-icon name="lucideLayers" /> Show sheets
              </button>
            }
            <button mat-button (click)="newRevision(d)">
              <ng-icon name="lucideFileUp" /> Upload new revision
            </button>
            <button mat-button (click)="download(d)">
              <ng-icon name="lucideDownload" /> Download
            </button>
            <button mat-button [disabled]="busy()" (click)="remove(d)">
              <ng-icon name="lucideTrash2" /> Delete
            </button>
          </div>
          @if (unfiledPlan(d)) {
            <p class="uf-hint">
              This project has {{ buildings().length }} buildings and this floor plan is filed at
              project level: the floor proposal of a building skips it. Pick the building it belongs
              to; a sheet that shows several blocks stays at project level.
            </p>
          }
          @if (d.kind === 'unclassified') {
            <p class="uf-hint">
              The name and the content did not say what this file is. Pick a kind. A project-level
              file set to Floor plans gets its floor suggestions with the next revision; a file
              filed under a building already has them.
            </p>
          }
          @if (sheets()[d.id]; as list) {
            <div class="uf-form-row uf-sets">
              <span class="uf-muted"
                >Map only the plans: exclude reprints, details and schedules.</span
              >
              @if (reprints(list).length; as n) {
                <button
                  mat-stroked-button
                  [disabled]="busy()"
                  (click)="exclude(d, reprints(list), true, 'reprint of an earlier page')"
                >
                  Exclude {{ n }} reprint(s)
                </button>
              }
              <mat-form-field appearance="outline" class="uf-pages"
                ><mat-label>Pages</mat-label>
                <input
                  matInput
                  [(ngModel)]="pageInput[d.id]"
                  [name]="'pages-' + d.id"
                  placeholder="12-51, 7"
                />
              </mat-form-field>
              <mat-form-field appearance="outline"
                ><mat-label>Reason</mat-label>
                <input
                  matInput
                  [(ngModel)]="reasonInput[d.id]"
                  [name]="'reason-' + d.id"
                  placeholder="fire-safety set"
                />
              </mat-form-field>
              <button
                mat-button
                [disabled]="busy() || !pageInput[d.id]"
                (click)="exclude(d, parsePages(pageInput[d.id]), true, reasonInput[d.id])"
              >
                Exclude
              </button>
              <button
                mat-button
                [disabled]="busy() || !pageInput[d.id]"
                (click)="exclude(d, parsePages(pageInput[d.id]), false, null)"
              >
                Include
              </button>
            </div>
            <div class="uf-sheets">
              @for (s of list; track s.id) {
                <a
                  class="uf-sheet"
                  [class.uf-sheet--excluded]="s.excluded"
                  [routerLink]="['../sheets', s.id]"
                  [attr.title]="s.exclusion_reason ?? null"
                >
                  @if (s.thumbnail_url) {
                    <img [src]="s.thumbnail_url" alt="page {{ s.page_no }}" />
                  } @else {
                    <div class="uf-sheet__ph">p{{ s.page_no }}</div>
                  }
                  <span class="uf-sheet__cap">Page {{ s.page_no }}</span>
                  <span class="uf-sheet__chips">
                    @if (s.excluded) {
                      <uf-status-chip domain="sheet.assignment" value="excluded" />
                    } @else {
                      <uf-status-chip domain="sheet.assignment" [value]="s.assignment_status" />
                      @if (kindOf(s)) {
                        <span class="uf-chip">{{ kindOf(s) }}</span>
                      }
                    }
                    @if (dupOf(s); as dup) {
                      @if (!s.excluded) {
                        <span class="uf-chip uf-tone-warning">reprint of p{{ dup }}</span>
                      }
                    }
                  </span>
                </a>
              }
            </div>
          }
        </uf-section-card>
      } @empty {
        @if (docs().length) {
          <uf-empty-state
            icon="lucideListFilter"
            title="Nothing in this filter"
            text="Every document has a confirmed kind, or nothing matches the search."
            [compact]="true"
          />
        } @else {
          <uf-empty-state
            icon="lucideFileText"
            title="No documents yet"
            text="Upload the site plan, the floor plans per building and the renders above. The worker reads the pages and proposes which floor each sheet shows."
          />
        }
      }
    </div>
  `,
  styles: `
    .search {
      min-width: 240px;
    }
    .search ng-icon {
      margin: 0 0.25rem 0 0.5rem;
      color: var(--uf-muted);
    }
    .uf-actions {
      display: flex;
      gap: 0.5rem;
      align-items: center;
      flex-wrap: wrap;
    }
    .kind {
      width: 12rem;
    }
    .building {
      width: 14rem;
    }
    .pick {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.6rem 0.9rem;
      border: 1px dashed var(--uf-border-strong);
      border-radius: var(--uf-radius-sm);
      cursor: pointer;
      color: var(--uf-primary);
      font-weight: 600;
    }
    .pick.is-busy {
      opacity: 0.5;
      pointer-events: none;
    }
    .uf-sheets {
      display: flex;
      gap: 0.75rem;
      flex-wrap: wrap;
      margin-top: 0.5rem;
    }
    .uf-sheet {
      display: flex;
      flex-direction: column;
      gap: 0.25rem;
      width: 160px;
      font-size: 0.75rem;
      text-decoration: none;
      color: inherit;
    }
    .uf-sheet:hover img,
    .uf-sheet:hover .uf-sheet__ph {
      border-color: var(--uf-primary);
    }
    .uf-sheet--excluded {
      opacity: 0.45;
    }
    .uf-sheet__cap {
      font-weight: 600;
    }
    .uf-sheet__chips {
      display: flex;
      gap: 0.25rem;
      flex-wrap: wrap;
    }
    .uf-pages {
      width: 9rem;
    }
    .uf-sets {
      margin-top: 0.5rem;
    }
    .uf-sheet img,
    .uf-sheet__ph {
      width: 160px;
      height: 110px;
      object-fit: contain;
      background: #fff;
      border: 1px solid var(--uf-border);
      border-radius: 6px;
      display: grid;
      place-items: center;
    }
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class DocumentsPage {
  private readonly api = inject(UnitformaApi);
  private readonly toast = inject(ToastService);
  private readonly dialogs = inject(DialogsService);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly docs = signal<DocumentOut[]>([]);
  readonly query = signal('');
  readonly labelOf = labelOf;
  readonly facts = computed<HeaderFact[]>(() => [
    { label: 'Documents', value: this.docs().length },
    {
      domain: 'document.kind_source',
      status: 'pending',
      value: `${this.needsKind().length} need a kind`,
    },
    {
      domain: 'document.processing',
      status: 'done',
      value: `${this.docs().filter((d) => d.current_revision?.processing_status === 'done').length} processed`,
    },
  ]);
  readonly buildings = signal<BuildingOut[]>([]);
  readonly sheets = signal<Record<string, SheetOut[]>>({});
  readonly busy = signal(false);
  readonly progress = signal<{
    done: number;
    total: number;
    current: string;
    fraction: number;
  } | null>(null);
  readonly error = signal<string | null>(null);
  readonly filter = signal<'all' | 'needs' | 'guessed'>('all');
  readonly kinds = KINDS;
  readonly needsKind = computed(() => this.docs().filter((d) => d.kind === 'unclassified'));
  readonly guessed = computed(() => this.docs().filter((d) => this.isGuessed(d)));
  readonly shown = computed(() => {
    const f = this.filter();
    const base = f === 'needs' ? this.needsKind() : f === 'guessed' ? this.guessed() : this.docs();
    const q = this.query().trim().toLowerCase();
    return q
      ? base.filter((d) =>
          `${d.title} ${d.current_revision?.file_name ?? ''}`.toLowerCase().includes(q),
        )
      : base;
  });

  kindIcon(kind: string): string {
    return (
      (
        {
          site_plan: 'lucideMap',
          floor_plan: 'lucideLayers',
          render: 'lucideImage',
          schedule: 'lucideTable',
          permit: 'lucideScrollText',
          model_ifc: 'lucideBox',
          model_glb: 'lucideBox',
        } as Record<string, string>
      )[kind] ?? 'lucideFileText'
    );
  }

  revSummary(d: DocumentOut): string {
    const r = d.current_revision;
    if (!r) return 'no file yet';
    return `rev ${r.revision_no} · ${r.file_name} · ${kb(r.byte_size)}${r.page_count ? ` · ${r.page_count} pages` : ''}`;
  }
  buildingId: string | null = null;
  note = '';
  selected: File[] = [];
  targetDoc: DocumentOut | null = null;

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  async load(): Promise<void> {
    try {
      const [d, b] = await Promise.all([
        this.api.listDocuments(this.tenantId(), this.projectId()),
        this.api.listBuildings(this.tenantId(), this.projectId()),
      ]);
      this.docs.set(d);
      this.buildings.set(b.filter((x) => x.kind === 'building'));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  pageInput: Record<string, string> = {};
  reasonInput: Record<string, string> = {};

  isModelKind(kind: string): boolean {
    return MODEL_KINDS.has(kind);
  }

  isGuessed(d: DocumentOut): boolean {
    return (
      d.kind !== 'unclassified' && (d.kind_source === 'filename' || d.kind_source === 'content')
    );
  }

  kindLabel(kind: string): string {
    return KIND_LABELS[kind] ?? kind;
  }

  sourceLabel(source: string | undefined): string {
    return SOURCE_LABELS[source ?? 'manual'] ?? source ?? '';
  }

  dupOf(s: SheetOut): number | null {
    return ((s.hints ?? {}) as { duplicate_of?: number }).duplicate_of ?? null;
  }

  reprints(list: SheetOut[]): number[] {
    return list.filter((s) => !s.excluded && this.dupOf(s) !== null).map((s) => s.page_no);
  }

  readonly parsePages = parsePages;

  /** A floor plan at project level in a multi-building project: the floor proposal of a
   *  building reads only that building's documents, so the file counts for none of them. */
  unfiledPlan(d: DocumentOut): boolean {
    return d.kind === 'floor_plan' && !d.building_id && this.buildings().length > 1;
  }

  buildingLabel(id: string | null): string {
    const b = this.buildings().find((x) => x.id === id);
    return b ? `${b.code} ${b.name ?? ''}`.trim() : 'project level';
  }

  /** Files the document under a building or back at project level (ADR-0008 Decision 3).
   *  Suggestions already made for its sheets stay; the building's floor proposal reads the
   *  document at once. */
  async setBuilding(d: DocumentOut, buildingId: string | null): Promise<void> {
    if ((d.building_id ?? null) === buildingId) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const updated = await this.api.updateDocument(
        this.tenantId(),
        d.id,
        buildingId ? { building_id: buildingId } : { clear_building: true },
      );
      this.docs.update((list) => list.map((x) => (x.id === d.id ? updated : x)));
      this.toast.ok(`${d.title}: ${this.buildingLabel(buildingId)}`);
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  async setKind(d: DocumentOut, kind: string | null): Promise<void> {
    if (!kind) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const updated = await this.api.updateDocument(this.tenantId(), d.id, { kind: kind as Kind });
      this.docs.update((list) => list.map((x) => (x.id === d.id ? updated : x)));
      this.toast.ok(`${d.title}: ${this.kindLabel(kind)}`);
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  /** A public render document's pages form the portal gallery with the next publication (ADR-0016). */
  async setVisibility(d: DocumentOut, isPublic: boolean): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const updated = await this.api.updateDocument(this.tenantId(), d.id, {
        visibility: isPublic ? 'public' : 'internal',
      });
      this.docs.update((list) => list.map((x) => (x.id === d.id ? updated : x)));
      this.toast.ok(
        isPublic
          ? `${d.title} is in the portal gallery from the next publication`
          : `${d.title} removed from the gallery`,
      );
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  async exclude(
    d: DocumentOut,
    pages: number[],
    excluded: boolean,
    reason: string | null | undefined,
  ): Promise<void> {
    if (!d.current_revision_id || !pages.length) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const list = await this.api.excludePages(
        this.tenantId(),
        d.current_revision_id,
        pages,
        excluded,
        reason || null,
      );
      this.sheets.update((m) => ({ ...m, [d.id]: list }));
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  kindOf(s: SheetOut): string {
    return String((s.hints as { kind?: string })?.kind ?? '');
  }

  onFiles(ev: Event): void {
    this.selected = Array.from((ev.target as HTMLInputElement).files ?? []);
  }

  newRevision(d: DocumentOut): void {
    this.targetDoc = d;
    this.selected = [];
    this.buildingId = d.building_id ?? null;
  }

  /** One document per file (title = file name, kind guessed by the backend), or one new revision. */
  async upload(): Promise<void> {
    const files = this.selected;
    if (!files.length) return;
    this.busy.set(true);
    this.error.set(null);
    const failed: string[] = [];
    let done = 0;
    try {
      for (const file of files) {
        this.progress.set({ done, total: files.length, current: file.name, fraction: 0 });
        try {
          const doc =
            this.targetDoc ??
            (await this.api.createDocument(this.tenantId(), this.projectId(), {
              kind: 'unclassified',
              title: file.name.replace(/\.[^.]+$/, ''),
              building_id: this.buildingId,
              visibility: 'internal',
              source: {},
            }));
          const ct =
            file.type ||
            (/\.dxf$/i.test(file.name) ? 'application/dxf' : 'application/octet-stream');
          const intent = await this.api.createUpload(this.tenantId(), doc.id, {
            file_name: file.name,
            content_type: ct,
            byte_size: file.size,
            source_note: this.note || null,
          });
          await this.api.uploadToPresignedUrl(intent.upload_url, file, ct, (p) =>
            this.progress.set({ done, total: files.length, current: file.name, fraction: p }),
          );
          await this.api.completeUpload(this.tenantId(), intent.revision.id);
        } catch (e) {
          failed.push(`${file.name}: ${problemMessage(e)}`);
        }
        done++;
      }
      if (failed.length)
        this.error.set(`${failed.length} of ${files.length} files failed. ${failed.join(' · ')}`);
      else
        this.toast.ok(
          `${files.length} file${files.length === 1 ? '' : 's'} uploaded; processing starts in the background`,
        );
      this.selected = [];
      this.targetDoc = null;
      this.note = '';
      await this.load();
    } finally {
      this.busy.set(false);
      this.progress.set(null);
    }
  }

  async loadSheets(d: DocumentOut): Promise<void> {
    if (!d.current_revision_id) return;
    try {
      const list = await this.api.listSheets(this.tenantId(), d.current_revision_id);
      this.sheets.update((m) => ({ ...m, [d.id]: list }));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  /** Two steps when units are outlined on it: the backend answers 409 `document-mapped` with the
   *  count, the second dialog states it, and the retry detaches them (ADR-0012 Decision 2). */
  async remove(d: DocumentOut): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: `Delete ${d.title}?`,
      message: 'The document, its revisions, sheets and files are removed.',
      confirmLabel: 'Delete',
      tone: 'bad',
      icon: 'lucideTrash2',
    });
    if (!ok) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      try {
        await this.api.deleteDocument(this.tenantId(), d.id);
      } catch (e) {
        const p = (e as { error?: { type?: string; units?: number } }).error;
        if (!p?.type?.endsWith('document-mapped')) throw e;
        const n = p.units ?? 0;
        const units = `${n} unit${n === 1 ? '' : 's'}`;
        const again = await this.dialogs.confirm({
          title: `${units} outlined on ${d.title}`,
          message:
            'Deleting it removes their outlines from the plan and the 3D model. The units keep ' +
            'their codes, prices and history. Delete anyway?',
          confirmLabel: `Delete and detach ${units}`,
          tone: 'bad',
          icon: 'lucideTrash2',
        });
        if (!again) return;
        await this.api.deleteDocument(this.tenantId(), d.id, true);
      }
      this.docs.update((list) => list.filter((x) => x.id !== d.id));
      this.toast.ok(`${d.title} deleted`);
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  async download(d: DocumentOut): Promise<void> {
    if (!d.current_revision_id) return;
    const r = await this.api.revisionDownloadUrl(this.tenantId(), d.current_revision_id);
    window.open(r.url, '_blank');
  }
}
