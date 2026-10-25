import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import {
  PaymentPlanOut,
  PromotionIn,
  PromotionOut,
  SalesSettingsOut,
  UnitformaApi,
  problemMessage,
} from 'api-client';
import {
  EmptyStateComponent,
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
  labelOf,
} from 'ui';
import { PUBLIC_FIELDS } from '../sales/sales-format';
import { ToastService } from '../ui/toast.service';

interface MilestoneForm {
  label: string;
  percent: number | null;
  due: string;
}

interface PlanForm {
  id: string | null;
  version: number;
  name: string;
  description: string;
  schedule: MilestoneForm[];
  is_public: boolean;
  is_active: boolean;
}

type PromotionKind = NonNullable<PromotionIn['kind']>;
const PROMOTION_KINDS: PromotionKind[] = [
  'discount_percent',
  'discount_amount',
  'gift',
  'financing',
  'other',
];

interface PromoForm {
  id: string | null;
  version: number;
  name: string;
  kind: PromotionKind;
  value: string;
  terms: string;
  valid_from: string;
  valid_to: string;
  is_public: boolean;
  is_active: boolean;
}

/** Project sales setup (plan §6.2, §6.6): price area type, public-field defaults, payment plans, promotions. */
@Component({
  selector: 'uf-sales-setup-page',
  imports: [
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
    NgIcon,
    PageHeaderComponent,
    SectionCardComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="Plans, promotions & defaults" icon="lucideHandCoins" [facts]="facts()">
        <ng-container actions
          ><a mat-stroked-button routerLink="../inventory"
            ><ng-icon name="lucideTable" /> Inventory</a
          ></ng-container
        >
      </uf-page-header>
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }

      @if (settings(); as s) {
        <uf-section-card
          title="Project defaults"
          icon="lucideSettings"
          [summary]="defaultsSummary()"
          storageKey="sales-defaults"
        >
          <div class="uf-form-row">
            <mat-form-field
              appearance="outline"
              subscriptSizing="dynamic"
              [class.uf-set]="!!priceAreaType"
              ><mat-label>Price per m² is based on</mat-label>
              <mat-select [(ngModel)]="priceAreaType" name="pat">
                @for (a of areaDefs(); track a.key) {
                  <mat-option [value]="a.key">{{ a.label ?? a.key }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
            <span class="uf-hint"
              >Every price per m² in the inventory and on the portal divides by this area type
              unless a unit overrides it.</span
            >
          </div>
          <p class="uf-small uf-muted">Fields shown to buyers by default (units can override):</p>
          <div class="uf-form-row">
            @for (f of publicFields; track f.key) {
              <mat-slide-toggle [(ngModel)]="publicDefaults[f.key]" [name]="'pf' + f.key">{{
                f.label
              }}</mat-slide-toggle>
            }
          </div>
          <p class="uf-hint">
            Internal notes, availability reasons, price history and imports are never published.
          </p>
          <div class="uf-actions">
            <button mat-flat-button [disabled]="busy()" (click)="saveSettings(s)">
              Save defaults
            </button>
          </div>
        </uf-section-card>
      }

      <div class="uf-grid2">
        <uf-section-card
          title="Payment plans"
          icon="lucideCalendar"
          [count]="plans().length"
          [summary]="plans().filter(isPublic).length + ' public'"
          storageKey="sales-plans"
        >
          @for (p of plans(); track p.id) {
            <div class="item" [class.is-editing]="plan.id === p.id">
              <div class="item__main">
                <strong>{{ p.name }}</strong>
                <span class="uf-muted uf-small">{{ scheduleText(p) }}</span>
              </div>
              <span class="uf-chip" [class.uf-tone-good]="p.is_public"
                ><ng-icon [name]="p.is_public ? 'lucideGlobe' : 'lucideEyeOff'" />{{
                  p.is_public ? 'public' : 'internal'
                }}</span
              >
              @if (!p.is_active) {
                <span class="uf-chip uf-tone-neutral">inactive</span>
              }
              <button mat-button (click)="editPlan(p)"><ng-icon name="lucidePencil" /> Edit</button>
            </div>
          } @empty {
            <uf-empty-state
              icon="lucideCalendar"
              title="No payment plans yet"
              text="Create one below; assign it to units in the inventory."
              [compact]="true"
            />
          }
          <h3 class="editor-title">
            <ng-icon [name]="plan.id ? 'lucidePencil' : 'lucidePlus'" />
            {{ plan.id ? 'Edit ' + plan.name : 'New payment plan' }}
          </h3>
          <div class="uf-form-row">
            <mat-form-field appearance="outline" subscriptSizing="dynamic"
              ><mat-label>Name</mat-label
              ><input matInput [(ngModel)]="plan.name" name="pname" placeholder="30 / 70"
            /></mat-form-field>
            <mat-slide-toggle [(ngModel)]="plan.is_public" name="ppub">Public</mat-slide-toggle>
            <mat-slide-toggle [(ngModel)]="plan.is_active" name="pact">Active</mat-slide-toggle>
          </div>
          <mat-form-field appearance="outline" class="wide" subscriptSizing="dynamic"
            ><mat-label>Description</mat-label
            ><textarea matInput rows="2" [(ngModel)]="plan.description" name="pdesc"></textarea>
          </mat-form-field>
          @for (m of plan.schedule; track $index; let i = $index) {
            <div class="uf-form-row">
              <mat-form-field appearance="outline" subscriptSizing="dynamic"
                ><mat-label>Milestone</mat-label
                ><input matInput [(ngModel)]="m.label" [name]="'ml' + i" placeholder="Deposit"
              /></mat-form-field>
              <mat-form-field appearance="outline" subscriptSizing="dynamic" class="num"
                ><mat-label>%</mat-label
                ><input matInput type="number" [(ngModel)]="m.percent" [name]="'mp' + i"
              /></mat-form-field>
              <mat-form-field appearance="outline" subscriptSizing="dynamic"
                ><mat-label>When</mat-label
                ><input matInput [(ngModel)]="m.due" [name]="'md' + i" placeholder="on signing"
              /></mat-form-field>
              <button
                mat-icon-button
                (click)="plan.schedule.splice(i, 1)"
                aria-label="Remove milestone"
                title="Remove"
              >
                <ng-icon name="lucideX" />
              </button>
            </div>
          }
          <div class="uf-form-row">
            <button mat-button (click)="plan.schedule.push({ label: '', percent: null, due: '' })">
              <ng-icon name="lucidePlus" /> Add milestone
            </button>
            <span
              class="uf-chip"
              [class.uf-tone-good]="total() === 100"
              [class.uf-tone-warning]="total() !== 100 && plan.schedule.length > 0"
              >total {{ total() }} %</span
            >
            @if (total() !== 100 && plan.schedule.length > 0) {
              <span class="uf-hint">Milestones should add up to 100 %.</span>
            }
          </div>
          <div class="uf-actions">
            <button mat-flat-button [disabled]="busy() || !plan.name" (click)="savePlan()">
              {{ plan.id ? 'Save plan' : 'Create plan' }}
            </button>
            @if (plan.id) {
              <button mat-button (click)="plan = blankPlan()">Cancel, new plan</button>
            }
          </div>
        </uf-section-card>

        <uf-section-card
          title="Promotions"
          icon="lucideGift"
          [count]="promotions().length"
          [summary]="promotions().filter(isActive).length + ' active'"
          storageKey="sales-promotions"
        >
          @for (p of promotions(); track p.id) {
            <div class="item" [class.is-editing]="promo.id === p.id">
              <div class="item__main">
                <strong>{{ p.name }}</strong>
                <span class="uf-muted uf-small">
                  @if (p.value) {
                    {{ p.value }}{{ p.kind === 'discount_percent' ? ' %' : '' }} ·
                  }
                  @if (p.valid_to) {
                    until {{ p.valid_to }}
                  } @else {
                    no end date
                  }
                </span>
              </div>
              <uf-status-chip domain="promotion_kind" [value]="p.kind" />
              <span class="uf-chip" [class.uf-tone-good]="p.is_public"
                ><ng-icon [name]="p.is_public ? 'lucideGlobe' : 'lucideEyeOff'" />{{
                  p.is_public ? 'public' : 'internal'
                }}</span
              >
              @if (!p.is_active) {
                <span class="uf-chip uf-tone-neutral">inactive</span>
              }
              <button mat-button (click)="editPromo(p)">
                <ng-icon name="lucidePencil" /> Edit
              </button>
            </div>
          } @empty {
            <uf-empty-state
              icon="lucideGift"
              title="No promotions yet"
              text="A discount, gift or financing offer with its validity; assign per unit in the inventory."
              [compact]="true"
            />
          }
          <h3 class="editor-title">
            <ng-icon [name]="promo.id ? 'lucidePencil' : 'lucidePlus'" />
            {{ promo.id ? 'Edit ' + promo.name : 'New promotion' }}
          </h3>
          <div class="uf-form-row">
            <mat-form-field appearance="outline" subscriptSizing="dynamic"
              ><mat-label>Name</mat-label
              ><input matInput [(ngModel)]="promo.name" name="prname" placeholder="Early bird"
            /></mat-form-field>
            <mat-form-field appearance="outline" subscriptSizing="dynamic"
              ><mat-label>Kind</mat-label>
              <mat-select [(ngModel)]="promo.kind" name="prkind">
                @for (k of promotionKinds; track k) {
                  <mat-option [value]="k">{{ labelOf('promotion_kind', k) }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="num"
              ><mat-label>Value</mat-label><input matInput [(ngModel)]="promo.value" name="prval"
            /></mat-form-field>
          </div>
          <div class="uf-form-row">
            <mat-form-field appearance="outline" subscriptSizing="dynamic"
              ><mat-label>Valid from</mat-label
              ><input matInput type="date" [(ngModel)]="promo.valid_from" name="prfrom"
            /></mat-form-field>
            <mat-form-field appearance="outline" subscriptSizing="dynamic"
              ><mat-label>Valid to</mat-label
              ><input matInput type="date" [(ngModel)]="promo.valid_to" name="prto"
            /></mat-form-field>
            <mat-slide-toggle [(ngModel)]="promo.is_public" name="prpub">Public</mat-slide-toggle>
            <mat-slide-toggle [(ngModel)]="promo.is_active" name="pract">Active</mat-slide-toggle>
          </div>
          <mat-form-field appearance="outline" class="wide" subscriptSizing="dynamic"
            ><mat-label>Terms</mat-label
            ><textarea matInput rows="2" [(ngModel)]="promo.terms" name="prterms"></textarea>
          </mat-form-field>
          <div class="uf-actions">
            <button mat-flat-button [disabled]="busy() || !promo.name" (click)="savePromo()">
              {{ promo.id ? 'Save promotion' : 'Create promotion' }}
            </button>
            @if (promo.id) {
              <button mat-button (click)="promo = blankPromo()">Cancel, new promotion</button>
            }
          </div>
        </uf-section-card>
      </div>
    </div>
  `,
  styles: `
    .num {
      width: 110px;
    }
    .wide {
      width: 100%;
    }
    .item {
      display: flex;
      gap: 0.5rem;
      align-items: center;
      flex-wrap: wrap;
      padding: 0.4rem 0.6rem;
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius-sm);
    }
    .item.is-editing {
      border-color: var(--uf-primary);
      background: var(--uf-primary-soft);
    }
    .item__main {
      display: grid;
      flex: 1;
      min-width: 10rem;
    }
    .editor-title {
      display: flex;
      align-items: center;
      gap: 0.4rem;
      margin: 0.75rem 0 0;
      font-size: 0.95rem;
      color: var(--uf-muted);
    }
    .editor-title ng-icon {
      color: var(--uf-primary);
    }
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.2rem;
    }
  `,
})
export class SalesSetupPage {
  private readonly api = inject(UnitformaApi);
  private readonly toast = inject(ToastService);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly settings = signal<SalesSettingsOut | null>(null);
  readonly areaDefs = signal<{ key: string; label?: string }[]>([]);
  readonly plans = signal<PaymentPlanOut[]>([]);
  readonly promotions = signal<PromotionOut[]>([]);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly publicFields = PUBLIC_FIELDS;
  readonly promotionKinds = PROMOTION_KINDS;
  readonly labelOf = labelOf;
  readonly facts = computed<HeaderFact[]>(() => [
    { label: 'Payment plans', value: this.plans().length },
    { label: 'Promotions', value: this.promotions().length },
    ...(this.settings()
      ? [{ label: 'Price per m² by', value: this.settings()!.price_area_type }]
      : []),
  ]);
  priceAreaType = '';
  publicDefaults: Record<string, boolean> = {};
  plan: PlanForm = this.blankPlan();
  promo: PromoForm = this.blankPromo();

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  isPublic = (p: { is_public: boolean }) => p.is_public;
  isActive = (p: { is_active: boolean }) => p.is_active;

  blankPlan(): PlanForm {
    return {
      id: null,
      version: 0,
      name: '',
      description: '',
      schedule: [
        { label: 'Deposit', percent: 30, due: 'on signing' },
        { label: 'Balance', percent: 70, due: 'on completion' },
      ],
      is_public: true,
      is_active: true,
    };
  }

  blankPromo(): PromoForm {
    return {
      id: null,
      version: 0,
      name: '',
      kind: 'other',
      value: '',
      terms: '',
      valid_from: '',
      valid_to: '',
      is_public: true,
      is_active: true,
    };
  }

  total(): number {
    return (
      Math.round(this.plan.schedule.reduce((a, m) => a + Number(m.percent ?? 0), 0) * 100) / 100
    );
  }

  scheduleText(p: PaymentPlanOut): string {
    return (
      (p.schedule as { label: string; percent: string }[])
        .map((m) => `${m.label} ${Number(m.percent)}%`)
        .join(' / ') || 'no milestones'
    );
  }

  defaultsSummary(): string {
    const on = this.publicFields.filter((f) => this.publicDefaults[f.key]).length;
    return `price per m² by ${this.priceAreaType || '?'} · ${on} of ${this.publicFields.length} fields public`;
  }

  async load(): Promise<void> {
    try {
      const [s, plans, promos] = await Promise.all([
        this.api.getSalesSettings(this.tenantId(), this.projectId()),
        this.api.listPaymentPlans(this.tenantId(), this.projectId()),
        this.api.listPromotions(this.tenantId(), this.projectId()),
      ]);
      this.settings.set(s);
      this.areaDefs.set(s.area_definitions as { key: string; label?: string }[]);
      this.priceAreaType = s.price_area_type;
      this.publicDefaults = { ...s.public_fields };
      this.plans.set(plans);
      this.promotions.set(promos);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  saveSettings(s: SalesSettingsOut): Promise<void> {
    return this.run(async () => {
      await this.api.putSalesSettings(this.tenantId(), this.projectId(), {
        price_area_type: this.priceAreaType,
        public_fields: this.publicDefaults,
        version: s.project_version,
      });
      this.toast.ok('Defaults saved');
    });
  }

  editPlan(p: PaymentPlanOut): void {
    const sched = p.schedule as { label: string; percent: string; due?: string | null }[];
    this.plan = {
      id: p.id,
      version: p.version,
      name: p.name,
      description: p.description ?? '',
      schedule: sched.map((m) => ({
        label: m.label,
        percent: Number(m.percent),
        due: m.due ?? '',
      })),
      is_public: p.is_public,
      is_active: p.is_active,
    };
  }

  savePlan(): Promise<void> {
    const p = this.plan;
    const schedule = p.schedule
      .filter((m) => m.label)
      .map((m) => ({ label: m.label, percent: String(m.percent ?? 0), due: m.due || null }));
    const body = {
      name: p.name,
      description: p.description || null,
      schedule,
      is_public: p.is_public,
      is_active: p.is_active,
    };
    return this.run(async () => {
      if (p.id)
        await this.api.updatePaymentPlan(this.tenantId(), p.id, { ...body, version: p.version });
      else await this.api.createPaymentPlan(this.tenantId(), this.projectId(), body);
      this.toast.ok(`Payment plan ${p.name} ${p.id ? 'saved' : 'created'}`);
      this.plan = this.blankPlan();
    });
  }

  editPromo(p: PromotionOut): void {
    this.promo = {
      id: p.id,
      version: p.version,
      name: p.name,
      kind: p.kind as PromotionKind,
      value: p.value ?? '',
      terms: p.terms ?? '',
      valid_from: p.valid_from ?? '',
      valid_to: p.valid_to ?? '',
      is_public: p.is_public,
      is_active: p.is_active,
    };
  }

  savePromo(): Promise<void> {
    const p = this.promo;
    const body = {
      name: p.name,
      kind: p.kind,
      value: p.value ? String(p.value) : null,
      terms: p.terms || null,
      valid_from: p.valid_from || null,
      valid_to: p.valid_to || null,
      is_public: p.is_public,
      is_active: p.is_active,
    };
    return this.run(async () => {
      if (p.id)
        await this.api.updatePromotion(this.tenantId(), p.id, { ...body, version: p.version });
      else await this.api.createPromotion(this.tenantId(), this.projectId(), body);
      this.toast.ok(`Promotion ${p.name} ${p.id ? 'saved' : 'created'}`);
      this.promo = this.blankPromo();
    });
  }

  private async run(fn: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await fn();
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
