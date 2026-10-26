import { ChangeDetectionStrategy, Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { StatusChipComponent, UF_ICONS, statusOf } from 'ui';
import { Favourites } from '../core/favourites';
import { area, money, typeLabel } from '../core/format';
import { PortalApi, UnitDoc } from '../core/portal-api';

/** One unit in a list: cover (first image or the plan), code and status, facts, price, save. */
@Component({
  selector: 'uf-unit-card',
  imports: [RouterLink, NgIcon, StatusChipComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let u = unit();
    <article
      class="uf-card uc"
      [class.uc--unavailable]="u.availability === 'sold' || u.availability === 'withdrawn'"
    >
      <a [routerLink]="link()" class="uc__cover" [attr.aria-label]="'Open ' + u.code">
        @if (cover(); as c) {
          @if (crop(); as cr) {
            <span
              class="uc__plan"
              role="img"
              [attr.aria-label]="typeLabel(u.unit_type) + ' ' + u.code + ' on the floor plan'"
              [style.background-image]="'url(' + c + ')'"
              [style.background-size]="cr.size"
              [style.background-position]="cr.position"
            ></span>
          } @else {
            <img [src]="c" [alt]="typeLabel(u.unit_type) + ' ' + u.code" loading="lazy" />
          }
        } @else {
          <span class="uc__ph"><ng-icon [name]="typeIcon()" /></span>
        }
        <span class="uc__status"
          ><uf-status-chip domain="availability" [value]="u.availability"
        /></span>
      </a>
      <div class="uc__body">
        <header class="uc__head">
          <a [routerLink]="link()" class="uc__code">{{ u.code }}</a>
          <span class="uf-muted uc__type">{{ typeLabel(u.unit_type) }}</span>
        </header>
        <ul class="uc__facts">
          <li><ng-icon name="lucideLayers" /> {{ u.floor_name }}</li>
          <li><ng-icon name="lucideBuilding2" /> Building {{ u.building_code }}</li>
          @if (u.entrance) {
            <li><ng-icon name="lucideMapPin" /> Entrance {{ u.entrance }}</li>
          }
          @if (u.rooms?.rooms) {
            <li><ng-icon name="lucideDoorOpen" /> {{ u.rooms?.rooms }} rooms</li>
          }
          @if (u.layout) {
            <li><ng-icon name="lucideLayoutGrid" /> Plan {{ u.layout }}</li>
          }
          @if (mainArea(); as a) {
            <li><ng-icon name="lucideMaximize2" /> {{ a }}</li>
          }
        </ul>
        <footer class="uc__foot">
          <div class="uc__price">
            <strong>{{ price() ?? 'Price on request' }}</strong>
            @if (perM2(); as p) {
              <span class="uf-muted uf-small">{{ p }} / m²</span>
            }
          </div>
          <button
            type="button"
            class="uf-ghost uc__fav"
            [attr.aria-pressed]="fav()"
            (click)="favs.toggle(slug(), u.code)"
            [title]="fav() ? 'Remove from saved' : 'Save'"
          >
            <ng-icon name="lucideHeart" [class.is-on]="fav()" /> {{ fav() ? 'Saved' : 'Save' }}
          </button>
        </footer>
      </div>
    </article>
  `,
  styles: `
    .uc {
      display: grid;
      padding: 0;
      overflow: hidden;
    }
    .uc--unavailable .uc__cover img {
      filter: grayscale(0.6);
    }
    .uc__cover {
      position: relative;
      display: block;
      aspect-ratio: 4 / 3;
      background: var(--uf-surface-2);
    }
    .uc__cover img {
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }
    .uc__plan {
      display: block;
      width: 100%;
      height: 100%;
      background-repeat: no-repeat;
      background-color: #fff;
    }
    .uc__ph {
      display: grid;
      place-items: center;
      width: 100%;
      height: 100%;
      color: var(--uf-border-strong);
      font-size: 3rem;
    }
    .uc__status {
      position: absolute;
      left: 0.6rem;
      top: 0.6rem;
    }
    .uc__body {
      display: grid;
      gap: 0.5rem;
      padding: 0.85rem 1rem 1rem;
    }
    .uc__head {
      display: flex;
      align-items: baseline;
      gap: 0.5rem;
      justify-content: space-between;
    }
    .uc__code {
      font-weight: 700;
      font-size: 1.15rem;
      text-decoration: none;
      color: var(--uf-text);
    }
    .uc__type {
      font-size: 0.9rem;
    }
    .uc__facts {
      display: flex;
      flex-wrap: wrap;
      gap: 0.25rem 0.9rem;
      list-style: none;
      margin: 0;
      padding: 0;
      font-size: 0.9rem;
      color: var(--uf-muted);
    }
    .uc__facts li {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
    }
    .uc__facts ng-icon {
      font-size: 1rem;
    }
    .uc__foot {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.5rem;
    }
    .uc__price {
      display: grid;
      line-height: 1.25;
    }
    .uc__price strong {
      font-size: 1.05rem;
    }
    .uc__fav {
      padding: 0.3rem 0.8rem;
    }
    .uc__fav ng-icon.is-on {
      color: var(--uf-tone-bad-fg);
    }
  `,
})
export class UnitCardComponent {
  protected readonly favs = inject(Favourites);
  private readonly api = inject(PortalApi);
  readonly unit = input.required<UnitDoc>();
  readonly slug = input.required<string>();
  readonly mainAreaType = input<string | null>(null);
  protected readonly typeLabel = typeLabel;
  readonly link = computed(() => ['/projects', this.slug(), 'units', this.unit().code]);
  readonly fav = computed(() => this.favs.has(this.slug(), this.unit().code));
  readonly price = computed(() => money(this.unit().price));
  readonly perM2 = computed(() => {
    const p = this.unit().price;
    return p?.per_m2 ? money({ amount: p.per_m2, currency: p.currency }) : null;
  });
  readonly typeIcon = computed(() => statusOf('unit_type', this.unit().unit_type).icon);
  readonly cover = computed(() => {
    const u = this.unit();
    const img = u.media?.find((m) => m.mime.startsWith('image/'));
    const url = img?.url ?? u.plan?.url ?? null;
    return url ? this.api.asset(url) : null;
  });
  /** Zoom the plan onto the unit: background-size and position from the outline's bounding box (with a margin). */
  readonly crop = computed(() => {
    const u = this.unit();
    const ring = u.plan?.ring;
    if (!ring?.length || u.media?.some((m) => m.mime.startsWith('image/'))) return null;
    const xs = ring.map((p) => p[0]);
    const ys = ring.map((p) => p[1]);
    const pad = 0.6; // show the neighbours too, so the unit reads in context
    let w = Math.max(...xs) - Math.min(...xs);
    let h = Math.max(...ys) - Math.min(...ys);
    const cx = (Math.max(...xs) + Math.min(...xs)) / 2;
    const cy = (Math.max(...ys) + Math.min(...ys)) / 2;
    // the card cover is 4:3; widen the window to that ratio in sheet space, then pad
    const sheet = (u.plan?.width ?? 4) / (u.plan?.height ?? 3);
    const want = 4 / 3 / sheet; // window width/height in normalised units
    if (w / h < want) w = h * want;
    else h = w / want;
    w *= 1 + pad;
    h *= 1 + pad;
    w = Math.min(1, w);
    h = Math.min(1, h);
    const x0 = Math.min(Math.max(cx - w / 2, 0), 1 - w);
    const y0 = Math.min(Math.max(cy - h / 2, 0), 1 - h);
    const pos = (v: number, span: number) => (span >= 1 ? 50 : (v / (1 - span)) * 100);
    return {
      size: `${(100 / w).toFixed(2)}% ${(100 / h).toFixed(2)}%`,
      position: `${pos(x0, w).toFixed(2)}% ${pos(y0, h).toFixed(2)}%`,
    };
  });
  readonly mainArea = computed(() => {
    const areas = this.unit().areas ?? {};
    const key = this.mainAreaType() ?? Object.keys(areas)[0];
    return key && areas[key] ? area(areas[key]) : null;
  });
}
