import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { combineLatest } from 'rxjs';
import { EmptyStateComponent, StatusChipComponent, UF_ICONS } from 'ui';
import { area, typeLabel } from '../core/format';
import { PortalApi, ProjectDoc, UnitDoc, problemOf } from '../core/portal-api';
import { SiteStore } from '../core/site.store';
import { UnitPlaygroundComponent } from './unit-playground.component';

/**
 * The renovation playground in its own window (ADR-0020 Phase A, owner's correction of 2026-10-26):
 * the apartment's plan beside the tools, opened from the unit page. Share links open this page.
 */
@Component({
  selector: 'uf-playground-page',
  imports: [RouterLink, NgIcon, StatusChipComponent, EmptyStateComponent, UnitPlaygroundComponent],
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
      <header class="pp__head">
        <a class="uf-ghost pp__back" [routerLink]="['/projects', slug(), 'units', u.code]">
          <ng-icon name="lucideArrowLeft" /> {{ u.code }}
        </a>
        <h1 class="pp__title">
          <ng-icon name="lucideArmchair" /> Design {{ typeLabel(u.unit_type) }} {{ u.code }}
        </h1>
        <span class="uf-muted pp__facts">
          {{ u.floor_name }}, building {{ u.building_code }}
          @if (largestArea(); as a) {
            · {{ a }}
          }
        </span>
        <uf-status-chip domain="availability" [value]="u.availability" />
      </header>
      @if (u.plan) {
        <uf-unit-playground [unit]="u" [slug]="slug()" />
      } @else {
        <uf-empty-state
          icon="lucideImage"
          title="No plan yet"
          text="The developer has not published a floor plan for this unit, so there is nothing to furnish."
        />
      }
    } @else {
      <p class="uf-muted">Loading…</p>
    }
  `,
  styles: `
    .pp__head {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.5rem 0.9rem;
      margin-bottom: 0.6rem;
    }
    .pp__title {
      margin: 0;
      font-size: 1.25rem;
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
    }
    .pp__back ng-icon {
      vertical-align: -0.15em;
    }
    .pp__facts {
      font-size: 0.9rem;
    }
  `,
})
export class PlaygroundPage {
  private readonly api = inject(PortalApi);
  private readonly store = inject(SiteStore);
  readonly slug = input.required<string>();
  readonly code = input.required<string>();
  readonly unit = signal<UnitDoc | null>(null);
  readonly doc = signal<ProjectDoc | null>(null);
  readonly notFound = signal(false);
  protected readonly typeLabel = typeLabel;
  /** The largest stated area, the one the plan's scale comes from. */
  readonly largestArea = computed(() => {
    const values = Object.values(this.unit()?.areas ?? {})
      .map(Number)
      .filter((x) => Number.isFinite(x) && x > 0);
    return values.length ? area(String(Math.max(...values))) : null;
  });

  constructor() {
    combineLatest([toObservable(this.slug), toObservable(this.code)]).subscribe(
      ([s, c]) => void this.load(s, c),
    );
  }

  private async load(slug: string, code: string): Promise<void> {
    this.unit.set(null);
    this.notFound.set(false);
    try {
      const [d, u] = await Promise.all([this.store.project(slug), this.api.unit(slug, code)]);
      this.doc.set(d);
      this.unit.set(u);
      document.title = `Design ${u.code} — ${d.project.name}`;
    } catch (e) {
      if (problemOf(e).status === 404) this.notFound.set(true);
    }
  }
}
