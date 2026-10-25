import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { EmptyStateComponent, UF_ICONS } from 'ui';
import { Favourites } from '../core/favourites';
import { PortalApi, UnitDoc } from '../core/portal-api';
import { UnitCardComponent } from '../ui/unit-card';

/** Saved units of this project (stored in this browser). */
@Component({
  selector: 'uf-favourites-page',
  imports: [RouterLink, NgIcon, UnitCardComponent, EmptyStateComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <nav class="uf-crumbs">
      <a [routerLink]="['/projects', slug()]">Project</a> <ng-icon name="lucideChevronRight" />
      <span>Saved</span>
    </nav>
    <h1><ng-icon name="lucideHeart" class="h-icon" /> Saved units</h1>
    <p class="uf-muted">
      Saved in this browser only; they do not follow you to another device yet.
    </p>
    <div class="uf-grid">
      @for (u of units(); track u.unit_id) {
        <uf-unit-card [unit]="u" [slug]="slug()" />
      } @empty {
        <uf-empty-state
          icon="lucideHeart"
          title="Nothing saved yet"
          text="Use Save on any unit to keep it here for comparison."
        >
          <a class="uf-btn" [routerLink]="['/projects', slug(), 'units']">Browse units</a>
        </uf-empty-state>
      }
    </div>
    @if (missing().length) {
      <p class="uf-indicative">
        <ng-icon name="lucideInfo" /> No longer published: {{ missing().join(', ') }}
      </p>
    }
  `,
  styles: `
    .h-icon {
      color: var(--uf-tone-bad-fg);
      vertical-align: -0.1em;
    }
  `,
})
export class FavouritesPage {
  private readonly api = inject(PortalApi);
  private readonly favs = inject(Favourites);
  readonly slug = input.required<string>();
  readonly units = signal<UnitDoc[]>([]);
  readonly missing = signal<string[]>([]);

  constructor() {
    toObservable(this.slug).subscribe((s) => void this.load(s));
  }

  private async load(slug: string): Promise<void> {
    const codes = this.favs.list(slug);
    const res = await Promise.all(codes.map((c) => this.api.unit(slug, c).catch(() => null)));
    this.units.set(res.filter((u): u is UnitDoc => !!u));
    this.missing.set(codes.filter((_, i) => !res[i]));
  }
}
