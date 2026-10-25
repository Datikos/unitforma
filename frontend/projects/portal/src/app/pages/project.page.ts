import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { PlanPolygon, PlanViewerComponent } from 'plan-viewer';
import { EmptyStateComponent, StatusChipComponent, UF_ICONS } from 'ui';
import type { MassingUnitInfo } from 'viewer-3d';
import { MassingViewerComponent } from 'viewer-3d';
import { detectCapabilities } from '../core/capabilities';
import { AVAILABILITY, area, areaRange, money } from '../core/format';
import { PortalApi, ProjectDoc, problemOf } from '../core/portal-api';
import { SiteStore } from '../core/site.store';

/** Project page with the site explorer: 2D site plan or schematic 3D massing (plan §7.1, §7.3). */
@Component({
  selector: 'uf-project-page',
  imports: [
    RouterLink,
    NgIcon,
    PlanViewerComponent,
    MassingViewerComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    @if (notFound()) {
      <uf-empty-state
        icon="lucideEyeOff"
        title="Not available"
        text="This project is not published."
        ><a routerLink="/" class="uf-btn">Home</a></uf-empty-state
      >
    } @else if (doc(); as d) {
      <section class="hero">
        <div>
          <h1>{{ d.project.name }}</h1>
          @if (d.project.hero_text) {
            <p class="hero__lead">{{ d.project.hero_text }}</p>
          }
          @if (address()) {
            <p class="uf-muted">{{ address() }}</p>
          }
          <ul class="uf-chips">
            <li>
              <uf-status-chip
                domain="availability"
                value="available"
                [label]="d.stats.available + ' of ' + d.stats.units + ' available'"
                size="lg"
              />
            </li>
            @if (money(d.stats.price_from); as pf) {
              <li class="uf-chip uf-chip--lg"><ng-icon name="lucideCoins" />from {{ pf }}</li>
            }
            @if (d.stats.area_min) {
              <li class="uf-chip uf-chip--lg">
                <ng-icon name="lucideMaximize2" />{{
                  areaRange(d.stats.area_min, d.stats.area_max)
                }}
              </li>
            }
            @if (d.project.construction_stage) {
              <li class="uf-chip uf-chip--lg">
                <ng-icon name="lucideBuilding2" />{{ d.project.construction_stage }}
              </li>
            }
            @if (d.project.completion) {
              <li class="uf-chip uf-chip--lg">
                <ng-icon name="lucideCalendar" />Completion {{ d.project.completion }}
              </li>
            }
          </ul>
        </div>
        <nav class="hero__nav">
          <a class="uf-btn" [routerLink]="['units']"
            ><ng-icon name="lucideLayoutGrid" /> Browse units</a
          >
          <a class="uf-btn uf-ghost" [routerLink]="['favourites']"
            ><ng-icon name="lucideHeart" /> Saved</a
          >
        </nav>
      </section>

      <section class="explore">
        <div class="explore__bar">
          <h2>Explore the site</h2>
          @if (has3d()) {
            <div class="uf-segmented" role="group" aria-label="View">
              <button type="button" [attr.aria-pressed]="!show3d()" (click)="show3d.set(false)">
                2D plan
              </button>
              <button type="button" [attr.aria-pressed]="show3d()" (click)="show3d.set(true)">
                3D
              </button>
            </div>
          }
        </div>
        @if (show3d() && d.massing) {
          @defer (when show3d()) {
            <uf-massing-viewer
              [src]="api.asset(d.massing.url)"
              [unitColors]="unitColors()"
              (unitPicked)="openUnit($event)"
            />
          } @loading (minimum 200ms) {
            <p class="uf-muted">Loading 3D…</p>
          }
          <p class="uf-muted small legend">
            Tap a unit to open its floor plan.
            @for (a of legend; track a.key) {
              <uf-status-chip domain="availability" [value]="a.key" />
            }
          </p>
        } @else if (d.site?.plan; as plan) {
          <uf-plan-viewer
            [src]="api.asset(plan.url)"
            [width]="plan.width"
            [height]="plan.height"
            [polygons]="sitePolygons()"
            mode="view"
            (polygonSelected)="openBuilding($event)"
          />
          <p class="uf-muted small">Select a building on the site plan.</p>
        }
        <div class="uf-grid buildings">
          @for (b of d.buildings; track b.code) {
            <a class="uf-card bcard" [routerLink]="['buildings', b.code]">
              <div class="bcard__head">
                <ng-icon name="lucideBuilding2" class="bcard__icon" />
                <h3>{{ b.name || 'Building ' + b.code }}</h3>
              </div>
              <p class="uf-muted">
                {{ b.floors.length }} floor{{ b.floors.length === 1 ? '' : 's' }}
              </p>
              <uf-status-chip
                domain="availability"
                value="available"
                [label]="availableIn(b.code) + ' available'"
              />
              <span class="bcard__go">Floors and plans <ng-icon name="lucideArrowRight" /></span>
            </a>
          }
        </div>
      </section>

      @if (d.project.description) {
        <section class="uf-card text">
          <h2>About</h2>
          <p>{{ d.project.description }}</p>
        </section>
      }
      @if (d.payment_plans.length || d.promotions.length) {
        <section class="uf-grid terms">
          @for (p of d.payment_plans; track p.name) {
            <div class="uf-card">
              <h3>{{ p.name }}</h3>
              @if (p.description) {
                <p>{{ p.description }}</p>
              }
              <ol>
                @for (m of p.schedule; track $index) {
                  <li>
                    {{ m.label }} — {{ +m.percent }} %
                    @if (m.due) {
                      , {{ m.due }}
                    }
                  </li>
                }
              </ol>
            </div>
          }
          @for (p of d.promotions; track p.name) {
            <div class="uf-card">
              <h3>{{ p.name }}</h3>
              @if (p.terms) {
                <p>{{ p.terms }}</p>
              }
              @if (p.valid_to) {
                <p class="uf-muted">Until {{ p.valid_to }}</p>
              }
            </div>
          }
        </section>
      }
    } @else {
      <p class="uf-muted">Loading…</p>
    }
  `,
  styles: `
    .legend {
      display: flex;
      gap: 0.35rem;
      align-items: center;
      flex-wrap: wrap;
    }
    .bcard {
      display: grid;
      gap: 0.4rem;
      align-content: start;
    }
    .bcard__head {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .bcard__head h3 {
      margin: 0;
    }
    .bcard__icon {
      color: var(--uf-primary);
      font-size: 1.3rem;
    }
    .bcard__go {
      color: var(--uf-primary);
      font-weight: 600;
      font-size: 0.85rem;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }
    .hero {
      display: flex;
      justify-content: space-between;
      gap: 1rem;
      flex-wrap: wrap;
      align-items: flex-end;
      margin-bottom: 1.5rem;
    }
    .hero__lead {
      font-size: 1.15rem;
      max-width: 60ch;
    }
    .hero__nav {
      display: flex;
      gap: 0.5rem;
    }
    .explore {
      display: grid;
      gap: 0.75rem;
      margin-bottom: 1.5rem;
    }
    .explore__bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .explore__bar h2 {
      margin: 0;
    }
    .small {
      font-size: 0.85rem;
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
      align-items: center;
    }
    .bcard {
      color: inherit;
      text-decoration: none;
    }
    .bcard:hover {
      border-color: var(--uf-primary);
    }
    .text,
    .terms {
      margin-bottom: 1.5rem;
    }
  `,
})
export class ProjectPage {
  protected readonly api = inject(PortalApi);
  private readonly store = inject(SiteStore);
  private readonly router = inject(Router);
  readonly slug = input.required<string>();
  readonly doc = signal<ProjectDoc | null>(null);
  readonly notFound = signal(false);
  private readonly caps = detectCapabilities();
  readonly show3d = signal(false);
  protected readonly money = money;
  protected readonly area = area;
  protected readonly areaRange = areaRange;
  protected readonly legend = Object.entries(AVAILABILITY).map(([key, v]) => ({
    key,
    label: v.label,
  }));

  readonly has3d = computed(() => !!this.doc()?.massing && this.caps.webgl2);
  readonly address = computed(() => {
    const a = this.doc()?.project.address ?? {};
    return ['line1', 'line2', 'city', 'country']
      .map((k) => a[k])
      .filter(Boolean)
      .join(', ');
  });
  readonly unitColors = computed(() => {
    const out: Record<string, string> = {};
    for (const b of this.doc()?.buildings ?? [])
      for (const f of b.floors)
        for (const u of f.units) out[u.id] = AVAILABILITY[u.availability].solid;
    return out;
  });
  readonly sitePolygons = computed<PlanPolygon[]>(() =>
    (this.doc()?.site?.buildings ?? [])
      .filter((b) => b.ring)
      .map((b) => ({
        id: b.code,
        ring: b.ring!,
        label: b.code,
        kind: 'footprint' as const,
        fill: 'color-mix(in srgb, var(--uf-primary) 30%, transparent)',
        stroke: 'var(--uf-primary)',
        title: `Building ${b.code}`,
      })),
  );

  constructor() {
    toObservable(this.slug).subscribe((slug) => void this.load(slug));
  }

  private async load(slug: string): Promise<void> {
    this.doc.set(null);
    this.notFound.set(false);
    try {
      const d = await this.store.project(slug);
      this.doc.set(d);
      // desktop with WebGL2 starts in 3D; phones and data-saver start in 2D (plan §7.3)
      this.show3d.set(!!d.massing && this.caps.prefer3d);
      document.title = `${d.project.name} — ${d.branding.display_name || d.tenant.name}`;
    } catch (e) {
      if (problemOf(e).status === 404) this.notFound.set(true);
    }
  }

  availableIn(code: string): number {
    const b = this.doc()?.buildings.find((x) => x.code === code);
    return (b?.floors ?? []).reduce(
      (n, f) => n + f.units.filter((u) => u.availability === 'available').length,
      0,
    );
  }

  openBuilding(code: string): void {
    void this.router.navigate(['/projects', this.slug(), 'buildings', code]);
  }

  /** Floor first (ADR-0006 Decision 6): a 3D pick opens the building page on that floor with the unit preselected. */
  openUnit(u: MassingUnitInfo): void {
    void this.router.navigate(['/projects', this.slug(), 'buildings', u.building_code], {
      queryParams: { floor: u.floor_level, unit: u.code },
    });
  }
}
