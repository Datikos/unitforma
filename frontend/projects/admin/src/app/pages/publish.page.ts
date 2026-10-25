import { SlicePipe } from '@angular/common';
import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { RouterLink } from '@angular/router';
import { ProjectOut, PublicationOut, ReadinessOut, TenantOut, UnitformaApi, problemMessage } from 'api-client';

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

const BRANDING_KEYS: (keyof BrandingForm)[] = ['display_name', 'tagline', 'primary_color', 'accent_color', 'contact_email', 'contact_phone', 'website', 'legal_text'];

/** Publication workspace (plan §9.3, J5): readiness → preview → publish; unpublish; portal text and branding. */
@Component({
  selector: 'uf-publish-page',
  imports: [FormsModule, SlicePipe, RouterLink, MatButtonModule, MatCardModule, MatFormFieldModule, MatInputModule],
  template: `
    <div class="uf-page">
      <div class="uf-page-header">
        <h2>Publish</h2>
        <span class="uf-links">
          @if (readiness()?.portal_url; as url) { <a mat-stroked-button [href]="url" target="_blank" rel="noopener">Open portal</a> }
          <a mat-stroked-button [routerLink]="['..']">Back to project</a>
        </span>
      </div>
      @if (error()) { <p class="uf-error" role="alert">{{ error() }}</p> }
      @if (notice()) { <p class="uf-ok" role="status">{{ notice() }}</p> }

      @if (readiness(); as r) {
        <mat-card appearance="outlined">
          <mat-card-header>
            <mat-card-title>Readiness</mat-card-title>
            <mat-card-subtitle>
              @if (r.published_version) { Live: version {{ r.published_version }} } @else { Not published }
              · units: {{ counts(r) }}
            </mat-card-subtitle>
          </mat-card-header>
          <mat-card-content>
            <ul class="uf-check">
              @for (i of r.items; track i.key) {
                <li [class]="'uf-' + i.level"><span class="uf-dot" aria-hidden="true"></span><span class="uf-sr">{{ i.level }}:</span> {{ i.message }}@if (i.count !== null && i.count !== undefined && i.key !== 'units') { ({{ i.count }}) }</li>
              }
            </ul>
            <div class="uf-row">
              <button mat-stroked-button [disabled]="busy()" (click)="markAll('published')">Mark all approved units public</button>
              <button mat-stroked-button [disabled]="busy()" (click)="markAll('unpublished')">Withdraw all units</button>
              <span class="uf-muted">Single units: select them in the inventory grid.</span>
            </div>
          </mat-card-content>
          <mat-card-actions>
            <button mat-stroked-button [disabled]="busy() || !r.ok" (click)="run('preview')">Preview</button>
            <button mat-flat-button [disabled]="busy() || !r.ok" (click)="run('publish')">{{ r.published_version ? 'Publish new version' : 'Publish' }}</button>
            <button mat-button [disabled]="busy() || !r.published_version" (click)="unpublish()">Unpublish</button>
          </mat-card-actions>
        </mat-card>
      }

      <div class="uf-grid2">
        <mat-card appearance="outlined">
          <mat-card-header><mat-card-title>Project page text</mat-card-title><mat-card-subtitle>Applies from the next publication</mat-card-subtitle></mat-card-header>
          <mat-card-content class="uf-form">
            <mat-form-field appearance="outline"><mat-label>Headline</mat-label><textarea matInput rows="2" [(ngModel)]="portal.hero_text" name="hero" maxlength="2000"></textarea></mat-form-field>
            <mat-form-field appearance="outline"><mat-label>Construction stage</mat-label><input matInput [(ngModel)]="portal.construction_stage" name="stage" maxlength="80" placeholder="e.g. frame complete" /></mat-form-field>
            <mat-form-field appearance="outline"><mat-label>Completion</mat-label><input matInput [(ngModel)]="portal.completion" name="completion" maxlength="80" placeholder="e.g. Q4 2027" /></mat-form-field>
          </mat-card-content>
          <mat-card-actions><button mat-flat-button [disabled]="busy()" (click)="savePortal()">Save text</button></mat-card-actions>
        </mat-card>

        <mat-card appearance="outlined">
          <mat-card-header><mat-card-title>Branding</mat-card-title><mat-card-subtitle>Company-wide; tenant administrators only</mat-card-subtitle></mat-card-header>
          <mat-card-content class="uf-form">
            <mat-form-field appearance="outline"><mat-label>Display name</mat-label><input matInput [(ngModel)]="brand.display_name" name="bname" maxlength="120" /></mat-form-field>
            <mat-form-field appearance="outline"><mat-label>Tagline</mat-label><input matInput [(ngModel)]="brand.tagline" name="btag" maxlength="200" /></mat-form-field>
            <div class="uf-row">
              <label class="uf-color">Primary colour <input type="color" [(ngModel)]="brand.primary_color" name="bprim" /></label>
              <label class="uf-color">Accent colour <input type="color" [(ngModel)]="brand.accent_color" name="bacc" /></label>
            </div>
            <mat-form-field appearance="outline"><mat-label>Sales e-mail</mat-label><input matInput type="email" [(ngModel)]="brand.contact_email" name="bmail" /></mat-form-field>
            <mat-form-field appearance="outline"><mat-label>Sales phone</mat-label><input matInput [(ngModel)]="brand.contact_phone" name="bphone" maxlength="50" /></mat-form-field>
            <mat-form-field appearance="outline"><mat-label>Website (https://…)</mat-label><input matInput [(ngModel)]="brand.website" name="bweb" /></mat-form-field>
            <mat-form-field appearance="outline"><mat-label>Legal text (footer)</mat-label><textarea matInput rows="3" [(ngModel)]="brand.legal_text" name="blegal" maxlength="4000"></textarea></mat-form-field>
          </mat-card-content>
          <mat-card-actions><button mat-flat-button [disabled]="busy()" (click)="saveBranding()">Save branding</button></mat-card-actions>
        </mat-card>
      </div>

      <mat-card appearance="outlined">
        <mat-card-header><mat-card-title>Publications</mat-card-title></mat-card-header>
        <mat-card-content>
          <table class="uf-pubs">
            <thead><tr><th>Version</th><th>Status</th><th>Built</th><th>Published</th><th>Units</th><th>Available</th></tr></thead>
            <tbody>
              @for (p of publications(); track p.id) {
                <tr><td>{{ p.version_no }}</td><td>{{ p.status }}</td><td>{{ p.created_at | slice: 0 : 16 }}</td><td>{{ (p.published_at ?? '') | slice: 0 : 16 }}</td><td>{{ p.summary['units'] }}</td><td>{{ p.summary['available'] }}</td></tr>
              } @empty { <tr><td colspan="6" class="uf-muted">Nothing built yet.</td></tr> }
            </tbody>
          </table>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: `
    .uf-links { display: flex; gap: 0.5rem; }
    .uf-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .uf-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    @media (max-width: 1000px) { .uf-grid2 { grid-template-columns: 1fr; } }
    .uf-form { display: grid; }
    .uf-check { list-style: none; padding: 0; display: grid; gap: 0.35rem; }
    .uf-check li { display: flex; gap: 0.5rem; align-items: center; }
    .uf-dot { width: 0.7rem; height: 0.7rem; border-radius: 50%; flex: none; }
    .uf-ok .uf-dot { background: #059669; } .uf-warning .uf-dot { background: #d97706; } .uf-error .uf-dot { background: #dc2626; }
    .uf-sr { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); }
    .uf-ok { color: #047857; }
    .uf-color { display: flex; gap: 0.5rem; align-items: center; }
    .uf-pubs { width: 100%; border-collapse: collapse; }
    .uf-pubs th, .uf-pubs td { text-align: left; padding: 0.3rem 0.5rem; border-bottom: 1px solid #e5e7eb; }
  `,
})
export class PublishPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly readiness = signal<ReadinessOut | null>(null);
  readonly publications = signal<PublicationOut[]>([]);
  readonly project = signal<ProjectOut | null>(null);
  readonly tenant = signal<TenantOut | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly notice = signal<string | null>(null);
  portal: PortalForm = { hero_text: '', construction_stage: '', completion: '' };
  brand: BrandingForm = blankBrand();

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  counts(r: ReadinessOut): string {
    const c = r.unit_counts ?? {};
    return ['published', 'hidden', 'unpublished'].map((k) => `${c[k] ?? 0} ${k}`).join(', ');
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
      this.tenant.set(t);
      const ps = (p.portal_settings ?? {}) as Partial<PortalForm>;
      this.portal = { hero_text: ps.hero_text ?? '', construction_stage: ps.construction_stage ?? '', completion: ps.completion ?? '' };
      const b = (t.branding ?? {}) as Partial<BrandingForm>;
      this.brand = { ...blankBrand(), ...Object.fromEntries(BRANDING_KEYS.map((k) => [k, b[k] ?? blankBrand()[k]])) };
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  markAll(status: 'published' | 'unpublished'): Promise<void> {
    return this.act(async () => {
      const r = await this.api.setUnitPublication(this.tenantId(), this.projectId(), status, null, true);
      this.notice.set(`${r.changed} unit(s) updated. Changes reach buyers with the next publication.`);
    });
  }

  run(mode: 'preview' | 'publish'): Promise<void> {
    return this.act(async () => {
      const r = await this.api.publish(this.tenantId(), this.projectId(), mode);
      if (mode === 'preview') {
        if (r.preview_url) window.open(r.preview_url, '_blank', 'noopener');
        this.notice.set(`Preview version ${r.publication.version_no} built; the link is valid for one hour.`);
      } else {
        this.notice.set(`Version ${r.publication.version_no} is live${r.portal_url ? ` at ${r.portal_url}` : ''}.`);
      }
    });
  }

  unpublish(): Promise<void> {
    if (!window.confirm('Take the project off the portal? Buyers will see "coming soon".')) return Promise.resolve();
    return this.act(async () => {
      await this.api.unpublish(this.tenantId(), this.projectId());
      this.notice.set('The project is no longer published.');
    });
  }

  savePortal(): Promise<void> {
    const p = this.project();
    if (!p) return Promise.resolve();
    const ps = { ...(p.portal_settings ?? {}), ...this.portal };
    return this.act(async () => {
      await this.api.updateProject(this.tenantId(), this.projectId(), { portal_settings: clean(ps), version: p.version });
      this.notice.set('Saved. Publish a new version to show it to buyers.');
    });
  }

  saveBranding(): Promise<void> {
    const t = this.tenant();
    const branding = { ...(t?.branding ?? {}), ...clean(this.brand as unknown as Record<string, string>) };
    for (const k of BRANDING_KEYS) if (!this.brand[k]) delete (branding as Record<string, unknown>)[k];
    return this.act(async () => {
      await this.api.updateTenant(this.tenantId(), { branding });
      this.notice.set('Branding saved. It applies to every project from its next publication.');
    });
  }

  private async act(fn: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    this.notice.set(null);
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
  return { display_name: '', tagline: '', primary_color: '#1d4ed8', accent_color: '#0f766e', contact_email: '', contact_phone: '', website: '', legal_text: '' };
}

function clean<T extends object>(o: T): Record<string, unknown> {
  return Object.fromEntries(Object.entries(o).filter(([, v]) => v !== '' && v !== null && v !== undefined));
}
