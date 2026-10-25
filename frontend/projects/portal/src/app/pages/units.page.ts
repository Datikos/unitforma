import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { combineLatest } from 'rxjs';
import { EmptyStateComponent, StatusChipComponent, UF_ICONS } from 'ui';
import { AVAILABILITY, area, money, typeLabel } from '../core/format';
import {
  Availability,
  PortalApi,
  ProjectDoc,
  UnitDoc,
  UnitFilters,
  problemOf,
} from '../core/portal-api';
import { SiteStore } from '../core/site.store';
import { UnitCardComponent } from '../ui/unit-card';

type View = 'cards' | 'table';
const VIEW_KEY = 'uf:units-view';

interface Form {
  availability: Availability[];
  unit_type: string[];
  building: string;
  /** Meaningful only with a building (ADR-0013 Decision 2). */
  entrance: string[];
  rooms: number[];
  min_price: number | null;
  max_price: number | null;
  min_area: number | null;
  max_area: number | null;
  sort: NonNullable<UnitFilters['sort']>;
  view: View;
}

/** Units list with filters; the filter state lives in the URL so results can be shared (plan §7.1). */
@Component({
  selector: 'uf-units-page',
  imports: [
    FormsModule,
    RouterLink,
    NgIcon,
    UnitCardComponent,
    EmptyStateComponent,
    StatusChipComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    @if (doc(); as d) {
      <nav class="uf-crumbs">
        <a [routerLink]="['/projects', slug()]">{{ d.project.name }}</a>
        <ng-icon name="lucideChevronRight" /> <span>Units</span>
      </nav>
      <div class="layout">
        <form class="uf-card filters" (ngSubmit)="apply()" aria-label="Filters">
          <h2 class="filters__title"><ng-icon name="lucideListFilter" /> Filters</h2>
          <fieldset>
            <legend>Availability</legend>
            @for (a of availabilities; track a.key) {
              <label
                ><input
                  type="checkbox"
                  [checked]="form.availability.includes(a.key)"
                  (change)="toggle(form.availability, a.key)"
                />
                {{ a.label }}</label
              >
            }
          </fieldset>
          @if (d.stats.unit_types.length > 1) {
            <fieldset>
              <legend>Type</legend>
              @for (t of d.stats.unit_types; track t) {
                <label
                  ><input
                    type="checkbox"
                    [checked]="form.unit_type.includes(t)"
                    (change)="toggle(form.unit_type, t)"
                  />
                  {{ typeLabel(t) }}</label
                >
              }
            </fieldset>
          }
          @if (d.buildings.length > 1) {
            <label
              >Building
              <select
                [(ngModel)]="form.building"
                (ngModelChange)="form.entrance = []"
                name="building"
              >
                <option value="">All</option>
                @for (b of d.buildings; track b.code) {
                  <option [value]="b.code">{{ b.name || b.code }}</option>
                }
              </select></label
            >
          }
          @if (entrancesFor(d); as es) {
            @if (es.length) {
              <fieldset>
                <legend>Entrance</legend>
                @for (e of es; track e) {
                  <label class="chip"
                    ><input
                      type="checkbox"
                      [checked]="form.entrance.includes(e)"
                      (change)="toggle(form.entrance, e)"
                    />
                    {{ e }}</label
                  >
                }
              </fieldset>
            }
          }
          @if (d.stats.rooms.length) {
            <fieldset>
              <legend>Rooms</legend>
              @for (r of roomOptions; track r) {
                <label class="chip"
                  ><input
                    type="checkbox"
                    [checked]="form.rooms.includes(r)"
                    (change)="toggle(form.rooms, r)"
                  />
                  {{ r === 5 ? '5+' : r }}</label
                >
              }
            </fieldset>
          }
          <fieldset>
            <legend>Price ({{ d.project.currency }})</legend>
            <div class="pair">
              <input
                type="number"
                min="0"
                placeholder="min"
                [(ngModel)]="form.min_price"
                name="minp"
                aria-label="Minimum price"
              /><input
                type="number"
                min="0"
                placeholder="max"
                [(ngModel)]="form.max_price"
                name="maxp"
                aria-label="Maximum price"
              />
            </div>
          </fieldset>
          <fieldset>
            <legend>Area (m²)</legend>
            <div class="pair">
              <input
                type="number"
                min="0"
                placeholder="min"
                [(ngModel)]="form.min_area"
                name="mina"
                aria-label="Minimum area"
              /><input
                type="number"
                min="0"
                placeholder="max"
                [(ngModel)]="form.max_area"
                name="maxa"
                aria-label="Maximum area"
              />
            </div>
          </fieldset>
          <label
            >Sort
            <select [(ngModel)]="form.sort" name="sort">
              <option value="code">Building and floor</option>
              <option value="price_asc">Price, low to high</option>
              <option value="price_desc">Price, high to low</option>
              <option value="area_asc">Area, small to large</option>
              <option value="area_desc">Area, large to small</option>
            </select>
          </label>
          <div class="actions">
            <button type="submit"><ng-icon name="lucideSearch" /> Show units</button
            ><button type="button" class="uf-ghost" (click)="reset()">Reset</button>
          </div>
        </form>
        <section aria-live="polite" class="results">
          <div class="results__bar">
            <div class="results__top">
              <p class="results__count">
                <strong>{{ total() }}</strong> unit{{ total() === 1 ? '' : 's' }}
                @if (hasPriceFilter()) {
                  <span class="uf-muted uf-small">
                    · units with price on request are not included in price filters</span
                  >
                }
              </p>
              <div class="uf-segmented" role="group" aria-label="List view">
                <button
                  type="button"
                  [attr.aria-pressed]="form.view === 'cards'"
                  (click)="setView('cards')"
                >
                  <ng-icon name="lucideLayoutGrid" /> Cards
                </button>
                <button
                  type="button"
                  [attr.aria-pressed]="form.view === 'table'"
                  (click)="setView('table')"
                >
                  <ng-icon name="lucideTable" /> Table
                </button>
              </div>
            </div>
            @if (d.project.price_note; as n) {
              <p class="uf-muted uf-small note"><ng-icon name="lucideInfo" /> {{ n }}</p>
            }
            @if (activeChips().length) {
              <ul class="uf-chips">
                @for (c of activeChips(); track c.key) {
                  <li>
                    <button
                      type="button"
                      class="uf-chip chip"
                      (click)="remove(c.key)"
                      [attr.aria-label]="'Remove filter ' + c.label"
                    >
                      {{ c.label }} <ng-icon name="lucideX" />
                    </button>
                  </li>
                }
                <li>
                  <button type="button" class="uf-ghost clear" (click)="reset()">Clear all</button>
                </li>
              </ul>
            }
          </div>
          @if (loading()) {
            <div class="uf-grid">
              @for (i of [1, 2, 3, 4, 5, 6]; track i) {
                <div class="uf-card sk">
                  <span class="uf-skeleton sk__img"></span><span class="uf-skeleton"></span
                  ><span class="uf-skeleton sk__short"></span>
                </div>
              }
            </div>
          } @else if (!items().length) {
            <uf-empty-state
              icon="lucideSearch"
              title="No units match these filters"
              text="Widen the price or area range, or clear a filter to see more."
            >
              <button type="button" (click)="reset()">Clear filters</button>
            </uf-empty-state>
          } @else if (form.view === 'table') {
            <div class="tablewrap">
              <table class="units">
                <thead>
                  <tr>
                    <th>Building</th>
                    <th>Floor</th>
                    @if (hasEntrance()) {
                      <th>Entrance</th>
                    }
                    <th>Unit</th>
                    <th>Type</th>
                    <th class="num">Rooms</th>
                    <th class="num">Area</th>
                    <th class="num">Price</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  @for (u of items(); track u.unit_id) {
                    <tr>
                      <td>{{ u.building_code }}</td>
                      <td>{{ u.floor_name }}</td>
                      @if (hasEntrance()) {
                        <td>{{ u.entrance ?? '' }}</td>
                      }
                      <td>
                        <a [routerLink]="['/projects', slug(), 'units', u.code]">{{ u.code }}</a>
                      </td>
                      <td>{{ typeLabel(u.unit_type) }}</td>
                      <td class="num">{{ u.rooms?.rooms ?? '' }}</td>
                      <td class="num">{{ areaOf(u, d.project.price_area_type) ?? '' }}</td>
                      <td class="num">{{ money(u.price) ?? 'On request' }}</td>
                      <td><uf-status-chip domain="availability" [value]="u.availability" /></td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          } @else {
            <div class="uf-grid">
              @for (u of items(); track u.unit_id) {
                <uf-unit-card
                  [unit]="u"
                  [slug]="slug()"
                  [mainAreaType]="d.project.price_area_type"
                />
              }
            </div>
          }
        </section>
      </div>
    } @else if (error()) {
      <uf-empty-state icon="lucideCircleX" title="Could not load units" [text]="error()" />
    } @else {
      <p class="uf-muted">Loading…</p>
    }
  `,
  styles: `
    .layout {
      display: grid;
      grid-template-columns: 280px 1fr;
      gap: 1rem;
      align-items: start;
    }
    @media (max-width: 860px) {
      .layout {
        grid-template-columns: 1fr;
      }
    }
    .filters {
      display: grid;
      gap: 0.75rem;
    }
    fieldset {
      border: 0;
      padding: 0;
      margin: 0;
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 0.75rem;
    }
    legend {
      font-weight: 600;
      margin-bottom: 0.25rem;
      width: 100%;
    }
    .pair {
      display: flex;
      gap: 0.5rem;
    }
    .pair input {
      width: 100%;
      min-width: 0;
    }
    .actions {
      display: flex;
      gap: 0.5rem;
    }
    .filters__title {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 1rem;
      margin: 0;
    }
    .results {
      display: grid;
      gap: 0.75rem;
      min-width: 0;
    }
    .results__bar {
      display: grid;
      gap: 0.5rem;
    }
    .results__top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
    }
    .note {
      margin: 0;
      display: flex;
      align-items: center;
      gap: 0.35rem;
    }
    .tablewrap {
      overflow-x: auto;
    }
    .units {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.95rem;
      background: var(--uf-surface);
      border-radius: var(--uf-radius-sm);
    }
    .units th,
    .units td {
      padding: 0.45rem 0.6rem;
      border-bottom: 1px solid var(--uf-border);
      text-align: left;
      white-space: nowrap;
    }
    .units th {
      font-weight: 600;
      color: var(--uf-muted);
    }
    .units .num {
      text-align: right;
      font-variant-numeric: tabular-nums;
    }
    .results__count {
      margin: 0;
    }
    .chip {
      cursor: pointer;
      border-color: var(--uf-primary);
      color: var(--uf-primary-strong);
      background: var(--uf-primary-soft);
      padding: 0.15rem 0.5rem 0.15rem 0.7rem;
    }
    .clear {
      padding: 0.15rem 0.6rem;
      font-size: 0.85rem;
    }
    .sk {
      display: grid;
      gap: 0.5rem;
      padding: 0;
      overflow: hidden;
    }
    .sk__img {
      aspect-ratio: 4 / 3;
      border-radius: 0;
    }
    .sk .uf-skeleton:not(.sk__img) {
      margin: 0 1rem;
      height: 0.9rem;
    }
    .sk__short {
      width: 50%;
      margin-bottom: 1rem !important;
    }
  `,
})
export class UnitsPage {
  private readonly api = inject(PortalApi);
  private readonly store = inject(SiteStore);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  readonly slug = input.required<string>();
  readonly doc = signal<ProjectDoc | null>(null);
  readonly items = signal<UnitDoc[]>([]);
  readonly total = signal(0);
  readonly error = signal<string | null>(null);
  readonly hasPriceFilter = signal(false);
  readonly loading = signal(true);
  readonly activeChips = signal<{ key: string; label: string }[]>([]);
  protected readonly availabilities = (Object.keys(AVAILABILITY) as Availability[]).map((key) => ({
    key,
    label: AVAILABILITY[key].label,
  }));
  protected readonly roomOptions = [1, 2, 3, 4, 5];
  protected readonly typeLabel = typeLabel;
  protected readonly money = money;
  readonly hasEntrance = computed(() => this.items().some((u) => !!u.entrance));
  readonly priceFilterHint = computed(() => this.hasPriceFilter());
  form: Form = blank();

  constructor() {
    combineLatest([toObservable(this.slug), this.route.queryParamMap]).subscribe(
      ([slug, q]) => void this.load(slug, q),
    );
  }

  private async load(slug: string, q: import('@angular/router').ParamMap): Promise<void> {
    try {
      this.doc.set(await this.store.project(slug));
      this.form = fromQuery(q);
      this.activeChips.set(chipsOf(this.form, this.doc()));
      this.loading.set(true);
      const f = toFilters(this.form);
      this.hasPriceFilter.set(f.min_price != null || f.max_price != null);
      const res = await this.api.units(slug, f);
      this.items.set(res.items);
      this.total.set(res.total);
    } catch (e) {
      this.error.set(problemOf(e).title ?? 'Could not load units');
    } finally {
      this.loading.set(false);
    }
  }

  /** Entrances of the chosen building; the filter means nothing across buildings (ADR-0013). */
  entrancesFor(d: ProjectDoc): string[] {
    if (!this.form.building) return [];
    return d.buildings.find((b) => b.code === this.form.building)?.entrances ?? [];
  }

  areaOf(u: UnitDoc, type: string): string | null {
    const areas = u.areas ?? {};
    return area(areas[type] ?? areas[Object.keys(areas)[0]]);
  }

  /** Cards or table; remembered in this browser and carried in the link (ADR-0013 Decision 5). */
  setView(v: View): void {
    this.form.view = v;
    try {
      localStorage.setItem(VIEW_KEY, v);
    } catch {
      /* storage unavailable */
    }
    this.apply();
  }

  /** Drop one active filter (a chip) and reload. */
  remove(key: string): void {
    const f = this.form;
    if (key.startsWith('availability:'))
      f.availability = f.availability.filter((a) => a !== key.slice(13));
    else if (key.startsWith('entrance:')) f.entrance = f.entrance.filter((e) => e !== key.slice(9));
    else if (key.startsWith('type:')) f.unit_type = f.unit_type.filter((t) => t !== key.slice(5));
    else if (key.startsWith('rooms:')) f.rooms = f.rooms.filter((r) => String(r) !== key.slice(6));
    else if (key === 'building') f.building = '';
    else if (key === 'price') f.min_price = f.max_price = null;
    else if (key === 'area') f.min_area = f.max_area = null;
    else if (key === 'sort') f.sort = 'code';
    this.apply();
  }

  toggle<T>(list: T[], v: T): void {
    const i = list.indexOf(v);
    if (i >= 0) list.splice(i, 1);
    else list.push(v);
  }

  apply(): void {
    void this.router.navigate([], { queryParams: toQuery(this.form) });
  }

  reset(): void {
    this.form = blank();
    void this.router.navigate([], { queryParams: {} });
  }
}

/** The active filters as removable chips. */
function chipsOf(f: Form, d: ProjectDoc | null): { key: string; label: string }[] {
  const out: { key: string; label: string }[] = [];
  for (const a of f.availability)
    out.push({ key: `availability:${a}`, label: AVAILABILITY[a].label });
  for (const t of f.unit_type) out.push({ key: `type:${t}`, label: typeLabel(t) });
  if (f.building)
    out.push({
      key: 'building',
      label: d?.buildings.find((b) => b.code === f.building)?.name || `Building ${f.building}`,
    });
  if (f.building)
    for (const e of f.entrance) out.push({ key: `entrance:${e}`, label: `Entrance ${e}` });
  for (const r of f.rooms) out.push({ key: `rooms:${r}`, label: `${r === 5 ? '5+' : r} rooms` });
  if (f.min_price != null || f.max_price != null)
    out.push({ key: 'price', label: `Price ${f.min_price ?? '…'} – ${f.max_price ?? '…'}` });
  if (f.min_area != null || f.max_area != null)
    out.push({ key: 'area', label: `Area ${f.min_area ?? '…'} – ${f.max_area ?? '…'} m²` });
  if (f.sort !== 'code')
    out.push({
      key: 'sort',
      label:
        { price_asc: 'Price ↑', price_desc: 'Price ↓', area_asc: 'Area ↑', area_desc: 'Area ↓' }[
          f.sort
        ] ?? f.sort,
    });
  return out;
}

function storedView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === 'table' ? 'table' : 'cards';
  } catch {
    return 'cards';
  }
}

function blank(): Form {
  return {
    availability: [],
    unit_type: [],
    building: '',
    entrance: [],
    rooms: [],
    min_price: null,
    max_price: null,
    min_area: null,
    max_area: null,
    sort: 'code',
    view: storedView(),
  };
}

function num(v: string | null): number | null {
  return v === null || v === '' || isNaN(Number(v)) ? null : Number(v);
}

function fromQuery(q: import('@angular/router').ParamMap): Form {
  const sort = q.get('sort') as Form['sort'] | null;
  return {
    availability: q.getAll('availability').filter((a): a is Availability => a in AVAILABILITY),
    unit_type: q.getAll('type'),
    building: q.get('building') ?? '',
    entrance: q.getAll('entrance'),
    rooms: q
      .getAll('rooms')
      .map(Number)
      .filter((n) => n > 0),
    min_price: num(q.get('min_price')),
    max_price: num(q.get('max_price')),
    min_area: num(q.get('min_area')),
    max_area: num(q.get('max_area')),
    sort:
      sort && ['code', 'price_asc', 'price_desc', 'area_asc', 'area_desc'].includes(sort)
        ? sort
        : 'code',
    view: q.get('view') === 'table' ? 'table' : q.get('view') === 'cards' ? 'cards' : storedView(),
  };
}

function toQuery(f: Form): Record<string, unknown> {
  return {
    availability: f.availability.length ? f.availability : null,
    type: f.unit_type.length ? f.unit_type : null,
    building: f.building || null,
    entrance: f.building && f.entrance.length ? f.entrance : null,
    rooms: f.rooms.length ? f.rooms : null,
    min_price: f.min_price ?? null,
    max_price: f.max_price ?? null,
    min_area: f.min_area ?? null,
    max_area: f.max_area ?? null,
    sort: f.sort === 'code' ? null : f.sort,
    view: f.view === 'table' ? 'table' : null,
  };
}

function toFilters(f: Form): UnitFilters {
  return {
    availability: f.availability,
    unit_type: f.unit_type,
    building: f.building ? [f.building] : [],
    entrance: f.building ? f.entrance : [],
    rooms: f.rooms,
    min_price: f.min_price,
    max_price: f.max_price,
    min_area: f.min_area,
    max_area: f.max_area,
    sort: f.sort,
  };
}
