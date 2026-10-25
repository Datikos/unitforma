import { Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { StatusChipComponent, UF_ICONS } from 'ui';
import { PORTAL_GUIDE } from '../guide/portal-guide';

/** Buyer-facing guide: how to find a unit, what the colours mean, what "indicative" means. */
@Component({
  selector: 'uf-how-to-use-page',
  imports: [RouterLink, NgIcon, StatusChipComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <nav class="uf-crumbs">
      <a routerLink="/">Home</a> <ng-icon name="lucideChevronRight" />
      <span>How to use this portal</span>
    </nav>
    <h1>How to use this portal</h1>
    <p class="uf-muted lead">
      Browse buildings, floors and units; filter, compare and save; ask the sales team. The colours
      below are the same everywhere.
    </p>
    <p class="uf-chips legend">
      <uf-status-chip domain="availability" value="available" size="lg" />
      <uf-status-chip domain="availability" value="reserved" size="lg" />
      <uf-status-chip domain="availability" value="sold" size="lg" />
      <uf-status-chip domain="availability" value="withdrawn" size="lg" />
    </p>
    <div class="uf-grid sections">
      @for (s of sections; track s.title) {
        <section class="uf-card sec">
          <h2><ng-icon [name]="s.icon" /> {{ s.title }}</h2>
          <p>{{ s.text }}</p>
          @if (s.points?.length) {
            <ul>
              @for (p of s.points; track p) {
                <li>{{ p }}</li>
              }
            </ul>
          }
        </section>
      }
    </div>
  `,
  styles: `
    .lead {
      max-width: 60ch;
    }
    .legend {
      margin: 0.5rem 0 1rem;
    }
    .sections {
      grid-template-columns: repeat(auto-fill, minmax(min(100%, 320px), 1fr));
    }
    .sec {
      display: grid;
      gap: 0.5rem;
      align-content: start;
    }
    .sec h2 {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: 1.1rem;
      margin: 0;
    }
    .sec h2 ng-icon {
      color: var(--uf-primary);
    }
    .sec p,
    .sec ul {
      margin: 0;
    }
    .sec ul {
      padding-left: 1.1rem;
      color: var(--uf-muted);
      font-size: 0.95rem;
    }
  `,
})
export class HowToUsePage {
  readonly sections = PORTAL_GUIDE;
}
