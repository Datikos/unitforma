import { DecimalPipe } from '@angular/common';
import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { BuildingOut, DocumentOut, SheetOut, UnitformaApi, problemMessage } from 'api-client';
import { parsePages } from '../core/page-ranges';

type Kind = 'site_plan' | 'floor_plan' | 'section' | 'elevation' | 'render' | 'schedule' | 'model_ifc' | 'model_glb' | 'texture' | 'permit' | 'other';

/** Project documents: upload revisions (presigned PUT), processing status, sheets (plan §13.1 steps 1–2). */
@Component({
  selector: 'uf-documents-page',
  imports: [FormsModule, DecimalPipe, MatCardModule, MatFormFieldModule, MatInputModule, MatSelectModule, MatButtonModule, MatProgressBarModule, RouterLink],
  template: `
    <div class="uf-page">
      <div class="uf-page-header"><h2>Documents</h2><a mat-stroked-button [routerLink]="['..']">Back to project</a></div>
      @if (error()) { <p class="uf-error">{{ error() }}</p> }
      <mat-card appearance="outlined">
        <mat-card-header><mat-card-title>Upload a document</mat-card-title></mat-card-header>
        <mat-card-content class="uf-form-row">
          <mat-form-field appearance="outline"><mat-label>Kind</mat-label>
            <mat-select [(ngModel)]="kind" name="kind">
              <mat-option value="site_plan">Site plan</mat-option><mat-option value="floor_plan">Floor plans</mat-option>
              <mat-option value="section">Sections</mat-option><mat-option value="elevation">Elevations</mat-option>
              <mat-option value="render">Renders</mat-option><mat-option value="schedule">Area schedule</mat-option>
              <mat-option value="permit">Permit document</mat-option><mat-option value="other">Other</mat-option>
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline"><mat-label>Building (optional)</mat-label>
            <mat-select [(ngModel)]="buildingId" name="buildingId">
              <mat-option [value]="null">Project level</mat-option>
              @for (b of buildings(); track b.id) { <mat-option [value]="b.id">{{ b.code }} {{ b.name ?? '' }}</mat-option> }
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline"><mat-label>Title</mat-label><input matInput [(ngModel)]="title" name="title" /></mat-form-field>
          <mat-form-field appearance="outline"><mat-label>Source note</mat-label><input matInput [(ngModel)]="note" name="note" placeholder="Rev C from architect" /></mat-form-field>
          <input type="file" #file accept="application/pdf,image/png,image/jpeg,.dxf,application/dxf,image/vnd.dxf" (change)="onFile($event)" />
          <button mat-flat-button [disabled]="busy() || !selected" (click)="upload()">Upload</button>
        </mat-card-content>
        <mat-card-content class="uf-muted formats">
          Accepted: PDF and PNG/JPG (plans, renders, schedules) and DXF exported from AutoCAD or ArchiCAD (one sheet per layout, scale taken from the drawing units). DWG must be saved as DXF first; IFC and GLB are stored but not processed yet. Any 2D source gives the schematic 3D model; exact 3D needs an IFC export.
        </mat-card-content>
        @if (progress() !== null) { <mat-progress-bar mode="determinate" [value]="(progress() ?? 0) * 100" /> }
      </mat-card>

      @for (d of docs(); track d.id) {
        <mat-card appearance="outlined">
          <mat-card-header>
            <mat-card-title>{{ d.title }}</mat-card-title>
            <mat-card-subtitle>{{ d.kind }} @if (d.current_revision; as r) { · rev {{ r.revision_no }} · {{ r.file_name }} · {{ (r.byte_size ?? 0) / 1048576 | number: '1.0-1' }} MB · {{ r.processing_status }} @if (r.page_count) { · {{ r.page_count }} pages } }</mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            @if (d.current_revision?.processing_error) { <p class="uf-error">{{ d.current_revision?.processing_error }}</p> }
            <div class="uf-actions">
              <button mat-button (click)="loadSheets(d)">Show sheets</button>
              <button mat-button (click)="newRevision(d)">Upload new revision</button>
              <button mat-button (click)="download(d)">Download</button>
            </div>
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
      } @empty { <p class="uf-muted">No documents yet.</p> }
    </div>
  `,
  styles: `
    .formats { font-size: 0.85rem; padding-top: 0; }
    .uf-form-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .uf-actions { display: flex; gap: 0.5rem; }
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
  readonly progress = signal<number | null>(null);
  readonly error = signal<string | null>(null);
  kind: Kind = 'floor_plan';
  buildingId: string | null = null;
  title = '';
  note = '';
  selected: File | null = null;
  private targetDoc: DocumentOut | null = null;

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

  dupOf(s: SheetOut): number | null {
    return ((s.hints ?? {}) as { duplicate_of?: number }).duplicate_of ?? null;
  }

  reprints(list: SheetOut[]): number[] {
    return list.filter((s) => !s.excluded && this.dupOf(s) !== null).map((s) => s.page_no);
  }

  readonly parsePages = parsePages;

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

  onFile(ev: Event): void {
    const f = (ev.target as HTMLInputElement).files?.[0] ?? null;
    this.selected = f;
    if (f && !this.title) this.title = f.name.replace(/\.[^.]+$/, '');
  }

  newRevision(d: DocumentOut): void {
    this.targetDoc = d;
    this.title = d.title;
    this.kind = d.kind as Kind;
    this.buildingId = d.building_id ?? null;
  }

  async upload(): Promise<void> {
    const file = this.selected;
    if (!file) return;
    this.busy.set(true);
    this.error.set(null);
    this.progress.set(0);
    try {
      const doc = this.targetDoc ?? (await this.api.createDocument(this.tenantId(), this.projectId(), { kind: this.kind, title: this.title || file.name, building_id: this.buildingId, visibility: 'internal', source: {} }));
      const ct = file.type || (/\.dxf$/i.test(file.name) ? 'application/dxf' : 'application/octet-stream');
      const intent = await this.api.createUpload(this.tenantId(), doc.id, { file_name: file.name, content_type: ct, byte_size: file.size, source_note: this.note || null });
      await this.api.uploadToPresignedUrl(intent.upload_url, file, ct, (p) => this.progress.set(p));
      await this.api.completeUpload(this.tenantId(), intent.revision.id);
      this.selected = null;
      this.targetDoc = null;
      this.title = this.note = '';
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
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
