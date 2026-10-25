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
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { HeaderFact, PageHeaderComponent, SectionCardComponent, UF_ICONS, labelOf } from 'ui';
import { RouteInfo } from '../../core/route-info';
import { AVAILABILITY, PUBLIC_FIELDS, formatPrice } from '../../sales/sales-format';
import { UnitHistoryComponent } from './unit-history.component';
import { UnitMediaComponent } from './unit-media.component';
import { showValue } from '../inventory/inventory.model';
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
    SectionCardComponent,
    UnitMediaComponent,
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
              title="Price & availability"
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
                      <mat-option [value]="a">{{ labelOf('availability', a) }}</mat-option>
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
              <p class="uf-hint">
                An empty price is shown as "price on request"; 0 is a real price and needs the
                checkbox.
                @if (r.price_per_m2) {
                  Today: {{ fmt(r.price_per_m2, r.currency) }} per m² of
                  {{ r.price_area_type }} area ({{
                    r.price_area_verified ? 'verified' : 'unverified'
                  }}).
                }
              </p>
            </uf-section-card>

            <uf-section-card
              title="Terms"
              icon="lucideHandCoins"
              [summary]="termsSummary()"
              storageKey="unit-terms"
            >
              <div class="uf-form-row">
                <mat-form-field
                  appearance="outline"
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
                Plans and promotions are defined once under
                <a routerLink="../../sales-setup">Plans &amp; promotions</a> and picked here.
              </p>
            </uf-section-card>

            <uf-section-card
              title="Rooms & description"
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
              <mat-form-field
                appearance="outline"
                class="wide"
                [class.uf-changed]="store.isChanged('public_description')"
                ><mat-label>Public description</mat-label
                ><textarea
                  matInput
                  rows="3"
                  [ngModel]="f.public_description"
                  (ngModelChange)="store.set('public_description', $event)"
                  name="pd"
                ></textarea>
              </mat-form-field>
              <mat-form-field
                appearance="outline"
                class="wide"
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
            </uf-section-card>

            <uf-unit-media />
            <uf-unit-history [entries]="store.timeline()" />
          </div>

          <aside class="uf-stack side">
            <uf-section-card
              title="Shown to buyers"
              icon="lucideEye"
              [summary]="publicSummary()"
              storageKey="unit-public"
            >
              <p class="uf-hint">
                Per-unit overrides of the project defaults. A changed row is marked.
              </p>
              @for (pf of publicFields; track pf.key) {
                <div class="toggle" [class.uf-changed]="pf.key in r.public_field_overrides">
                  <mat-slide-toggle
                    [checked]="r.public_fields[pf.key]"
                    (change)="store.togglePublic(pf.key, $event.checked)"
                    >{{ pf.label }}</mat-slide-toggle
                  >
                  <span class="uf-muted uf-small">{{
                    pf.key in r.public_field_overrides ? 'overridden' : 'project default'
                  }}</span>
                </div>
              }
              <button
                mat-button
                [disabled]="!store.hasOverrides()"
                (click)="store.clearOverrides()"
              >
                Reset to project defaults
              </button>
            </uf-section-card>
            <uf-section-card
              title="Buyer preview"
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
      grid-template-columns: minmax(0, 2fr) minmax(300px, 1fr);
      gap: 1rem;
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
      width: 130px;
    }
    .ccy {
      width: 110px;
    }
    .wide {
      width: 100%;
    }
    .toggle {
      display: flex;
      gap: 0.75rem;
      align-items: center;
      padding: 0.25rem 0.5rem;
      border-radius: 6px;
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

  readonly facts = computed<HeaderFact[]>(() => {
    const r = this.store.row();
    if (!r) return [];
    return [
      { domain: 'availability', status: r.availability },
      { domain: 'unit.verification', status: r.verification_status },
      { domain: 'unit.publication', status: r.publication_status },
      {
        label: 'Price',
        value:
          formatPrice(r.list_price, r.currency) ?? (r.price_on_request ? 'on request' : 'not set'),
      },
      { label: 'Version', value: r.version },
    ];
  });

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
    return `${labelOf('availability', f.availability)} · ${price}`;
  }

  termsSummary(): string {
    const f = this.store.form();
    const parts = [
      f.price_area_type ? `per m² of ${f.price_area_type}` : 'project area type',
      this.store.planName() ?? 'no payment plan',
    ];
    const promos = this.store.promotionNames();
    parts.push(
      promos.length
        ? `${promos.length} promotion${promos.length === 1 ? '' : 's'}`
        : 'no promotion',
    );
    return parts.join(' · ');
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
