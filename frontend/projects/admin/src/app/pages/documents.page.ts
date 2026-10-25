import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { BuildingOut, DocumentOut, SheetOut, UnitformaApi, problemMessage } from 'api-client';
import { parsePages } from '../core/page-ranges';

type Kind = 'site_plan' | 'floor_plan' | 'section' | 'elevation' | 'render' | 'schedule' | 'model_ifc' | 'model_glb' | 'texture' | 'permit' | 'other' | 'unclassified';

/** Kinds a person can choose; model kinds are fixed by the file type. */
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
const KIND_LABELS: Record<string, string> = Object.fromEntries(KINDS.map((k) => [k.value, k.label]));
KIND_LABELS['model_ifc'] = 'IFC model';
KIND_LABELS['model_glb'] = 'GLB model';
KIND_LABELS['texture'] = 'Texture';
KIND_LABELS['unclassified'] = 'Uncategorized';
const SOURCE_LABELS: Record<string, string> = {
  manual: 'set by you',
  filename: 'guessed from the name',
  content: 'guessed from the content',
  pending: 'needs a kind',
};

/**
 * Project documents (plan §13.1 steps 1–2, ADR-0008): upload several files at once, let the
 * platform guess each kind from the name and then from the content, confirm or fix the kind on
 * the card; processing status and sheets per revision.
 */
@Component({
  selector: 'uf-documents-page',
  imports: [FormsModule, DecimalPipe, MatCardModule, MatFormFieldModule, MatInputModule, MatSelectModule, MatButtonModule, MatButtonToggleModule, MatProgressBarModule, RouterLink],
  template: `
    <div class="uf-page">
      <div class="uf-page-header"><h2>Documents</h2><a mat-stroked-button [routerLink]="['..']">Back to project</a></div>
      @if (error()) { <p class="uf-error" role="alert">{{ error() }}</p> }
      <mat-card appearance="outlined">
        <mat-card-header>
          <mat-card-title>{{ targetDoc ? 'New revision of ' + targetDoc.title : 'Upload files' }}</mat-card-title>
          <mat-card-subtitle>Pick several files; each becomes a document named after the file. The kind is guessed from the name now and from the content after processing; confirm it on the card.</mat-card-subtitle>
        </mat-card-header>
        <mat-card-content class="uf-form-row">
          <mat-form-field appearance="outline"><mat-label>Building (optional, for all files)</mat-label>
            <mat-select [(ngModel)]="buildingId" name="buildingId">
              <mat-option [value]="null">Project level</mat-option>
              @for (b of buildings(); track b.id) { <mat-option [value]="b.id">{{ b.code }} {{ b.name ?? '' }}</mat-option> }
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline"><mat-label>Source note</mat-label><input matInput [(ngModel)]="note" name="note" placeholder="Rev C from architect" /></mat-form-field>
          <input type="file" #file [multiple]="!targetDoc" accept="application/pdf,image/png,image/jpeg,.dxf,application/dxf,image/vnd.dxf" (change)="onFiles($event)" />
          <button mat-flat-button [disabled]="busy() || !selected.length" (click)="upload()">
            {{ targetDoc ? 'Upload revision' : selected.length > 1 ? 'Upload ' + selected.length + ' files' : 'Upload' }}
          </button>
          @if (targetDoc) { <button mat-button (click)="targetDoc = null; selected = []">Cancel</button> }
        </mat-card-content>
        <mat-card-content class="uf-muted formats">
          Accepted: PDF and PNG/JPG (plans, renders, schedules) and DXF exported from AutoCAD or ArchiCAD (one sheet per layout, scale taken from the drawing units). DWG must be saved as DXF first; IFC and GLB are stored but not processed yet. Any 2D source gives the schematic 3D model; exact 3D needs an IFC export.
        </mat-card-content>
        @if (progress(); as pr) {
          <mat-card-content class="uf-muted formats">{{ pr.done }} of {{ pr.total }} files · {{ pr.current }}</mat-card-content>
          <mat-progress-bar mode="determinate" [value]="((pr.done + pr.fraction) / pr.total) * 100" />
        }
      </mat-card>

      @if (docs().length) {
        <div class="uf-form-row">
          <mat-button-toggle-group [value]="filter()" (change)="filter.set($event.value)" aria-label="Filter">
            <mat-button-toggle value="all">All · {{ docs().length }}</mat-button-toggle>
            <mat-button-toggle value="needs">Needs a kind · {{ needsKind().length }}</mat-button-toggle>
            <mat-button-toggle value="guessed">Guessed, unconfirmed · {{ guessed().length }}</mat-button-toggle>
          </mat-button-toggle-group>
        </div>
      }

      @for (d of shown(); track d.id) {
        <mat-card appearance="outlined" [class.card--needs]="d.kind === 'unclassified'" [class.card--guessed]="isGuessed(d)">
          <mat-card-header>
            <mat-card-title>{{ d.title }}</mat-card-title>
            <mat-card-subtitle>
              <span class="chip" [class.chip--needs]="d.kind === 'unclassified'" [class.chip--guessed]="isGuessed(d)" [class.chip--manual]="d.kind_source === 'manual'">
                {{ kindLabel(d.kind) }} · {{ sourceLabel(d.kind_source) }}
              </span>
              @if (d.current_revision; as r) { · rev {{ r.revision_no }} · {{ r.file_name }} · {{ (r.byte_size ?? 0) / 1048576 | number: '1.0-1' }} MB · {{ r.processing_status }} @if (r.page_count) { · {{ r.page_count }} pages } }
            </mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            @if (d.current_revision?.processing_error) { <p class="uf-error">{{ d.current_revision?.processing_error }}</p> }
            <div class="uf-actions">
              <mat-form-field appearance="outline" class="kind">
                <mat-label>Kind</mat-label>
                <mat-select [value]="d.kind === 'unclassified' ? null : d.kind" (selectionChange)="setKind(d, $event.value)" [disabled]="busy()">
                  @for (k of kinds; track k.value) { <mat-option [value]="k.value">{{ k.label }}</mat-option> }
                </mat-select>
              </mat-form-field>
              @if (isGuessed(d)) { <button mat-stroked-button [disabled]="busy()" (click)="setKind(d, d.kind)">Confirm {{ kindLabel(d.kind) }}</button> }
              <button mat-button (click)="loadSheets(d)">Show sheets</button>
              <button mat-button (click)="newRevision(d)">Upload new revision</button>
              <button mat-button (click)="download(d)">Download</button>
            </div>
            @if (d.kind === 'unclassified') {
              <p class="uf-muted small">The name and the content did not say what this file is. Pick a kind. A project-level file set to Floor plans gets its floor suggestions with the next revision; a file filed under a building already has them.</p>
            }
            @if (sheets()[d.id]; as list) {
              <div class="uf-form-row uf-sets">
                <span class="uf-muted">Map only the plans: exclude reprints, details and schedules.</span>
                @if (reprints(list).length; as n) {
                  <button mat-stroked-button [disabled]="busy()" (click)="exclude(d, reprints(list), true, 'reprint of an earlier page')">Exclude {{ n }} reprint(s)</button>
                }
                <mat-form-field appearance="outline" class="uf-pages"><mat-label>Pages</mat-label>
                  <input matInput [(ngModel)]="pageInput[d.id]" [name]="'pages-' + d.id" placeholder="12-51, 7" />
                </mat-form-field>
                <mat-form-field appearance="outline"><mat-label>Reason</mat-label>
                  <input matInput [(ngModel)]="reasonInput[d.id]" [name]="'reason-' + d.id" placeholder="fire-safety set" />
                </mat-form-field>
                <button mat-button [disabled]="busy() || !pageInput[d.id]" (click)="exclude(d, parsePages(pageInput[d.id]), true, reasonInput[d.id])">Exclude</button>
                <button mat-button [disabled]="busy() || !pageInput[d.id]" (click)="exclude(d, parsePages(pageInput[d.id]), false, null)">Include</button>
              </div>
              <div class="uf-sheets">
                @for (s of list; track s.id) {
                  <a class="uf-sheet" [class.uf-sheet--excluded]="s.excluded" [routerLink]="['../sheets', s.id]" [attr.title]="s.exclusion_reason ?? null">
                    @if (s.thumbnail_url) { <img [src]="s.thumbnail_url" alt="page {{ s.page_no }}" /> } @else { <div class="uf-sheet__ph">p{{ s.page_no }}</div> }
                    <span>Page {{ s.page_no }} · @if (s.excluded) { excluded } @else { {{ s.assignment_status }} · {{ kindOf(s) }} }</span>
                    @if (dupOf(s); as dup) { @if (!s.excluded) { <span class="uf-badge">reprint of p{{ dup }}</span> } }
                  </a>
                }
              </div>
            }
          </mat-card-content>
        </mat-card>
      } @empty {
        <p class="uf-muted">{{ docs().length ? 'Nothing in this filter.' : 'No documents yet.' }}</p>
      }
    </div>
  `,
  styles: `
    .formats { font-size: 0.85rem; padding-top: 0; }
    .small { font-size: 0.85rem; margin: 0.25rem 0; }
    .uf-form-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .uf-actions { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
    .kind { width: 12rem; }
    .chip { display: inline-block; padding: 0.05rem 0.5rem; border-radius: 999px; background: var(--mat-sys-surface-container-high); font-size: 0.8rem; }
    .chip--guessed { background: #fef3c7; color: #92400e; }
    .chip--needs { background: #fee2e2; color: #991b1b; }
    .chip--manual { background: #d1fae5; color: #065f46; }
    .card--needs { border-color: #fca5a5; }
    .card--guessed { border-color: #fcd34d; }
    .uf-sheets { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-top: 0.5rem; }
    .uf-sheet { display: flex; flex-direction: column; gap: 0.25rem; width: 160px; font-size: 0.75rem; text-decoration: none; color: inherit; }
    .uf-sheet--excluded { opacity: 0.45; }
    .uf-badge { align-self: flex-start; padding: 0 0.35rem; border-radius: 4px; background: #fef3c7; }
    .uf-pages { width: 9rem; }
    .uf-sets { margin-top: 0.5rem; }
    .uf-sheet img, .uf-sheet__ph { width: 160px; height: 110px; object-fit: contain; background: #fff; border: 1px solid #e5e7eb; display: grid; place-items: center; }
  `,
})
export class DocumentsPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly docs = signal<DocumentOut[]>([]);
  readonly buildings = signal<BuildingOut[]>([]);
  readonly sheets = signal<Record<string, SheetOut[]>>({});
  readonly busy = signal(false);
  readonly progress = signal<{ done: number; total: number; current: string; fraction: number } | null>(null);
  readonly error = signal<string | null>(null);
  readonly filter = signal<'all' | 'needs' | 'guessed'>('all');
  readonly kinds = KINDS;
  readonly needsKind = computed(() => this.docs().filter((d) => d.kind === 'unclassified'));
  readonly guessed = computed(() => this.docs().filter((d) => this.isGuessed(d)));
  readonly shown = computed(() => {
    const f = this.filter();
    return f === 'needs' ? this.needsKind() : f === 'guessed' ? this.guessed() : this.docs();
  });
  buildingId: string | null = null;
  note = '';
  selected: File[] = [];
  targetDoc: DocumentOut | null = null;

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  async load(): Promise<void> {
    try {
      const [d, b] = await Promise.all([this.api.listDocuments(this.tenantId(), this.projectId()), this.api.listBuildings(this.tenantId(), this.projectId())]);
      this.docs.set(d);
      this.buildings.set(b.filter((x) => x.kind === 'building'));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  pageInput: Record<string, string> = {};
  reasonInput: Record<string, string> = {};

  isGuessed(d: DocumentOut): boolean {
    return d.kind !== 'unclassified' && (d.kind_source === 'filename' || d.kind_source === 'content');
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

  async setKind(d: DocumentOut, kind: string | null): Promise<void> {
    if (!kind) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const updated = await this.api.updateDocument(this.tenantId(), d.id, { kind: kind as Kind });
      this.docs.update((list) => list.map((x) => (x.id === d.id ? updated : x)));
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  async exclude(d: DocumentOut, pages: number[], excluded: boolean, reason: string | null | undefined): Promise<void> {
    if (!d.current_revision_id || !pages.length) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const list = await this.api.excludePages(this.tenantId(), d.current_revision_id, pages, excluded, reason || null);
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
          const ct = file.type || (/\.dxf$/i.test(file.name) ? 'application/dxf' : 'application/octet-stream');
          const intent = await this.api.createUpload(this.tenantId(), doc.id, { file_name: file.name, content_type: ct, byte_size: file.size, source_note: this.note || null });
          await this.api.uploadToPresignedUrl(intent.upload_url, file, ct, (p) => this.progress.set({ done, total: files.length, current: file.name, fraction: p }));
          await this.api.completeUpload(this.tenantId(), intent.revision.id);
        } catch (e) {
          failed.push(`${file.name}: ${problemMessage(e)}`);
        }
        done++;
      }
      if (failed.length) this.error.set(`${failed.length} of ${files.length} files failed. ${failed.join(' · ')}`);
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

  async download(d: DocumentOut): Promise<void> {
    if (!d.current_revision_id) return;
    const r = await this.api.revisionDownloadUrl(this.tenantId(), d.current_revision_id);
    window.open(r.url, '_blank');
  }
}
