import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { combineLatest } from 'rxjs';
import { EmptyStateComponent, StatusChipComponent, UF_ICONS } from 'ui';
import { PlanPolygon, PlanViewerComponent, PolygonMove, Ring } from 'plan-viewer';
import { MassingViewerComponent, type SiteFeature3D } from 'viewer-3d';
import { Favourites } from '../core/favourites';
import { AVAILABILITY, area, money, typeLabel } from '../core/format';
import { PortalApi, ProjectDoc, UnitDoc, problemOf } from '../core/portal-api';
import { SiteStore } from '../core/site.store';

/** Unit page: plan, labelled media, areas with definitions, price and terms (plan §7.1, §7.4). */
interface Piece {
  id: string;
  name: string;
  w: number; // metres
  h: number;
  cx: number; // normalised plan coordinates of the centre
  cy: number;
  rotated: boolean;
}

/** Common pieces, metres: a buyer checks what fits where. */
const FURNITURE: { name: string; w: number; h: number }[] = [
  { name: 'Bed 160×200', w: 1.6, h: 2.0 },
  { name: 'Bed 140×200', w: 1.4, h: 2.0 },
  { name: 'Sofa 220×90', w: 2.2, h: 0.9 },
  { name: 'Table 120×80', w: 1.2, h: 0.8 },
  { name: 'Wardrobe 200×60', w: 2.0, h: 0.6 },
  { name: 'Desk 120×60', w: 1.2, h: 0.6 },
  { name: 'Bathtub 170×75', w: 1.7, h: 0.75 },
];

/** Approximate sRGB of the RAL classic codes developers quote most (RAL colour charts). */
const RAL: Record<string, string> = {
  '1013': '#e3d9c6',
  '1015': '#e6d2b5',
  '3000': '#a72920',
  '5010': '#0e294b',
  '6005': '#0f4336',
  '7016': '#383e42',
  '7035': '#cbd0cc',
  '7040': '#9da3a6',
  '8017': '#44322d',
  '9001': '#e9e0d2',
  '9002': '#d7d5cb',
  '9003': '#ecece7',
  '9004': '#2b2b2c',
  '9005': '#0e0e10',
  '9010': '#f1ece1',
  '9016': '#f1f0ea',
};

@Component({
  selector: 'uf-unit-page',
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
        title="Unit not available"
        text="This unit is not published."
        ><a class="uf-btn" [routerLink]="['/projects', slug(), 'units']"
          >All units</a
        ></uf-empty-state
      >
    } @else if (unit(); as u) {
      <nav class="uf-crumbs">
        <a [routerLink]="['/projects', slug()]">{{ doc()?.project?.name }}</a>
        <ng-icon name="lucideChevronRight" />
        <a [routerLink]="['/projects', slug(), 'buildings', u.building_code]"
          >Building {{ u.building_code }}</a
        >
        <ng-icon name="lucideChevronRight" />
        <a
          [routerLink]="['/projects', slug(), 'buildings', u.building_code]"
          [queryParams]="{ floor: u.floor_level }"
          >{{ u.floor_name }}</a
        >
        <ng-icon name="lucideChevronRight" /> <span>{{ u.code }}</span>
      </nav>
      <header class="head">
        <div class="head__main">
          <h1>{{ typeLabel(u.unit_type) }} {{ u.code }}</h1>
          <uf-status-chip domain="availability" [value]="u.availability" size="lg" />
        </div>
        <button
          type="button"
          class="uf-ghost"
          [attr.aria-pressed]="fav()"
          (click)="favs.toggle(slug(), u.code)"
        >
          <ng-icon name="lucideHeart" [class.is-on]="fav()" /> {{ fav() ? 'Saved' : 'Save' }}
        </button>
      </header>
      @if (u.indicative) {
        <p class="uf-indicative">
          <ng-icon name="lucideInfo" /> Plan and areas are indicative: they have not been verified
          against the final drawings yet.
        </p>
      }

      <div class="layout">
        <section class="main">
          @if (hero(); as h) {
            <figure class="hero3d">
              <div class="media">
                <img [src]="api.asset(h.url)" [alt]="h.alt_text || '3D view of ' + u.code" />
                @if (h.is_ai_generated) {
                  <span class="uf-ai-label">Illustrative — AI generated</span>
                }
              </div>
              <figcaption class="uf-muted small">
                3D view of {{ u.code }} from its floor plan.
                @if (h.is_ai_generated && h.ai_disclosure_text) {
                  {{ h.ai_disclosure_text }}.
                }
                @if (h.shared_from; as from) {
                  Shared with {{ from }} (layout {{ u.layout }}): the same plan, the finish may
                  differ.
                }
              </figcaption>
            </figure>
          }
          @if (u.plan; as plan) {
            <div class="planbox">
              <uf-plan-viewer
                [src]="api.asset(plan.url)"
                [width]="plan.width"
                [height]="plan.height"
                [polygons]="planPolygons()"
                [focus]="plan.ring"
                [mode]="furniture().length ? 'move' : 'view'"
                (polygonMoved)="onMoved($event)"
              />
              <p class="uf-hint planbox__hint">
                <ng-icon name="lucideMaximize2" /> The plan opens zoomed on {{ u.code }}; scroll to
                zoom, drag to see the neighbours.
              </p>
              @if (pxPerM()) {
                <div class="furn">
                  <span class="uf-muted small">Try furniture, true to scale:</span>
                  @for (f of catalogue; track f.name) {
                    <button type="button" class="uf-chip-btn" (click)="addFurniture(f)">
                      {{ f.name }}
                    </button>
                  }
                  @if (furniture().length) {
                    <button type="button" class="uf-chip-btn" (click)="rotateLast()">Rotate</button>
                    <button type="button" class="uf-chip-btn" (click)="furniture.set([])">
                      Clear
                    </button>
                    <span class="uf-muted small">Drag the pieces on the plan.</span>
                  }
                </div>
              }
            </div>
          }
          @if (doc()?.massing || building()?.model) {
            <section class="uf-card model">
              <h2>In the building</h2>
              @defer (on viewport) {
                <uf-massing-viewer
                  class="model__view"
                  [src]="api.asset(building()?.model?.url ?? doc()?.massing?.url)"
                  [buildingCode]="building()?.model ? null : u.building_code"
                  [floorLevel]="u.floor_level"
                  [selectedUnitId]="u.unit_id"
                  tintMode="neutral"
                  [siteFeatures]="siteFeatures3d()"
                />
              } @placeholder {
                <div class="uf-skeleton model__view"></div>
              }
              <p class="uf-muted small">{{ u.code }} is highlighted; the other floors are faded.</p>
            </section>
          }
          @if (otherMedia().length) {
            @if (otherMedia()[0].shared_from; as from) {
              <p class="uf-indicative">
                <ng-icon name="lucideInfo" /> Renders of layout {{ u.layout }}, shared with
                {{ from }}: the same plan, the finish may differ.
              </p>
            }
            <div class="gallery">
              @for (m of otherMedia(); track m.url) {
                <figure>
                  <div class="media">
                    @if (m.mime.startsWith('image/')) {
                      <img
                        [src]="api.asset(m.url)"
                        [alt]="m.alt_text || typeLabel(u.unit_type) + ' ' + u.code"
                        loading="lazy"
                      />
                    } @else if (m.mime === 'video/mp4') {
                      <video [src]="api.asset(m.url)" controls preload="none"></video>
                    } @else {
                      <a [href]="api.asset(m.url)" target="_blank" rel="noopener">Open document</a>
                    }
                    @if (m.is_ai_generated) {
                      <span class="uf-ai-label">Illustrative — AI generated</span>
                    }
                  </div>
                  @if (m.is_ai_generated && m.ai_disclosure_text) {
                    <figcaption class="uf-muted small">{{ m.ai_disclosure_text }}</figcaption>
                  }
                </figure>
              }
            </div>
          }
          @if (u.description) {
            <section class="uf-card">
              <h2>Description</h2>
              <p class="pre">{{ u.description }}</p>
            </section>
          }
        </section>

        <aside class="side">
          @if (cover(); as g) {
            <a
              class="uf-card cover"
              [routerLink]="['/projects', slug(), 'buildings', u.building_code]"
            >
              <img [src]="api.asset(g.url)" [alt]="g.caption" loading="lazy" />
              <span class="cover__cap">{{ g.caption }} · building {{ u.building_code }}</span>
            </a>
          }
          <section class="uf-card action" aria-label="Price and actions">
            <p class="price">{{ price() ?? 'Price on request' }}</p>
            @if (u.price?.per_m2) {
              <p
                class="uf-muted"
                [title]="
                  'Per m² of ' +
                  areaLabel(u.price?.per_m2_area_type) +
                  (u.price?.per_m2_area_verified ? ' (verified)' : ' (indicative)')
                "
              >
                {{ money({ amount: u.price!.per_m2!, currency: u.price!.currency }) }} per m²
                {{ areaLabel(u.price?.per_m2_area_type) }}
              </p>
            }
            @if (doc()?.project?.price_note; as n) {
              <p class="uf-muted uf-small">{{ n }}</p>
            }
            <div class="action__row">
              @if (contact(); as c) {
                <a class="uf-btn" [href]="c"
                  ><ng-icon name="lucideMail" /> Ask about {{ u.code }}</a
                >
              }
              <button
                type="button"
                class="uf-ghost"
                [attr.aria-pressed]="fav()"
                (click)="favs.toggle(slug(), u.code)"
              >
                <ng-icon name="lucideHeart" [class.is-on]="fav()" /> {{ fav() ? 'Saved' : 'Save' }}
              </button>
            </div>
            @if (u.payment_plan; as p) {
              <p class="uf-muted uf-small"><ng-icon name="lucideCalendar" /> {{ p.name }}</p>
            }
          </section>
          <section class="uf-card">
            <h2>Facts</h2>
            <dl>
              <dt>Type</dt>
              <dd>{{ typeLabel(u.unit_type) }}</dd>
              @if (u.wall_colour) {
                <dt>Walls</dt>
                <dd>
                  <span class="swatch" [style.background]="swatch(u.wall_colour)"></span
                  >{{ u.wall_colour }}
                </dd>
              }
              <dt>Floor</dt>
              <dd>
                <a
                  [routerLink]="['/projects', slug(), 'buildings', u.building_code]"
                  [queryParams]="{ floor: u.floor_level, unit: u.code }"
                  >{{ u.floor_name }}, building {{ u.building_code }}</a
                >
              </dd>
              @if (u.rooms?.rooms != null) {
                <dt>Rooms</dt>
                <dd>{{ u.rooms?.rooms }}</dd>
              }
              @if (u.rooms?.bedrooms != null) {
                <dt>Bedrooms</dt>
                <dd>{{ u.rooms?.bedrooms }}</dd>
              }
              @if (u.rooms?.bathrooms != null) {
                <dt>Bathrooms</dt>
                <dd>{{ u.rooms?.bathrooms }}</dd>
              }
              @if (u.rooms?.orientation) {
                <dt>Orientation</dt>
                <dd>{{ u.rooms?.orientation }}</dd>
              }
              @if (u.entrance) {
                <dt>Entrance</dt>
                <dd>{{ u.entrance }}</dd>
              }
            </dl>
          </section>
          @if (building()?.terms; as t) {
            <section class="uf-card">
              <h2>Terms</h2>
              <p class="pre">{{ t }}</p>
            </section>
          }
          @if (areaRows().length) {
            <section class="uf-card">
              <h2>Areas</h2>
              <table>
                @for (a of areaRows(); track a.key) {
                  <tr>
                    <th scope="row" [title]="a.description ?? ''">{{ a.label }}</th>
                    <td>{{ a.value }}</td>
                  </tr>
                }
              </table>
              <p class="uf-muted small">
                @if (u.indicative) {
                  Measured from the plan, indicative.
                } @else {
                  Verified against the drawings.
                }
              </p>
            </section>
          }
          @if (u.payment_plan; as p) {
            <section class="uf-card">
              <h2>{{ p.name }}</h2>
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
            </section>
          }
          @for (p of u.promotions ?? []; track p.name) {
            <section class="uf-card">
              <h2>{{ p.name }}</h2>
              @if (p.terms) {
                <p>{{ p.terms }}</p>
              }
              @if (p.valid_to) {
                <p class="uf-muted">Until {{ p.valid_to }}</p>
              }
            </section>
          }
        </aside>
      </div>
    } @else {
      <p class="uf-muted">Loading…</p>
    }
  `,
  styles: `
    .planbox {
      display: grid;
      gap: 0.25rem;
    }
    .planbox uf-plan-viewer {
      --uf-plan-max-height: 60vh;
      border-radius: var(--uf-radius);
      overflow: hidden;
    }
    .planbox__hint ng-icon {
      vertical-align: -0.15em;
    }
    .model {
      display: grid;
      gap: 0.5rem;
    }
    .model h2 {
      margin: 0;
    }
    .model__view {
      --uf-3d-height: 46vh;
      --uf-3d-min-height: 300px;
      display: block;
      border-radius: var(--uf-radius-sm);
      overflow: hidden;
    }
    .cover {
      display: block;
      padding: 0;
      overflow: hidden;
      position: relative;
      text-decoration: none;
      color: inherit;
    }
    .cover img {
      width: 100%;
      aspect-ratio: 16 / 10;
      object-fit: cover;
      display: block;
    }
    .cover__cap {
      display: block;
      padding: 0.4rem 0.75rem;
      font-size: 0.85rem;
      color: var(--uf-muted);
    }
    .head {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 1rem;
      margin-bottom: 0.75rem;
    }
    .head__main {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
    }
    .head__main h1 {
      margin: 0;
    }
    ng-icon.is-on {
      color: var(--uf-tone-bad-fg);
    }
    .action {
      position: sticky;
      top: calc(4.5rem);
      display: grid;
      gap: 0.5rem;
    }
    .action__row {
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
    }
    .action .uf-small ng-icon {
      vertical-align: -0.15em;
    }
    @media (max-width: 900px) {
      .action {
        position: fixed;
        left: 0;
        right: 0;
        bottom: 0;
        top: auto;
        border-radius: var(--uf-radius) var(--uf-radius) 0 0;
        box-shadow: var(--uf-shadow-lg);
        z-index: 6;
      }
      .layout {
        padding-bottom: 9rem;
      }
    }
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr);
      gap: 1rem;
      margin-top: 0.75rem;
    }
    @media (max-width: 900px) {
      .layout {
        grid-template-columns: 1fr;
      }
      .side {
        order: -1;
      }
    }
    .main,
    .side {
      display: grid;
      gap: 1rem;
      align-content: start;
      min-width: 0;
    }
    .price {
      font-size: 1.6rem;
      font-weight: 700;
      margin: 0;
    }
    .gallery {
      display: grid;
      gap: 0.75rem;
      grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr));
    }
    figure {
      margin: 0;
      display: grid;
      gap: 0.25rem;
    }
    .media {
      position: relative;
    }
    .furn {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.4rem;
      margin: 0.5rem 0 0;
    }
    .swatch {
      display: inline-block;
      width: 1em;
      height: 1em;
      border: 1px solid var(--uf-border);
      border-radius: 3px;
      vertical-align: -0.15em;
      margin-right: 0.35em;
      background: transparent;
    }
    /* the generated 3D plan view leads the page: shown whole, never cropped to 4:3 */
    .hero3d img {
      aspect-ratio: auto;
      max-height: 72vh;
      object-fit: contain;
      background: #fff;
      border: 1px solid var(--uf-border);
    }
    figure img,
    figure video {
      width: 100%;
      border-radius: var(--uf-radius);
      display: block;
      background: #e2e8f0;
      aspect-ratio: 4 / 3;
      object-fit: cover;
    }
    dl {
      display: grid;
      grid-template-columns: auto 1fr;
      gap: 0.25rem 1rem;
      margin: 0;
    }
    dt {
      color: var(--uf-muted);
    }
    dd {
      margin: 0;
    }
    table {
      width: 100%;
      border-collapse: collapse;
    }
    th,
    td {
      text-align: left;
      padding: 0.3rem 0;
      border-bottom: 1px solid var(--uf-border);
      font-weight: normal;
    }
    td {
      text-align: right;
      font-weight: 600;
    }
    .small {
      font-size: 0.85rem;
    }
    .pre {
      white-space: pre-line;
    }
  `,
})
export class UnitPage {
  protected readonly api = inject(PortalApi);
  private readonly store = inject(SiteStore);
  protected readonly favs = inject(Favourites);
  readonly slug = input.required<string>();
  readonly code = input.required<string>();
  readonly unit = signal<UnitDoc | null>(null);
  readonly doc = signal<ProjectDoc | null>(null);
  readonly notFound = signal(false);
  protected readonly money = money;
  protected readonly typeLabel = typeLabel;

  readonly av = computed(() => AVAILABILITY[this.unit()?.availability ?? 'available']);
  readonly price = computed(() => money(this.unit()?.price));
  /** The unit's building as published: its terms (ADR-0014 Decision 3). */
  readonly building = computed(
    () => this.doc()?.buildings.find((b) => b.code === this.unit()?.building_code) ?? null,
  );
  readonly fav = computed(() => !!this.unit() && this.favs.has(this.slug(), this.unit()!.code));
  readonly cover = computed(() => this.doc()?.gallery?.[0] ?? null);
  // --- furniture ruler (ADR-0017, owner's item 4): pieces at true scale, dragged on the plan
  readonly catalogue = FURNITURE;
  readonly furniture = signal<Piece[]>([]);
  /** Plan pixels per metre from the unit's outline and its largest stated area; null without them. */
  readonly pxPerM = computed(() => {
    const u = this.unit();
    const ring = u?.plan?.ring;
    const areas = Object.values(u?.areas ?? {})
      .map(Number)
      .filter((x) => x > 0);
    if (!u?.plan || !ring || ring.length < 3 || !areas.length) return null;
    const w = u.plan.width;
    const h = u.plan.height;
    let a = 0;
    for (let i = 0; i < ring.length; i++) {
      const [x0, y0] = ring[i];
      const [x1, y1] = ring[(i + 1) % ring.length];
      a += x0 * w * y1 * h - x1 * w * y0 * h;
    }
    const px2 = Math.abs(a) / 2;
    return px2 > 0 ? Math.sqrt(px2 / Math.max(...areas)) : null;
  });

  rect(f: Piece): Ring {
    const u = this.unit()!;
    const k = this.pxPerM() ?? 1;
    const [w, h] = f.rotated ? [f.h, f.w] : [f.w, f.h];
    const hw = (w * k) / 2 / u.plan!.width;
    const hh = (h * k) / 2 / u.plan!.height;
    return [
      [f.cx - hw, f.cy - hh],
      [f.cx + hw, f.cy - hh],
      [f.cx + hw, f.cy + hh],
      [f.cx - hw, f.cy + hh],
    ];
  }

  addFurniture(f: { name: string; w: number; h: number }): void {
    const ring = this.unit()?.plan?.ring;
    if (!ring) return;
    const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length;
    const cy = ring.reduce((s, p) => s + p[1], 0) / ring.length;
    const n = this.furniture().length;
    this.furniture.update((list) => [
      ...list,
      {
        id: `furniture-${Date.now()}-${n}`,
        ...f,
        cx: cx + n * 0.01,
        cy: cy + n * 0.01,
        rotated: false,
      },
    ]);
  }

  rotateLast(): void {
    this.furniture.update((list) =>
      list.map((f, i) => (i === list.length - 1 ? { ...f, rotated: !f.rotated } : f)),
    );
  }

  onMoved(mv: PolygonMove): void {
    this.furniture.update((list) =>
      list.map((f) => (f.id === mv.id ? { ...f, cx: f.cx + mv.dx, cy: f.cy + mv.dy } : f)),
    );
  }
  /** A swatch for a hex colour or one of the common RAL codes; transparent otherwise. */
  swatch(code: string): string {
    const c = code.trim().toLowerCase();
    if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/.test(c)) return c;
    const ral = c.replace(/^ral\s*/, '');
    return RAL[ral] ?? 'transparent';
  }
  /** The 3D plan view (generated or uploaded `plan_render`) leads the page (ADR-0017). */
  readonly hero = computed(
    () =>
      (this.unit()?.media ?? []).find(
        (m) => m.kind === 'plan_render' && m.mime.startsWith('image/'),
      ) ?? null,
  );
  readonly otherMedia = computed(() => {
    const h = this.hero();
    return (this.unit()?.media ?? []).filter((m) => m !== h);
  });
  readonly siteFeatures3d = computed<SiteFeature3D[]>(() =>
    (this.doc()?.site?.features ?? [])
      .filter((f) => f.ring_m && f.ring_m.length >= 3)
      .map((f) => ({ kind: f.kind, name: f.name, ring_m: f.ring_m as [number, number][] })),
  );
  readonly planPolygons = computed<PlanPolygon[]>(() => {
    const u = this.unit();
    if (!u?.plan?.ring) return [];
    return [
      {
        id: u.unit_id,
        ring: u.plan.ring,
        label: u.code,
        fill: 'color-mix(in srgb, var(--uf-primary) 28%, transparent)',
        stroke: 'var(--uf-primary)',
        title: u.code,
        locked: true,
      },
      ...this.furniture().map((f) => ({
        id: f.id,
        ring: this.rect(f),
        label: f.name,
        kind: 'furniture' as const,
        title: f.name,
      })),
    ];
  });
  readonly areaRows = computed(() => {
    const areas = this.unit()?.areas ?? {};
    const defs = this.doc()?.project.area_definitions ?? [];
    return Object.entries(areas).map(([key, v]) => {
      const d = defs.find((x) => x.key === key);
      return { key, label: d?.label ?? key, description: d?.description ?? null, value: area(v) };
    });
  });
  readonly contact = computed(() => {
    const b = this.doc()?.branding;
    const u = this.unit();
    if (!b?.contact_email || !u) return null;
    return `mailto:${b.contact_email}?subject=${encodeURIComponent(`${this.doc()?.project.name} — ${u.code}`)}`;
  });

  constructor() {
    combineLatest([toObservable(this.slug), toObservable(this.code)]).subscribe(
      ([s, c]) => void this.load(s, c),
    );
  }

  areaLabel(key: string | null | undefined): string {
    return (
      (this.doc()?.project.area_definitions ?? [])
        .find((d) => d.key === key)
        ?.label?.toLowerCase() ??
      key ??
      ''
    );
  }

  private async load(slug: string, code: string): Promise<void> {
    this.unit.set(null);
    this.notFound.set(false);
    try {
      const [d, u] = await Promise.all([this.store.project(slug), this.api.unit(slug, code)]);
      this.doc.set(d);
      this.unit.set(u);
      document.title = `${u.code} — ${d.project.name}`;
    } catch (e) {
      if (problemOf(e).status === 404) this.notFound.set(true);
    }
  }
}
