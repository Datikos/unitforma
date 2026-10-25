import { ChangeDetectionStrategy, Component, computed, inject, output } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { UF_ICONS } from 'ui';
import { RouteInfo } from '../core/route-info';
import { GUIDE, GuideKey } from './guide-content';
import { GuideEntryComponent } from './guide-entry.component';

/** Right-hand drawer: the guide entry of the page that is open. */
@Component({
  selector: 'uf-guide-drawer',
  imports: [RouterLink, NgIcon, GuideEntryComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="gd">
      <header class="gd__head">
        <span class="gd__kicker"
          ><ng-icon name="lucideBookOpen" aria-hidden="true" /> About this page</span
        >
        <button
          type="button"
          class="nav__icon-btn gd__close"
          (click)="closed.emit()"
          aria-label="Close guide"
        >
          <ng-icon name="lucideX" />
        </button>
      </header>
      @if (entry(); as e) {
        <uf-guide-entry [entry]="e" />
      } @else {
        <p class="uf-muted">This page has no guide entry yet.</p>
      }
      <p class="gd__all">
        <a routerLink="/guide" (click)="closed.emit()"
          >Open the full guide <ng-icon name="lucideArrowRight" aria-hidden="true"
        /></a>
      </p>
    </div>
  `,
  styles: `
    .gd {
      padding: 1rem 1.25rem 1.5rem;
      display: grid;
      gap: 1rem;
      width: min(92vw, 420px);
    }
    .gd__head {
      display: flex;
      align-items: center;
      justify-content: space-between;
    }
    .gd__kicker {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--uf-muted);
      font-weight: 600;
    }
    .gd__close {
      color: var(--uf-muted);
    }
    .gd__all {
      margin: 0;
      font-size: 0.9rem;
    }
    .gd__all a {
      display: inline-flex;
      align-items: center;
      gap: 0.3rem;
      color: var(--uf-primary);
      text-decoration: none;
    }
  `,
})
export class GuideDrawerComponent {
  private readonly route = inject(RouteInfo);
  readonly closed = output<void>();
  readonly key = computed(() => this.route.str('guide') as GuideKey | null);
  readonly entry = computed(() => {
    const k = this.key();
    return k ? GUIDE[k] : null;
  });
}
