import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { SectionCardComponent, UF_ICONS, ago, whenShort } from 'ui';
import { TimelineEntry } from './unit-sales.model';

@Component({
  selector: 'uf-unit-history',
  imports: [NgIcon, SectionCardComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <uf-section-card
      title="History"
      icon="lucideHistory"
      [count]="entries().length"
      [summary]="entries()[0] ? 'last change ' + ago(entries()[0].at) : 'no changes yet'"
      storageKey="unit-history"
      [open]="false"
    >
      <ul class="uf-timeline">
        @for (e of entries(); track $index) {
          <li [class]="'is-' + e.tone">
            <div class="uf-timeline__when">{{ when(e.at) }} · {{ ago(e.at) }}</div>
            <div>
              <ng-icon [name]="e.icon" class="ic" aria-hidden="true" /> {{ e.text }}
              @if (e.reason) {
                <span class="uf-muted">— {{ e.reason }}</span>
              }
            </div>
          </li>
        } @empty {
          <li class="uf-muted">No changes yet.</li>
        }
      </ul>
    </uf-section-card>
  `,
  styles: `
    .ic {
      vertical-align: -0.15em;
      color: var(--uf-muted);
    }
  `,
})
export class UnitHistoryComponent {
  readonly entries = input.required<TimelineEntry[]>();
  when = whenShort;
  ago = ago;
}
