import { Component, computed, inject, input, linkedSignal, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { PlanPolygon, PlanViewerComponent } from 'plan-viewer';
import { StatusChipComponent, UF_ICONS, statusOf } from 'ui';
import type { MassingUnitInfo, SiteFeature3D } from 'viewer-3d';
import { MassingViewerComponent } from 'viewer-3d';
import { detectCapabilities } from '../core/capabilities';
import { AVAILABILITY, typeLabel } from '../core/format';
import { Availability, PortalApi, ProjectDoc } from '../core/portal-api';
import { SiteStore } from '../core/site.store';
import {
  countByAvailability,
  defaultFloor,
  floorChosen,
  groupUnitsByType,
  tapOnModel,
} from './building.model';

/**
 * Building view, floor first (plan §7.1, ADR-0006 Decision 6): the floor stack, the 3D building
 * (whole until a floor is chosen, then with that floor in focus: the other floors faded, or the
 * architect's model cut open above the floor, ADR-0036 #D3), and below it the floor plan where
 * the buyer taps the exact unit. `?floor=` and `?unit=` carry the choice, so a pick on the project
 * page's 3D model and a shared link both land here with the floor and unit already selected.
 */
@Component({
  selector: 'uf-building-page',
  imports: [RouterLink, NgIcon, PlanViewerComponent, MassingViewerComponent, StatusChipComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    @if (doc(); as d) {
      <nav class="uf-crumbs">
        <a [routerLink]="['/projects', slug()]">{{ d.project.name }}</a>
        <ng-icon name="lucideChevronRight" />
        <span>{{ building()?.name || 'Building ' + code() }}</span>
      </nav>
      @if (building(); as b) {
        @if (b.construction_status || b.completion) {
          <p class="bmeta">
            @if (b.construction_status) {
              <uf-status-chip domain="building.construction" [value]="b.construction_status" />
            }
            @if (b.completion) {
              <span class="uf-muted"
                ><ng-icon name="lucideCalendar" /> Completion {{ b.completion }}</span
              >
            }
          </p>
        }
        <div class="layout">
          <aside class="floors" aria-label="Floors">
            @for (f of floorsTopDown(); track f.level) {
              <button
                type="button"
                class="floor"
                [attr.aria-pressed]="f.level === level()"
                (click)="pick(f.level)"
              >
                <span>{{ f.name }}</span>
                <span
                  class="floor__count"
                  [class.is-none]="!count(f.level)"
                  [title]="count(f.level) + ' of ' + f.units.length + ' available'"
                  >{{ count(f.level) }} / {{ f.units.length }}</span
                >
              </button>
            }
          </aside>
          <section class="plan">
            <div class="plan__bar">
              <h2>{{ floor()?.name || 'Floors' }}</h2>
              @if (has3d() || b.elevation) {
                <div class="uf-segmented" role="group" aria-label="Building view">
                  <button
                    type="button"
                    [attr.aria-pressed]="view() === 'plan'"
                    (click)="view.set('plan')"
                  >
                    Plan only
                  </button>
                  @if (b.elevation) {
                    <button
                      type="button"
                      [attr.aria-pressed]="view() === 'elevation'"
                      (click)="view.set('elevation')"
                    >
                      Facade + plan
                    </button>
                  }
                  @if (has3d()) {
                    <button
                      type="button"
                      [attr.aria-pressed]="view() === '3d'"
                      (click)="view.set('3d')"
                    >
                      3D + plan
                    </button>
                  }
                </div>
              }
              @if (view() === '3d' && chosen()) {
                <button
                  type="button"
                  class="uf-chip-btn"
                  (click)="wholeBuilding()"
                  title="Show the whole building again, not cut open at this floor"
                >
                  <ng-icon name="lucideBuilding2" /> Whole building
                </button>
              }
              @if (view() === '3d') {
                <button
                  type="button"
                  class="uf-chip-btn"
                  [attr.aria-pressed]="tint() === 'availability'"
                  (click)="tint.set(tint() === 'availability' ? 'neutral' : 'availability')"
                  title="Colour the 3D model by availability, or show the neutral finish"
                >
                  Availability colours
                </button>
              }
            </div>
            @if (view() === 'elevation' && b.elevation; as el) {
              <uf-plan-viewer
                class="facade"
                [src]="api.asset(el.plan.url)"
                [width]="el.plan.width"
                [height]="el.plan.height"
                [polygons]="bandPolygons()"
                mode="view"
                (polygonSelected)="pickBand($event)"
              />
            }
            @if (view() === '3d' && (b.model || d.massing)) {
              @defer (when view() === '3d') {
                <uf-massing-viewer
                  class="model"
                  [src]="api.asset(b.model?.url ?? d.massing?.url)"
                  [srcMatrix]="b.model?.site_matrix ?? null"
                  [badge]="
                    b.model?.disclaimer ??
                    'Schematic model generated from floor plans — not an architectural model'
                  "
                  [buildingCode]="b.model ? null : b.code"
                  [floorLevel]="chosen() ? level() : null"
                  [selectedUnitId]="selected()"
                  [unitColors]="unitColors()"
                  [tintMode]="tint()"
                  [siteFeatures]="siteFeatures3d()"
                  (unitPicked)="pick3d($event)"
                />
              } @loading (minimum 200ms) {
                <p class="uf-muted">Loading 3D…</p>
              }
            }
            <p class="uf-muted small guide">
              Pick a floor on the left
              @if (view() === '3d') {
                or tap a floor on the building
              } @else if (view() === 'elevation') {
                or tap a floor band on the facade drawing
              }
              , then tap a unit on the plan to see its status and open it.
            </p>
            @if (floor(); as f) {
              @if (f.plan; as plan) {
                <uf-plan-viewer
                  [src]="api.asset(plan.url)"
                  [width]="plan.width"
                  [height]="plan.height"
                  [polygons]="polygons()"
                  [callout]="selected()"
                  mode="view"
                  (polygonSelected)="selected.set($event)"
                >
                  @if (selectedUnit(); as u) {
                    <a
                      callout
                      class="callout"
                      [routerLink]="['/projects', slug(), 'units', u.code]"
                      title="Open the unit page"
                    >
                      <strong>{{ u.code }}</strong>
                      <uf-status-chip domain="availability" [value]="u.availability" />
                      <ng-icon name="lucideArrowRight" aria-hidden="true" />
                    </a>
                  }
                </uf-plan-viewer>
              } @else {
                <p class="uf-muted">No plan published for this floor.</p>
              }
              @if (f.units.length) {
                <div class="status-bar">
                  <ul class="legend" aria-label="Availability on this floor">
                    @for (a of legend; track a.key) {
                      <li [class.is-zero]="!counts()[a.key]">
                        <uf-status-chip
                          domain="availability"
                          [value]="a.key"
                          [label]="a.label + ' · ' + counts()[a.key]"
                          [tooltip]="
                            counts()[a.key] + ' of ' + f.units.length + ' ' + a.label.toLowerCase()
                          "
                        />
                      </li>
                    }
                  </ul>
                  @if (!selectedUnit()) {
                    <span class="uf-muted uf-small"
                      >Tap a unit on the plan or below to open it.</span
                    >
                  }
                </div>
              }
              @if (selectedUnit(); as u) {
                <div class="pick" role="status">
                  <strong class="pick__code">{{ u.code }}</strong>
                  <span class="uf-muted pick__meta">
                    {{ typeLabel(u.unit_type) }} · {{ f.name }}
                    @if (u.entrance) {
                      · Entrance {{ u.entrance }}
                    }
                  </span>
                  <uf-status-chip domain="availability" [value]="u.availability" />
                  <a class="uf-btn pick__open" [routerLink]="['/projects', slug(), 'units', u.code]"
                    >Open <ng-icon name="lucideArrowRight"
                  /></a>
                </div>
              } @else if (!f.units.length) {
                <p class="uf-muted uf-small">No units are published on this floor.</p>
              }
              @for (g of groups(); track g.type) {
                <section class="group">
                  <h3 class="group__title">
                    {{ g.label }}
                    <span class="uf-muted"
                      >· {{ g.available }} of {{ g.units.length }} available</span
                    >
                  </h3>
                  <ul class="tiles">
                    @for (u of g.units; track u.id) {
                      <li>
                        <a
                          class="tile uf-tone-{{ tone(u.availability) }}"
                          [class.is-selected]="u.id === selected()"
                          [routerLink]="['/projects', slug(), 'units', u.code]"
                          [attr.aria-current]="u.id === selected() ? 'true' : null"
                          [attr.aria-label]="u.code + ', ' + label(u.availability)"
                          [title]="u.code + ' · ' + label(u.availability)"
                          ><ng-icon [name]="icon(u.availability)" aria-hidden="true" />{{
                            u.code
                          }}</a
                        >
                      </li>
                    }
                  </ul>
                </section>
              }
            }
          </section>
        </div>
        @if (b.terms) {
          <details class="uf-card terms">
            <summary><h2>Terms</h2></summary>
            <p class="pre">{{ b.terms }}</p>
          </details>
        }
      } @else {
        <p>Building not found.</p>
      }
    } @else {
      <p class="uf-muted">Loading…</p>
    }
  `,
  styles: `
    .layout {
      display: grid;
      grid-template-columns: 200px 1fr;
      gap: 1rem;
    }
    @media (max-width: 760px) {
      .layout {
        grid-template-columns: 1fr;
      }
      .floors {
        flex-direction: row;
        overflow-x: auto;
      }
    }
    .floors {
      display: flex;
      flex-direction: column;
      gap: 0.35rem;
    }
    .floor {
      display: flex;
      justify-content: space-between;
      gap: 0.5rem;
      background: var(--uf-surface);
      color: var(--uf-text);
      border: 1px solid var(--uf-border);
      border-radius: 8px;
      white-space: nowrap;
    }
    .floor[aria-pressed='true'] {
      border-color: var(--uf-primary);
      box-shadow: inset 4px 0 0 var(--uf-primary);
      font-weight: 700;
    }
    .floor__count {
      font-size: 0.8rem;
      font-weight: 600;
      padding: 0 0.5rem;
      border-radius: var(--uf-radius-pill);
      background: var(--uf-tone-good-bg);
      color: var(--uf-tone-good-fg);
    }
    .floor__count.is-none {
      background: var(--uf-tone-neutral-bg);
      color: var(--uf-tone-neutral-fg);
    }
    .plan {
      display: grid;
      gap: 0.5rem;
      min-width: 0;
    }
    .plan__bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .plan__bar h2 {
      margin: 0;
    }
    .model {
      --uf-3d-height: 42vh;
      --uf-3d-min-height: 300px;
      border-radius: 8px;
      overflow: hidden;
    }
    .small {
      font-size: 0.85rem;
      margin: 0;
    }
    /* one slim row: the legend with counts on the left, the hint on the right */
    .status-bar {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 0.5rem 1rem;
      flex-wrap: wrap;
      margin: 0.15rem 0 0;
    }
    .legend {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      gap: 0.35rem;
      flex-wrap: wrap;
    }
    .legend .is-zero {
      opacity: 0.55;
    }
    /* one compact tap target on the plan: code, status, arrow; the whole pill opens the unit */
    .callout {
      display: inline-flex;
      align-items: center;
      gap: 0.45rem;
      padding: 0.25rem 0.5rem 0.25rem 0.7rem;
      font-size: 0.9rem;
      line-height: 1.4;
      color: var(--uf-text);
      text-decoration: none;
      background: var(--uf-surface);
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius-pill);
      box-shadow: 0 2px 8px rgba(15, 23, 42, 0.14);
      white-space: nowrap;
    }
    .callout:hover,
    .callout:focus-visible {
      border-color: var(--uf-primary);
      background: var(--uf-primary-soft);
    }
    .callout ng-icon {
      font-size: 1.05em;
      color: var(--uf-primary);
    }
    /* the selected unit: a slim strip with a primary accent, not a full card */
    .pick {
      display: flex;
      gap: 0.6rem;
      align-items: center;
      flex-wrap: wrap;
      padding: 0.4rem 0.6rem 0.4rem 0.75rem;
      border: 1px solid var(--uf-border);
      border-left: 4px solid var(--uf-primary);
      border-radius: var(--uf-radius-sm);
      background: var(--uf-surface);
      box-shadow: var(--uf-shadow);
    }
    .pick__code {
      font-size: 1.05rem;
    }
    .pick__meta {
      font-size: 0.9rem;
    }
    .pick__open {
      margin-left: auto;
      padding: 0.3rem 0.8rem;
      font-size: 0.9rem;
    }
    /* unit tiles, grouped by type: the chip vocabulary (icon + tone) carries the status */
    .group {
      display: grid;
      gap: 0.35rem;
      margin-top: 0.35rem;
    }
    .group__title {
      margin: 0;
      font-size: 0.8rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--uf-text);
    }
    .group__title .uf-muted {
      font-weight: 500;
      text-transform: none;
      letter-spacing: 0;
    }
    .tiles {
      list-style: none;
      margin: 0;
      padding: 0;
      display: flex;
      flex-wrap: wrap;
      gap: 0.3rem;
    }
    .tile {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      padding: 0.18rem 0.6rem 0.18rem 0.5rem;
      font-size: 0.85rem;
      font-weight: 600;
      line-height: 1.5;
      text-decoration: none;
      border: 1px solid var(--uf-tone-neutral-border);
      border-radius: var(--uf-radius-pill);
      background: var(--uf-tone-neutral-bg);
      color: var(--uf-tone-neutral-fg);
      transition:
        box-shadow 0.15s,
        border-color 0.15s;
    }
    /* the component's scoped rule outranks the global tone classes, so the tones are restated here */
    .tile.uf-tone-good {
      border-color: var(--uf-tone-good-border);
      background: var(--uf-tone-good-bg);
      color: var(--uf-tone-good-fg);
    }
    .tile.uf-tone-warning {
      border-color: var(--uf-tone-warning-border);
      background: var(--uf-tone-warning-bg);
      color: var(--uf-tone-warning-fg);
    }
    .tile.uf-tone-bad {
      border-color: var(--uf-tone-bad-border);
      background: var(--uf-tone-bad-bg);
      color: var(--uf-tone-bad-fg);
    }
    .tile ng-icon {
      font-size: 0.9em;
      flex: none;
    }
    .tile:hover,
    .tile:focus-visible {
      border-color: currentColor;
      box-shadow: var(--uf-shadow);
    }
    .tile.is-selected {
      outline: 2px solid var(--uf-primary);
      outline-offset: 1px;
    }
    .bmeta {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      flex-wrap: wrap;
      margin: 0 0 0.75rem;
    }
    .facade {
      border-radius: 8px;
      overflow: hidden;
    }
    .terms {
      margin-top: 1rem;
    }
    .terms summary {
      cursor: pointer;
    }
    .terms h2 {
      display: inline;
      margin: 0;
      font-size: 1.1rem;
    }
    .pre {
      white-space: pre-wrap;
    }
  `,
})
export class BuildingPage {
  protected readonly api = inject(PortalApi);
  private readonly store = inject(SiteStore);
  private readonly router = inject(Router);
  readonly slug = input.required<string>();
  readonly code = input.required<string>();
  // the router binds ?floor= and ?unit= to inputs of these names (withComponentInputBinding)
  // eslint-disable-next-line @angular-eslint/no-input-rename
  readonly floorParam = input<string | undefined>(undefined, { alias: 'floor' });
  // eslint-disable-next-line @angular-eslint/no-input-rename
  readonly unitParam = input<string | undefined>(undefined, { alias: 'unit' });
  readonly doc = signal<ProjectDoc | null>(null);
  private readonly caps = detectCapabilities();
  protected readonly legend = (Object.keys(AVAILABILITY) as Availability[]).map((key) => ({
    key,
    label: AVAILABILITY[key].label,
  }));
  protected readonly typeLabel = typeLabel;

  readonly building = computed(
    () =>
      this.doc()?.buildings.find((b) => b.code.toLowerCase() === this.code().toLowerCase()) ?? null,
  );
  /** The architect's IFC model when the building has one (ADR-0006 Decision 5), else the project massing. */
  readonly siteFeatures3d = computed<SiteFeature3D[]>(() =>
    (this.doc()?.site?.features ?? [])
      .filter((f) => f.ring_m && f.ring_m.length >= 3)
      .map((f) => ({ kind: f.kind, name: f.name, ring_m: f.ring_m as [number, number][] })),
  );
  readonly has3d = computed(
    () => !!(this.doc()?.massing || this.building()?.model) && this.caps.webgl2,
  );
  /**
   * Which companion the floor plan gets (ADR-0014 Decision 1): desktops with WebGL2 start in 3D
   * (ADR-0006 Decision 6), phones and data-saver start on the facade drawing when the building
   * has one, else plan only. The buyer can switch.
   */
  readonly view = linkedSignal<'plan' | 'elevation' | '3d'>(() => {
    if (this.has3d() && this.caps.prefer3d) return '3d';
    return this.building()?.elevation ? 'elevation' : 'plan';
  });
  readonly floorsTopDown = computed(() =>
    [...(this.building()?.floors ?? [])].sort((a, b) => b.level - a.level),
  );
  /** The floor from `?floor=`, else the floor of `?unit=`, else the lowest floor with flats (#D5). */
  readonly level = computed(() => {
    const fs = this.building()?.floors ?? [];
    const want = Number(this.floorParam());
    if (fs.some((f) => f.level === want)) return want;
    const unit = this.unitParam()?.toLowerCase();
    const byUnit = unit
      ? fs.find((f) => f.units.some((u) => u.code.toLowerCase() === unit))
      : undefined;
    return byUnit?.level ?? defaultFloor(fs) ?? 0;
  });
  readonly floor = computed(
    () => this.building()?.floors.find((f) => f.level === this.level()) ?? null,
  );
  /** Whether the buyer chose a floor; until then the 3D building is shown whole (ADR-0036 #D3). */
  readonly chosen = computed(() => floorChosen(this.floorParam(), this.unitParam()));
  /** Preselected from `?unit=` on the current floor; a tap on the plan or the model overrides it. */
  readonly selected = linkedSignal<string | null>(() => {
    const unit = this.unitParam()?.toLowerCase();
    return (unit && this.floor()?.units.find((u) => u.code.toLowerCase() === unit)?.id) || null;
  });
  /** Availability colours by default here: the colour is how a buyer picks the unit. */
  readonly tint = signal<'availability' | 'neutral'>('availability');
  readonly selectedUnit = computed(
    () => this.floor()?.units.find((u) => u.id === this.selected()) ?? null,
  );
  /** The list below the plan: one group per unit type, codes in natural order (building.model.ts). */
  readonly groups = computed(() => groupUnitsByType(this.floor()?.units ?? []));
  /** Legend counts for the current floor, every state present. */
  readonly counts = computed(() => countByAvailability(this.floor()?.units ?? []));
  readonly polygons = computed<PlanPolygon[]>(() =>
    (this.floor()?.units ?? [])
      .filter((u) => u.ring)
      .map((u) => ({
        id: u.id,
        ring: u.ring!,
        label: u.code,
        fill: AVAILABILITY[u.availability].fill,
        stroke: AVAILABILITY[u.availability].stroke,
        selected: u.id === this.selected(),
        title: `${u.code}, ${AVAILABILITY[u.availability].label}`,
      })),
  );
  readonly unitColors = computed(() => {
    const out: Record<string, string> = {};
    for (const b of this.doc()?.buildings ?? [])
      for (const f of b.floors)
        for (const u of f.units) out[u.id] = AVAILABILITY[u.availability].solid;
    return out;
  });
  /** One clickable band per floor on the facade; floors without published units are inert regions. */
  readonly bandPolygons = computed<PlanPolygon[]>(() => {
    const b = this.building();
    return (b?.elevation?.bands ?? []).map((band) => {
      const floor = b!.floors.find((f) => f.level === band.level);
      const name = floor?.name ?? `Level ${band.level}`;
      if (!band.published || !floor)
        return {
          id: `L${band.level}`,
          ring: band.ring,
          label: name,
          kind: 'region' as const,
          title: `${name}, nothing published`,
        };
      const avail = floor.units.filter((u) => u.availability === 'available').length;
      const tone = avail ? AVAILABILITY.available : AVAILABILITY.withdrawn;
      return {
        id: `L${band.level}`,
        ring: band.ring,
        label: `${name} · ${avail} of ${floor.units.length}`,
        fill: tone.fill,
        stroke: tone.stroke,
        selected: band.level === this.level(),
        title: `${name}, ${avail} of ${floor.units.length} available`,
      };
    });
  });

  constructor() {
    toObservable(this.slug).subscribe(
      (s) => void this.store.project(s).then((d) => this.doc.set(d)),
    );
  }

  count(level: number): number {
    return (this.building()?.floors.find((f) => f.level === level)?.units ?? []).filter(
      (u) => u.availability === 'available',
    ).length;
  }

  label(a: keyof typeof AVAILABILITY): string {
    return AVAILABILITY[a].label;
  }

  /** Tile tone and icon come from the shared status vocabulary, the same as the chips. */
  tone(a: keyof typeof AVAILABILITY): string {
    return statusOf('availability', a).tone;
  }

  icon(a: keyof typeof AVAILABILITY): string {
    return statusOf('availability', a).icon;
  }

  /** Facade band: the polygon id carries the level. */
  pickBand(id: string): void {
    const level = Number(id.slice(1));
    if (Number.isFinite(level)) this.pick(level);
  }

  /** Floor stack: change floor, drop the unit selection. */
  pick(level: number): void {
    void this.router.navigate([], {
      queryParams: { floor: level, unit: null },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  /** Back to the whole building: the floor and unit leave the link, the plan shows the first floor. */
  wholeBuilding(): void {
    void this.router.navigate([], {
      queryParams: { floor: null, unit: null },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  /** 3D model: a unit on the floor cut open is selected in place; any other moves there with it preselected. */
  pick3d(u: MassingUnitInfo): void {
    if (tapOnModel(this.chosen(), this.level(), u.floor_level) === 'select') {
      this.selected.set(u.unit_id);
      return;
    }
    void this.router.navigate([], {
      queryParams: { floor: u.floor_level, unit: u.code },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }
}
