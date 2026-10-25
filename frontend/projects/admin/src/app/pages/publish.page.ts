import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  ProjectOut,
  PublicationOut,
  ReadinessOut,
  TenantOut,
  UnitformaApi,
  problemMessage,
} from 'api-client';
import {
  EmptyStateComponent,
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
  whenShort,
} from 'ui';
import { ProjectContext } from '../core/project-context';
import { DialogsService } from '../ui/dialogs.service';
import { ToastService } from '../ui/toast.service';

interface PortalForm {
  hero_text: string;
  construction_stage: string;
  completion: string;
}

interface BrandingForm {
  display_name: string;
  tagline: string;
  primary_color: string;
  accent_color: string;
  contact_email: string;
  contact_phone: string;
  website: string;
  legal_text: string;
}

const BRANDING_KEYS: (keyof BrandingForm)[] = [
  'display_name',
  'tagline',
  'primary_color',
  'accent_color',
  'contact_email',
  'contact_phone',
  'website',
  'legal_text',
];

/** Where a readiness item is fixed, by key fragment. */
const FIX_LINKS: [RegExp, string, string][] = [
  [/price|inventory|avail/i, 'inventory', 'Open inventory'],
  [/media|render|photo/i, 'inventory', 'Open inventory'],
  [/place|site/i, 'placement', 'Open site placement'],
  [/floor|building|structure/i, '.', 'Open overview'],
  [/sheet|map|verif|unit/i, 'documents', 'Open documents'],
];

/** Publication workspace (plan §9.3, J5): readiness → preview → publish; unpublish; portal text and branding. */
@Component({
  selector: 'uf-publish-page',
  imports: [
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    NgIcon,
    PageHeaderComponent,
    SectionCardComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="Publish" icon="lucideRocket" [facts]="facts()">
        <ng-container actions>
          @if (readiness()?.portal_url; as url) {
            <a mat-stroked-button [href]="url" target="_blank" rel="noopener"
              ><ng-icon name="lucideExternalLink" /> Open portal</a
            >
          }
          @if (readiness(); as r) {
            <button mat-stroked-button [disabled]="busy() || !r.ok" (click)="run('preview')">
              <ng-icon name="lucideEye" /> Preview
            </button>
            <button mat-flat-button [disabled]="busy() || !r.ok" (click)="run('publish')">
              <ng-icon name="lucideRocket" />
              {{ r.published_version ? 'Publish new version' : 'Publish' }}
            </button>
          }
        </ng-container>
      </uf-page-header>
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }

      @if (readiness(); as r) {
        <uf-section-card
          title="Readiness"
          icon="lucideClipboardCheck"
          [summary]="readinessSummary(r)"
          storageKey="publish-readiness"
        >
          <div actions>
            <uf-status-chip
              domain="readiness"
              [value]="r.ok ? 'ok' : 'error'"
              [label]="r.ok ? 'Ready to publish' : 'Not ready'"
            />
          </div>
          <ul class="checks">
            @for (i of r.items; track i.key) {
              <li>
                <uf-status-chip domain="readiness" [value]="i.level" />
                <span
                  >{{ i.message }}
                  @if (i.count !== null && i.count !== undefined && i.key !== 'units') {
                    <span class="uf-muted"> ({{ i.count }})</span>
                  }
                </span>
                @if (i.level !== 'ok' && fixLink(i.key); as fx) {
                  <a [routerLink]="'../' + fx[0]" class="fix"
                    >{{ fx[1] }} <ng-icon name="lucideArrowRight"
                  /></a>
                }
              </li>
            }
          </ul>
          <div class="uf-actions">
            <button mat-stroked-button [disabled]="busy()" (click)="markAll('published')">
              <ng-icon name="lucideGlobe" /> Mark all approved units public
            </button>
            <button mat-button [disabled]="busy()" (click)="markAll('unpublished')">
              <ng-icon name="lucideEyeOff" /> Withdraw all units
            </button>
            <span class="uf-hint"
              >Single units: select them in the inventory grid. Blocking items must be fixed;
              warnings can be published with.</span
            >
          </div>
          @if (r.published_version) {
            <div class="uf-actions">
              <button mat-button [disabled]="busy()" (click)="unpublish()">
                <ng-icon name="lucideBan" /> Unpublish
              </button>
              <span class="uf-hint"
                >Takes the project off the portal; buyers see "coming soon" until the next
                publish.</span
              >
            </div>
          }
        </uf-section-card>
      }

      <div class="uf-grid2">
        <uf-section-card
          title="Project page text"
          icon="lucidePencil"
          [summary]="textSummary()"
          storageKey="publish-text"
        >
          <p class="uf-hint">Applies from the next publication.</p>
          <mat-form-field appearance="outline" class="wide"
            ><mat-label>Headline</mat-label
            ><textarea
              matInput
              rows="2"
              [(ngModel)]="portal.hero_text"
              name="hero"
              maxlength="2000"
            ></textarea>
          </mat-form-field>
          <div class="uf-form-row">
            <mat-form-field appearance="outline"
              ><mat-label>Construction stage</mat-label
              ><input
                matInput
                [(ngModel)]="portal.construction_stage"
                name="stage"
                maxlength="80"
                placeholder="e.g. frame complete"
            /></mat-form-field>
            <mat-form-field appearance="outline"
              ><mat-label>Completion</mat-label
              ><input
                matInput
                [(ngModel)]="portal.completion"
                name="completion"
                maxlength="80"
                placeholder="e.g. Q4 2027"
            /></mat-form-field>
          </div>
          <div class="uf-actions">
            <button mat-flat-button [disabled]="busy()" (click)="savePortal()">Save text</button>
          </div>
        </uf-section-card>

        <uf-section-card
          title="Branding"
          icon="lucideSparkles"
          [summary]="brandSummary()"
          storageKey="publish-branding"
        >
          <p class="uf-hint">
            Company-wide: applies to every project's portal. Tenant administrators only.
          </p>
          <div class="uf-form-row">
            <mat-form-field appearance="outline"
              ><mat-label>Display name</mat-label
              ><input matInput [(ngModel)]="brand.display_name" name="bname" maxlength="120"
            /></mat-form-field>
            <mat-form-field appearance="outline" class="grow"
              ><mat-label>Tagline</mat-label
              ><input matInput [(ngModel)]="brand.tagline" name="btag" maxlength="200"
            /></mat-form-field>
          </div>
          <div class="uf-form-row colors">
            <label class="color"
              ><input type="color" [(ngModel)]="brand.primary_color" name="bprim" /> Primary
              <code>{{ brand.primary_color }}</code></label
            >
            <label class="color"
              ><input type="color" [(ngModel)]="brand.accent_color" name="bacc" /> Accent
              <code>{{ brand.accent_color }}</code></label
            >
            <span class="swatch" [style.background]="brand.primary_color"
              ><span class="swatch__accent" [style.background]="brand.accent_color"></span>
              preview</span
            >
          </div>
          <div class="uf-form-row">
            <mat-form-field appearance="outline"
              ><mat-label>Sales e-mail</mat-label
              ><input matInput type="email" [(ngModel)]="brand.contact_email" name="bmail"
            /></mat-form-field>
            <mat-form-field appearance="outline"
              ><mat-label>Sales phone</mat-label
              ><input matInput [(ngModel)]="brand.contact_phone" name="bphone" maxlength="50"
            /></mat-form-field>
            <mat-form-field appearance="outline" class="grow"
              ><mat-label>Website (https://…)</mat-label
              ><input matInput [(ngModel)]="brand.website" name="bweb"
            /></mat-form-field>
          </div>
          <mat-form-field appearance="outline" class="wide"
            ><mat-label>Legal text (footer)</mat-label
            ><textarea
              matInput
              rows="3"
              [(ngModel)]="brand.legal_text"
              name="blegal"
              maxlength="4000"
            ></textarea>
          </mat-form-field>
          <div class="uf-actions">
            <button mat-flat-button [disabled]="busy()" (click)="saveBranding()">
              Save branding
            </button>
          </div>
        </uf-section-card>
      </div>

      <uf-section-card
        title="Publications"
        icon="lucideHistory"
        [count]="publications().length"
        [summary]="
          publications()[0]
            ? 'latest v' + publications()[0].version_no + ' · ' + when(publications()[0].created_at)
            : 'nothing built yet'
        "
        [flush]="true"
        storageKey="publish-history"
      >
        @if (publications().length) {
          <table class="uf-plain">
            <thead>
              <tr>
                <th>Version</th>
                <th>Status</th>
                <th>Built</th>
                <th>Published</th>
                <th class="uf-num">Units</th>
                <th class="uf-num">Available</th>
              </tr>
            </thead>
            <tbody>
              @for (p of publications(); track p.id) {
                <tr>
                  <td>
                    <strong>v{{ p.version_no }}</strong>
                  </td>
                  <td><uf-status-chip domain="publication" [value]="p.status" /></td>
                  <td>{{ when(p.created_at) }}</td>
                  <td>{{ when(p.published_at) }}</td>
                  <td class="uf-num">{{ p.summary['units'] }}</td>
                  <td class="uf-num">{{ p.summary['available'] }}</td>
                </tr>
              }
            </tbody>
          </table>
        } @else {
          <uf-empty-state
            icon="lucideRocket"
            title="Nothing published yet"
            text="Fix the blocking readiness items, preview, then publish. Each publish is an immutable, numbered snapshot."
            [compact]="true"
          />
        }
      </uf-section-card>
    </div>
  `,
  styles: `
    .checks {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 0.4rem;
    }
    .checks li {
      display: flex;
      gap: 0.6rem;
      align-items: center;
      flex-wrap: wrap;
    }
    .fix {
      margin-left: auto;
      color: var(--uf-primary);
      text-decoration: none;
      font-size: 0.85rem;
      font-weight: 600;
      display: inline-flex;
      align-items: center;
      gap: 0.2rem;
    }
    .wide {
      width: 100%;
    }
    .grow {
      flex: 1;
      min-width: 14rem;
    }
    .color {
      display: inline-flex;
      gap: 0.5rem;
      align-items: center;
      font-size: 0.9rem;
    }
    .color input {
      width: 2.2rem;
      height: 2.2rem;
      border: 1px solid var(--uf-border);
      border-radius: 6px;
      padding: 0;
      background: none;
    }
    .swatch {
      display: inline-flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.4rem 0.8rem;
      border-radius: var(--uf-radius-pill);
      color: #fff;
      font-size: 0.8rem;
      font-weight: 600;
    }
    .swatch__accent {
      width: 0.9rem;
      height: 0.9rem;
      border-radius: 50%;
      border: 2px solid #fff;
    }
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class PublishPage {
  private readonly api = inject(UnitformaApi);
  private readonly ctx = inject(ProjectContext);
  private readonly dialogs = inject(DialogsService);
  private readonly toast = inject(ToastService);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly readiness = signal<ReadinessOut | null>(null);
  readonly publications = signal<PublicationOut[]>([]);
  readonly project = signal<ProjectOut | null>(null);
  readonly tenant = signal<TenantOut | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  portal: PortalForm = { hero_text: '', construction_stage: '', completion: '' };
  brand: BrandingForm = blankBrand();
  when = whenShort;

  readonly facts = computed<HeaderFact[]>(() => {
    const r = this.readiness();
    if (!r) return [];
    const c = r.unit_counts ?? {};
    return [
      r.published_version
        ? { domain: 'publication', status: 'published', value: `live: v${r.published_version}` }
        : { domain: 'publication', status: 'retired', value: 'not published' },
      { domain: 'unit.publication', status: 'published', value: `${c['published'] ?? 0} public` },
      { domain: 'unit.publication', status: 'hidden', value: `${c['hidden'] ?? 0} link only` },
      {
        domain: 'unit.publication',
        status: 'unpublished',
        value: `${c['unpublished'] ?? 0} not published`,
      },
    ];
  });

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  readinessSummary(r: ReadinessOut): string {
    const n = (lvl: string) => r.items.filter((i) => i.level === lvl).length;
    return `${n('ok')} ok · ${n('warning')} warnings · ${n('error')} blocking`;
  }

  fixLink(key: string): [string, string] | null {
    const hit = FIX_LINKS.find(([re]) => re.test(key));
    return hit ? [hit[1], hit[2]] : null;
  }

  textSummary(): string {
    const parts = [this.portal.hero_text ? 'headline set' : 'no headline'];
    if (this.portal.construction_stage) parts.push(this.portal.construction_stage);
    if (this.portal.completion) parts.push(`completion ${this.portal.completion}`);
    return parts.join(' · ');
  }

  brandSummary(): string {
    const set = BRANDING_KEYS.filter(
      (k) =>
        this.brand[k] &&
        !(k === 'primary_color' && this.brand[k] === '#1d4ed8') &&
        !(k === 'accent_color' && this.brand[k] === '#0f766e'),
    );
    return set.length
      ? `${this.brand.display_name || 'no display name'} · ${set.length} of ${BRANDING_KEYS.length} fields set`
      : 'defaults';
  }

  async load(): Promise<void> {
    try {
      const [r, pubs, p, t] = await Promise.all([
        this.api.publishReadiness(this.tenantId(), this.projectId()),
        this.api.listPublications(this.tenantId(), this.projectId()),
        this.api.getProject(this.tenantId(), this.projectId()),
        this.api.getTenant(this.tenantId()),
      ]);
      this.readiness.set(r);
      this.publications.set(pubs);
      this.project.set(p);
      this.ctx.set(p);
      this.tenant.set(t);
      const ps = (p.portal_settings ?? {}) as Partial<PortalForm>;
      this.portal = {
        hero_text: ps.hero_text ?? '',
        construction_stage: ps.construction_stage ?? '',
        completion: ps.completion ?? '',
      };
      const b = (t.branding ?? {}) as Partial<BrandingForm>;
      this.brand = {
        ...blankBrand(),
        ...Object.fromEntries(BRANDING_KEYS.map((k) => [k, b[k] ?? blankBrand()[k]])),
      };
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  markAll(status: 'published' | 'unpublished'): Promise<void> {
    return this.act(async () => {
      const r = await this.api.setUnitPublication(
        this.tenantId(),
        this.projectId(),
        status,
        null,
        true,
      );
      this.toast.ok(
        `${r.changed} unit(s) updated. Changes reach buyers with the next publication.`,
      );
    });
  }

  run(mode: 'preview' | 'publish'): Promise<void> {
    return this.act(async () => {
      const r = await this.api.publish(this.tenantId(), this.projectId(), mode);
      if (mode === 'preview') {
        if (r.preview_url) window.open(r.preview_url, '_blank', 'noopener');
        this.toast.ok(
          `Preview version ${r.publication.version_no} built; the link is valid for one hour.`,
        );
      } else {
        this.toast.ok(
          `Version ${r.publication.version_no} is live${r.portal_url ? ` at ${r.portal_url}` : ''}.`,
        );
      }
    });
  }

  async unpublish(): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Take the project off the portal?',
      message: 'The published snapshot is retired. Buyers who open the portal see "coming soon".',
      consequence: 'Favourites and links buyers saved stop working until you publish again.',
      confirmLabel: 'Unpublish',
      tone: 'bad',
    });
    if (!ok) return;
    return this.act(async () => {
      await this.api.unpublish(this.tenantId(), this.projectId());
      this.toast.ok('The project is no longer published.');
    });
  }

  savePortal(): Promise<void> {
    const p = this.project();
    if (!p) return Promise.resolve();
    const ps = { ...(p.portal_settings ?? {}), ...this.portal };
    return this.act(async () => {
      await this.api.updateProject(this.tenantId(), this.projectId(), {
        portal_settings: clean(ps),
        version: p.version,
      });
      this.toast.ok('Text saved. Publish a new version to show it to buyers.');
    });
  }

  saveBranding(): Promise<void> {
    const t = this.tenant();
    const branding = {
      ...(t?.branding ?? {}),
      ...clean(this.brand as unknown as Record<string, string>),
    };
    for (const k of BRANDING_KEYS)
      if (!this.brand[k]) delete (branding as Record<string, unknown>)[k];
    return this.act(async () => {
      await this.api.updateTenant(this.tenantId(), { branding });
      this.toast.ok('Branding saved. It applies to every project from its next publication.');
    });
  }

  private async act(fn: () => Promise<unknown>): Promise<void> {
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

function blankBrand(): BrandingForm {
  return {
    display_name: '',
    tagline: '',
    primary_color: '#1d4ed8',
    accent_color: '#0f766e',
    contact_email: '',
    contact_phone: '',
    website: '',
    legal_text: '',
  };
}

function clean<T extends object>(o: T): Record<string, unknown> {
  return Object.fromEntries(
    Object.entries(o).filter(([, v]) => v !== '' && v !== null && v !== undefined),
  );
}
