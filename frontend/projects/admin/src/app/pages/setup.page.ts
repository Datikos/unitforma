import { DecimalPipe } from '@angular/common';
import { Component, OnDestroy, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { SetupDecisionOut, SetupOut, SetupStepOut, UnitformaApi, problemMessage } from 'api-client';
import {
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
} from 'ui';
import { ToastService } from '../ui/toast.service';

/** The admin screen that completes a step, relative to `projects/:projectId/setup`. */
const SCREEN: Record<string, { label: string; path: string[] }> = {
  documents: { label: 'Documents', path: ['..', 'documents'] },
  overview: { label: 'Overview & structure', path: ['..'] },
  placement: { label: 'Site placement', path: ['..', 'placement'] },
  inventory: { label: 'Inventory & prices', path: ['..', 'inventory'] },
  publish: { label: 'Publish', path: ['..', 'publish'] },
  layouts: { label: 'Layouts & renders', path: ['..', 'layouts'] },
};

const POLL_MS = 5000;

/**
 * Setup checklist (ADR-0017 Decision 5) and the review surface of the setup solver (ADR-0025
 * Decision 7): the switches, "Run now", what the last run decided and what it left for you.
 */
@Component({
  selector: 'uf-setup-page',
  imports: [
    DecimalPipe,
    FormsModule,
    MatButtonModule,
    MatSlideToggleModule,
    NgIcon,
    PageHeaderComponent,
    RouterLink,
    SectionCardComponent,
    StatusChipComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
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
      <uf-section-card
        title="Set up automatically"
        icon="lucideSparkles"
        [summary]="autoSummary()"
        [tone]="s.auto?.enabled ? 'good' : null"
        storageKey="setup-auto"
      >
        <div class="switches">
          <mat-slide-toggle
            [ngModel]="s.auto?.enabled ?? false"
            (ngModelChange)="
              setAuto($event, s.auto?.approve_sheets ?? false, s.auto?.publish_defaults ?? false)
            "
            [disabled]="busy()"
            name="autoEnabled"
            >Apply the confident proposals after every processed document</mat-slide-toggle
          >
          <mat-slide-toggle
            [ngModel]="s.auto?.approve_sheets ?? false"
            (ngModelChange)="
              setAuto(s.auto?.enabled ?? false, $event, s.auto?.publish_defaults ?? false)
            "
            [disabled]="busy()"
            name="autoApprove"
            >Approve mapped sheets when every printed label is outlined</mat-slide-toggle
          >
          <mat-slide-toggle
            [ngModel]="s.auto?.publish_defaults ?? false"
            (ngModelChange)="
              setAuto(s.auto?.enabled ?? false, s.auto?.approve_sheets ?? false, $event)
            "
            [disabled]="busy()"
            name="autoPublish"
            >Publish the first version with defaults when the solver is done</mat-slide-toggle
          >
          <span class="uf-spacer"></span>
          <button mat-stroked-button [disabled]="busy() || s.auto?.running" (click)="runNow()">
            <ng-icon name="lucidePlay" /> Run now
          </button>
          <button
            mat-flat-button
            [disabled]="busy() || s.auto?.running"
            (click)="publishDefaults()"
            title="Approve the solver's drafts, confirm its plan types, write a first description, list every active unit and publish a version"
          >
            <ng-icon name="lucideSparkles" /> Publish with defaults
          </button>
        </div>
        <p class="uf-hint">
          Floors from the level markers, sheets to their floors, scale from the printed 1:N (and
          your calibration of one page for the other pages of its document), unit outlines the
          drawing names clearly (0.85 or more), the site plan, the placement, the gallery, the map
          position and proposed plan types. Nothing a person set is changed; approval needs the
          mapping approve right. "Publish with defaults" (ADR-0029) ends with a live portal: drafts
          approved, plan types confirmed, a first description from the project's facts, every active
          unit listed, prices on request, a new version published. Adjust afterwards and publish
          again.
        </p>
        @if (s.auto?.running) {
          <div class="uf-alert uf-alert--info" role="status">
            <ng-icon name="lucideLoaderCircle" /> A run is queued or in progress; this page
            refreshes every 5 seconds.
          </div>
        } @else if (s.auto?.last_run; as r) {
          <div class="uf-row last-run">
            <uf-status-chip domain="setup.run" [value]="r.status" />
            <span class="uf-muted"
              >Last run ({{ triggerLabel(r.trigger) }}): {{ r.accepted }} decided for you,
              {{ r.needs_you }} need you{{ r.errors ? ', ' + r.errors + ' failed' : '' }}
              @if (r.error) {
                · {{ r.error }}
              }
            </span>
          </div>
        }
      </uf-section-card>

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
              @if (st.auto_detail) {
                <div class="step__auto"><ng-icon name="lucideSparkles" /> {{ st.auto_detail }}</div>
              }
            </div>
            <a mat-stroked-button [routerLink]="screen(st).path" class="step__open">
              Open {{ screen(st).label }}
            </a>
          </li>
        }
      </ol>

      @if (s.decisions?.length) {
        <uf-section-card
          title="Decided for you"
          icon="lucideClipboardCheck"
          [summary]="decisionSummary()"
          [count]="shownDecisions().length"
          storageKey="setup-decisions"
        >
          <div class="uf-filterbar">
            <mat-slide-toggle
              [ngModel]="onlyNeedsMe()"
              (ngModelChange)="onlyNeedsMe.set($event)"
              name="onlyNeedsMe"
              >Only what needs me</mat-slide-toggle
            >
            <div class="chips" role="group" aria-label="Filter by step">
              <button
                type="button"
                class="uf-chip"
                [class.uf-chip--active]="stepFilter() === null"
                (click)="stepFilter.set(null)"
              >
                All steps
              </button>
              @for (k of stepKeys(); track k) {
                <button
                  type="button"
                  class="uf-chip"
                  [class.uf-chip--active]="stepFilter() === k"
                  (click)="stepFilter.set(k)"
                >
                  {{ stepLabel(k) }}
                </button>
              }
            </div>
          </div>
          <ul class="decisions">
            @for (d of shownDecisions(); track $index) {
              <li class="decision" [class.decision--needs]="d.needs_you">
                <uf-status-chip domain="setup.decision" [value]="d.kind" />
                <div class="decision__body">
                  <div class="uf-row">
                    <strong>{{ d.title }}</strong>
                    @if (d.confidence !== null && d.confidence !== undefined) {
                      <span
                        class="uf-chip"
                        [class.uf-tone-good]="d.confidence >= 0.9"
                        [class.uf-tone-warning]="d.confidence < 0.9"
                        title="Confidence recorded with the decision"
                        >{{ d.confidence | number: '1.2-2' }}</span
                      >
                    }
                    <span class="uf-muted uf-small">{{ stepLabel(d.step) }}</span>
                  </div>
                  <div class="uf-muted">{{ d.detail }}</div>
                  @if (d.needs_you && d.todo) {
                    <div class="decision__todo"><strong>To do:</strong> {{ d.todo }}</div>
                  }
                </div>
                <a mat-button [routerLink]="linkOf(d)" class="decision__open">
                  {{ openLabel(d) }}
                </a>
              </li>
            } @empty {
              <p class="uf-muted">Nothing matches the filter.</p>
            }
          </ul>
        </uf-section-card>
      }
    } @else if (!error()) {
      <p class="uf-muted">Loading…</p>
    }
  `,
  styles: [
    `
      .switches {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem 1.5rem;
        align-items: center;
      }
      .last-run {
        margin-top: 0.5rem;
      }
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
      .steps,
      .decisions {
        list-style: none;
        padding: 0;
        margin: 1rem 0 0;
        display: grid;
        gap: 0.5rem;
      }
      .step,
      .decision {
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
      .decision {
        grid-template-columns: auto 1fr auto;
        padding: 0.5rem 0.75rem;
      }
      .step--done {
        border-left-color: var(--uf-good, #059669);
      }
      .step--attention,
      .decision--needs {
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
      .step__body,
      .decision__body {
        min-width: 0;
      }
      .decision__todo {
        margin-top: 0.25rem;
        color: var(--uf-text);
      }
      .step__auto {
        margin-top: 0.25rem;
        font-size: 0.9rem;
        color: var(--uf-primary);
      }
      .step__auto ng-icon {
        vertical-align: -0.15em;
      }
      .chips {
        display: flex;
        flex-wrap: wrap;
        gap: 0.3rem;
      }
      .uf-chip--active {
        background: var(--uf-primary);
        color: var(--uf-on-primary, #fff);
        border-color: var(--uf-primary);
      }
      button ng-icon {
        vertical-align: -0.15em;
        margin-right: 0.25rem;
      }
      @media (max-width: 700px) {
        .step,
        .decision {
          grid-template-columns: 2rem 1fr;
        }
        .decision {
          grid-template-columns: auto 1fr;
        }
        .step__open,
        .decision__open {
          grid-column: 2;
          justify-self: start;
        }
      }
    `,
  ],
})
export class SetupPage implements OnDestroy {
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  private readonly api = inject(UnitformaApi);
  private readonly toast = inject(ToastService);
  protected readonly SCREEN = SCREEN;
  readonly setup = signal<SetupOut | null>(null);
  readonly error = signal<string | null>(null);
  readonly busy = signal(false);
  readonly onlyNeedsMe = signal(false);
  readonly stepFilter = signal<string | null>(null);
  private pollTimer: ReturnType<typeof setTimeout> | null = null;

  readonly facts = computed<HeaderFact[]>(() => {
    const s = this.setup();
    if (!s) return [];
    const attention = s.steps.filter((x) => x.status === 'attention').length;
    const needs = (s.decisions ?? []).filter((d) => d.needs_you).length;
    return [
      { label: 'Done', value: `${s.done} / ${s.total}` },
      { label: 'Needs attention', value: attention },
      ...(s.auto?.last_run ? [{ label: 'Need you', value: needs }] : []),
    ];
  });
  readonly optionalLeft = computed(
    () => (this.setup()?.steps ?? []).filter((x) => x.status === 'optional').length,
  );
  readonly autoSummary = computed(() => {
    const a = this.setup()?.auto;
    if (!a) return 'off';
    if (!a.enabled) return 'off · "Run now" runs it once';
    const first = a.publish_defaults ? ' · first version published with defaults' : '';
    return (
      (a.approve_sheets ? 'on · sheets approved when complete' : 'on · units stay drafts') + first
    );
  });
  readonly stepKeys = computed(() => {
    const keys: string[] = [];
    for (const d of this.setup()?.decisions ?? []) if (!keys.includes(d.step)) keys.push(d.step);
    return keys;
  });
  readonly shownDecisions = computed(() => {
    const all = this.setup()?.decisions ?? [];
    return all.filter(
      (d) =>
        (!this.onlyNeedsMe() || d.needs_you) &&
        (this.stepFilter() === null || d.step === this.stepFilter()),
    );
  });
  readonly decisionSummary = computed(() => {
    const all = this.setup()?.decisions ?? [];
    const needs = all.filter((d) => d.needs_you).length;
    return `${all.length - needs} made for you · ${needs} need you · lowest confidence first`;
  });

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.load());
  }

  ngOnDestroy(): void {
    if (this.pollTimer) clearTimeout(this.pollTimer);
  }

  async load(): Promise<void> {
    this.error.set(null);
    try {
      const s = await this.api.projectSetup(this.tenantId(), this.projectId());
      this.setup.set(s);
      this.schedulePoll(!!s.auto?.running);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  private schedulePoll(running: boolean): void {
    if (this.pollTimer) clearTimeout(this.pollTimer);
    this.pollTimer = running ? setTimeout(() => void this.load(), POLL_MS) : null;
  }

  async setAuto(enabled: boolean, approveSheets: boolean, publishDefaults = false): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.setSetupAuto(this.tenantId(), this.projectId(), {
        enabled,
        approve_sheets: approveSheets,
        publish_defaults: publishDefaults,
      });
      this.toast.ok(
        enabled ? 'Set up automatically: on; a run is queued' : 'Set up automatically: off',
      );
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  async runNow(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.runSetup(this.tenantId(), this.projectId());
      this.toast.ok('Run queued; the decisions appear below when it finishes');
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  /** ADR-0029 Decision 1: one confirmed click, then the run does the rest and the portal goes live. */
  async publishDefaults(): Promise<void> {
    const ok = window.confirm(
      'Publish with defaults will, in this order:\n' +
        '• approve every sheet whose outlines the solver drew (drafts become active)\n' +
        '• confirm the proposed plan types\n' +
        "• write a first description from the project's facts when there is none\n" +
        '• list every active unit; prices stay as they are ("price on request" when empty)\n' +
        '• publish a new version of the portal\n\n' +
        'Nothing a person set is changed. Continue?',
    );
    if (!ok) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.publishSetupDefaults(this.tenantId(), this.projectId());
      this.toast.ok('Publishing queued; the portal goes live when the run finishes');
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  /** The button of a decision names the place: the sheet it is about, else the screen. */
  openLabel(d: SetupDecisionOut): string {
    if (d.sheet_id) {
      const m = /p\.(\d+)/.exec(d.title);
      return m ? `Open page ${m[1]}` : 'Open the sheet';
    }
    return `Open ${this.screenOf(d).label}`;
  }

  screen(st: SetupStepOut): { label: string; path: string[] } {
    return SCREEN[st.link] ?? SCREEN['overview'];
  }

  linkOf(d: SetupDecisionOut): string[] {
    if (d.sheet_id) return ['..', 'sheets', d.sheet_id];
    return this.screenOf(d).path;
  }

  screenOf(d: SetupDecisionOut): { label: string; path: string[] } {
    return SCREEN[d.link ?? 'overview'] ?? SCREEN['overview'];
  }

  stepLabel(key: string): string {
    const labels: Record<string, string> = {
      documents: 'Documents',
      classify: 'Document kinds',
      floors: 'Floors',
      calibration: 'Scale',
      sheet_floors: 'Sheets → floors',
      mapping: 'Unit outlines',
      site_plan: 'Site plan',
      placement: 'Placement',
      facades: 'Facades',
      gallery: 'Gallery',
      location: 'Map position',
      layouts: 'Plan types',
    };
    return labels[key] ?? key;
  }

  triggerLabel(trigger: string): string {
    const labels: Record<string, string> = {
      document_processed: 'after a processed document',
      permit_import: 'after the permit import',
      floors_saved: 'after floors were saved',
      switched_on: 'when switched on',
      run_now: 'run now',
    };
    return labels[trigger] ?? trigger;
  }
}
