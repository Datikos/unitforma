import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { UF_ICONS } from './icons';
import { StatusDomain, statusOf } from './status';

/** One status, one chip: tone colour, icon and label from the shared vocabulary. */
@Component({
  selector: 'uf-status-chip',
  imports: [NgIcon],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <span
      class="uf-chip uf-tone-{{ view().tone }}"
      [class.uf-chip--lg]="size() === 'lg'"
      [title]="tooltip() ?? view().label"
    >
      <ng-icon
        [name]="view().icon"
        [class.uf-spin]="view().icon === 'lucideLoaderCircle'"
        aria-hidden="true"
      />{{ label() ?? view().label }}
    </span>
  `,
})
export class StatusChipComponent {
  readonly domain = input.required<StatusDomain>();
  readonly value = input<string | null | undefined>();
  /** Overrides the vocabulary label (for counts: "3 open"). */
  readonly label = input<string | null>(null);
  readonly tooltip = input<string | null>(null);
  readonly size = input<'md' | 'lg'>('md');
  protected readonly view = computed(() => statusOf(this.domain(), this.value()));
}
