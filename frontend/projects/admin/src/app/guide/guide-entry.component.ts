import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { UF_ICONS } from 'ui';
import { GuideEntry, roleLabel } from './guide-content';

/** One guide entry rendered the same way in the drawer and on the guide page. */
@Component({
  selector: 'uf-guide-entry',
  imports: [NgIcon],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    @let e = entry();
    <article class="ge">
      <h2 class="ge__title"><ng-icon [name]="e.icon" aria-hidden="true" />{{ e.title }}</h2>
      <p class="ge__purpose">{{ e.purpose }}</p>
      <h3>Controls</h3>
      <dl class="ge__controls">
        @for (c of e.controls; track c.name) {
          <dt>{{ c.name }}</dt>
          <dd>{{ c.does }}</dd>
        }
      </dl>
      @if (e.waits) {
        <p class="ge__note"><ng-icon name="lucideClock" aria-hidden="true" /> {{ e.waits }}</p>
      }
      @if (e.result) {
        <p class="ge__note">
          <ng-icon name="lucideArrowRight" aria-hidden="true" /> {{ e.result }}
        </p>
      }
      @if (e.tips?.length) {
        <ul class="ge__tips">
          @for (t of e.tips; track t) {
            <li>{{ t }}</li>
          }
        </ul>
      }
      <p class="ge__roles">
        <span class="uf-muted">Who may change things here:</span>
        @for (r of e.roles; track r) {
          <span class="uf-chip">{{ label(r) }}</span>
        }
      </p>
    </article>
  `,
  styles: `
    .ge {
      display: grid;
      gap: 0.5rem;
    }
    .ge__title {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      margin: 0;
      font-size: 1.15rem;
    }
    .ge__title ng-icon {
      color: var(--uf-primary);
    }
    .ge__purpose {
      margin: 0;
      line-height: 1.5;
    }
    h3 {
      margin: 0.5rem 0 0;
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--uf-muted);
    }
    .ge__controls {
      margin: 0;
      display: grid;
      gap: 0.15rem 0.75rem;
      grid-template-columns: max-content 1fr;
      font-size: 0.925rem;
    }
    .ge__controls dt {
      font-weight: 600;
    }
    .ge__controls dd {
      margin: 0;
      color: var(--uf-muted);
    }
    .ge__note {
      margin: 0;
      display: flex;
      gap: 0.4rem;
      align-items: flex-start;
      font-size: 0.925rem;
    }
    .ge__note ng-icon {
      flex: none;
      margin-top: 0.15rem;
      color: var(--uf-primary);
    }
    .ge__tips {
      margin: 0;
      padding-left: 1.1rem;
      font-size: 0.9rem;
      color: var(--uf-muted);
    }
    .ge__roles {
      margin: 0.25rem 0 0;
      display: flex;
      gap: 0.35rem;
      flex-wrap: wrap;
      align-items: center;
      font-size: 0.85rem;
    }
    @media (max-width: 600px) {
      .ge__controls {
        grid-template-columns: 1fr;
      }
      .ge__controls dd {
        margin-bottom: 0.35rem;
      }
    }
  `,
})
export class GuideEntryComponent {
  readonly entry = input.required<GuideEntry>();
  label = roleLabel;
}
