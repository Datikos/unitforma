import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { SectionCardComponent, StatusChipComponent, UF_ICONS, labelOf } from 'ui';
import { measuredArea, printedArea } from './sheet.model';
import { SheetStore } from './sheet.store';

@Component({
  selector: 'uf-sheet-units-table',
  imports: [MatButtonModule, NgIcon, SectionCardComponent, StatusChipComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <uf-section-card
      title="Units on this sheet"
      icon="lucideLayers"
      [count]="store.units().length"
      [summary]="
        store.draftCount() ? store.draftCount() + ' draft, not yet approved' : 'all approved'
      "
      [flush]="true"
      storageKey="sheet-units"
    >
      <table class="uf-plain">
        <thead>
          <tr>
            <th>Code</th>
            <th>Type</th>
            <th>Status</th>
            <th>Source</th>
            <th class="uf-num">Measured</th>
            <th class="uf-num">Printed</th>
            <th></th>
          </tr>
        </thead>
        <tbody>
          @for (u of store.units(); track u.id) {
            <tr
              [class.is-selected]="u.id === store.selectedUnitId()"
              (click)="store.selectedUnitId.set(u.id)"
            >
              <td>
                <strong>{{ u.code }}</strong>
              </td>
              <td>{{ labelOf('unit_type', u.unit_type) }}</td>
              <td class="chips">
                <uf-status-chip domain="unit.lifecycle" [value]="u.lifecycle_status" />
                <uf-status-chip domain="unit.verification" [value]="u.verification_status" />
              </td>
              <td class="uf-muted">
                {{
                  store.sourceOf(u) === 'vector_suggest'
                    ? 'suggested outline'
                    : store.sourceOf(u) || '—'
                }}
              </td>
              <td class="uf-num">
                @if (measured(u); as a) {
                  {{ a.value_m2 }} m²
                  <span class="uf-muted uf-small">{{ a.verification_status }}</span>
                } @else {
                  —
                }
              </td>
              <td class="uf-num">
                @if (printed(u); as a) {
                  {{ a.value_m2 }} m²
                  <span class="uf-muted uf-small">{{ a.verification_status }}</span>
                } @else {
                  —
                }
              </td>
              <td class="actions">
                <button mat-button (click)="store.relabel(u); $event.stopPropagation()">
                  <ng-icon name="lucideTag" /> Relabel
                </button>
                <button mat-button (click)="store.remove(u); $event.stopPropagation()">
                  <ng-icon name="lucideCircleX" /> Remove
                </button>
              </td>
            </tr>
          } @empty {
            <tr>
              <td colspan="7" class="uf-muted empty">
                No units on this sheet yet. Use Suggest boundaries, or Draw unit and click the
                corners.
              </td>
            </tr>
          }
        </tbody>
      </table>
    </uf-section-card>
  `,
  styles: `
    tr {
      cursor: pointer;
    }
    tr.is-selected td {
      background: var(--uf-tone-warning-bg);
    }
    .chips {
      display: flex;
      gap: 0.25rem;
      flex-wrap: wrap;
    }
    .actions {
      white-space: nowrap;
      text-align: right;
    }
    .empty {
      padding: 1.25rem;
      text-align: center;
    }
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.2rem;
    }
  `,
})
export class SheetUnitsTableComponent {
  protected readonly store = inject(SheetStore);
  readonly labelOf = labelOf;
  printed = printedArea;
  measured = measuredArea;
}
