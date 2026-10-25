import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink, RouterLinkActive } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { UF_ICONS } from 'ui';
import { filter, map, startWith } from 'rxjs';
import { Favourites } from '../core/favourites';
import { SiteStore } from '../core/site.store';

/**
 * Portal header: brand, and inside a project the navigation (project, units, saved with a count).
 * The current project comes from the URL (`/projects/:slug/...`), so no page has to report it.
 */
@Component({
  selector: 'uf-portal-header',
  imports: [RouterLink, RouterLinkActive, NgIcon],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="hd">
      <a routerLink="/" class="hd__brand">
        <span class="hd__mark" aria-hidden="true">{{ brandName().slice(0, 1) }}</span>
        <span class="hd__names">
          <span class="hd__name">{{ brandName() }}</span>
          @if (store.site()?.branding?.tagline; as t) {
            <span class="hd__tag">{{ t }}</span>
          }
        </span>
      </a>
      <nav class="hd__nav" aria-label="Portal">
        @if (slug(); as s) {
          @if ((store.site()?.projects?.length ?? 0) > 1) {
            <a routerLink="/" class="hd__link"><ng-icon name="lucideLayoutDashboard" /> Projects</a>
          }
          <a
            [routerLink]="['/projects', s]"
            routerLinkActive="is-active"
            [routerLinkActiveOptions]="{ exact: true }"
            class="hd__link"
            ><ng-icon name="lucideMap" /> {{ projectName() ?? 'Project' }}</a
          >
          <a [routerLink]="['/projects', s, 'units']" routerLinkActive="is-active" class="hd__link"
            ><ng-icon name="lucideLayoutGrid" /> Units</a
          >
          <a
            [routerLink]="['/projects', s, 'favourites']"
            routerLinkActive="is-active"
            class="hd__link"
            ><ng-icon name="lucideHeart" /> Saved
            @if (savedCount()) {
              <span class="hd__count">{{ savedCount() }}</span>
            }
          </a>
        } @else {
          <a routerLink="/how-to-use" routerLinkActive="is-active" class="hd__link"
            ><ng-icon name="lucideCircleHelp" /> How to use</a
          >
        }
      </nav>
    </header>
  `,
  styles: `
    .hd {
      display: flex;
      align-items: center;
      gap: 1rem;
      padding: 0.7rem clamp(1rem, 4vw, 2.5rem);
      background: var(--uf-surface);
      border-bottom: 1px solid var(--uf-border);
      flex-wrap: wrap;
      position: sticky;
      top: 0;
      z-index: 5;
    }
    .hd__brand {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      color: var(--uf-text);
      text-decoration: none;
      min-width: 0;
    }
    .hd__mark {
      display: grid;
      place-items: center;
      width: 2.2rem;
      height: 2.2rem;
      border-radius: 9px;
      background: var(--uf-primary);
      color: #fff;
      font-weight: 800;
      flex: none;
    }
    .hd__names {
      display: grid;
      min-width: 0;
    }
    .hd__name {
      font-weight: 700;
      font-size: 1.1rem;
      line-height: 1.2;
    }
    .hd__tag {
      color: var(--uf-muted);
      font-size: 0.8rem;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }
    .hd__nav {
      display: flex;
      gap: 0.25rem;
      margin-left: auto;
      flex-wrap: wrap;
    }
    .hd__link {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
      padding: 0.4rem 0.75rem;
      border-radius: var(--uf-radius-pill);
      color: var(--uf-text);
      text-decoration: none;
      font-weight: 500;
      font-size: 0.95rem;
    }
    .hd__link:hover {
      background: var(--uf-surface-2);
    }
    .hd__link.is-active {
      background: var(--uf-primary-soft);
      color: var(--uf-primary-strong);
      font-weight: 600;
    }
    .hd__link ng-icon {
      font-size: 1.1rem;
    }
    .hd__count {
      display: inline-grid;
      place-items: center;
      min-width: 1.35rem;
      height: 1.35rem;
      padding: 0 0.35rem;
      border-radius: var(--uf-radius-pill);
      background: var(--uf-primary);
      color: #fff;
      font-size: 0.75rem;
      font-weight: 700;
    }
    @media (max-width: 600px) {
      .hd__nav {
        width: 100%;
        margin-left: 0;
        justify-content: space-between;
      }
      .hd__link {
        padding: 0.35rem 0.5rem;
        font-size: 0.9rem;
      }
    }
  `,
})
export class PortalHeaderComponent {
  protected readonly store = inject(SiteStore);
  private readonly favs = inject(Favourites);
  private readonly router = inject(Router);
  private readonly url = toSignal(
    this.router.events.pipe(
      filter((e) => e instanceof NavigationEnd),
      map((e) => e.urlAfterRedirects),
      startWith(this.router.url),
    ),
    { initialValue: this.router.url },
  );
  readonly slug = computed(() => this.url().match(/^\/projects\/([^/?#]+)/)?.[1] ?? null);
  readonly projectName = computed(() => {
    const s = this.slug();
    return s ? (this.store.site()?.projects.find((p) => p.slug === s)?.name ?? null) : null;
  });
  readonly brandName = computed(() => {
    const s = this.store.site();
    return s?.branding?.display_name || s?.tenant.name || 'Unitforma';
  });
  readonly savedCount = computed(() => {
    const s = this.slug();
    return s ? this.favs.list(s).length : 0;
  });
}
