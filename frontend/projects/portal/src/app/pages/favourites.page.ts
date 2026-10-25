import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { Favourites } from '../core/favourites';
import { PortalApi, UnitDoc } from '../core/portal-api';
import { UnitCardComponent } from '../ui/unit-card';

/** Saved units of this project (stored in this browser). */
@Component({
  selector: 'uf-favourites-page',
  imports: [RouterLink, UnitCardComponent],
  template: `
    <nav class="uf-crumbs"><a [routerLink]="['/projects', slug()]">Project</a> › Saved</nav>
    <h1>Saved units</h1>
    <p class="uf-muted">Saved in this browser.</p>
    <div class="uf-grid">
      @for (u of units(); track u.unit_id) { <uf-unit-card [unit]="u" [slug]="slug()" /> }
      @empty { <p>Nothing saved yet. Use ♡ Save on any unit.</p> }
    </div>
    @if (missing().length) { <p class="uf-muted">No longer published: {{ missing().join(', ') }}</p> }
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
