import { ChangeDetectionStrategy, Component, computed, input, signal } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { UF_ICONS } from './icons';

/**
 * A titled block that can collapse. The header carries a summary of what is inside
 * ("Timeouts · connect 500 ms · read 2 s") and a count, so a closed section still tells its state.
 * The open state is remembered per `storageKey` in localStorage (per browser convenience).
 */
@Component({
  selector: 'uf-section-card',
  imports: [NgIcon],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <section class="sc" [class.sc--closed]="!isOpen()" [class.sc--flush]="flush()">
      <header class="sc__head">
        @if (collapsible()) {
          <button
            type="button"
            class="sc__toggle"
            (click)="toggle()"
            [attr.aria-expanded]="isOpen()"
            [attr.aria-controls]="id"
          >
            <ng-icon
              [name]="isOpen() ? 'lucideChevronDown' : 'lucideChevronRight'"
              aria-hidden="true"
            />
            @if (icon()) {
              <ng-icon [name]="icon()!" class="sc__icon" aria-hidden="true" />
            }
            <span class="sc__title">{{ title() }}</span>
            @if (count() !== null) {
              <span class="sc__count">{{ count() }}</span>
            }
            @if (summary()) {
              <span class="sc__summary">{{ summary() }}</span>
            }
          </button>
        } @else {
          <div class="sc__toggle sc__toggle--static">
            @if (icon()) {
              <ng-icon [name]="icon()!" class="sc__icon" aria-hidden="true" />
            }
            <span class="sc__title">{{ title() }}</span>
            @if (count() !== null) {
              <span class="sc__count">{{ count() }}</span>
            }
            @if (summary()) {
              <span class="sc__summary">{{ summary() }}</span>
            }
          </div>
        }
        <div class="sc__actions"><ng-content select="[actions]" /></div>
      </header>
      @if (isOpen()) {
        <div class="sc__body" [id]="id"><ng-content /></div>
      }
    </section>
  `,
  styles: `
    .sc {
      background: var(--uf-surface);
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius);
      box-shadow: var(--uf-shadow);
    }
    .sc__head {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.45rem 0.75rem 0.45rem 0.5rem;
      min-height: 3rem;
    }
    .sc--closed .sc__head {
      border-bottom: 0;
    }
    .sc__toggle {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      flex: 1 1 auto;
      min-width: 0;
      border: 0;
      background: none;
      font: inherit;
      color: inherit;
      text-align: left;
      padding: 0.25rem 0.5rem;
      border-radius: var(--uf-radius-sm);
      cursor: pointer;
    }
    .sc__toggle--static {
      cursor: default;
    }
    button.sc__toggle:hover {
      background: var(--uf-surface-2);
    }
    .sc__icon {
      color: var(--uf-primary);
    }
    .sc__title {
      font-weight: 600;
      font-size: 1rem;
    }
    .sc__count {
      font-size: 0.75rem;
      font-weight: 700;
      padding: 0 0.5rem;
      border-radius: var(--uf-radius-pill);
      background: var(--uf-tone-neutral-bg);
      color: var(--uf-tone-neutral-fg);
      border: 1px solid var(--uf-tone-neutral-border);
      line-height: 1.5;
    }
    .sc__summary {
      color: var(--uf-muted);
      font-size: 0.85rem;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .sc__actions {
      display: flex;
      gap: 0.25rem;
      align-items: center;
      flex: none;
    }
    .sc__body {
      padding: 0.25rem 0.9rem 0.75rem;
      border-top: 1px solid var(--uf-border);
      padding-top: 0.75rem;
      display: grid;
      gap: 0.75rem;
    }
    .sc--flush .sc__body {
      padding: 0;
    }
  `,
})
export class SectionCardComponent {
  private static seq = 0;
  readonly id = `uf-sc-${++SectionCardComponent.seq}`;
  readonly title = input.required<string>();
  readonly icon = input<string | null>(null);
  readonly summary = input<string | null>(null);
  readonly count = input<number | string | null>(null);
  readonly collapsible = input(true);
  readonly open = input(true);
  /** Remember the open state under this key (localStorage, per browser). */
  readonly storageKey = input<string | null>(null);
  /** No inner padding (for tables and grids that fill the card). */
  readonly flush = input(false);
  private readonly manual = signal<boolean | null>(null);
  protected readonly isOpen = computed(() => {
    if (!this.collapsible()) return true;
    const m = this.manual();
    if (m !== null) return m;
    const k = this.storageKey();
    if (k) {
      try {
        const saved = localStorage.getItem(`uf:section:${k}`);
        if (saved === '0') return false;
        if (saved === '1') return true;
      } catch {
        /* storage unavailable: fall back to the input */
      }
    }
    return this.open();
  });

  toggle(): void {
    const next = !this.isOpen();
    this.manual.set(next);
    const k = this.storageKey();
    if (k) {
      try {
        localStorage.setItem(`uf:section:${k}`, next ? '1' : '0');
      } catch {
        /* ignore */
      }
    }
  }
}
