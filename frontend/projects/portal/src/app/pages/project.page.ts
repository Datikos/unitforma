import { Component, ElementRef, computed, inject, input, signal, viewChild } from '@angular/core';
import { DomSanitizer, SafeResourceUrl } from '@angular/platform-browser';
import { toObservable } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { PlanPolygon, PlanViewerComponent } from 'plan-viewer';
import { EmptyStateComponent, StatusChipComponent, UF_ICONS } from 'ui';
import type { MassingUnitInfo, PlacedModel, SiteFeature3D } from 'viewer-3d';
import { MassingViewerComponent } from 'viewer-3d';
import { detectCapabilities } from '../core/capabilities';
import { AVAILABILITY, CONSTRUCTION, area, areaRange, money } from '../core/format';
import { LayoutDoc, PortalApi, ProjectDoc, UnitMedia, problemOf } from '../core/portal-api';
import { SiteStore } from '../core/site.store';
import { siteBadge } from './site-view.model';

/** Site feature colours on the 2D site plan; the 3D viewer uses the same hues. */
const FEATURE_FILL: Record<string, string> = {
  garden: 'rgba(111, 184, 106, 0.35)',
  road: 'rgba(139, 145, 154, 0.35)',
  parking_zone: 'rgba(154, 161, 171, 0.35)',
  amenity: 'rgba(95, 178, 220, 0.35)',
  common_area: 'rgba(201, 181, 143, 0.35)',
  entrance: 'rgba(232, 150, 63, 0.45)',
  other: 'rgba(184, 181, 174, 0.35)',
};
const FEATURE_STROKE: Record<string, string> = {
  garden: '#4f9d5a',
  road: '#6b7280',
  parking_zone: '#7c8591',
  amenity: '#2f8fc2',
  common_area: '#a68c5b',
  entrance: '#d97706',
  other: '#9b968d',
};

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
      <section class="hero" id="top">
        <div class="hero__text">
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
          <nav class="hero__nav">
            <a class="uf-btn" [routerLink]="['units']"
              ><ng-icon name="lucideLayoutGrid" /> Browse units</a
            >
            <a class="uf-btn uf-ghost" [routerLink]="['favourites']"
              ><ng-icon name="lucideHeart" /> Saved</a
            >
          </nav>
        </div>
        @if (gallery().length) {
          <div class="hero__media">
            <button
              type="button"
              class="hero__cover"
              (click)="openLightbox(0)"
              [attr.aria-label]="'Open ' + label(0)"
            >
              <img [src]="api.asset(gallery()[0].url)" [alt]="label(0)" />
              <span class="hero__count"><ng-icon name="lucideImage" /> {{ gallery().length }}</span>
            </button>
            @if (gallery().length > 1) {
              <div class="hero__thumbs">
                @for (g of gallery().slice(1, 5); track g.url; let i = $index) {
                  <button
                    type="button"
                    class="hero__thumb"
                    (click)="openLightbox(i + 1)"
                    [attr.aria-label]="'Open ' + label(i + 1)"
                  >
                    <img [src]="api.asset(g.url)" [alt]="label(i + 1)" loading="lazy" />
                  </button>
                }
              </div>
            }
          </div>
        }
      </section>

      <section class="facts" aria-label="Key facts">
        @for (f of facts(); track f.label) {
          <div class="fact">
            <span class="fact__label"><ng-icon [name]="f.icon" /> {{ f.label }}</span>
            <span class="fact__value">{{ f.value }}</span>
          </div>
        }
      </section>

      <nav class="subnav" aria-label="Sections">
        @for (n of sections(); track n.id) {
          <a [href]="'#' + n.id" (click)="jump($event, n.id)">{{ n.label }}</a>
        }
      </nav>

      <section class="explore" id="site">
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
            @if (show3d()) {
              <button
                type="button"
                class="uf-chip-btn"
                [attr.aria-pressed]="tint() === 'availability'"
                (click)="tint.set(tint() === 'availability' ? 'neutral' : 'availability')"
                title="Colour the 3D model by availability instead of the neutral finish"
              >
                <ng-icon name="lucideLayers" /> Availability colours
              </button>
            }
          }
        </div>
        @if (show3d() && d.massing) {
          @defer (when show3d()) {
            <div class="explore__3d" [class.explore__3d--split]="gallery().length">
              <uf-massing-viewer
                [src]="api.asset(d.massing.url)"
                [models]="placedModels()"
                [badge]="siteBadge()"
                [unitColors]="unitColors()"
                [tintMode]="tint()"
                [siteFeatures]="siteFeatures3d()"
                (unitPicked)="openUnit($event)"
              />
              @if (gallery().length) {
                <button type="button" class="explore__render" (click)="openLightbox(0)">
                  <img [src]="api.asset(gallery()[0].url)" [alt]="label(0)" loading="lazy" />
                  <span class="explore__caption">{{ label(0) }} · rendered view</span>
                </button>
              }
            </div>
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
          <p class="uf-muted small legend">
            Select a building on the site plan.
            @for (c of constructionLegend(); track c) {
              <uf-status-chip domain="building.construction" [value]="c" />
            }
          </p>
        }
        <div class="uf-grid buildings" id="buildings">
          @for (b of d.buildings; track b.code) {
            <a class="uf-card bcard" [routerLink]="['buildings', b.code]">
              <div class="bcard__head">
                <ng-icon name="lucideBuilding2" class="bcard__icon" />
                <h3>{{ b.name || 'Building ' + b.code }}</h3>
              </div>
              <p class="uf-muted">
                {{ b.floors.length }} floor{{ b.floors.length === 1 ? '' : 's' }}
              </p>
              @if (b.construction_status) {
                <uf-status-chip domain="building.construction" [value]="b.construction_status" />
              }
              @if (b.completion) {
                <p class="uf-muted uf-small">
                  <ng-icon name="lucideCalendar" /> Completion {{ b.completion }}
                </p>
              }
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

      @if (d.layouts?.length) {
        <section class="plans" id="plans">
          <div class="plans__head">
            <h2>Plan types</h2>
            <a class="uf-btn" [routerLink]="['/projects', slug(), 'plans']"
              >All plan types, with the units left <ng-icon name="lucideArrowRight"
            /></a>
          </div>
          <div class="uf-grid plans__grid">
            @for (l of d.layouts!.slice(0, 6); track l.code) {
              <a
                class="uf-card pcard"
                [routerLink]="['/projects', slug(), 'units']"
                [queryParams]="{ layout: l.code }"
              >
                @if (layoutCover(l); as c) {
                  <img
                    [src]="api.asset(c.url)"
                    [alt]="c.alt_text || 'Plan type ' + l.code"
                    loading="lazy"
                  />
                } @else {
                  <span class="pcard__ph"><ng-icon name="lucideLayoutGrid" /></span>
                }
                <span class="pcard__cap"
                  ><strong>{{ l.code }}</strong>
                  @if (l.name) {
                    <span class="uf-muted">{{ l.name }}</span>
                  }
                </span>
              </a>
            }
          </div>
        </section>
      }
      @if (gallery().length > 1) {
        <section class="gallery" id="gallery">
          <h2>Gallery</h2>
          <div class="gallery__grid">
            @for (g of gallery(); track g.url; let i = $index) {
              <button
                type="button"
                class="gallery__item"
                (click)="openLightbox(i)"
                [attr.aria-label]="'Open ' + label(i)"
              >
                <img [src]="api.asset(g.url)" [alt]="label(i)" loading="lazy" />
                <span>{{ label(i) }}</span>
              </button>
            }
          </div>
        </section>
      }
      @if (d.project.description) {
        <section class="uf-card text" id="about">
          <h2>About</h2>
          <p>{{ d.project.description }}</p>
        </section>
      }
      @if (coords()) {
        <section class="location" id="location">
          <h2>Location</h2>
          @if (address()) {
            <p class="uf-muted">{{ address() }}</p>
          }
          @if (mapEmbed(); as m) {
            <iframe
              class="location__map"
              [src]="m"
              title="Map of the project location (OpenStreetMap)"
              loading="lazy"
              referrerpolicy="no-referrer"
            ></iframe>
          }
          <p class="uf-muted uf-small">
            <a [href]="mapLink()" target="_blank" rel="noopener">Open in OpenStreetMap</a> · map
            data ©
            <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener"
              >OpenStreetMap</a
            >
            contributors
          </p>
        </section>
      }
      @if (d.payment_plans.length || d.promotions.length) {
        <section class="uf-grid terms" id="terms">
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
      <!-- a click on the backdrop closes it; Escape closes a modal dialog natively -->
      <!-- eslint-disable-next-line @angular-eslint/template/click-events-have-key-events, @angular-eslint/template/interactive-supports-focus -->
      <dialog
        #lightbox
        class="lightbox"
        (click)="onLightboxClick($event)"
        (close)="lightboxIndex.set(null)"
      >
        @if (lightboxItem(); as g) {
          <figure>
            <img [src]="api.asset(g.url)" [alt]="label(lightboxIndex() ?? 0)" />
            <figcaption>
              {{ label(lightboxIndex() ?? 0) }}
              <span class="uf-muted"
                >{{ (lightboxIndex() ?? 0) + 1 }} / {{ gallery().length }}</span
              >
            </figcaption>
          </figure>
        }
        <button
          type="button"
          class="lightbox__btn lightbox__btn--prev"
          (click)="stepLightbox(-1)"
          aria-label="Previous"
        >
          <ng-icon name="lucideChevronLeft" />
        </button>
        <button
          type="button"
          class="lightbox__btn lightbox__btn--next"
          (click)="stepLightbox(1)"
          aria-label="Next"
        >
          <ng-icon name="lucideChevronRight" />
        </button>
        <button
          type="button"
          class="lightbox__btn lightbox__btn--close"
          (click)="closeLightbox()"
          aria-label="Close"
        >
          <ng-icon name="lucideX" />
        </button>
      </dialog>
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
      display: grid;
      grid-template-columns: minmax(0, 1fr) minmax(0, 1.1fr);
      gap: 1.5rem;
      align-items: start;
      margin-bottom: 1.25rem;
    }
    .hero__text {
      display: grid;
      gap: 0.5rem;
      align-content: start;
    }
    .hero__media {
      display: grid;
      gap: 0.5rem;
    }
    .hero__cover,
    .hero__thumb,
    .gallery__item,
    .explore__render {
      border: 0;
      padding: 0;
      background: var(--uf-surface);
      border-radius: var(--uf-radius);
      overflow: hidden;
      cursor: zoom-in;
      position: relative;
      display: block;
      color: inherit;
      font: inherit;
      box-shadow: var(--uf-shadow);
    }
    .hero__cover img {
      width: 100%;
      aspect-ratio: 16 / 10;
      object-fit: cover;
      display: block;
    }
    .hero__count,
    .explore__caption {
      position: absolute;
      left: 0.6rem;
      bottom: 0.6rem;
      background: rgba(15, 23, 42, 0.75);
      color: #fff;
      border-radius: var(--uf-radius-pill);
      padding: 0.15rem 0.6rem;
      font-size: 0.8rem;
      display: inline-flex;
      gap: 0.3rem;
      align-items: center;
    }
    .hero__thumbs {
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 0.5rem;
    }
    .hero__thumb img,
    .gallery__item img {
      width: 100%;
      aspect-ratio: 4 / 3;
      object-fit: cover;
      display: block;
    }
    .facts {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(10rem, 1fr));
      gap: 0.75rem;
      margin-bottom: 1rem;
    }
    .fact {
      display: grid;
      gap: 0.15rem;
      padding: 0.65rem 0.9rem;
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius);
      background: var(--uf-surface);
    }
    .fact__label {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--uf-muted);
      display: inline-flex;
      gap: 0.3rem;
      align-items: center;
    }
    .fact__value {
      font-weight: 700;
      font-size: 1.05rem;
    }
    .subnav {
      position: sticky;
      top: 3.9rem;
      z-index: 4;
      display: flex;
      gap: 0.25rem;
      overflow-x: auto;
      padding: 0.35rem 0;
      margin: 0 0 1rem;
      background: var(--uf-bg);
      border-bottom: 1px solid var(--uf-border);
    }
    .plans__head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 0.75rem;
      flex-wrap: wrap;
      margin-bottom: 0.75rem;
    }
    .plans__head h2 {
      margin: 0;
    }
    .plans__grid {
      grid-template-columns: repeat(auto-fill, minmax(min(100%, 220px), 1fr));
    }
    .pcard {
      display: grid;
      padding: 0;
      overflow: hidden;
      text-decoration: none;
      color: inherit;
    }
    .pcard img,
    .pcard__ph {
      width: 100%;
      aspect-ratio: 4 / 3;
      object-fit: cover;
      display: grid;
      place-items: center;
      background: var(--uf-surface-2);
      color: var(--uf-muted);
      font-size: 2rem;
    }
    .pcard__cap {
      display: flex;
      gap: 0.5rem;
      align-items: baseline;
      padding: 0.6rem 0.8rem;
      flex-wrap: wrap;
    }
    .subnav a {
      white-space: nowrap;
      padding: 0.35rem 0.8rem;
      border-radius: var(--uf-radius-pill);
      color: var(--uf-text);
      text-decoration: none;
      font-weight: 500;
      font-size: 0.9rem;
    }
    .subnav a:hover {
      background: var(--uf-primary-soft);
      color: var(--uf-primary-strong);
    }
    .explore__3d--split {
      display: grid;
      grid-template-columns: minmax(0, 3fr) minmax(0, 2fr);
      gap: 0.75rem;
      align-items: stretch;
    }
    .explore__render img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .gallery {
      margin-bottom: 1.5rem;
    }
    .gallery__grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(min(100%, 240px), 1fr));
      gap: 0.75rem;
    }
    .gallery__item span {
      display: block;
      padding: 0.4rem 0.6rem;
      font-size: 0.85rem;
      color: var(--uf-muted);
      text-align: left;
    }
    .location {
      margin-bottom: 1.5rem;
      display: grid;
      gap: 0.5rem;
    }
    .location__map {
      width: 100%;
      height: min(60vh, 420px);
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius);
      background: var(--uf-surface-2);
    }
    @media (max-width: 860px) {
      .hero {
        grid-template-columns: 1fr;
      }
      .explore__3d--split {
        grid-template-columns: 1fr;
      }
      .subnav {
        top: 0;
      }
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
  private readonly sanitizer = inject(DomSanitizer);
  private readonly lightboxEl = viewChild<ElementRef<HTMLDialogElement>>('lightbox');
  readonly lightboxIndex = signal<number | null>(null);
  readonly gallery = computed(() => this.doc()?.gallery ?? []);

  /** Gallery captions: the document title and page, or "Render n" when the title is only a number
   * (a file named 1.pdf). */
  label(i: number): string {
    const g = this.gallery()[i];
    if (!g) return '';
    return /^\d+$/.test(g.document ?? '') ? `Render ${i + 1}` : g.caption;
  }
  readonly lightboxItem = computed(() => {
    const i = this.lightboxIndex();
    return i === null ? null : (this.gallery()[i] ?? null);
  });
  /** Buildings whose architect's model sits on the site replace their schematic one (ADR-0037). */
  readonly placedModels = computed<PlacedModel[]>(() =>
    (this.doc()?.buildings ?? []).flatMap((b) => {
      const src = b.model ? this.api.asset(b.model.url) : null;
      const matrix = b.model?.site_matrix;
      return src && matrix?.length === 16 ? [{ src, matrix, buildingCode: b.code }] : [];
    }),
  );
  /** The disclaimer names which buildings are the architect's model and which are schematic. */
  readonly siteBadge = computed(() => siteBadge(this.doc()?.buildings ?? []));
  readonly siteFeatures3d = computed<SiteFeature3D[]>(() =>
    (this.doc()?.site?.features ?? [])
      .filter((f) => f.ring_m && f.ring_m.length >= 3)
      .map((f) => ({ kind: f.kind, name: f.name, ring_m: f.ring_m as [number, number][] })),
  );
  /** Headline facts a buyer reads first: what, how many, how big, when. */
  readonly facts = computed(() => {
    const d = this.doc();
    if (!d) return [];
    const floors = Math.max(0, ...d.buildings.map((b) => b.floors.length));
    const out: { label: string; value: string; icon: string }[] = [
      { label: 'Buildings', value: String(d.buildings.length), icon: 'lucideBuilding2' },
      { label: 'Floors', value: floors ? String(floors) : '—', icon: 'lucideLayers' },
      {
        label: 'Units',
        value: `${d.stats.available} of ${d.stats.units} available`,
        icon: 'lucideLayoutGrid',
      },
    ];
    const ar = areaRange(d.stats.area_min, d.stats.area_max);
    if (ar) out.push({ label: 'Areas', value: ar, icon: 'lucideMaximize2' });
    const pf = money(d.stats.price_from);
    if (pf) out.push({ label: 'From', value: pf, icon: 'lucideCoins' });
    if (d.project.construction_stage) {
      out.push({
        label: 'Stage',
        value: d.project.construction_stage,
        icon: 'lucideClipboardCheck',
      });
    }
    if (d.project.completion) {
      out.push({ label: 'Completion', value: d.project.completion, icon: 'lucideCalendar' });
    }
    return out;
  });
  readonly sections = computed(() => {
    const d = this.doc();
    if (!d) return [];
    const out: { id: string; label: string }[] = [];
    if (d.massing || d.site?.plan) out.push({ id: 'site', label: 'Site' });
    out.push({ id: 'buildings', label: 'Buildings' });
    if (d.layouts?.length) out.push({ id: 'plans', label: 'Plan types' });
    if (this.gallery().length > 1) out.push({ id: 'gallery', label: 'Gallery' });
    if (d.project.description) out.push({ id: 'about', label: 'About' });
    if (this.coords()) out.push({ id: 'location', label: 'Location' });
    if (d.payment_plans.length || d.promotions.length) out.push({ id: 'terms', label: 'Terms' });
    return out;
  });
  readonly coords = computed(() => {
    const a = this.doc()?.project.address ?? {};
    if (a['lat'] === undefined || a['lng'] === undefined) return null;
    const lat = Number(a['lat']);
    const lng = Number(a['lng']);
    return Number.isFinite(lat) && Number.isFinite(lng) ? { lat, lng } : null;
  });
  /** OpenStreetMap embed around the position (ADR-0016 Decision 5): no key, no script. The
   * operator can turn the iframe off (`map_embed` on the site document, ADR-0016 E4); the
   * address and the link stay. */
  readonly mapEmbed = computed<SafeResourceUrl | null>(() => {
    const c = this.coords();
    if (!c || this.store.site()?.map_embed === false) return null;
    const d = 0.004;
    const bbox = [c.lng - d, c.lat - d, c.lng + d, c.lat + d].map((v) => v.toFixed(5)).join('%2C');
    const marker = `${c.lat.toFixed(6)}%2C${c.lng.toFixed(6)}`;
    return this.sanitizer.bypassSecurityTrustResourceUrl(
      `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${marker}`,
    );
  });

  /** The first image of a plan type, a 3D plan render first (ADR-0024). */
  layoutCover(l: LayoutDoc): UnitMedia | null {
    const images = l.media.filter((m) => m.mime.startsWith('image/'));
    return images.find((m) => m.kind === 'plan_render') ?? images[0] ?? null;
  }

  mapLink(): string {
    const c = this.coords();
    return c
      ? `https://www.openstreetmap.org/?mlat=${c.lat}&mlon=${c.lng}#map=17/${c.lat}/${c.lng}`
      : '#';
  }

  jump(ev: Event, id: string): void {
    ev.preventDefault();
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  openLightbox(i: number): void {
    this.lightboxIndex.set(i);
    const el = this.lightboxEl()?.nativeElement;
    if (el && !el.open) el.showModal();
  }

  closeLightbox(): void {
    this.lightboxEl()?.nativeElement.close();
    this.lightboxIndex.set(null);
  }

  stepLightbox(delta: number): void {
    const n = this.gallery().length;
    const i = this.lightboxIndex();
    if (!n || i === null) return;
    this.lightboxIndex.set((i + delta + n) % n);
  }

  onLightboxClick(ev: MouseEvent): void {
    if (ev.target === this.lightboxEl()?.nativeElement) this.closeLightbox();
  }

  protected readonly api = inject(PortalApi);
  private readonly store = inject(SiteStore);
  private readonly router = inject(Router);
  readonly slug = input.required<string>();
  readonly doc = signal<ProjectDoc | null>(null);
  readonly notFound = signal(false);
  private readonly caps = detectCapabilities();
  readonly show3d = signal(false);
  /** Neutral finish by default; buyers flip to availability colours (ADR-0017 Decision 2). */
  readonly tint = signal<'availability' | 'neutral'>('neutral');
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
  /** Footprints coloured by construction status when any building states one (ADR-0014 Decision 3). */
  readonly sitePolygons = computed<PlanPolygon[]>(() => [
    ...(this.doc()?.site?.features ?? [])
      .filter((f) => f.ring?.length >= 3)
      .map((f) => ({
        id: 'feature:' + f.name,
        ring: f.ring,
        label: f.name,
        kind: 'region' as const,
        fill: FEATURE_FILL[f.kind] ?? FEATURE_FILL['other'],
        stroke: FEATURE_STROKE[f.kind] ?? FEATURE_STROKE['other'],
        title: `${f.name} (${f.kind.replace('_', ' ')})`,
      })),
    ...(this.doc()?.site?.buildings ?? [])
      .filter((b) => b.ring)
      .map((b) => {
        const c = b.construction_status ? CONSTRUCTION[b.construction_status] : null;
        return {
          id: b.code,
          ring: b.ring!,
          label: b.code,
          kind: 'footprint' as const,
          fill: c?.fill ?? 'color-mix(in srgb, var(--uf-primary) 30%, transparent)',
          stroke: c?.stroke ?? 'var(--uf-primary)',
          title: `Building ${b.code}${c ? ', ' + c.label : ''}`,
        };
      }),
  ]);
  readonly constructionLegend = computed(() => {
    const present = new Set(
      (this.doc()?.site?.buildings ?? []).map((b) => b.construction_status).filter(Boolean),
    );
    return (Object.keys(CONSTRUCTION) as (keyof typeof CONSTRUCTION)[]).filter((k) =>
      present.has(k),
    );
  });

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
