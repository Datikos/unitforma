import { Component, effect, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { EmptyStateComponent, StatusChipComponent, UF_ICONS } from 'ui';
import { area, areaRange, money } from '../core/format';
import { SiteStore } from '../core/site.store';

/** Tenant landing: live projects, or "coming soon"; a project domain goes straight to its project. */
@Component({
  selector: 'uf-home-page',
  imports: [RouterLink, NgIcon, StatusChipComponent, EmptyStateComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    @if (store.site(); as s) {
      @if (s.status === 'coming_soon') {
        <uf-empty-state
          icon="lucideClock"
          title="Coming soon"
          [text]="
            (s.branding.display_name || s.tenant.name) +
            ' is preparing its projects. Please check back shortly.'
          "
        >
          @if (s.branding.contact_email) {
            <a class="uf-btn" [href]="'mailto:' + s.branding.contact_email"
              ><ng-icon name="lucideMail" /> Contact the sales team</a
            >
          }
        </uf-empty-state>
      } @else {
        <h1>{{ s.branding.display_name || s.tenant.name }}</h1>
        <div class="uf-grid">
          @for (p of s.projects; track p.slug) {
            <a class="uf-card proj" [routerLink]="['/projects', p.slug]">
              <h2>{{ p.name }}</h2>
              @if (p.hero_text) {
                <p class="uf-muted">{{ p.hero_text }}</p>
              }
              <ul class="uf-chips">
                <li>
                  <uf-status-chip
                    domain="availability"
                    value="available"
                    [label]="p.stats.available + ' of ' + p.stats.units + ' available'"
                  />
                </li>
                @if (money(p.stats.price_from); as pf) {
                  <li class="uf-chip"><ng-icon name="lucideCoins" />from {{ pf }}</li>
                }
                @if (p.stats.area_min) {
                  <li class="uf-chip">
                    <ng-icon name="lucideMaximize2" />{{
                      areaRange(p.stats.area_min, p.stats.area_max)
                    }}
                  </li>
                }
                @if (p.construction_stage) {
                  <li class="uf-chip">
                    <ng-icon name="lucideBuilding2" />{{ p.construction_stage }}
                  </li>
                }
              </ul>
              <span class="proj__go">Explore <ng-icon name="lucideArrowRight" /></span>
            </a>
          }
        </div>
      }
    }
  `,
  styles: `
    .proj {
      display: grid;
      gap: 0.5rem;
      align-content: start;
    }
    .proj h2 {
      margin: 0;
    }
    .proj__go {
      color: var(--uf-primary);
      font-weight: 600;
      font-size: 0.9rem;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }
  `,
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
