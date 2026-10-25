import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatListModule } from '@angular/material/list';
import { Router, RouterLink } from '@angular/router';
import { PermitAttachmentOut, PermitPreviewOut, ProjectOut, UnitformaApi, problemMessage } from 'api-client';

const KIND_LABELS: Record<string, string> = {
  site_plan: 'Site plan',
  floor_plan: 'Floor plans',
  section: 'Sections',
  elevation: 'Facades',
  render: 'Renders',
  permit: 'Permit file',
};

/** Projects: create one by hand, or start from a public building permit (ADR-0007). */
@Component({
  selector: 'uf-projects-page',
  imports: [DecimalPipe, FormsModule, MatCardModule, MatFormFieldModule, MatInputModule, MatButtonModule, MatListModule, RouterLink],
  template: `
    <div class="uf-page">
      <mat-card appearance="outlined">
        <mat-card-header><mat-card-title>New project</mat-card-title></mat-card-header>
        <mat-card-content class="uf-form-row">
          <mat-form-field appearance="outline"><mat-label>Slug</mat-label><input matInput [(ngModel)]="slug" name="slug" /></mat-form-field>
          <mat-form-field appearance="outline"><mat-label>Name</mat-label><input matInput [(ngModel)]="name" name="name" /></mat-form-field>
          <button mat-flat-button [disabled]="busy()" (click)="create()">Create</button>
        </mat-card-content>
        @if (error()) { <mat-card-footer><p class="uf-error">{{ error() }}</p></mat-card-footer> }
      </mat-card>

      @if (permitAvailable()) {
        <mat-card appearance="outlined">
          <mat-card-header>
            <mat-card-title>Start from a building permit</mat-card-title>
            <mat-card-subtitle>Tbilisi Architecture Service (tas.ge): the permit record and its current drawings become a project</mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            <div class="uf-form-row">
              <mat-form-field appearance="outline" class="wide">
                <mat-label>Permit page address or document id</mat-label>
                <input matInput [(ngModel)]="reference" name="reference" placeholder="https://tas.ge/?p=publicpage&documentId=…" (keyup.enter)="previewPermit()" />
              </mat-form-field>
              <button mat-stroked-button [disabled]="permitBusy() || !reference.trim()" (click)="previewPermit()">Preview</button>
            </div>
            <p class="uf-muted small">Only the document id is used; the record is fetched once per click from the registry. Personal data in the permit (names, personal numbers, phones) is never stored.</p>
            @if (permitError()) { <p class="uf-error" role="alert">{{ permitError() }}</p> }

            @if (permitPreview(); as p) {
              <div class="facts">
                <div><span class="uf-muted">Permit</span><strong>{{ p.permit['application_no'] || '—' }}</strong></div>
                <div><span class="uf-muted">Status</span><strong>{{ p.permit['status'] }}</strong></div>
                <div><span class="uf-muted">Decided</span><strong>{{ day(p.permit['decided_at']) }}</strong></div>
                <div><span class="uf-muted">Category</span><strong>{{ p.nomenclature['category'] || '—' }}</strong></div>
                <div><span class="uf-muted">Class</span><strong>{{ p.nomenclature['class'] || '—' }}</strong></div>
                <div><span class="uf-muted">Address</span><strong>{{ p.permit['address'] || '—' }}</strong></div>
                <div><span class="uf-muted">Height above 0.00</span><strong>{{ p.heights['above_zero_m'] ?? '—' }} m</strong></div>
                <div><span class="uf-muted">Depth below 0.00</span><strong>{{ p.heights['below_zero_m'] ?? '—' }} m</strong></div>
                @for (x of p.parcels; track x['cadastral_code']) {
                  <div><span class="uf-muted">Parcel</span><strong>{{ x['cadastral_code'] }} · {{ num(x['area_m2']) | number }} m²</strong></div>
                }
              </div>
              @if (p.technical_indicators.length) {
                <details>
                  <summary>Technical indicators · {{ p.technical_indicators.length }}</summary>
                  <table class="uf-table plain">
                    @for (t of p.technical_indicators; track t['field_id']) {
                      <tr><td>{{ t['label'] }}</td><td class="num">{{ num(t['value']) | number: '1.0-2' }}</td></tr>
                    }
                  </table>
                </details>
              }

              <h3>Files · {{ p.counts['import'] }} will be imported, {{ p.counts['skip'] }} skipped</h3>
              <p class="uf-muted small">The newest file of each permit section is taken. Floor plans, sections and facades go through the same review as an upload; ArchiCAD and archive files cannot be read and must be exported by the developer as PDF, DXF or IFC.</p>
              <table class="uf-table plain">
                @for (a of p.attachments; track a.attached_file_id) {
                  <tr [class.skipped]="a.skip_reason">
                    <td>{{ kindLabel(a) }}</td>
                    <td>{{ a.file_name }}</td>
                    <td class="uf-muted">{{ a.fieldset }}</td>
                    <td>@if (a.skip_reason) { <span class="uf-muted">skipped: {{ a.skip_reason }}</span> } @else { <span class="uf-av-available">import</span> }</td>
                  </tr>
                }
              </table>

              <h3>Project to create</h3>
              <div class="uf-form-row">
                <mat-form-field appearance="outline"><mat-label>Slug</mat-label><input matInput [(ngModel)]="permitSlug" name="permitSlug" /></mat-form-field>
                <mat-form-field appearance="outline" class="wide"><mat-label>Name</mat-label><input matInput [(ngModel)]="permitName" name="permitName" /></mat-form-field>
                <mat-form-field appearance="outline"><mat-label>Building code</mat-label><input matInput [(ngModel)]="permitBuilding" name="permitBuilding" /></mat-form-field>
                <button mat-flat-button [disabled]="permitBusy()" (click)="importPermit()">Import</button>
              </div>
              <p class="uf-muted small">Creates the project with its address and one building. Floors are added by you on the project page (the heights above are the hint); the drawings arrive in Documents within a minute and propose floors from their level markers.</p>
            }
          </mat-card-content>
        </mat-card>
      }

      <mat-nav-list>
        @for (p of projects(); track p.id) {
          <a mat-list-item [routerLink]="[p.id]">
            <span matListItemTitle>{{ p.name }}</span>
            <span matListItemLine>{{ p.slug }} · {{ p.status }} · {{ p.currency }}@if (p.regulatory?.['application_no']) { · permit {{ p.regulatory['application_no'] }} }</span>
          </a>
        } @empty {
          <p class="uf-muted">No projects yet.</p>
        }
      </mat-nav-list>
    </div>
  `,
  styles: `
    .uf-form-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .wide { min-width: 24rem; flex: 1; }
    .small { font-size: 0.85rem; margin: 0.25rem 0 0.5rem; }
    .facts { display: grid; grid-template-columns: repeat(auto-fill, minmax(14rem, 1fr)); gap: 0.5rem 1rem; margin: 0.5rem 0; }
    .facts div { display: grid; }
    .facts span { font-size: 0.8rem; }
    .plain { width: 100%; border-collapse: collapse; }
    .plain td { padding: 0.2rem 0.5rem; border-bottom: 1px solid var(--mat-sys-outline-variant); vertical-align: top; }
    .num { text-align: right; white-space: nowrap; }
    .skipped td { opacity: 0.65; }
    h3 { margin: 1rem 0 0.25rem; font-size: 1rem; }
    details summary { cursor: pointer; margin: 0.5rem 0; }
  `,
})
export class ProjectsPage {
  private readonly api = inject(UnitformaApi);
  private readonly router = inject(Router);
  readonly tenantId = input.required<string>();
  readonly projects = signal<ProjectOut[]>([]);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  slug = '';
  name = '';

  // permit import (ADR-0007)
  readonly permitPreview = signal<PermitPreviewOut | null>(null);
  readonly permitBusy = signal(false);
  readonly permitError = signal<string | null>(null);
  /** The backend answers 404 when the installation has the import switched off. */
  readonly permitDisabled = signal(false);
  readonly permitAvailable = computed(() => !this.permitDisabled());
  reference = '';
  permitSlug = '';
  permitName = '';
  permitBuilding = '';

  constructor() {
    toObservable(this.tenantId).subscribe(() => void this.load());
  }

  async load(): Promise<void> {
    try {
      this.projects.set(await this.api.listProjects(this.tenantId()));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  async create(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.createProject(this.tenantId(), { slug: this.slug, name: this.name });
      this.slug = this.name = '';
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  kindLabel(a: PermitAttachmentOut): string {
    return KIND_LABELS[a.kind] ?? a.kind;
  }

  num(v: unknown): number | null {
    return typeof v === 'number' ? v : null;
  }

  day(v: unknown): string {
    return typeof v === 'string' && v ? v.slice(0, 10) : '—';
  }

  async previewPermit(): Promise<void> {
    this.permitBusy.set(true);
    this.permitError.set(null);
    this.permitPreview.set(null);
    try {
      const p = await this.api.previewPermit(this.tenantId(), this.reference.trim());
      this.permitPreview.set(p);
      this.permitSlug = p.suggestions['slug'] ?? '';
      this.permitName = p.suggestions['name'] ?? '';
      this.permitBuilding = p.suggestions['building_code'] ?? 'A';
    } catch (e) {
      const status = (e as { status?: number })?.status;
      if (status === 404 && /disabled/i.test(problemMessage(e))) this.permitDisabled.set(true);
      this.permitError.set(problemMessage(e));
    } finally {
      this.permitBusy.set(false);
    }
  }

  async importPermit(): Promise<void> {
    this.permitBusy.set(true);
    this.permitError.set(null);
    try {
      const res = await this.api.importPermit(this.tenantId(), {
        reference: this.reference.trim(),
        slug: this.permitSlug || null,
        name: this.permitName || null,
        building_code: this.permitBuilding || null,
      });
      await this.router.navigate(['/t', this.tenantId(), 'projects', res.project.id]);
    } catch (e) {
      this.permitError.set(problemMessage(e));
    } finally {
      this.permitBusy.set(false);
    }
  }
}
