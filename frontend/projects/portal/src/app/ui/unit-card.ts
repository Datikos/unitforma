import { Component, computed, inject, input } from '@angular/core';
import { RouterLink } from '@angular/router';
import { Favourites } from '../core/favourites';
import { AVAILABILITY, area, money, typeLabel } from '../core/format';
import { UnitDoc } from '../core/portal-api';

@Component({
  selector: 'uf-unit-card',
  imports: [RouterLink],
  template: `
    @let u = unit();
    <article class="uf-card uc">
      <header class="uc__head">
        <a [routerLink]="['/projects', slug(), 'units', u.code]" class="uc__code">{{ u.code }}</a>
        <span class="uf-badge" [class]="'uf-badge uf-av-' + u.availability">{{ av().label }}</span>
      </header>
      <p class="uf-muted uc__meta">
        {{ type() }} · {{ u.floor_name }} (building {{ u.building_code }})
        @if (u.rooms?.rooms) { · {{ u.rooms?.rooms }} rooms }
        @if (mainArea(); as a) { · {{ a }} }
      </p>
      <p class="uc__price">{{ price() ?? 'Price on request' }}</p>
      <footer class="uc__foot">
        <a [routerLink]="['/projects', slug(), 'units', u.code]">Details</a>
        <button type="button" class="uf-ghost uc__fav" [attr.aria-pressed]="fav()" (click)="favs.toggle(slug(), u.code)">
          {{ fav() ? '♥ Saved' : '♡ Save' }}
        </button>
      </footer>
    </article>
  `,
  styles: `
    .uc { display: grid; gap: 0.25rem; }
    .uc__head { display: flex; justify-content: space-between; align-items: center; gap: 0.5rem; }
    .uc__code { font-weight: 700; font-size: 1.1rem; text-decoration: none; color: var(--uf-text); }
    .uc__meta { margin: 0; font-size: 0.9rem; }
    .uc__price { margin: 0.25rem 0; font-weight: 600; font-size: 1.05rem; }
    .uc__foot { display: flex; justify-content: space-between; align-items: center; }
    .uc__fav { padding: 0.25rem 0.8rem; }
  `,
})
export class UnitCardComponent {
  protected readonly favs = inject(Favourites);
  readonly unit = input.required<UnitDoc>();
  readonly slug = input.required<string>();
  readonly mainAreaType = input<string | null>(null);
  protected readonly av = computed(() => AVAILABILITY[this.unit().availability]);
  protected readonly type = computed(() => typeLabel(this.unit().unit_type));
  protected readonly price = computed(() => money(this.unit().price));
  protected readonly fav = computed(() => this.favs.has(this.slug(), this.unit().code));
  protected readonly mainArea = computed(() => {
    const a = this.unit().areas ?? {};
    const k = this.mainAreaType();
    return area((k && a[k]) || Object.values(a)[0]);
  });
}
