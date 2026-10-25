import { Component, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { RouterLink } from '@angular/router';
import { PaymentPlanOut, PromotionIn, PromotionOut, SalesSettingsOut, UnitformaApi, problemMessage } from 'api-client';
import { PUBLIC_FIELDS } from '../sales/sales-format';

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
  imports: [FormsModule, RouterLink, MatButtonModule, MatCardModule, MatCheckboxModule, MatFormFieldModule, MatInputModule, MatSelectModule, MatSlideToggleModule],
  template: `
    <div class="uf-page">
      <div class="uf-page-header"><h2>Plans, promotions &amp; settings</h2><a mat-stroked-button routerLink="../inventory">Inventory</a></div>
      @if (error()) { <p class="uf-error" role="alert">{{ error() }}</p> }

      @if (settings(); as s) {
        <mat-card appearance="outlined">
          <mat-card-header><mat-card-title>Project defaults</mat-card-title></mat-card-header>
          <mat-card-content>
            <div class="uf-row">
              <mat-form-field appearance="outline"><mat-label>Price per m² is based on</mat-label>
                <mat-select [(ngModel)]="priceAreaType" name="pat">
                  @for (a of areaDefs(); track a.key) { <mat-option [value]="a.key">{{ a.label ?? a.key }}</mat-option> }
                </mat-select>
              </mat-form-field>
            </div>
            <p class="uf-muted">Fields shown to buyers by default (units can override):</p>
            <div class="uf-row">
              @for (f of publicFields; track f.key) { <mat-slide-toggle [(ngModel)]="publicDefaults[f.key]" [name]="'pf' + f.key">{{ f.label }}</mat-slide-toggle> }
            </div>
            <p class="uf-muted">Internal notes, availability reasons, price history and imports are never published.</p>
          </mat-card-content>
          <mat-card-actions><button mat-flat-button [disabled]="busy()" (click)="saveSettings(s)">Save defaults</button></mat-card-actions>
        </mat-card>
      }

      <div class="uf-grid2">
        <mat-card appearance="outlined">
          <mat-card-header><mat-card-title>Payment plans</mat-card-title></mat-card-header>
          <mat-card-content>
            <ul class="uf-list">
              @for (p of plans(); track p.id) {
                <li>
                  <button mat-button (click)="editPlan(p)">{{ p.name }}</button>
                  <span class="uf-muted">{{ scheduleText(p) }} · {{ p.is_public ? 'public' : 'internal' }}{{ p.is_active ? '' : ' · inactive' }}</span>
                </li>
              } @empty { <li class="uf-muted">No payment plans yet.</li> }
            </ul>
            <h4>{{ plan.id ? 'Edit ' + plan.name : 'New payment plan' }}</h4>
            <div class="uf-row">
              <mat-form-field appearance="outline"><mat-label>Name</mat-label><input matInput [(ngModel)]="plan.name" name="pname" /></mat-form-field>
              <mat-slide-toggle [(ngModel)]="plan.is_public" name="ppub">Public</mat-slide-toggle>
              <mat-slide-toggle [(ngModel)]="plan.is_active" name="pact">Active</mat-slide-toggle>
            </div>
            <mat-form-field appearance="outline" class="uf-wide"><mat-label>Description</mat-label><textarea matInput rows="2" [(ngModel)]="plan.description" name="pdesc"></textarea></mat-form-field>
            @for (m of plan.schedule; track $index; let i = $index) {
              <div class="uf-row">
                <mat-form-field appearance="outline"><mat-label>Milestone</mat-label><input matInput [(ngModel)]="m.label" [name]="'ml' + i" /></mat-form-field>
                <mat-form-field appearance="outline" class="uf-num"><mat-label>%</mat-label><input matInput type="number" [(ngModel)]="m.percent" [name]="'mp' + i" /></mat-form-field>
                <mat-form-field appearance="outline"><mat-label>When</mat-label><input matInput [(ngModel)]="m.due" [name]="'md' + i" placeholder="on signing" /></mat-form-field>
                <button mat-button (click)="plan.schedule.splice(i, 1)">Remove</button>
              </div>
            }
            <div class="uf-row">
              <button mat-button (click)="plan.schedule.push({ label: '', percent: null, due: '' })">Add milestone</button>
              <span [class.uf-error]="total() !== 100 && plan.schedule.length > 0" class="uf-muted">total {{ total() }} %</span>
            </div>
          </mat-card-content>
          <mat-card-actions>
            <button mat-flat-button [disabled]="busy() || !plan.name" (click)="savePlan()">{{ plan.id ? 'Save plan' : 'Create plan' }}</button>
            @if (plan.id) { <button mat-button (click)="plan = blankPlan()">New plan</button> }
          </mat-card-actions>
        </mat-card>

        <mat-card appearance="outlined">
          <mat-card-header><mat-card-title>Promotions</mat-card-title></mat-card-header>
          <mat-card-content>
            <ul class="uf-list">
              @for (p of promotions(); track p.id) {
                <li>
                  <button mat-button (click)="editPromo(p)">{{ p.name }}</button>
                  <span class="uf-muted">{{ p.kind }}@if (p.value) { {{ p.value }} } @if (p.valid_to) { · until {{ p.valid_to }} } · {{ p.is_public ? 'public' : 'internal' }}{{ p.is_active ? '' : ' · inactive' }}</span>
                </li>
              } @empty { <li class="uf-muted">No promotions yet.</li> }
            </ul>
            <h4>{{ promo.id ? 'Edit ' + promo.name : 'New promotion' }}</h4>
            <div class="uf-row">
              <mat-form-field appearance="outline"><mat-label>Name</mat-label><input matInput [(ngModel)]="promo.name" name="prname" /></mat-form-field>
              <mat-form-field appearance="outline"><mat-label>Kind</mat-label>
                <mat-select [(ngModel)]="promo.kind" name="prkind">
                  <mat-option value="discount_percent">Discount %</mat-option><mat-option value="discount_amount">Discount amount</mat-option>
                  <mat-option value="gift">Gift</mat-option><mat-option value="financing">Financing</mat-option><mat-option value="other">Other</mat-option>
                </mat-select>
              </mat-form-field>
              <mat-form-field appearance="outline" class="uf-num"><mat-label>Value</mat-label><input matInput [(ngModel)]="promo.value" name="prval" /></mat-form-field>
            </div>
            <div class="uf-row">
              <mat-form-field appearance="outline"><mat-label>Valid from</mat-label><input matInput type="date" [(ngModel)]="promo.valid_from" name="prfrom" /></mat-form-field>
              <mat-form-field appearance="outline"><mat-label>Valid to</mat-label><input matInput type="date" [(ngModel)]="promo.valid_to" name="prto" /></mat-form-field>
              <mat-slide-toggle [(ngModel)]="promo.is_public" name="prpub">Public</mat-slide-toggle>
              <mat-slide-toggle [(ngModel)]="promo.is_active" name="pract">Active</mat-slide-toggle>
            </div>
            <mat-form-field appearance="outline" class="uf-wide"><mat-label>Terms</mat-label><textarea matInput rows="2" [(ngModel)]="promo.terms" name="prterms"></textarea></mat-form-field>
          </mat-card-content>
          <mat-card-actions>
            <button mat-flat-button [disabled]="busy() || !promo.name" (click)="savePromo()">{{ promo.id ? 'Save promotion' : 'Create promotion' }}</button>
            @if (promo.id) { <button mat-button (click)="promo = blankPromo()">New promotion</button> }
          </mat-card-actions>
        </mat-card>
      </div>
    </div>
  `,
  styles: `
    .uf-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .uf-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; }
    @media (max-width: 1100px) { .uf-grid2 { grid-template-columns: 1fr; } }
    .uf-num { width: 110px; }
    .uf-wide { width: 100%; }
    .uf-list { list-style: none; padding: 0; }
  `,
})
export class SalesSetupPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly settings = signal<SalesSettingsOut | null>(null);
  readonly areaDefs = signal<{ key: string; label?: string }[]>([]);
  readonly plans = signal<PaymentPlanOut[]>([]);
  readonly promotions = signal<PromotionOut[]>([]);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly publicFields = PUBLIC_FIELDS;
  priceAreaType = '';
  publicDefaults: Record<string, boolean> = {};
  plan: PlanForm = this.blankPlan();
  promo: PromoForm = this.blankPromo();

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  blankPlan(): PlanForm {
    return { id: null, version: 0, name: '', description: '', schedule: [{ label: 'Deposit', percent: 30, due: 'on signing' }, { label: 'Balance', percent: 70, due: 'on completion' }], is_public: true, is_active: true };
  }

  blankPromo(): PromoForm {
    return { id: null, version: 0, name: '', kind: 'other', value: '', terms: '', valid_from: '', valid_to: '', is_public: true, is_active: true };
  }

  total(): number {
    return Math.round(this.plan.schedule.reduce((a, m) => a + Number(m.percent ?? 0), 0) * 100) / 100;
  }

  scheduleText(p: PaymentPlanOut): string {
    return (p.schedule as { label: string; percent: string }[]).map((m) => `${m.label} ${Number(m.percent)}%`).join(' / ') || 'no milestones';
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
    return this.run(() => this.api.putSalesSettings(this.tenantId(), this.projectId(), { price_area_type: this.priceAreaType, public_fields: this.publicDefaults, version: s.project_version }));
  }

  editPlan(p: PaymentPlanOut): void {
    const sched = p.schedule as { label: string; percent: string; due?: string | null }[];
    this.plan = { id: p.id, version: p.version, name: p.name, description: p.description ?? '', schedule: sched.map((m) => ({ label: m.label, percent: Number(m.percent), due: m.due ?? '' })), is_public: p.is_public, is_active: p.is_active };
  }

  savePlan(): Promise<void> {
    const p = this.plan;
    const schedule = p.schedule.filter((m) => m.label).map((m) => ({ label: m.label, percent: String(m.percent ?? 0), due: m.due || null }));
    const body = { name: p.name, description: p.description || null, schedule, is_public: p.is_public, is_active: p.is_active };
    return this.run(async () => {
      if (p.id) await this.api.updatePaymentPlan(this.tenantId(), p.id, { ...body, version: p.version });
      else await this.api.createPaymentPlan(this.tenantId(), this.projectId(), body);
      this.plan = this.blankPlan();
    });
  }

  editPromo(p: PromotionOut): void {
    this.promo = { id: p.id, version: p.version, name: p.name, kind: p.kind as PromotionKind, value: p.value ?? '', terms: p.terms ?? '', valid_from: p.valid_from ?? '', valid_to: p.valid_to ?? '', is_public: p.is_public, is_active: p.is_active };
  }

  savePromo(): Promise<void> {
    const p = this.promo;
    const body = { name: p.name, kind: p.kind, value: p.value ? String(p.value) : null, terms: p.terms || null, valid_from: p.valid_from || null, valid_to: p.valid_to || null, is_public: p.is_public, is_active: p.is_active };
    return this.run(async () => {
      if (p.id) await this.api.updatePromotion(this.tenantId(), p.id, { ...body, version: p.version });
      else await this.api.createPromotion(this.tenantId(), this.projectId(), body);
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
