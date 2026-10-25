import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { PlanPolygon, PlanViewerComponent } from 'plan-viewer';
import { AVAILABILITY, typeLabel } from '../core/format';
import { PortalApi, ProjectDoc } from '../core/portal-api';
import { SiteStore } from '../core/site.store';

/** Building view: floor stack with availability counts and the floor plan (plan §7.1). */
@Component({
  selector: 'uf-building-page',
  imports: [RouterLink, PlanViewerComponent],
  template: `
    @if (doc(); as d) {
      <nav class="uf-crumbs"><a [routerLink]="['/projects', slug()]">{{ d.project.name }}</a> › {{ building()?.name || 'Building ' + code() }}</nav>
      @if (building(); as b) {
        <div class="layout">
          <aside class="floors" aria-label="Floors">
            @for (f of floorsTopDown(); track f.level) {
              <button type="button" class="floor" [attr.aria-pressed]="f.level === level()" (click)="pick(f.level)">
                <span>{{ f.name }}</span>
                <span class="uf-muted">{{ count(f.level) }} / {{ f.units.length }}</span>
              </button>
            }
          </aside>
          <section class="plan">
            @if (floor(); as f) {
              <h2>{{ f.name }}</h2>
              @if (f.plan; as plan) {
                <uf-plan-viewer [src]="api.asset(plan.url)" [width]="plan.width" [height]="plan.height" [polygons]="polygons()" mode="view" (polygonSelected)="selected.set($event)" />
              } @else { <p class="uf-muted">No plan published for this floor.</p> }
              <p class="legend">@for (a of legend; track a.key) { <span [class]="'uf-badge uf-av-' + a.key">{{ a.label }}</span> }</p>
              @if (selectedUnit(); as u) {
                <div class="uf-card pick" role="status">
                  <strong>{{ u.code }}</strong> · {{ typeLabel(u.unit_type) }}
                  <span [class]="'uf-badge uf-av-' + u.availability">{{ label(u.availability) }}</span>
                  <a class="uf-btn" [routerLink]="['/projects', slug(), 'units', u.code]">Open</a>
                </div>
              }
              <ul class="list">
                @for (u of f.units; track u.id) {
                  <li><a [routerLink]="['/projects', slug(), 'units', u.code]">{{ u.code }}</a> <span [class]="'uf-badge uf-av-' + u.availability">{{ label(u.availability) }}</span></li>
                }
              </ul>
            }
          </section>
        </div>
      } @else { <p>Building not found.</p> }
    } @else { <p class="uf-muted">Loading…</p> }
  `,
  styles: `
    .layout { display: grid; grid-template-columns: 200px 1fr; gap: 1rem; }
    @media (max-width: 760px) { .layout { grid-template-columns: 1fr; } .floors { flex-direction: row; overflow-x: auto; } }
    .floors { display: flex; flex-direction: column; gap: 0.35rem; }
    .floor { display: flex; justify-content: space-between; gap: 0.5rem; background: var(--uf-surface); color: var(--uf-text); border: 1px solid var(--uf-border); border-radius: 8px; white-space: nowrap; }
    .floor[aria-pressed="true"] { border-color: var(--uf-primary); box-shadow: inset 4px 0 0 var(--uf-primary); }
    .plan { display: grid; gap: 0.5rem; min-width: 0; }
    .legend { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0; }
    .pick { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .list { list-style: none; padding: 0; display: flex; flex-wrap: wrap; gap: 0.5rem 1rem; }
  `,
})
export class BuildingPage {
  protected readonly api = inject(PortalApi);
  private readonly store = inject(SiteStore);
  private readonly router = inject(Router);
  readonly slug = input.required<string>();
  readonly code = input.required<string>();
  readonly floorParam = input<string | undefined>(undefined, { alias: 'floor' });
  readonly doc = signal<ProjectDoc | null>(null);
  readonly selected = signal<string | null>(null);
  protected readonly legend = Object.entries(AVAILABILITY).map(([key, v]) => ({ key, label: v.label }));
  protected readonly typeLabel = typeLabel;

  readonly building = computed(() => this.doc()?.buildings.find((b) => b.code.toLowerCase() === this.code().toLowerCase()) ?? null);
  readonly floorsTopDown = computed(() => [...(this.building()?.floors ?? [])].sort((a, b) => b.level - a.level));
  readonly level = computed(() => {
    const fs = this.building()?.floors ?? [];
    const want = Number(this.floorParam());
    return fs.some((f) => f.level === want) ? want : (fs[0]?.level ?? 0);
  });
  readonly floor = computed(() => this.building()?.floors.find((f) => f.level === this.level()) ?? null);
  readonly selectedUnit = computed(() => this.floor()?.units.find((u) => u.id === this.selected()) ?? null);
  readonly polygons = computed<PlanPolygon[]>(() =>
    (this.floor()?.units ?? [])
      .filter((u) => u.ring)
      .map((u) => ({ id: u.id, ring: u.ring!, label: u.code, fill: AVAILABILITY[u.availability].fill, stroke: AVAILABILITY[u.availability].stroke, selected: u.id === this.selected(), title: `${u.code}, ${AVAILABILITY[u.availability].label}` })),
  );

  constructor() {
    toObservable(this.slug).subscribe((s) => void this.store.project(s).then((d) => this.doc.set(d)));
  }

  count(level: number): number {
    return (this.building()?.floors.find((f) => f.level === level)?.units ?? []).filter((u) => u.availability === 'available').length;
  }

  label(a: keyof typeof AVAILABILITY): string {
    return AVAILABILITY[a].label;
  }

  pick(level: number): void {
    this.selected.set(null);
    void this.router.navigate([], { queryParams: { floor: level }, replaceUrl: true });
  }
}
