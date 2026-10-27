import { JsonPipe } from '@angular/common';
import { Component, computed, effect, inject, input } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { PlanViewerComponent } from 'plan-viewer';
import {
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
  ago,
  labelOf,
} from 'ui';
import { RouteInfo } from '../../core/route-info';
import { AVAILABILITY, PUBLIC_FIELDS, formatPrice } from '../../sales/sales-format';
import { UnitHistoryComponent } from './unit-history.component';
import { UnitMediaComponent } from './unit-media.component';
import { UnitRendersComponent } from './unit-renders.component';
import { showValue } from '../inventory/inventory.model';
import { AVAILABILITY_FILL } from './unit-sales.model';
import { UnitSalesStore } from './unit-sales.store';

/** Unit commercial detail (plan §11.2 "Unit detail"): pricing & terms, publication fields, media, history. */
@Component({
  selector: 'uf-unit-sales-page',
  imports: [
    FormsModule,
    JsonPipe,
    RouterLink,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
    NgIcon,
    PageHeaderComponent,
    PlanViewerComponent,
    SectionCardComponent,
    StatusChipComponent,
    UnitMediaComponent,
    UnitRendersComponent,
    UnitHistoryComponent,
  ],
  providers: [UnitSalesStore],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      @let r = store.row();
      <uf-page-header
        [title]="r ? r.code : 'Unit'"
        icon="lucideCoins"
        [kicker]="
          r
            ? labelOf('unit_type', r.unit_type) +
              ' · building ' +
              r.building_code +
              ' · level ' +
              r.floor_level
            : null
        "
        [facts]="facts()"
      >
        <ng-container actions>
          <a mat-stroked-button routerLink=".."><ng-icon name="lucideArrowLeft" /> Inventory</a>
          <button
            mat-flat-button
            [disabled]="store.busy() || !store.dirtyCount()"
            (click)="store.save()"
          >
            Save {{ store.dirtyCount() || '' }} change{{ store.dirtyCount() === 1 ? '' : 's' }}
          </button>
          <button
            mat-button
            [disabled]="store.busy() || !store.dirtyCount()"
            (click)="store.reset()"
          >
            Undo
          </button>
        </ng-container>
      </uf-page-header>
      @if (store.error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }
      @if (store.conflict(); as c) {
        <div class="uf-alert uf-alert--warning" role="alert">
          <ng-icon name="lucideTriangleAlert" />
          <div class="uf-stack">
            <strong>Someone else changed this unit</strong> (now version {{ c.version }}). Fields
            you edited:
            @for (k of store.conflictKeys(); track k) {
              <div>
                <span class="uf-muted">{{ k }}</span
                >: yours <code>{{ show(store.pending(), k) }}</code> · current
                <code>{{ show(c, k) }}</code>
              </div>
            }
            <div class="uf-actions">
              <button mat-flat-button (click)="store.saveOnTop()">
                Apply mine on top of the current version
              </button>
              <button mat-button (click)="store.discardMine()">Load the current values</button>
            </div>
          </div>
        </div>
      }

      @if (r) {
        @let f = store.form();
        <div class="layout">
          <div class="uf-stack main">
            <uf-section-card
              title="Price & terms"
              tone="good"
              icon="lucideTag"
              [summary]="priceSummary()"
              storageKey="unit-price"
            >
              <div class="uf-form-row">
                <mat-form-field
                  appearance="outline"
                  [class.uf-changed]="store.isChanged('availability')"
                  ><mat-label>Availability</mat-label>
                  <mat-select
                    [ngModel]="f.availability"
                    (ngModelChange)="store.set('availability', $event)"
                    name="availability"
                  >
                    @for (a of availability; track a) {
                      <mat-option [value]="a"
                        ><uf-status-chip domain="availability" [value]="a"
                      /></mat-option>
                    }
                  </mat-select>
                </mat-form-field>
                <mat-form-field appearance="outline" class="grow"
                  ><mat-label>Reason for the change</mat-label
                  ><input
                    matInput
                    [(ngModel)]="store.reason"
                    name="reason"
                    [placeholder]="
                      r.availability === 'sold'
                        ? 'required when a sold unit changes'
                        : 'optional, kept in the history'
                    "
                /></mat-form-field>
              </div>
              <div class="uf-form-row">
                <mat-form-field
                  appearance="outline"
                  [class.uf-changed]="store.isChanged('list_price')"
                  ><mat-label>Price</mat-label
                  ><input
                    matInput
                    [ngModel]="f.list_price"
                    (ngModelChange)="store.set('list_price', $event)"
                    name="price"
                    placeholder="empty = on request"
                /></mat-form-field>
                <mat-form-field
                  appearance="outline"
                  class="ccy"
                  [class.uf-changed]="store.isChanged('currency')"
                  ><mat-label>Currency</mat-label
                  ><input
                    matInput
                    [ngModel]="f.currency"
                    (ngModelChange)="store.set('currency', $event)"
                    name="currency"
                    maxlength="3"
                /></mat-form-field>
                <div class="checks">
                  <mat-checkbox
                    [ngModel]="f.price_on_request"
                    (ngModelChange)="store.set('price_on_request', $event)"
                    name="por"
                    [class.uf-changed]="store.isChanged('price_on_request')"
                    >Price on request</mat-checkbox
                  >
                  <mat-checkbox [(ngModel)]="store.confirmZero" name="zero"
                    >Price 0 is intended</mat-checkbox
                  >
                </div>
              </div>
              <p class="uf-hint">
                @if (store.perM2(); as pm) {
                  <span [class]="pm.verified ? 'uf-text-good' : 'uf-text-warning'"
                    >= {{ pm.text }}{{ pm.verified ? '' : ' (area unverified)' }}</span
                  >
                  ·
                } @else if (r.price_area_m2) {
                  Pricing area {{ r.price_area_m2 }} m² ({{ areaLabel(r.price_area_type) }},
                  {{ r.price_area_verified ? 'verified' : 'unverified' }}) ·
                } @else {
                  <span class="uf-text-warning">No pricing area yet: per-m² stays empty.</span> ·
                }
                Empty price = "on request"; 0 is a real price and needs the checkbox.
              </p>
              <div class="uf-form-row">
                <mat-form-field
                  appearance="outline"
                  class="term term--wide"
                  [class.uf-changed]="store.isChanged('price_area_type')"
                  ><mat-label>Price per m² based on</mat-label>
                  <mat-select
                    [ngModel]="f.price_area_type"
                    (ngModelChange)="store.set('price_area_type', $event)"
                    name="pat"
                  >
                    <mat-option [value]="null">Project default</mat-option>
                    @for (a of store.areaDefs(); track a.key) {
                      <mat-option [value]="a.key">{{ a.label ?? a.key }}</mat-option>
                    }
                  </mat-select>
                </mat-form-field>
                <mat-form-field
                  appearance="outline"
                  class="term"
                  [class.uf-changed]="store.isChanged('payment_plan_id')"
                  ><mat-label>Payment plan</mat-label>
                  <mat-select
                    [ngModel]="f.payment_plan_id"
                    (ngModelChange)="store.set('payment_plan_id', $event)"
                    name="plan"
                  >
                    <mat-option [value]="null">— none —</mat-option>
                    @for (p of store.plans(); track p.id) {
                      <mat-option [value]="p.id"
                        >{{ p.name }}
                        @if (!p.is_public) {
                          (internal)
                        }
                      </mat-option>
                    }
                  </mat-select>
                </mat-form-field>
                <mat-form-field
                  appearance="outline"
                  class="term"
                  [class.uf-changed]="store.isChanged('promotion_ids')"
                  ><mat-label>Promotions</mat-label>
                  <mat-select
                    [ngModel]="f.promotion_ids"
                    (ngModelChange)="store.set('promotion_ids', $event)"
                    name="promos"
                    multiple
                  >
                    @for (p of store.promotions(); track p.id) {
                      <mat-option [value]="p.id">{{ p.name }}</mat-option>
                    }
                  </mat-select>
                </mat-form-field>
              </div>
              <p class="uf-hint">
                @if (!f.price_area_type && r.price_area_type) {
                  Area basis follows the project default ({{ areaLabel(r.price_area_type) }}) ·
                }
                Plans and promotions are defined under
                <a routerLink="../../sales-setup">Plans &amp; promotions</a>.
              </p>
            </uf-section-card>

            <uf-section-card
              title="Rooms & description"
              tone="info"
              icon="lucideBuilding"
              [summary]="roomsSummary()"
              storageKey="unit-rooms"
            >
              <div class="uf-form-row">
                <mat-form-field
                  appearance="outline"
                  class="num"
                  [class.uf-changed]="store.isChanged('rooms')"
                  ><mat-label>Rooms</mat-label
                  ><input
                    matInput
                    type="number"
                    min="0"
                    [ngModel]="f.rooms"
                    (ngModelChange)="store.set('rooms', $event)"
                    name="rooms"
                /></mat-form-field>
                <mat-form-field
                  appearance="outline"
                  class="num"
                  [class.uf-changed]="store.isChanged('bedrooms')"
                  ><mat-label>Bedrooms</mat-label
                  ><input
                    matInput
                    type="number"
                    min="0"
                    [ngModel]="f.bedrooms"
                    (ngModelChange)="store.set('bedrooms', $event)"
                    name="bedrooms"
                /></mat-form-field>
                <mat-form-field
                  appearance="outline"
                  class="num"
                  [class.uf-changed]="store.isChanged('bathrooms')"
                  ><mat-label>Bathrooms</mat-label
                  ><input
                    matInput
                    type="number"
                    min="0"
                    [ngModel]="f.bathrooms"
                    (ngModelChange)="store.set('bathrooms', $event)"
                    name="bathrooms"
                /></mat-form-field>
                <mat-form-field
                  appearance="outline"
                  class="num"
                  [class.uf-changed]="store.isChanged('orientation')"
                  ><mat-label>Orientation</mat-label
                  ><input
                    matInput
                    [ngModel]="f.orientation"
                    (ngModelChange)="store.set('orientation', $event)"
                    name="orientation"
                    maxlength="20"
                    placeholder="S / SW"
                /></mat-form-field>
                <mat-form-field
                  appearance="outline"
                  class="num"
                  [class.uf-changed]="store.isChanged('layout')"
                  ><mat-label>Layout</mat-label
                  ><input
                    matInput
                    [ngModel]="f.layout"
                    (ngModelChange)="store.set('layout', $event)"
                    name="layout"
                    maxlength="40"
                    list="uf-layout-codes"
                    placeholder="L1"
                  />
                  <datalist id="uf-layout-codes">
                    @for (l of store.layouts(); track l.id) {
                      @if (l.status === 'confirmed') {
                        <option [value]="l.code">{{ l.name ?? '' }}</option>
                      }
                    }
                  </datalist>
                  <mat-hint><a routerLink="../../layouts">Layouts</a></mat-hint></mat-form-field
                >
                <mat-form-field
                  appearance="outline"
                  class="num"
                  [class.uf-changed]="store.isChanged('wall_colour')"
                  ><mat-label>Walls (RAL or hex)</mat-label
                  ><input
                    matInput
                    [ngModel]="f.wall_colour"
                    (ngModelChange)="store.set('wall_colour', $event)"
                    name="wall_colour"
                    maxlength="40"
                    placeholder="RAL 9010"
                /></mat-form-field>
                <mat-form-field
                  appearance="outline"
                  class="num"
                  [class.uf-changed]="store.isChanged('entrance')"
                  ><mat-label>Entrance</mat-label
                  ><input
                    matInput
                    [ngModel]="f.entrance"
                    (ngModelChange)="store.set('entrance', $event)"
                    name="entrance"
                    maxlength="20"
                    placeholder="1"
                /></mat-form-field>
              </div>
              <div class="uf-form-row">
                <mat-form-field
                  appearance="outline"
                  class="desc"
                  [class.uf-changed]="store.isChanged('public_description')"
                  ><mat-label>Public description</mat-label
                  ><textarea
                    matInput
                    rows="2"
                    [ngModel]="f.public_description"
                    (ngModelChange)="store.set('public_description', $event)"
                    name="pd"
                  ></textarea>
                  <mat-hint align="end">{{ f.public_description.length }} characters</mat-hint>
                </mat-form-field>
                <mat-form-field
                  appearance="outline"
                  class="notes"
                  [class.uf-changed]="store.isChanged('internal_notes')"
                  ><mat-label>Internal notes</mat-label
                  ><textarea
                    matInput
                    rows="2"
                    [ngModel]="f.internal_notes"
                    (ngModelChange)="store.set('internal_notes', $event)"
                    name="notes"
                  ></textarea
                  ><mat-hint>Never published</mat-hint></mat-form-field
                >
              </div>
            </uf-section-card>

            <uf-unit-media />
            <uf-unit-renders />
            <uf-unit-history [entries]="store.timeline()" />
          </div>

          <aside class="uf-stack side">
            <uf-section-card
              title="On the plan"
              icon="lucideMap"
              tone="info"
              [summary]="
                store.plan()
                  ? 'level ' + r.floor_level + ' · ' + store.plan()!.others + ' other units'
                  : 'no outline yet'
              "
              storageKey="unit-plan"
            >
              @if (store.plan(); as p) {
                <div class="plan">
                  <uf-plan-viewer
                    [src]="p.src"
                    [width]="p.width"
                    [height]="p.height"
                    [polygons]="p.polygons"
                    [focus]="p.focus"
                    mode="view"
                    (polygonSelected)="openUnit($event)"
                  />
                </div>
                <div class="legend">
                  @for (l of legend; track l.key) {
                    <span><i [style.background]="l.stroke"></i>{{ l.label }}</span>
                  }
                  <a [routerLink]="['../../sheets', p.sheetId]"
                    ><ng-icon name="lucideFileImage" /><span>Open the sheet</span></a
                  >
                </div>
              } @else {
                <p class="uf-hint">
                  No current outline on a processed sheet yet. Draw or approve one on the sheet page
                  under <a routerLink="../../documents">Documents</a>.
                </p>
              }
            </uf-section-card>
            <uf-section-card
              title="Shown to buyers"
              tone="info"
              icon="lucideEye"
              [summary]="publicSummary()"
              storageKey="unit-public"
            >
              <p class="uf-hint">
                Per-unit overrides of the project defaults; a changed row is marked.
              </p>
              <div class="toggles">
                @for (pf of publicFields; track pf.key) {
                  <div
                    class="toggle"
                    [class.uf-changed]="pf.key in r.public_field_overrides"
                    [title]="
                      pf.key in r.public_field_overrides
                        ? 'Overridden for this unit'
                        : 'Project default'
                    "
                  >
                    <mat-slide-toggle
                      [checked]="r.public_fields[pf.key]"
                      (change)="store.togglePublic(pf.key, $event.checked)"
                      >{{ pf.label }}</mat-slide-toggle
                    >
                    @if (pf.key in r.public_field_overrides) {
                      <span class="uf-chip uf-tone-warning">overridden</span>
                    }
                  </div>
                }
              </div>
              <button
                mat-button
                [disabled]="!store.hasOverrides()"
                (click)="store.clearOverrides()"
              >
                Reset to project defaults
              </button>
            </uf-section-card>
            <uf-section-card
              title="Same floor"
              icon="lucideLayers"
              tone="neutral"
              [count]="store.neighbours().length"
              [summary]="
                'level ' +
                r.floor_level +
                (r.floor_name && r.floor_name !== '' + r.floor_level ? ' · ' + r.floor_name : '')
              "
              storageKey="unit-floor"
            >
              @if (store.neighbours().length) {
                <div class="mates">
                  @for (n of store.neighbours(); track n.unit_id) {
                    <a class="mate" [routerLink]="['..', n.unit_id]" [title]="mateTitle(n)"
                      ><uf-status-chip
                        domain="availability"
                        [value]="n.availability"
                        [label]="n.code"
                    /></a>
                  }
                </div>
              } @else {
                <p class="uf-hint">The only unit on this floor.</p>
              }
              @if (r.layout) {
                <p class="uf-field-note">
                  Layout <a routerLink="../../layouts">{{ r.layout }}</a
                  >{{ r.layout_name ? ' (' + r.layout_name + ')' : '' }}:
                  @for (n of store.layoutMates(); track n.unit_id; let last = $last) {
                    <a [routerLink]="['..', n.unit_id]">{{ n.code }}</a
                    >{{ last ? '' : ', ' }}
                  }
                  @if (!store.layoutMates().length) {
                    no other unit yet
                  }
                  · every linked unit shows the layout's media after its own.
                </p>
              }
            </uf-section-card>
            <uf-section-card
              title="Buyer preview"
              tone="neutral"
              icon="lucideGlobe"
              summary="what the portal receives"
              storageKey="unit-preview"
              [open]="false"
            >
              <pre class="pre">{{ store.preview() | json }}</pre>
            </uf-section-card>
          </aside>
        </div>
      }
    </div>
  `,
  styles: `
    .layout {
      display: grid;
      grid-template-columns: minmax(0, 2fr) minmax(280px, 1fr);
      gap: 0.75rem;
      align-items: start;
    }
    @media (max-width: 1100px) {
      .layout {
        grid-template-columns: 1fr;
      }
    }
    .grow {
      flex: 1;
      min-width: 220px;
    }
    .num {
      flex: 1 1 7rem;
      min-width: 0;
    }
    .term {
      flex: 1 1 9rem;
      min-width: 0;
    }
    .ccy {
      width: 96px;
    }
    .checks {
      display: flex;
      flex-direction: column;
      margin-top: 0 !important;
    }
    .desc {
      flex: 2 1 18rem;
    }
    .notes {
      flex: 1 1 12rem;
    }
    .plan uf-plan-viewer {
      --uf-plan-min-height: 170px;
      --uf-plan-height: 230px;
      display: block;
      border-radius: var(--uf-radius-sm);
      overflow: hidden;
      border: 1px solid var(--uf-border);
    }
    .legend {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 0.2rem 0.7rem;
      font-size: 0.8rem;
      color: var(--uf-muted);
    }
    .legend i {
      display: inline-block;
      width: 0.65rem;
      height: 0.65rem;
      border-radius: 3px;
      margin-right: 0.3rem;
      vertical-align: -1px;
    }
    .legend a {
      margin-left: auto;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }
    .mates {
      display: flex;
      flex-wrap: wrap;
      gap: 0.35rem;
    }
    .mate {
      text-decoration: none;
    }
    .toggles {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
      gap: 0 0.25rem;
    }
    .toggle mat-slide-toggle {
      white-space: nowrap;
    }
    .term--wide {
      flex: 1.6 1 11rem;
    }
    .toggle {
      display: flex;
      gap: 0.5rem;
      align-items: center;
      padding: 0.05rem 0.35rem;
      border-radius: 6px;
      font-size: 0.9rem;
    }
    .pre {
      background: var(--uf-surface-2);
      padding: 0.5rem;
      font-size: 0.75rem;
      max-height: 320px;
      overflow: auto;
      margin: 0;
      border-radius: 6px;
    }
    mat-form-field.uf-changed {
      border-radius: 6px;
    }
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class UnitSalesPage {
  protected readonly store = inject(UnitSalesStore);
  private readonly routeInfo = inject(RouteInfo);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly unitId = input.required<string>();
  readonly availability = AVAILABILITY;
  readonly publicFields = PUBLIC_FIELDS;
  readonly labelOf = labelOf;
  show = showValue;

  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);
  readonly legend = Object.entries(AVAILABILITY_FILL).map(([key, v]) => ({ key, ...v }));

  readonly facts = computed<HeaderFact[]>(() => {
    const r = this.store.row();
    if (!r) return [];
    const facts: HeaderFact[] = [
      { domain: 'availability', status: r.availability },
      { domain: 'unit.verification', status: r.verification_status },
      { domain: 'unit.publication', status: r.publication_status },
      {
        label: 'Price',
        icon: 'lucideTag',
        value:
          formatPrice(r.list_price, r.currency) ?? (r.price_on_request ? 'on request' : 'not set'),
      },
    ];
    if (r.price_per_m2)
      facts.push({ label: 'per m²', value: formatPrice(r.price_per_m2, r.currency) });
    if (r.price_area_m2)
      facts.push({
        label: 'Area',
        icon: 'lucideRuler',
        value: `${r.price_area_m2} m² ${this.areaLabel(r.price_area_type)}${r.price_area_verified ? '' : ' (unverified)'}`,
      });
    if (r.rooms !== null && r.rooms !== undefined)
      facts.push({
        label: 'Rooms',
        icon: 'lucideBedDouble',
        value: `${r.rooms}${r.bedrooms !== null && r.bedrooms !== undefined ? ` · ${r.bedrooms} bed` : ''}`,
      });
    const when = r.updated_at ? ago(r.updated_at) : '';
    facts.push({ label: 'Version', value: when ? `${r.version} · ${when}` : r.version });
    return facts;
  });

  /** A click on a neighbour's outline opens that unit; a click on this unit does nothing. */
  openUnit(unitId: string): void {
    if (unitId === this.unitId() || !this.store.allRows().some((r) => r.unit_id === unitId)) return;
    void this.router.navigate(['..', unitId], { relativeTo: this.route });
  }

  /** An area type key in words ("net internal"), the vocabulary the inventory uses. */
  areaLabel(key: string | null | undefined): string {
    return (key ?? '').replace(/_/g, ' ');
  }

  mateTitle(n: { code: string; availability: string; rooms?: number | null }): string {
    const rooms = n.rooms !== null && n.rooms !== undefined ? ` · ${n.rooms} rooms` : '';
    return `${n.code} · ${labelOf('availability', n.availability)}${rooms}`;
  }

  constructor() {
    toObservable(this.unitId).subscribe(() => {
      this.store.init(this.tenantId(), this.projectId(), this.unitId());
      void this.store.load();
    });
    effect(() => {
      const r = this.store.row();
      this.routeInfo.setLeaf(r ? r.code : null);
    });
  }

  fmt(v: string | null | undefined, c: string): string {
    return formatPrice(v, c) ?? '';
  }

  priceSummary(): string {
    const f = this.store.form();
    const price = f.price_on_request
      ? 'on request'
      : (formatPrice(f.list_price, f.currency) ?? 'no price');
    const promos = this.store.promotionNames();
    return [
      labelOf('availability', f.availability),
      price,
      this.store.planName() ?? 'no payment plan',
      promos.length
        ? `${promos.length} promotion${promos.length === 1 ? '' : 's'}`
        : 'no promotion',
    ].join(' · ');
  }

  roomsSummary(): string {
    const f = this.store.form();
    const parts: string[] = [];
    if (f.rooms !== null) parts.push(`${f.rooms} rooms`);
    if (f.bedrooms !== null) parts.push(`${f.bedrooms} bed`);
    if (f.bathrooms !== null) parts.push(`${f.bathrooms} bath`);
    if (f.orientation) parts.push(f.orientation);
    if (f.entrance) parts.push(`entrance ${f.entrance}`);
    parts.push(f.public_description ? 'description set' : 'no description');
    return parts.join(' · ');
  }

  publicSummary(): string {
    const r = this.store.row();
    if (!r) return '';
    const on = this.publicFields.filter((p) => r.public_fields[p.key]).length;
    const ov = Object.keys(r.public_field_overrides ?? {}).length;
    return `${on} of ${this.publicFields.length} shown${ov ? ` · ${ov} overridden` : ''}`;
  }
}
