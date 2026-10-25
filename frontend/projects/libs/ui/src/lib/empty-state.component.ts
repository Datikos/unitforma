import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { UF_ICONS } from './icons';

/** An empty list says what to do next, never a blank table. */
@Component({
  selector: 'uf-empty-state',
  imports: [NgIcon],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="es" [class.es--compact]="compact()">
      <ng-icon [name]="icon()" class="es__icon" aria-hidden="true" />
      <p class="es__title">{{ title() }}</p>
      @if (text()) {
        <p class="es__text">{{ text() }}</p>
      }
      <div class="es__actions"><ng-content /></div>
    </div>
  `,
  styles: `
    .es {
      display: grid;
      min-width: 0;
      max-width: 100%;
      justify-items: center;
      text-align: center;
      gap: 0.35rem;
      padding: 2.5rem 1rem;
      border: 1px dashed var(--uf-border-strong);
      border-radius: var(--uf-radius);
      background: var(--uf-surface-2);
      color: var(--uf-text);
    }
    .es--compact {
      padding: 1.25rem 1rem;
    }
    .es__icon {
      font-size: 2rem;
      color: var(--uf-muted);
    }
    .es__title {
      margin: 0.25rem 0 0;
      font-weight: 600;
    }
    .es__text {
      margin: 0;
      color: var(--uf-muted);
      max-width: min(48ch, 100%);
      overflow-wrap: anywhere;
    }
    .es__actions {
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
      justify-content: center;
      margin-top: 0.5rem;
    }
    .es__actions:empty {
      display: none;
    }
  `,
})
export class EmptyStateComponent {
  readonly icon = input<string>('lucideCircleDashed');
  readonly title = input.required<string>();
  readonly text = input<string | null>(null);
  readonly compact = input(false);
}
