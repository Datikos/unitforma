import { JsonPipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { AuditOut, UnitformaApi, problemMessage } from 'api-client';
import {
  EmptyStateComponent,
  PageHeaderComponent,
  StatusChipComponent,
  UF_ICONS,
  ago,
  humanise,
  whenShort,
} from 'ui';

/** Every change made through the API: who, what, which action, values after (plan §2.2 audit). */
@Component({
  selector: 'uf-audit-page',
  imports: [
    JsonPipe,
    FormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    NgIcon,
    PageHeaderComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header
        title="Audit log"
        icon="lucideScrollText"
        [facts]="[
          { label: 'Entries', value: total() },
          { label: 'Loaded', value: items().length },
        ]"
      />
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }

      @if (items().length) {
        <div class="uf-filterbar">
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Entity</mat-label>
            <mat-select [ngModel]="entity()" (ngModelChange)="entity.set($event)"
              ><mat-option [value]="null">All</mat-option>
              @for (e of entities(); track e) {
                <mat-option [value]="e">{{ humanise(e) }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <mat-form-field appearance="outline" subscriptSizing="dynamic"
            ><mat-label>Action</mat-label>
            <mat-select [ngModel]="action()" (ngModelChange)="action.set($event)"
              ><mat-option [value]="null">All</mat-option>
              @for (a of actions(); track a) {
                <mat-option [value]="a">{{ humanise(a) }}</mat-option>
              }
            </mat-select>
          </mat-form-field>
          <span class="uf-count"
            >{{ shown().length }} of {{ items().length }} loaded · {{ total() }} in total</span
          >
        </div>
        <div class="uf-card uf-stack" style="padding: 0">
          <table class="uf-plain">
            <thead>
              <tr>
                <th>When</th>
                <th>Who</th>
                <th>What</th>
                <th>Change</th>
              </tr>
            </thead>
            <tbody>
              @for (a of shown(); track a.id) {
                <tr>
                  <td class="uf-nowrap">
                    <div>{{ when(a.at) }}</div>
                    <div class="uf-muted uf-small">{{ ago(a.at) }}</div>
                  </td>
                  <td><uf-status-chip domain="role" [value]="a.actor_role" /></td>
                  <td>
                    <strong>{{ humanise(a.action) }}</strong>
                    <span class="uf-muted">{{ humanise(a.entity_type) }}</span>
                  </td>
                  <td>
                    @if (a.after) {
                      <details>
                        <summary class="uf-link">
                          {{ keys(a.after).slice(0, 4).join(', ')
                          }}{{ keys(a.after).length > 4 ? ' …' : '' }}
                        </summary>
                        <pre class="json">{{ a.after | json }}</pre>
                      </details>
                    } @else {
                      <span class="uf-muted">—</span>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
          <div class="more">
            <span class="uf-muted uf-small">{{ items().length }} of {{ total() }}</span>
            @if (items().length < total()) {
              <button mat-stroked-button (click)="more()">
                <ng-icon name="lucideChevronDown" /> Load more
              </button>
            }
          </div>
        </div>
      } @else if (loaded()) {
        <uf-empty-state
          icon="lucideScrollText"
          title="Nothing recorded yet"
          text="Every change made through the admin API appears here with its actor, entity and the values after the change."
        />
      }
    </div>
  `,
  styles: `
    .json {
      font-size: 0.75rem;
      white-space: pre-wrap;
      word-break: break-all;
      margin: 0.25rem 0 0;
      background: var(--uf-surface-2);
      padding: 0.5rem;
      border-radius: 6px;
      max-width: 48rem;
    }
    details summary {
      cursor: pointer;
      font-size: 0.9rem;
    }
    .more {
      display: flex;
      gap: 0.75rem;
      align-items: center;
      padding: 0.6rem 1rem;
    }
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class AuditPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly items = signal<AuditOut[]>([]);
  readonly total = signal(0);
  readonly loaded = signal(false);
  readonly error = signal<string | null>(null);
  readonly entity = signal<string | null>(null);
  readonly action = signal<string | null>(null);
  readonly entities = computed(() => [...new Set(this.items().map((a) => a.entity_type))].sort());
  readonly actions = computed(() => [...new Set(this.items().map((a) => a.action))].sort());
  readonly shown = computed(() =>
    this.items().filter(
      (a) =>
        (!this.entity() || a.entity_type === this.entity()) &&
        (!this.action() || a.action === this.action()),
    ),
  );
  when = whenShort;
  ago = ago;
  humanise = humanise;

  constructor() {
    toObservable(this.tenantId).subscribe(() => void this.load(true));
  }

  keys(o: Record<string, unknown>): string[] {
    return Object.keys(o);
  }

  async load(reset = false): Promise<void> {
    try {
      const page = await this.api.listAudit(this.tenantId(), 50, reset ? 0 : this.items().length);
      this.items.set(reset ? page.items : [...this.items(), ...page.items]);
      this.total.set(page.total);
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.loaded.set(true);
    }
  }

  more(): Promise<void> {
    return this.load(false);
  }
}
