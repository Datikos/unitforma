import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { UF_ICONS } from 'ui';
import { showValue } from './inventory.model';
import { InventoryStore } from './inventory.store';

/** "Changed by someone else" (409): both values side by side, apply mine or keep theirs. */
@Component({
  selector: 'uf-inventory-conflict-card',
  imports: [MatButtonModule, NgIcon],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @if (store.conflict(); as c) {
      <div class="uf-alert uf-alert--warning" role="alert">
        <ng-icon name="lucideTriangleAlert" />
        <div class="body">
          <strong>{{ c.code }} was changed by someone else</strong> while you were editing.
          <table class="uf-plain diff">
            <thead>
              <tr>
                <th>Field</th>
                <th>Yours</th>
                <th>Current</th>
              </tr>
            </thead>
            <tbody>
              @for (k of store.conflictKeys(); track k) {
                <tr>
                  <td>{{ k }}</td>
                  <td>
                    <code>{{ show(c.mine, k) }}</code>
                  </td>
                  <td>
                    <code>{{ show(c.current, k) }}</code>
                  </td>
                </tr>
              }
            </tbody>
          </table>
          <div class="uf-actions">
            <button mat-flat-button (click)="store.reapply(c)">
              Apply mine on top of the current version
            </button>
            <button mat-button (click)="store.conflict.set(null)">Keep the current values</button>
          </div>
        </div>
      </div>
    }
  `,
  styles: `
    .body {
      display: grid;
      gap: 0.5rem;
      flex: 1;
    }
    .diff {
      max-width: 48rem;
      background: var(--uf-surface);
      border-radius: var(--uf-radius-sm);
    }
  `,
})
export class InventoryConflictCardComponent {
  protected readonly store = inject(InventoryStore);
  show = showValue;
}
