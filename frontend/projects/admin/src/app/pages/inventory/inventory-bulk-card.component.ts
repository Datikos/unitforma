import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { SectionCardComponent, UF_ICONS, labelOf } from 'ui';
import { AVAILABILITY } from '../../sales/sales-format';
import { BulkForm, KEEP, NONE } from './inventory.model';
import { InventoryStore } from './inventory.store';

/** Bulk edit of the selected rows: set fields, preview the count, apply; publication flags. */
@Component({
  selector: 'uf-inventory-bulk-card',
  imports: [
    FormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    NgIcon,
    SectionCardComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <uf-section-card
      [title]="'Bulk edit · ' + store.selected().length + ' selected'"
      icon="lucideListFilter"
      [collapsible]="false"
    >
      <div actions class="uf-actions">
        <button mat-button [disabled]="store.busy()" (click)="store.setPublication('published')">
          <ng-icon name="lucideGlobe" /> Make public
        </button>
        <button mat-button [disabled]="store.busy()" (click)="store.setPublication('hidden')">
          <ng-icon name="lucideLink" /> Link only
        </button>
        <button mat-button [disabled]="store.busy()" (click)="store.setPublication('unpublished')">
          <ng-icon name="lucideEyeOff" /> Withdraw
        </button>
        <button mat-button (click)="store.clearSelection()">Clear selection</button>
      </div>
      <div class="uf-form-row">
        <mat-form-field appearance="outline"
          ><mat-label>Availability</mat-label>
          <mat-select
            [ngModel]="b.availability"
            (ngModelChange)="set('availability', $event)"
            name="bAvail"
          >
            <mat-option [value]="KEEP">— keep —</mat-option>
            @for (a of availability; track a) {
              <mat-option [value]="a">{{ label(a) }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field appearance="outline"
          ><mat-label>Reason</mat-label
          ><input
            matInput
            [ngModel]="b.reason"
            (ngModelChange)="set('reason', $event)"
            name="bReason"
            placeholder="required to change sold units"
        /></mat-form-field>
        <mat-form-field appearance="outline" class="num"
          ><mat-label>Set price</mat-label
          ><input
            matInput
            [ngModel]="b.price"
            (ngModelChange)="set('price', $event)"
            name="bPrice"
            placeholder="keep"
        /></mat-form-field>
        <mat-form-field appearance="outline" class="num"
          ><mat-label>or adjust %</mat-label
          ><input
            matInput
            type="number"
            [ngModel]="b.adjust"
            (ngModelChange)="set('adjust', $event)"
            name="bAdjust"
        /></mat-form-field>
        <mat-form-field appearance="outline" class="ccy"
          ><mat-label>Currency</mat-label
          ><input
            matInput
            [ngModel]="b.currency"
            (ngModelChange)="set('currency', $event)"
            name="bCcy"
            placeholder="keep"
            maxlength="3"
        /></mat-form-field>
        <mat-form-field appearance="outline"
          ><mat-label>Payment plan</mat-label>
          <mat-select [ngModel]="b.plan" (ngModelChange)="set('plan', $event)" name="bPlan">
            <mat-option [value]="KEEP">— keep —</mat-option>
            <mat-option [value]="NONE">— none —</mat-option>
            @for (p of store.plans(); track p.id) {
              <mat-option [value]="p.id">{{ p.name }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-form-field appearance="outline"
          ><mat-label>Promotions</mat-label>
          <mat-select
            [ngModel]="b.promotions"
            (ngModelChange)="set('promotions', $event)"
            name="bPromo"
            multiple
            [disabled]="!b.setPromotions"
          >
            @for (p of store.promotions(); track p.id) {
              <mat-option [value]="p.id">{{ p.name }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-checkbox
          [ngModel]="b.setPromotions"
          (ngModelChange)="set('setPromotions', $event)"
          name="bSetPromo"
          >Replace promotions</mat-checkbox
        >
        <mat-checkbox
          [ngModel]="b.confirmZero"
          (ngModelChange)="set('confirmZero', $event)"
          name="bZero"
          >Allow price 0</mat-checkbox
        >
      </div>
      <div class="uf-actions">
        <button mat-stroked-button [disabled]="store.busy()" (click)="store.runBulk(true)">
          <ng-icon name="lucideFlaskConical" /> Preview
        </button>
        <button
          mat-flat-button
          [disabled]="store.busy() || !store.preview()"
          (click)="store.runBulk(false)"
        >
          Apply to {{ store.selected().length }} unit(s)
        </button>
        <span class="uf-hint">Preview first: it lists what would change and writes nothing.</span>
      </div>
      @if (store.preview(); as p) {
        <div class="preview">
          <p class="uf-small">
            <strong>{{ p.changed_units }}</strong> of {{ p.units.length }} unit(s) would change.
          </p>
          <table class="uf-plain">
            <thead>
              <tr>
                <th>Unit</th>
                <th>Changes</th>
              </tr>
            </thead>
            <tbody>
              @for (u of p.units; track u.unit_id) {
                <tr>
                  <td>{{ u.code }}</td>
                  <td>
                    @for (c of u.changes; track $index) {
                      <span class="chg"
                        >{{ c['field'] }}: <s>{{ c['old'] ?? '∅' }}</s> →
                        <strong>{{ c['new'] ?? '∅' }}</strong></span
                      >
                    } @empty {
                      <span class="uf-muted">no change</span>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }
    </uf-section-card>
  `,
  styles: `
    .num {
      width: 130px;
    }
    .ccy {
      width: 100px;
    }
    .preview {
      max-height: 280px;
      overflow: auto;
    }
    .chg {
      display: inline-block;
      margin-right: 0.75rem;
    }
    ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class InventoryBulkCardComponent {
  protected readonly store = inject(InventoryStore);
  readonly availability = AVAILABILITY;
  readonly KEEP = KEEP;
  readonly NONE = NONE;
  protected get b(): BulkForm {
    return this.store.bulk();
  }
  label(a: string): string {
    return labelOf('availability', a);
  }
  set<K extends keyof BulkForm>(key: K, value: BulkForm[K]): void {
    this.store.bulk.update((b) => ({ ...b, [key]: value }));
  }
}
