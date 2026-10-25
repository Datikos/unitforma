import { DecimalPipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  PermitAttachmentOut,
  PermitPreviewOut,
  ProjectOut,
  UnitformaApi,
  problemMessage,
} from 'api-client';
import {
  EmptyStateComponent,
  Fact,
  FactsComponent,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
  dayOf,
  labelOf,
} from 'ui';
import { TenantContext } from '../core/tenant-context';
import { ToastService } from '../ui/toast.service';

/** Projects: create one by hand, or start from a public building permit (ADR-0007). */
@Component({
  selector: 'uf-projects-page',
  imports: [
    DecimalPipe,
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
      <uf-page-header
        title="Projects"
        icon="lucideFolderKanban"
        [facts]="[
          { label: 'Projects', value: projects().length },
          { domain: 'project', status: 'active', value: activeCount() + ' active' },
        ]"
      />
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }

      <div class="uf-grid2">
        <uf-section-card
          title="New project"
          icon="lucidePlus"
          summary="slug and name"
          storageKey="projects-new"
          [open]="projects().length === 0"
        >
          <div class="uf-form-row">
            <mat-form-field appearance="outline" subscriptSizing="dynamic"
              ><mat-label>Slug</mat-label
              ><input
                matInput
                [(ngModel)]="slug"
                name="slug"
                placeholder="green-hills"
                (keyup.enter)="create()"
              /><mat-hint>Part of the portal address</mat-hint></mat-form-field
            >
            <mat-form-field appearance="outline" subscriptSizing="dynamic"
              ><mat-label>Name</mat-label
              ><input
                matInput
                [(ngModel)]="name"
                name="name"
                placeholder="Green Hills"
                (keyup.enter)="create()"
            /></mat-form-field>
            <button
              mat-flat-button
              [disabled]="busy() || !slug.trim() || !name.trim()"
              (click)="create()"
            >
              Create
            </button>
          </div>
        </uf-section-card>

        @if (permitAvailable()) {
          <uf-section-card
            title="Start from a building permit"
            icon="lucideScrollText"
            summary="Tbilisi Architecture Service (tas.ge)"
            storageKey="projects-permit"
            [open]="projects().length === 0 || !!permitPreview()"
          >
            <p class="uf-hint">
              Paste a tas.ge permit address. The permit record and its current drawings become a
              project. Only the document id is used; personal data in the permit is never stored.
            </p>
            <div class="uf-form-row">
              <mat-form-field appearance="outline" subscriptSizing="dynamic" class="wide">
                <mat-label>Permit page address or document id</mat-label>
                <input
                  matInput
                  [(ngModel)]="reference"
                  name="reference"
                  placeholder="https://tas.ge/?p=publicpage&documentId=…"
                  (keyup.enter)="previewPermit()"
                />
              </mat-form-field>
              <button
                mat-stroked-button
                [disabled]="permitBusy() || !reference.trim()"
                (click)="previewPermit()"
              >
                <ng-icon name="lucideSearch" /> Preview
              </button>
            </div>
            @if (permitError(); as e) {
              <div class="uf-alert uf-alert--bad" role="alert">
                <ng-icon name="lucideCircleX" />{{ e }}
              </div>
            }

            @if (permitPreview(); as p) {
              <uf-facts [facts]="permitFacts(p)" />
              @if (p.technical_indicators.length) {
                <details>
                  <summary class="uf-link">
                    Technical indicators · {{ p.technical_indicators.length }}
                  </summary>
                  <table class="uf-plain">
                    @for (t of p.technical_indicators; track t['field_id']) {
                      <tr>
                        <td>{{ t['label'] }}</td>
                        <td class="uf-num">{{ num(t['value']) | number: '1.0-2' }}</td>
                      </tr>
                    }
                  </table>
                </details>
              }
              <h3 class="files">
                Files · {{ p.counts['import'] }} will be imported, {{ p.counts['skip'] }} skipped
              </h3>
              <p class="uf-hint">
                The newest file of each permit section is taken. Floor plans, sections and facades
                go through the same review as an upload; ArchiCAD and archive files cannot be read
                and must be exported by the developer as PDF, DXF or IFC.
              </p>
              <table class="uf-plain">
                @for (a of p.attachments; track a.attached_file_id) {
                  <tr [class.skipped]="a.skip_reason">
                    <td>
                      <span class="uf-chip">{{ kindLabel(a) }}</span>
                    </td>
                    <td>{{ a.file_name }}</td>
                    <td class="uf-muted">{{ a.fieldset }}</td>
                    <td>
                      @if (a.skip_reason) {
                        <span class="uf-chip uf-tone-neutral">skipped: {{ a.skip_reason }}</span>
                      } @else {
                        <span class="uf-chip uf-tone-good"
                          ><ng-icon name="lucideCheck" />import</span
                        >
                      }
                    </td>
                  </tr>
                }
              </table>
              <h3 class="files">Project to create</h3>
              <div class="uf-form-row">
                <mat-form-field appearance="outline" subscriptSizing="dynamic"
                  ><mat-label>Slug</mat-label
                  ><input matInput [(ngModel)]="permitSlug" name="permitSlug"
                /></mat-form-field>
                <mat-form-field appearance="outline" subscriptSizing="dynamic" class="wide"
                  ><mat-label>Name</mat-label
                  ><input matInput [(ngModel)]="permitName" name="permitName"
                /></mat-form-field>
                <mat-form-field appearance="outline" subscriptSizing="dynamic" class="short"
                  ><mat-label>Building code</mat-label
                  ><input matInput [(ngModel)]="permitBuilding" name="permitBuilding"
                /></mat-form-field>
                <button mat-flat-button [disabled]="permitBusy()" (click)="importPermit()">
                  <ng-icon name="lucideDownload" /> Import
                </button>
              </div>
              <p class="uf-hint">
                Creates the project with its address and one building. Floors are added by you on
                the project page (the heights above are the hint); the drawings arrive in Documents
                within a minute and propose floors from their level markers.
              </p>
            }
          </uf-section-card>
        }
      </div>

      @if (projects().length > 0) {
        <div class="uf-filterbar">
          <mat-form-field appearance="outline" subscriptSizing="dynamic" class="search">
            <ng-icon matPrefix name="lucideSearch" />
            <input
              matInput
              [ngModel]="query()"
              (ngModelChange)="query.set($event)"
              placeholder="Search name, slug or permit…"
              aria-label="Search projects"
            />
          </mat-form-field>
          <span class="uf-count">{{ shown().length }} of {{ projects().length }}</span>
        </div>
        <div class="uf-grid3">
          @for (p of shown(); track p.id) {
            <a class="uf-card card uf-quiet" [routerLink]="[p.id]">
              <div class="card__head">
                <strong class="card__name">{{ p.name }}</strong>
                <uf-status-chip domain="project" [value]="p.status" />
              </div>
              <div class="uf-muted uf-small">{{ p.slug }} · {{ p.currency }}</div>
              @if (p.regulatory?.['application_no']) {
                <div class="uf-small">
                  <ng-icon name="lucideScrollText" class="ic" /> permit
                  {{ p.regulatory['application_no'] }}
                </div>
              }
              <span class="card__go">Open <ng-icon name="lucideArrowRight" /></span>
            </a>
          } @empty {
            <uf-empty-state
              icon="lucideSearch"
              title="Nothing matches"
              text="Try another name or slug."
              [compact]="true"
            />
          }
        </div>
      } @else {
        <uf-empty-state
          icon="lucideFolderKanban"
          title="No projects yet"
          text="Create one above with a slug and a name, or paste a tas.ge permit address and import the project with its drawings."
        />
      }
    </div>
  `,
  styles: `
    .wide {
      min-width: 22rem;
      flex: 1;
    }
    .short {
      width: 9rem;
    }
    .search {
      min-width: 280px;
    }
    .search ng-icon {
      margin: 0 0.25rem 0 0.5rem;
      color: var(--uf-muted);
    }
    .files {
      margin: 0.75rem 0 0.25rem;
      font-size: 0.95rem;
    }
    .skipped td {
      opacity: 0.6;
    }
    details summary {
      cursor: pointer;
      margin: 0.25rem 0;
    }
    .card {
      display: grid;
      gap: 0.35rem;
      align-content: start;
      transition:
        box-shadow 0.15s,
        border-color 0.15s;
    }
    .card:hover {
      box-shadow: var(--uf-shadow-lg);
      border-color: var(--uf-primary);
    }
    .card__head {
      display: flex;
      justify-content: space-between;
      gap: 0.5rem;
      align-items: center;
    }
    .card__name {
      font-size: 1.05rem;
    }
    .card__go {
      color: var(--uf-primary);
      font-weight: 600;
      font-size: 0.85rem;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
      margin-top: 0.25rem;
    }
    .ic {
      vertical-align: -0.15em;
      color: var(--uf-muted);
    }
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class ProjectsPage {
  private readonly api = inject(UnitformaApi);
  private readonly router = inject(Router);
  private readonly tenantCtx = inject(TenantContext);
  private readonly toast = inject(ToastService);
  readonly tenantId = input.required<string>();
  readonly projects = signal<ProjectOut[]>([]);
  readonly query = signal('');
  readonly shown = computed(() => {
    const q = this.query().trim().toLowerCase();
    return q
      ? this.projects().filter((p) =>
          `${p.name} ${p.slug} ${p.regulatory?.['application_no'] ?? ''}`.toLowerCase().includes(q),
        )
      : this.projects();
  });
  readonly activeCount = computed(
    () => this.projects().filter((p) => p.status === 'active').length,
  );
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
    if (!this.slug.trim() || !this.name.trim()) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const p = await this.api.createProject(this.tenantId(), {
        slug: this.slug.trim(),
        name: this.name.trim(),
      });
      this.slug = this.name = '';
      this.toast.ok(`Project ${p.name} created`);
      await this.load();
      void this.tenantCtx.refreshProjects();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  permitFacts(p: PermitPreviewOut): Fact[] {
    return [
      { label: 'Permit', value: String(p.permit['application_no'] ?? '') },
      { label: 'Status', value: String(p.permit['status'] ?? '') },
      { label: 'Decided', value: dayOf(this.day(p.permit['decided_at'])) },
      { label: 'Category', value: String(p.nomenclature['category'] ?? '') },
      { label: 'Class', value: String(p.nomenclature['class'] ?? '') },
      { label: 'Address', value: String(p.permit['address'] ?? '') },
      { label: 'Height above 0.00', value: p.heights['above_zero_m'] ?? null, unit: 'm' },
      { label: 'Depth below 0.00', value: p.heights['below_zero_m'] ?? null, unit: 'm' },
      ...p.parcels.map((x) => ({
        label: 'Parcel',
        value: `${x['cadastral_code']} · ${this.num(x['area_m2']) ?? '?'} m²`,
      })),
    ];
  }

  kindLabel(a: PermitAttachmentOut): string {
    return labelOf('document.kind', a.kind);
  }

  num(v: unknown): number | null {
    return typeof v === 'number' ? v : null;
  }

  day(v: unknown): string | null {
    return typeof v === 'string' && v ? v : null;
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
      this.toast.ok('Project created from the permit; drawings are being imported');
      void this.tenantCtx.refreshProjects();
      await this.router.navigate(['/t', this.tenantId(), 'projects', res.project.id]);
    } catch (e) {
      this.permitError.set(problemMessage(e));
    } finally {
      this.permitBusy.set(false);
    }
  }
}
