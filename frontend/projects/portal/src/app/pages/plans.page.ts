import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { EmptyStateComponent, UF_ICONS } from 'ui';
import { areaRange, money } from '../core/format';
import { LayoutSummary, PortalApi, ProjectDoc, UnitMedia, problemOf } from '../core/portal-api';
import { SiteStore } from '../core/site.store';

/** The project's plan types (ADR-0024 Decision 4): one card per layout with its render, the
 * facts derived from its units and the live number of units left. */
@Component({
  selector: 'uf-plans-page',
  imports: [RouterLink, NgIcon, EmptyStateComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    @if (doc(); as d) {
      <nav class="uf-crumbs">
        <a routerLink="/">Home</a> <ng-icon name="lucideChevronRight" />
        <a [routerLink]="['/projects', slug()]">{{ d.project.name }}</a>
        <ng-icon name="lucideChevronRight" /> <span>Plan types</span>
      </nav>
      <header class="head">
        <h1>Plan types</h1>
        <p class="uf-muted lead">
          Every apartment of a plan type has the same layout; the finish and the view differ per
          unit. The numbers are live: a sale shows here at once.
        </p>
        <a class="uf-btn" [routerLink]="['/projects', slug(), 'units']"
          ><ng-icon name="lucideListFilter" /> All units</a
        >
      </header>
      @if (error(); as e) {
        <p class="uf-alert uf-alert--bad" role="alert">{{ e }}</p>
      }
      @if (items().length) {
        <div class="uf-grid plans">
          @for (p of items(); track p.code) {
            <article class="uf-card plan" [class.plan--none]="!p.available">
              <a [routerLink]="unitsLink(p)" [queryParams]="{ layout: p.code }" class="plan__cover">
                @if (cover(p); as c) {
                  <img
                    [src]="api.asset(c.url)"
                    [alt]="c.alt_text || 'Plan type ' + p.code"
                    loading="lazy"
                  />
                  @if (c.is_ai_generated) {
                    <span class="uf-ai-label">Illustrative — AI generated</span>
                  }
                } @else {
                  <span class="plan__ph"><ng-icon name="lucideLayoutGrid" /></span>
                }
              </a>
              <div class="plan__body">
                <header class="plan__head">
                  <h2>
                    <a [routerLink]="unitsLink(p)" [queryParams]="{ layout: p.code }">{{
                      p.code
                    }}</a>
                  </h2>
                  @if (p.name) {
                    <span class="uf-muted">{{ p.name }}</span>
                  }
                </header>
                <ul class="plan__facts">
                  @if (p.rooms.length) {
                    <li><ng-icon name="lucideDoorOpen" /> {{ roomsText(p.rooms) }}</li>
                  }
                  @if (areaText(p); as a) {
                    <li><ng-icon name="lucideMaximize2" /> {{ a }}</li>
                  }
                  @if (p.buildings.length) {
                    <li>
                      <ng-icon name="lucideBuilding2" /> Building {{ p.buildings.join(', ') }}
                    </li>
                  }
                </ul>
                <p class="plan__left" [class.is-none]="!p.available">
                  <strong>{{ p.available }}</strong> of {{ p.units }}
                  {{ p.units === 1 ? 'unit' : 'units' }} available
                </p>
                <footer class="plan__foot">
                  <span class="plan__price">
                    @if (money(p.price_from); as m) {
                      from <strong>{{ m }}</strong>
                    } @else {
                      <span class="uf-muted">Price on request</span>
                    }
                  </span>
                  <a class="uf-btn" [routerLink]="unitsLink(p)" [queryParams]="{ layout: p.code }"
                    >See the units <ng-icon name="lucideArrowRight"
                  /></a>
                </footer>
                @if (others(p).length) {
                  <div class="plan__strip" aria-label="More images">
                    @for (m of others(p); track m.url) {
                      <a [href]="api.asset(m.url)" target="_blank" rel="noopener">
                        <img [src]="api.asset(m.url)" [alt]="m.alt_text || ''" loading="lazy" />
                      </a>
                    }
                  </div>
                }
              </div>
            </article>
          }
        </div>
      } @else if (!loading()) {
        <uf-empty-state
          icon="lucideLayoutGrid"
          title="No plan types yet"
          text="The developer has not grouped the units by plan type. Browse the units list instead."
        />
      }
    }
  `,
  styles: `
    .head {
      display: grid;
      gap: 0.5rem;
      margin-bottom: 1rem;
    }
    .head h1 {
      margin: 0;
    }
    .lead {
      max-width: 60ch;
      margin: 0;
    }
    .head .uf-btn {
      justify-self: start;
    }
    .plans {
      grid-template-columns: repeat(auto-fill, minmax(min(100%, 340px), 1fr));
    }
    .plan {
      display: grid;
      padding: 0;
      overflow: hidden;
    }
    .plan--none {
      opacity: 0.85;
    }
    .plan__cover {
      position: relative;
      display: block;
      aspect-ratio: 4 / 3;
      background: var(--uf-surface-2);
    }
    .plan__cover img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .plan__ph {
      display: grid;
      place-items: center;
      height: 100%;
      color: var(--uf-muted);
      font-size: 2.5rem;
    }
    .plan__body {
      display: grid;
      gap: 0.5rem;
      padding: 0.9rem 1rem 1rem;
    }
    .plan__head {
      display: flex;
      align-items: baseline;
      gap: 0.5rem;
      flex-wrap: wrap;
    }
    .plan__head h2 {
      margin: 0;
      font-size: 1.25rem;
    }
    .plan__head a {
      text-decoration: none;
      color: inherit;
    }
    .plan__facts {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem 1rem;
      color: var(--uf-muted);
      font-size: 0.95rem;
    }
    .plan__facts li {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
    }
    .plan__left {
      margin: 0;
      color: var(--uf-good, #15803d);
    }
    .plan__left.is-none {
      color: var(--uf-muted);
    }
    .plan__foot {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.5rem;
      flex-wrap: wrap;
    }
    .plan__strip {
      display: flex;
      gap: 0.35rem;
      overflow-x: auto;
    }
    .plan__strip img {
      width: 72px;
      height: 54px;
      object-fit: cover;
      border-radius: 6px;
      border: 1px solid var(--uf-border);
    }
  `,
})
export class PlansPage {
  protected readonly api = inject(PortalApi);
  private readonly store = inject(SiteStore);
  readonly slug = input.required<string>();
  readonly doc = signal<ProjectDoc | null>(null);
  readonly items = signal<LayoutSummary[]>([]);
  readonly loading = signal(true);
  readonly error = signal<string | null>(null);
  money = (m: LayoutSummary['price_from']) => money(m);

  constructor() {
    toObservable(this.slug).subscribe((s) => void this.load(s));
  }

  unitsLink(_p: LayoutSummary): unknown[] {
    return ['/projects', this.slug(), 'units'];
  }

  /** The first image of the layout, a 3D plan render first (ADR-0017). */
  cover(p: LayoutSummary): UnitMedia | null {
    const images = p.media.filter((m) => m.mime.startsWith('image/'));
    return images.find((m) => m.kind === 'plan_render') ?? images[0] ?? null;
  }

  others(p: LayoutSummary): UnitMedia[] {
    const c = this.cover(p);
    return p.media.filter((m) => m !== c && m.mime.startsWith('image/'));
  }

  roomsText(rooms: number[]): string {
    if (rooms.length === 1) return `${rooms[0]} rooms`;
    return `${rooms[0]}–${rooms[rooms.length - 1]} rooms`;
  }

  areaText(p: LayoutSummary): string | null {
    return areaRange(p.area_min, p.area_max);
  }

  private async load(slug: string): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      const [d, r] = await Promise.all([this.store.project(slug), this.api.layouts(slug)]);
      this.doc.set(d);
      this.items.set(r.items);
      document.title = `Plan types — ${d.project.name}`;
    } catch (e) {
      this.error.set(problemOf(e).title ?? 'Could not load the plan types');
    } finally {
      this.loading.set(false);
    }
  }
}
