import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { SectionCardComponent, StatusChipComponent, UF_ICONS } from 'ui';
import { SheetStore } from './sheet.store';

/** Which floors this sheet shows; suggested ones are confirmed in one save. */
@Component({
  selector: 'uf-sheet-floors-card',
  imports: [
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    NgIcon,
    SectionCardComponent,
    StatusChipComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <uf-section-card
      title="Floors on this sheet"
      icon="lucideLayers"
      [count]="store.draft().length"
      [summary]="summary()"
      storageKey="sheet-floors"
    >
      <div actions class="uf-actions">
        @if (store.floorsEdited()) {
          <button mat-button [disabled]="store.busy()" (click)="store.resetFloors()">Undo</button>
        }
        <button
          mat-flat-button
          [disabled]="store.busy() || !store.floorsDirty()"
          (click)="store.saveFloors()"
        >
          {{
            store.hasSuggested() && !store.floorsEdited()
              ? 'Confirm suggested floors'
              : 'Save floors'
          }}
        </button>
      </div>
      <p class="uf-hint">
        A sheet of a stepped or multi-block building can show several floors; give each its region
        so units land on the right floor.
      </p>
      @for (a of store.draft(); track a.floor_id) {
        <div class="row" [class.uf-changed]="a.status === 'suggested'">
          <strong>{{ store.floorLabel(a.floor_id) }}</strong>
          <uf-status-chip domain="sheet.floor" [value]="a.status" />
          <span class="uf-muted uf-small">
            @if (a.marker) {
              marker "{{ a.marker }}" ·
            }
            @if (a.source === 'inherited') {
              from previous revision ·
            }
            {{ a.region ? 'own region' : 'whole sheet' }}
          </span>
          <span class="uf-spacer"></span>
          <button mat-button [disabled]="store.busy()" (click)="store.drawRegion(a.floor_id)">
            <ng-icon name="lucidePenTool" /> {{ a.region ? 'Redraw region' : 'Draw region' }}
          </button>
          @if (a.region) {
            <button mat-button [disabled]="store.busy()" (click)="store.clearRegion(a.floor_id)">
              Whole sheet
            </button>
          }
          <button mat-button [disabled]="store.busy()" (click)="store.removeFloor(a.floor_id)">
            <ng-icon name="lucideX" /> Remove
          </button>
        </div>
      } @empty {
        <p class="uf-muted">
          No floor assigned yet. Pick one below; the worker suggests floors from level markers when
          it finds them.
        </p>
      }
      <div class="uf-form-row">
        <mat-form-field appearance="outline" class="floor" subscriptSizing="dynamic">
          <mat-label>Add floor</mat-label>
          <mat-select [value]="null" (valueChange)="store.addFloor($event)">
            @for (f of store.unassignedFloors(); track f.id) {
              <mat-option [value]="f.id">{{ f.label }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        @if (store.regionTarget(); as rt) {
          <span class="uf-chip uf-tone-warning"
            ><ng-icon name="lucidePenTool" />Drawing region of {{ store.floorLabel(rt) }}: click
            corners, double-click to close</span
          >
        }
      </div>
    </uf-section-card>
  `,
  styles: `
    .row {
      display: flex;
      gap: 0.5rem;
      align-items: center;
      flex-wrap: wrap;
      padding: 0.3rem 0.5rem;
      border-radius: 6px;
    }
    .floor {
      min-width: 240px;
    }
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.2rem;
    }
  `,
})
export class SheetFloorsCardComponent {
  protected readonly store = inject(SheetStore);
  summary(): string {
    const d = this.store.draft();
    if (!d.length) return 'none assigned';
    const s = d.filter((a) => a.status === 'suggested').length;
    return (
      d.map((a) => this.store.floorLabel(a.floor_id).split(' (')[0]).join(', ') +
      (s ? ` · ${s} to confirm` : '')
    );
  }
}
