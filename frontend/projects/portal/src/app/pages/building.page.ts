import { Component, computed, inject, input, linkedSignal, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { PlanPolygon, PlanViewerComponent } from 'plan-viewer';
import { StatusChipComponent, UF_ICONS } from 'ui';
import type { MassingUnitInfo } from 'viewer-3d';
import { MassingViewerComponent } from 'viewer-3d';
import { detectCapabilities } from '../core/capabilities';
import { AVAILABILITY, typeLabel } from '../core/format';
import { PortalApi, ProjectDoc } from '../core/portal-api';
import { SiteStore } from '../core/site.store';

/**
 * Building view, floor first (plan §7.1, ADR-0006 Decision 6): the floor stack, the 3D building
 * with the chosen floor in focus and the other floors faded, and below it the floor plan where
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
              @if (has3d()) {
                <div class="uf-segmented" role="group" aria-label="Building view">
                  <button type="button" [attr.aria-pressed]="!show3d()" (click)="show3d.set(false)">
                    Plan only
                  </button>
                  <button type="button" [attr.aria-pressed]="show3d()" (click)="show3d.set(true)">
                    3D + plan
                  </button>
                </div>
              }
            </div>
            @if (show3d() && (b.model || d.massing)) {
              @defer (when show3d()) {
                <uf-massing-viewer
                  class="model"
                  [src]="api.asset(b.model?.url ?? d.massing?.url)"
                  [badge]="b.model?.disclaimer ?? 'Schematic model generated from floor plans — not an architectural model'"
                  [buildingCode]="b.model ? null : b.code"
                  [floorLevel]="level()"
                  [selectedUnitId]="selected()"
                  [unitColors]="unitColors()"
                  (unitPicked)="pick3d($event)"
                />
              } @loading (minimum 200ms) {
                <p class="uf-muted">Loading 3D…</p>
              }
            }
            <p class="uf-muted small guide">
              Pick a floor on the left
              @if (show3d()) {
                or tap a floor on the building
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
                  mode="view"
                  (polygonSelected)="selected.set($event)"
                />
              } @else {
                <p class="uf-muted">No plan published for this floor.</p>
              }
              <p class="legend">
                @for (a of legend; track a.key) {
                  <uf-status-chip domain="availability" [value]="a.key" />
                }
              </p>
              @if (selectedUnit(); as u) {
                <div class="uf-card pick" role="status">
                  <strong>{{ u.code }}</strong> · {{ typeLabel(u.unit_type) }} · {{ f.name }}
                  <uf-status-chip domain="availability" [value]="u.availability" />
                  <a class="uf-btn" [routerLink]="['/projects', slug(), 'units', u.code]"
                    >Open <ng-icon name="lucideArrowRight"
                  /></a>
                </div>
              } @else if (f.units.length) {
                <p class="uf-muted small">
                  {{ count(f.level) }} of {{ f.units.length }} units on this floor available. Tap
                  one on the plan or in the list.
                </p>
              } @else {
                <p class="uf-muted small">No units are published on this floor.</p>
              }
              <ul class="list">
                @for (u of f.units; track u.id) {
                  <li>
                    <a [routerLink]="['/projects', slug(), 'units', u.code]" class="unit-link"
                      ><strong>{{ u.code }}</strong>
                      <uf-status-chip domain="availability" [value]="u.availability"
                    /></a>
                  </li>
                }
              </ul>
            }
          </section>
        </div>
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
    .unit-link {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      text-decoration: none;
      color: var(--uf-text);
      padding: 0.25rem 0.5rem;
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius-sm);
      background: var(--uf-surface);
    }
    .unit-link:hover {
      border-color: var(--uf-primary);
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
    .legend {
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
      margin: 0;
    }
    .pick {
      display: flex;
      gap: 0.75rem;
      align-items: center;
      flex-wrap: wrap;
    }
    .list {
      list-style: none;
      padding: 0;
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
    }
  `,
})
export class BuildingPage {
  protected readonly api = inject(PortalApi);
  private readonly store = inject(SiteStore);
  private readonly router = inject(Router);
  readonly slug = input.required<string>();
  readonly code = input.required<string>();
  readonly floorParam = input<string | undefined>(undefined, { alias: 'floor' });
  readonly unitParam = input<string | undefined>(undefined, { alias: 'unit' });
  readonly doc = signal<ProjectDoc | null>(null);
  private readonly caps = detectCapabilities();
  readonly show3d = signal(this.caps.prefer3d);
  protected readonly legend = Object.entries(AVAILABILITY).map(([key, v]) => ({
    key,
    label: v.label,
  }));
  protected readonly typeLabel = typeLabel;

  readonly building = computed(
    () =>
      this.doc()?.buildings.find((b) => b.code.toLowerCase() === this.code().toLowerCase()) ?? null,
  );
  /** The architect's IFC model when the building has one (ADR-0006 Decision 5), else the project massing. */
  readonly has3d = computed(() => !!(this.doc()?.massing || this.building()?.model) && this.caps.webgl2);
  readonly floorsTopDown = computed(() =>
    [...(this.building()?.floors ?? [])].sort((a, b) => b.level - a.level),
  );
  /** The floor from `?floor=`, else the floor of `?unit=`, else the first published floor. */
  readonly level = computed(() => {
    const fs = this.building()?.floors ?? [];
    const want = Number(this.floorParam());
    if (fs.some((f) => f.level === want)) return want;
    const unit = this.unitParam()?.toLowerCase();
    const byUnit = unit
      ? fs.find((f) => f.units.some((u) => u.code.toLowerCase() === unit))
      : undefined;
    return byUnit?.level ?? fs[0]?.level ?? 0;
  });
  readonly floor = computed(
    () => this.building()?.floors.find((f) => f.level === this.level()) ?? null,
  );
  /** Preselected from `?unit=` on the current floor; a tap on the plan or the model overrides it. */
  readonly selected = linkedSignal<string | null>(() => {
    const unit = this.unitParam()?.toLowerCase();
    return (unit && this.floor()?.units.find((u) => u.code.toLowerCase() === unit)?.id) || null;
  });
  readonly selectedUnit = computed(
    () => this.floor()?.units.find((u) => u.id === this.selected()) ?? null,
  );
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

  /** Floor stack: change floor, drop the unit selection. */
  pick(level: number): void {
    void this.router.navigate([], {
      queryParams: { floor: level, unit: null },
      queryParamsHandling: 'merge',
      replaceUrl: true,
    });
  }

  /** 3D model: a unit on the current floor is selected in place; one on another floor moves there with it preselected. */
  pick3d(u: MassingUnitInfo): void {
    if (u.floor_level === this.level()) {
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
