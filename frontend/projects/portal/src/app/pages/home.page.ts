import { Component, effect, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { area, areaRange, money } from '../core/format';
import { SiteStore } from '../core/site.store';

/** Tenant landing: live projects, or "coming soon"; a project domain goes straight to its project. */
@Component({
  selector: 'uf-home-page',
  imports: [RouterLink],
  template: `
    @if (store.site(); as s) {
      @if (s.status === 'coming_soon') {
        <section class="uf-empty">
          <h1>Coming soon</h1>
          <p>{{ s.branding.display_name || s.tenant.name }} is preparing its projects. Please check back shortly.</p>
          @if (s.branding.contact_email) { <p><a [href]="'mailto:' + s.branding.contact_email">Contact the sales team</a></p> }
        </section>
      } @else {
        <h1>{{ s.branding.display_name || s.tenant.name }}</h1>
        <div class="uf-grid">
          @for (p of s.projects; track p.slug) {
            <a class="uf-card proj" [routerLink]="['/projects', p.slug]">
              <h2>{{ p.name }}</h2>
              @if (p.hero_text) { <p>{{ p.hero_text }}</p> }
              <ul class="uf-chips">
                <li class="uf-chip">{{ p.stats.available }} of {{ p.stats.units }} available</li>
                @if (money(p.stats.price_from); as pf) { <li class="uf-chip">from {{ pf }}</li> }
                @if (p.stats.area_min) { <li class="uf-chip">{{ areaRange(p.stats.area_min, p.stats.area_max) }}</li> }
                @if (p.construction_stage) { <li class="uf-chip">{{ p.construction_stage }}</li> }
              </ul>
            </a>
          }
        </div>
      }
    }
  `,
  styles: `.proj { color: inherit; text-decoration: none; display: block; } .proj:hover { border-color: var(--uf-primary); }`,
})
export class HomePage {
  protected readonly store = inject(SiteStore);
  private readonly router = inject(Router);
  protected readonly money = money;
  protected readonly area = area;
  protected readonly areaRange = areaRange;

  constructor() {
    effect(() => {
      const s = this.store.site();
      if (s && s.mode === 'project' && s.projects.length === 1) {
        void this.router.navigate(['/projects', s.projects[0].slug], { replaceUrl: true });
      }
    });
  }
}
