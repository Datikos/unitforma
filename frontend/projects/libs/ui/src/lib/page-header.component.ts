import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { UF_ICONS } from './icons';
import { StatusDomain } from './status';
import { StatusChipComponent } from './status-chip.component';

/** A headline fact: plain text, or a status rendered as a chip. */
export interface HeaderFact {
  label?: string;
  value?: string | number | null;
  domain?: StatusDomain;
  status?: string | null;
  icon?: string;
}

/**
 * Page header: kicker, title, headline facts ("v5 · approver · 1h ago"), then the actions.
 * Facts come first because a new operator must read the state without scrolling.
 */
@Component({
  selector: 'uf-page-header',
  imports: [NgIcon, StatusChipComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <header class="ph">
      <div class="ph__main">
        @if (kicker()) {
          <p class="ph__kicker">{{ kicker() }}</p>
        }
        <h1 class="ph__title">
          @if (icon()) {
            <ng-icon [name]="icon()!" class="ph__icon" aria-hidden="true" />
          }
          {{ title() }}
        </h1>
        @if (facts().length) {
          <ul class="ph__facts">
            @for (f of facts(); track $index) {
              <li>
                @if (f.domain) {
                  <uf-status-chip
                    [domain]="f.domain"
                    [value]="f.status"
                    [label]="f.value === undefined || f.value === null ? null : '' + f.value"
                  />
                } @else {
                  @if (f.icon) {
                    <ng-icon [name]="f.icon" aria-hidden="true" />
                  }
                  @if (f.label) {
                    <span class="ph__label">{{ f.label }}</span>
                  }
                  <span class="ph__value">{{ f.value ?? '—' }}</span>
                }
              </li>
            }
          </ul>
        }
        <ng-content select="[subtitle]" />
      </div>
      <div class="ph__actions"><ng-content select="[actions]" /></div>
    </header>
    <ng-content />
  `,
  styles: `
    .ph {
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 1rem;
      flex-wrap: wrap;
    }
    .ph__main {
      display: grid;
      gap: 0.35rem;
      min-width: 0;
      /* the facts wrap under the title; the actions keep the top-right corner */
      flex: 1 1 20rem;
    }
    .ph__kicker {
      margin: 0;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--uf-muted);
      font-weight: 600;
    }
    .ph__title {
      margin: 0;
      font-size: 1.5rem;
      font-weight: 700;
      letter-spacing: -0.01em;
      display: flex;
      align-items: center;
      gap: 0.5rem;
      line-height: 1.2;
      overflow-wrap: anywhere;
    }
    .ph__icon {
      color: var(--uf-primary);
    }
    .ph__facts {
      display: flex;
      flex-wrap: wrap;
      gap: 0.4rem 1rem;
      margin: 0;
      padding: 0;
      list-style: none;
      align-items: center;
      font-size: 0.9rem;
      color: var(--uf-muted);
    }
    .ph__facts li {
      display: inline-flex;
      align-items: center;
      gap: 0.35rem;
    }
    .ph__label::after {
      content: ':';
    }
    .ph__value {
      color: var(--uf-text);
      font-weight: 500;
    }
    .ph__actions {
      display: flex;
      gap: 0.5rem;
      flex-wrap: wrap;
      align-items: center;
      justify-content: flex-end;
    }
    .ph__actions:empty {
      display: none;
    }
  `,
})
export class PageHeaderComponent {
  readonly title = input.required<string>();
  readonly kicker = input<string | null>(null);
  readonly icon = input<string | null>(null);
  readonly facts = input<HeaderFact[]>([]);
}
