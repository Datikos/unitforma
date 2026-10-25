import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { StatusDomain } from './status';
import { StatusChipComponent } from './status-chip.component';

export interface Fact {
  label: string;
  value?: string | number | null;
  unit?: string;
  domain?: StatusDomain;
  status?: string | null;
  /** Mark the row as holding a saved (non-default) value even if the value is falsy. */
  set?: boolean;
}

/** Key / value grid. Rows with a value get a green left mark so "what is set" is visible at once. */
@Component({
  selector: 'uf-facts',
  imports: [StatusChipComponent],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <dl class="uf-facts">
      @for (f of facts(); track f.label) {
        <div [class.is-set]="isSet(f)">
          <dt>{{ f.label }}</dt>
          <dd [class.is-empty]="!isSet(f)">
            @if (f.domain) {
              <uf-status-chip [domain]="f.domain" [value]="f.status" />
            } @else if (isSet(f)) {
              {{ f.value }}
              @if (f.unit) {
                <span class="uf-muted"> {{ f.unit }}</span>
              }
            } @else {
              {{ empty() }}
            }
          </dd>
        </div>
      }
    </dl>
  `,
})
export class FactsComponent {
  readonly facts = input.required<Fact[]>();
  readonly empty = input('not set');
  isSet(f: Fact): boolean {
    if (f.set !== undefined) return f.set;
    if (f.domain) return !!f.status;
    return f.value !== null && f.value !== undefined && f.value !== '';
  }
}
