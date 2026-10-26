import { Component, effect, inject } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { EmptyStateComponent, StatusChipComponent, UF_ICONS } from 'ui';
import { area, areaRange, money } from '../core/format';
import { PortalApi } from '../core/portal-api';
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
        <div class="uf-grid home-grid" [style.--n]="min(s.projects.length, 3)">
          @for (p of s.projects; track p.slug) {
            <a
              class="uf-card proj"
              [class.proj--cover]="p.cover"
              [routerLink]="['/projects', p.slug]"
            >
              @if (p.cover) {
                <img class="proj__cover" [src]="api.asset(p.cover)" [alt]="p.name" loading="lazy" />
              }
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
    /* one or two projects get cards of a reasonable width, not one column of a four-column grid */
    .home-grid {
      max-width: calc(var(--n) * 480px + (var(--n) - 1) * 1rem);
      grid-template-columns: repeat(auto-fit, minmax(min(100%, 280px), 1fr));
    }
    .proj {
      display: grid;
      /* minmax(0, …): an auto track would grow to the widest no-wrap chip and overflow the card */
      grid-template-columns: minmax(0, 1fr);
      gap: 0.5rem;
      align-content: start;
    }
    .proj > * {
      min-width: 0;
    }
    .proj .uf-chip {
      white-space: normal; /* a long construction stage wraps inside this card */
    }
    .proj--cover {
      padding: 0;
    }
    .proj--cover > :not(.proj__cover) {
      margin-left: 1.25rem;
      margin-right: 1.25rem;
    }
    .proj--cover > :last-child {
      margin-bottom: 1rem;
    }
    .proj__cover {
      width: 100%;
      aspect-ratio: 16 / 10;
      object-fit: cover;
      display: block;
      border-radius: var(--uf-radius) var(--uf-radius) 0 0;
    }
    .proj h2 {
      margin: 0;
      font-size: 1.25rem;
      overflow-wrap: anywhere; /* long Georgian names */
    }
    .proj p {
      margin: 0;
      display: -webkit-box;
      -webkit-line-clamp: 4;
      -webkit-box-orient: vertical;
      overflow: hidden;
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
  protected readonly api = inject(PortalApi);
  private readonly router = inject(Router);
  protected readonly money = money;
  protected readonly area = area;
  protected readonly areaRange = areaRange;
  protected readonly min = Math.min;

  constructor() {
    effect(() => {
      const s = this.store.site();
      if (s && s.mode === 'project' && s.projects.length === 1) {
        void this.router.navigate(['/projects', s.projects[0].slug], { replaceUrl: true });
      }
    });
  }
}
