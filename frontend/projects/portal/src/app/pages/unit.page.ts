import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { RouterLink } from '@angular/router';
import { combineLatest } from 'rxjs';
import { PlanPolygon, PlanViewerComponent } from 'plan-viewer';
import { Favourites } from '../core/favourites';
import { AVAILABILITY, area, money, typeLabel } from '../core/format';
import { PortalApi, ProjectDoc, UnitDoc, problemOf } from '../core/portal-api';
import { SiteStore } from '../core/site.store';

/** Unit page: plan, labelled media, areas with definitions, price and terms (plan §7.1, §7.4). */
@Component({
  selector: 'uf-unit-page',
  imports: [RouterLink, PlanViewerComponent],
  template: `
    @if (notFound()) {
      <section class="uf-empty"><h1>Unit not available</h1><p>This unit is not published.</p><a class="uf-btn" [routerLink]="['/projects', slug(), 'units']">All units</a></section>
    } @else if (unit(); as u) {
      <nav class="uf-crumbs">
        <a [routerLink]="['/projects', slug()]">{{ doc()?.project?.name }}</a> ›
        <a [routerLink]="['/projects', slug(), 'buildings', u.building_code]" [queryParams]="{ floor: u.floor_level }">{{ u.floor_name }}</a> › {{ u.code }}
      </nav>
      <header class="head">
        <div>
          <h1>{{ typeLabel(u.unit_type) }} {{ u.code }}</h1>
          <span [class]="'uf-badge uf-av-' + u.availability">{{ av().label }}</span>
        </div>
        <button type="button" class="uf-ghost" [attr.aria-pressed]="fav()" (click)="favs.toggle(slug(), u.code)">{{ fav() ? '♥ Saved' : '♡ Save' }}</button>
      </header>
      @if (u.indicative) { <p class="uf-indicative">Plan and areas are indicative: they have not been verified against the final drawings yet.</p> }

      <div class="layout">
        <section class="main">
          @if (u.plan; as plan) {
            <uf-plan-viewer [src]="api.asset(plan.url)" [width]="plan.width" [height]="plan.height" [polygons]="planPolygons()" mode="view" />
          }
          @if (u.media?.length) {
            <div class="gallery">
              @for (m of u.media; track m.url) {
                <figure>
                  <div class="media">
                    @if (m.mime.startsWith('image/')) {
                      <img [src]="api.asset(m.url)" [alt]="m.alt_text || typeLabel(u.unit_type) + ' ' + u.code" loading="lazy" />
                    } @else if (m.mime === 'video/mp4') {
                      <video [src]="api.asset(m.url)" controls preload="none"></video>
                    } @else { <a [href]="api.asset(m.url)" target="_blank" rel="noopener">Open document</a> }
                    @if (m.is_ai_generated) { <span class="uf-ai-label">Illustrative — AI generated</span> }
                  </div>
                  @if (m.is_ai_generated && m.ai_disclosure_text) { <figcaption class="uf-muted small">{{ m.ai_disclosure_text }}</figcaption> }
                </figure>
              }
            </div>
          }
          @if (u.description) { <section class="uf-card"><h2>Description</h2><p class="pre">{{ u.description }}</p></section> }
        </section>

        <aside class="side">
          <section class="uf-card">
            <p class="price">{{ price() ?? 'Price on request' }}</p>
            @if (u.price?.per_m2) {
              <p class="uf-muted" [title]="'Per m² of ' + areaLabel(u.price?.per_m2_area_type) + (u.price?.per_m2_area_verified ? ' (verified)' : ' (indicative)')">
                {{ money({ amount: u.price!.per_m2!, currency: u.price!.currency }) }} per m² {{ areaLabel(u.price?.per_m2_area_type) }}
              </p>
            }
            @if (contact(); as c) {
              <p><a class="uf-btn" [href]="c">Ask about {{ u.code }}</a></p>
            }
          </section>
          <section class="uf-card">
            <h2>Facts</h2>
            <dl>
              <dt>Floor</dt><dd>{{ u.floor_name }} (building {{ u.building_code }})</dd>
              @if (u.rooms?.rooms != null) { <dt>Rooms</dt><dd>{{ u.rooms?.rooms }}</dd> }
              @if (u.rooms?.bedrooms != null) { <dt>Bedrooms</dt><dd>{{ u.rooms?.bedrooms }}</dd> }
              @if (u.rooms?.bathrooms != null) { <dt>Bathrooms</dt><dd>{{ u.rooms?.bathrooms }}</dd> }
              @if (u.rooms?.orientation) { <dt>Orientation</dt><dd>{{ u.rooms?.orientation }}</dd> }
            </dl>
          </section>
          @if (areaRows().length) {
            <section class="uf-card">
              <h2>Areas</h2>
              <table>
                @for (a of areaRows(); track a.key) {
                  <tr><th scope="row" [title]="a.description ?? ''">{{ a.label }}</th><td>{{ a.value }}</td></tr>
                }
              </table>
              <p class="uf-muted small">@if (u.indicative) { Measured from the plan, indicative. } @else { Verified against the drawings. }</p>
            </section>
          }
          @if (u.payment_plan; as p) {
            <section class="uf-card"><h2>{{ p.name }}</h2>@if (p.description) { <p>{{ p.description }}</p> }
              <ol>@for (m of p.schedule; track $index) { <li>{{ m.label }} — {{ +m.percent }} %@if (m.due) { , {{ m.due }} }</li> }</ol>
            </section>
          }
          @for (p of u.promotions ?? []; track p.name) {
            <section class="uf-card"><h2>{{ p.name }}</h2>@if (p.terms) { <p>{{ p.terms }}</p> }@if (p.valid_to) { <p class="uf-muted">Until {{ p.valid_to }}</p> }</section>
          }
        </aside>
      </div>
    } @else { <p class="uf-muted">Loading…</p> }
  `,
  styles: `
    .head { display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; margin-bottom: 0.75rem; }
    .layout { display: grid; grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr); gap: 1rem; margin-top: 0.75rem; }
    @media (max-width: 900px) { .layout { grid-template-columns: 1fr; } .side { order: -1; } }
    .main, .side { display: grid; gap: 1rem; align-content: start; min-width: 0; }
    .price { font-size: 1.6rem; font-weight: 700; margin: 0; }
    .gallery { display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fill, minmax(min(100%, 260px), 1fr)); }
    figure { margin: 0; display: grid; gap: 0.25rem; }
    .media { position: relative; }
    figure img, figure video { width: 100%; border-radius: var(--uf-radius); display: block; background: #e2e8f0; aspect-ratio: 4 / 3; object-fit: cover; }
    dl { display: grid; grid-template-columns: auto 1fr; gap: 0.25rem 1rem; margin: 0; }
    dt { color: var(--uf-muted); } dd { margin: 0; }
    table { width: 100%; border-collapse: collapse; }
    th, td { text-align: left; padding: 0.3rem 0; border-bottom: 1px solid var(--uf-border); font-weight: normal; }
    td { text-align: right; font-weight: 600; }
    .small { font-size: 0.85rem; }
    .pre { white-space: pre-line; }
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
  readonly fav = computed(() => !!this.unit() && this.favs.has(this.slug(), this.unit()!.code));
  readonly planPolygons = computed<PlanPolygon[]>(() => {
    const u = this.unit();
    if (!u?.plan?.ring) return [];
    return [{ id: u.unit_id, ring: u.plan.ring, label: u.code, fill: 'color-mix(in srgb, var(--uf-primary) 28%, transparent)', stroke: 'var(--uf-primary)', title: u.code }];
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
    combineLatest([toObservable(this.slug), toObservable(this.code)]).subscribe(([s, c]) => void this.load(s, c));
  }

  areaLabel(key: string | null | undefined): string {
    return (this.doc()?.project.area_definitions ?? []).find((d) => d.key === key)?.label?.toLowerCase() ?? key ?? '';
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
