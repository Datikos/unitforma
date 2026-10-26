import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { MatButtonModule } from '@angular/material/button';
import { RouterLink } from '@angular/router';
import { SetupOut, SetupStepOut, UnitformaApi, problemMessage } from 'api-client';
import { HeaderFact, PageHeaderComponent, StatusChipComponent } from 'ui';

/** The admin screen that completes a step, relative to `projects/:projectId/setup`. */
const SCREEN: Record<string, { label: string; path: string[] }> = {
  documents: { label: 'Documents', path: ['..', 'documents'] },
  overview: { label: 'Overview & structure', path: ['..'] },
  placement: { label: 'Site placement', path: ['..', 'placement'] },
  inventory: { label: 'Inventory & prices', path: ['..', 'inventory'] },
  publish: { label: 'Publish', path: ['..', 'publish'] },
};

/** Setup checklist (ADR-0017 Decision 5): the order of work, computed from the project's data. */
@Component({
  selector: 'uf-setup-page',
  imports: [MatButtonModule, PageHeaderComponent, RouterLink, StatusChipComponent],
  template: `
    <uf-page-header
      title="Setup checklist"
      icon="lucideClipboardCheck"
      kicker="The order of work for this project"
      [facts]="facts()"
    />
    @if (error(); as e) {
      <div class="uf-alert uf-alert--bad" role="alert">{{ e }}</div>
    }
    @if (setup(); as s) {
      <div
        class="progress"
        role="progressbar"
        [attr.aria-valuenow]="s.done"
        [attr.aria-valuemin]="0"
        [attr.aria-valuemax]="s.total"
      >
        <span [style.width.%]="(100 * s.done) / s.total"></span>
      </div>
      <p class="uf-muted">
        {{ s.done }} of {{ s.total }} steps done · {{ optionalLeft() }} optional step(s) open.
        "Done" is computed from the project's data, never ticked by hand: open a step's screen, come
        back, and the list has moved on.
      </p>
      <ol class="steps">
        @for (st of s.steps; track st.key; let i = $index) {
          <li
            class="step"
            [class.step--done]="st.status === 'done'"
            [class.step--attention]="st.status === 'attention'"
          >
            <span class="step__no">{{ i + 1 }}</span>
            <div class="step__body">
              <div class="uf-row">
                <strong>{{ st.title }}</strong>
                <uf-status-chip domain="setup" [value]="st.status" />
              </div>
              <div class="uf-muted">{{ st.detail }}</div>
            </div>
            <a mat-stroked-button [routerLink]="screen(st).path" class="step__open">
              Open {{ screen(st).label }}
            </a>
          </li>
        }
      </ol>
    } @else if (!error()) {
      <p class="uf-muted">Loading…</p>
    }
  `,
  styles: [
    `
      .progress {
        height: 0.5rem;
        border-radius: 999px;
        background: var(--uf-surface-2);
        overflow: hidden;
        margin: 0.5rem 0;
      }
      .progress span {
        display: block;
        height: 100%;
        background: var(--uf-good, #059669);
        transition: width 0.3s;
      }
      .steps {
        list-style: none;
        padding: 0;
        margin: 1rem 0 0;
        display: grid;
        gap: 0.5rem;
      }
      .step {
        display: grid;
        grid-template-columns: 2rem 1fr auto;
        gap: 0.75rem;
        align-items: center;
        padding: 0.75rem 1rem;
        background: var(--uf-surface);
        border: 1px solid var(--uf-border);
        border-left: 4px solid var(--uf-border);
        border-radius: var(--uf-radius);
      }
      .step--done {
        border-left-color: var(--uf-good, #059669);
      }
      .step--attention {
        border-left-color: var(--uf-warning, #d97706);
      }
      .step__no {
        width: 2rem;
        height: 2rem;
        display: grid;
        place-items: center;
        border-radius: 50%;
        background: var(--uf-surface-2);
        font-weight: 700;
      }
      .step__body {
        min-width: 0;
      }
      @media (max-width: 700px) {
        .step {
          grid-template-columns: 2rem 1fr;
        }
        .step__open {
          grid-column: 2;
          justify-self: start;
        }
      }
    `,
  ],
})
export class SetupPage {
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  private readonly api = inject(UnitformaApi);
  readonly setup = signal<SetupOut | null>(null);
  readonly error = signal<string | null>(null);
  readonly facts = computed<HeaderFact[]>(() => {
    const s = this.setup();
    if (!s) return [];
    const attention = s.steps.filter((x) => x.status === 'attention').length;
    return [
      { label: 'Done', value: `${s.done} / ${s.total}` },
      { label: 'Needs attention', value: attention },
    ];
  });
  readonly optionalLeft = computed(
    () => (this.setup()?.steps ?? []).filter((x) => x.status === 'optional').length,
  );

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  async load(): Promise<void> {
    this.error.set(null);
    try {
      this.setup.set(await this.api.projectSetup(this.tenantId(), this.projectId()));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  screen(st: SetupStepOut): { label: string; path: string[] } {
    return SCREEN[st.link] ?? SCREEN['overview'];
  }
}
