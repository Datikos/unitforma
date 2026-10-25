import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { ImportBatchOut, ImportOptions, UnitformaApi, problemMessage } from 'api-client';
import {
  EmptyStateComponent,
  HeaderFact,
  PageHeaderComponent,
  SectionCardComponent,
  StatusChipComponent,
  UF_ICONS,
  whenShort,
} from 'ui';
import { DialogsService } from '../ui/dialogs.service';
import { ToastService } from '../ui/toast.service';

interface ReportRow {
  row: number;
  unit_id: string | null;
  code: string | null;
  status: 'changed' | 'unchanged' | 'error';
  changes: { field: string; old: unknown; new: unknown }[];
  errors: string[];
  warnings: string[];
}

interface Summary {
  rows: number;
  changed: number;
  unchanged: number;
  errors: number;
  warnings: number;
  unknown_codes: string[];
  changes_by_field: Record<string, number>;
  total_changes: number;
}

const FIELD_HELP: Record<string, string> = {
  unit_id: 'identifies the unit (from an export)',
  code: 'identifies the unit when there is no unit_id',
  availability: 'available / reserved / sold / withdrawn; empty keeps',
  list_price: 'empty = price on request (NULL), never 0',
  currency: 'ISO code; required when a price is given',
  price_on_request: 'true/false; empty keeps',
  payment_plan: 'plan name; empty clears',
  promotions: 'names separated by ";"; empty clears',
};

/** Import wizard (plan §6.3): upload → column mapping (saved per project) → dry run → apply. */
@Component({
  selector: 'uf-import-page',
  imports: [
    FormsModule,
    RouterLink,
    MatButtonModule,
    MatButtonToggleModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatSelectModule,
    NgIcon,
    PageHeaderComponent,
    SectionCardComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header title="Import prices & terms" icon="lucideFileSpreadsheet" [facts]="facts()">
        <ng-container actions
          ><a mat-stroked-button routerLink="../inventory"
            ><ng-icon name="lucideTable" /> Inventory</a
          ></ng-container
        >
      </uf-page-header>
      @if (error(); as e) {
        <div class="uf-alert uf-alert--bad" role="alert">
          <ng-icon name="lucideCircleX" />{{ e }}
        </div>
      }

      <ol class="uf-steps" aria-label="Import steps">
        <li [class.is-current]="step() === 1" [class.is-done]="step() > 1">File</li>
        <li [class.is-current]="step() === 2" [class.is-done]="step() > 2">Columns</li>
        <li [class.is-current]="step() === 3" [class.is-done]="step() > 3">Dry run</li>
        <li [class.is-current]="step() === 4" [class.is-done]="step() > 4">Apply</li>
      </ol>

      <uf-section-card
        title="1 · File"
        icon="lucideFileUp"
        [summary]="
          batch()
            ? batch()!.file_name + ' · ' + batch()!.row_count + ' rows'
            : 'CSV or XLSX, first row = column names'
        "
        storageKey="import-file"
      >
        <div actions>
          @if (batch(); as b) {
            <uf-status-chip domain="import_batch" [value]="b.status" />
          }
        </div>
        <div class="uf-form-row">
          <label class="pick" [class.is-busy]="busy()">
            <ng-icon name="lucideFileUp" /> Choose a file…
            <input
              type="file"
              accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
              (change)="upload($event)"
              [disabled]="busy()"
              hidden
            />
          </label>
          <span class="uf-hint"
            >An inventory export is a ready-made template: export, edit prices, import.</span
          >
        </div>
      </uf-section-card>

      @if (batch(); as b) {
        <uf-section-card
          title="2 · Columns"
          icon="lucideListFilter"
          [summary]="mappedCount() + ' of ' + (b.targets?.length ?? 0) + ' fields mapped'"
          storageKey="import-columns"
          [open]="b.status !== 'applied'"
        >
          <p class="uf-hint">
            Unmapped columns are ignored; the mapping is remembered for this project.
          </p>
          <div class="map">
            @for (t of b.targets; track t) {
              <mat-form-field appearance="outline" [class.uf-set]="!!mapping[t]">
                <mat-label>{{ t }}</mat-label>
                <mat-select
                  [(ngModel)]="mapping[t]"
                  [name]="'m' + t"
                  [disabled]="b.status === 'applied'"
                >
                  <mat-option [value]="null">— not imported —</mat-option>
                  @for (h of b.headers; track h) {
                    @if (h) {
                      <mat-option [value]="h">{{ h }}</mat-option>
                    }
                  }
                </mat-select>
                @if (help[t]) {
                  <mat-hint>{{ help[t] }}</mat-hint>
                }
              </mat-form-field>
            }
          </div>
          <div class="uf-form-row">
            <mat-form-field appearance="outline" subscriptSizing="dynamic"
              ><mat-label>Decimal separator</mat-label>
              <mat-select [(ngModel)]="options.decimal_separator" name="dec"
                ><mat-option value=".">. (1234.50)</mat-option
                ><mat-option value=",">, (1234,50)</mat-option></mat-select
              >
            </mat-form-field>
            <mat-form-field appearance="outline" subscriptSizing="dynamic"
              ><mat-label>Thousands separator</mat-label>
              <mat-select [(ngModel)]="options.thousands_separator" name="thou">
                <mat-option value="">none</mat-option><mat-option value=" ">space</mat-option
                ><mat-option value=",">,</mat-option><mat-option value=".">.</mat-option
                ><mat-option value="'">'</mat-option>
              </mat-select>
            </mat-form-field>
            <mat-checkbox [(ngModel)]="options.confirm_zero_price" name="zero"
              >Accept price 0 where price_on_request is false</mat-checkbox
            >
            <button
              mat-flat-button
              [disabled]="busy() || b.status === 'applied'"
              (click)="dryRun()"
            >
              <ng-icon name="lucideFlaskConical" /> Dry run
            </button>
          </div>
          <p class="uf-hint">
            A dry run matches rows to units and lists what would change. Nothing is written.
          </p>
        </uf-section-card>
      }

      @if (summary(); as s) {
        <uf-section-card
          title="3 · Dry run"
          icon="lucideFlaskConical"
          [summary]="s.changed + ' units change · ' + s.errors + ' errors'"
          storageKey="import-dryrun"
        >
          <div actions>
            @if (batch(); as b) {
              <uf-status-chip domain="import_batch" [value]="b.status" />
            }
          </div>
          <div class="uf-stats">
            <div class="uf-stat">
              <span class="uf-stat__label">Rows</span
              ><span class="uf-stat__value">{{ s.rows }}</span>
            </div>
            <div class="uf-stat">
              <span class="uf-stat__label">Units change</span
              ><span class="uf-stat__value uf-text-good">{{ s.changed }}</span
              ><span class="uf-stat__hint">{{ s.total_changes }} values</span>
            </div>
            <div class="uf-stat">
              <span class="uf-stat__label">Unchanged</span
              ><span class="uf-stat__value">{{ s.unchanged }}</span>
            </div>
            <div class="uf-stat">
              <span class="uf-stat__label">With errors</span
              ><span class="uf-stat__value" [class.uf-text-bad]="s.errors">{{ s.errors }}</span>
            </div>
            <div class="uf-stat">
              <span class="uf-stat__label">With warnings</span
              ><span class="uf-stat__value" [class.uf-text-warning]="s.warnings">{{
                s.warnings
              }}</span>
            </div>
          </div>
          @if (s.unknown_codes.length) {
            <div class="uf-alert uf-alert--bad">
              <ng-icon name="lucideCircleX" />Unknown codes:
              {{ s.unknown_codes.slice(0, 30).join(', ') }}
              @if (s.unknown_codes.length > 30) {
                …
              }
            </div>
          }
          @if (fieldCounts().length) {
            <div class="uf-chips">
              @for (f of fieldCounts(); track f[0]) {
                <span class="uf-chip">{{ f[0] }} · {{ f[1] }}</span>
              }
            </div>
          }
          <div class="uf-filterbar">
            <mat-button-toggle-group
              [value]="filter()"
              (valueChange)="filter.set($event)"
              hideSingleSelectionIndicator
            >
              <mat-button-toggle value="error">Errors · {{ s.errors }}</mat-button-toggle>
              <mat-button-toggle value="changed">Changes · {{ s.changed }}</mat-button-toggle>
              <mat-button-toggle value="all">All rows · {{ s.rows }}</mat-button-toggle>
            </mat-button-toggle-group>
            @if (filteredCount() > visibleRows().length) {
              <span class="uf-count"
                >Showing {{ visibleRows().length }} of {{ filteredCount() }}</span
              >
            }
          </div>
          <table class="uf-plain report">
            <thead>
              <tr>
                <th>Row</th>
                <th>Unit</th>
                <th>Result</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              @for (r of visibleRows(); track r.row) {
                <tr [class.is-error]="r.status === 'error'">
                  <td class="uf-num">{{ r.row }}</td>
                  <td>{{ r.code ?? '—' }}</td>
                  <td>
                    <span
                      class="uf-chip"
                      [class.uf-tone-bad]="r.status === 'error'"
                      [class.uf-tone-good]="r.status === 'changed'"
                      >{{ r.status }}</span
                    >
                  </td>
                  <td>
                    @for (e of r.errors; track $index) {
                      <div class="uf-text-bad">{{ e }}</div>
                    }
                    @for (w of r.warnings; track $index) {
                      <div class="uf-text-warning">{{ w }}</div>
                    }
                    @for (c of r.changes; track $index) {
                      <span class="chg"
                        >{{ c.field }}: <s>{{ c.old ?? '∅' }}</s> →
                        <strong>{{ c.new ?? '∅' }}</strong></span
                      >
                    }
                  </td>
                </tr>
              } @empty {
                <tr>
                  <td colspan="4" class="uf-muted">No rows in this view.</td>
                </tr>
              }
            </tbody>
          </table>
          <div class="uf-actions">
            @if (batch()?.status === 'dry_run') {
              <mat-checkbox [(ngModel)]="skipInvalid" name="skip" [disabled]="!s.errors"
                >Skip the {{ s.errors }} row(s) with errors</mat-checkbox
              >
              <button
                mat-flat-button
                [disabled]="busy() || (s.errors > 0 && !skipInvalid) || s.total_changes === 0"
                (click)="apply()"
              >
                <ng-icon name="lucideCheck" /> Apply {{ s.total_changes }} change(s)
              </button>
              <button mat-button [disabled]="busy()" (click)="discard()">
                <ng-icon name="lucideTrash2" /> Discard
              </button>
              <span class="uf-hint"
                >Apply writes every change with this import's id in the audit log.</span
              >
            } @else if (batch()?.status === 'applied') {
              <div class="uf-alert uf-alert--good">
                <ng-icon name="lucideCircleCheck" />Applied {{ batch()?.change_count }} change(s)
                {{ when(batch()?.applied_at) }}. Every change is in the audit log with this import's
                id.
              </div>
            }
          </div>
        </uf-section-card>
      }

      <uf-section-card
        title="Previous imports"
        icon="lucideHistory"
        [count]="past().length"
        [summary]="past()[0] ? 'latest ' + when(past()[0].created_at) : 'none yet'"
        [flush]="true"
        storageKey="import-past"
        [open]="!batch()"
      >
        @if (past().length) {
          <table class="uf-plain">
            <thead>
              <tr>
                <th>File</th>
                <th>Status</th>
                <th>When</th>
                <th class="uf-num">Rows</th>
                <th class="uf-num">Changes</th>
                <th class="uf-num">Errors</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (h of past(); track h.id) {
                <tr>
                  <td>
                    <strong>{{ h.file_name }}</strong>
                  </td>
                  <td><uf-status-chip domain="import_batch" [value]="h.status" /></td>
                  <td>{{ when(h.created_at) }}</td>
                  <td class="uf-num">{{ h.row_count }}</td>
                  <td class="uf-num">{{ h.change_count }}</td>
                  <td class="uf-num" [class.uf-text-bad]="h.error_count">{{ h.error_count }}</td>
                  <td class="actions">
                    <button mat-button (click)="open(h.id)">
                      Open <ng-icon name="lucideArrowRight" />
                    </button>
                  </td>
                </tr>
              }
            </tbody>
          </table>
        } @else {
          <uf-empty-state
            icon="lucideFileSpreadsheet"
            title="No imports yet"
            text="Upload a CSV or XLSX above. Export the inventory first if you want a template with the right columns."
            [compact]="true"
          />
        }
      </uf-section-card>
    </div>
  `,
  styles: `
    .pick {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.6rem 0.9rem;
      border: 1px dashed var(--uf-border-strong);
      border-radius: var(--uf-radius-sm);
      cursor: pointer;
      color: var(--uf-primary);
      font-weight: 600;
    }
    .pick.is-busy {
      opacity: 0.5;
      pointer-events: none;
    }
    .map {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(230px, 1fr));
      gap: 0 0.75rem;
    }
    .map mat-form-field.uf-set {
      border-radius: 6px;
    }
    .report td {
      font-size: 0.85rem;
      vertical-align: top;
    }
    .is-error td {
      background: var(--uf-tone-bad-bg);
    }
    .chg {
      display: inline-block;
      margin-right: 0.75rem;
    }
    .actions {
      text-align: right;
    }
    a ng-icon,
    button ng-icon {
      vertical-align: -0.15em;
      margin-right: 0.25rem;
    }
  `,
})
export class ImportPage {
  private readonly api = inject(UnitformaApi);
  private readonly dialogs = inject(DialogsService);
  private readonly toast = inject(ToastService);
  when = whenShort;
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly batch = signal<ImportBatchOut | null>(null);
  readonly past = signal<ImportBatchOut[]>([]);
  readonly filter = signal<'error' | 'changed' | 'all'>('error');
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly help = FIELD_HELP;
  mapping: Record<string, string | null> = {};
  options: ImportOptions = {
    decimal_separator: '.',
    thousands_separator: '',
    confirm_zero_price: false,
  };
  skipInvalid = false;

  readonly summary = computed(
    () => (this.batch()?.report?.['summary'] as Summary | undefined) ?? null,
  );
  private readonly reportRows = computed(
    () => (this.batch()?.report?.['rows'] as ReportRow[] | undefined) ?? [],
  );
  private readonly filtered = computed(() => {
    const f = this.filter();
    return this.reportRows().filter((r) => f === 'all' || r.status === f);
  });
  readonly filteredCount = computed(() => this.filtered().length);
  readonly visibleRows = computed(() => this.filtered().slice(0, 500));
  readonly fieldCounts = computed(() => Object.entries(this.summary()?.changes_by_field ?? {}));
  readonly step = computed<number>(() => {
    const b = this.batch();
    if (!b) return 1;
    if (b.status === 'applied') return 5;
    return this.summary() ? 3 : 2;
  });
  readonly mappedCount = computed(() => Object.values(this.mapping).filter(Boolean).length);
  readonly facts = computed<HeaderFact[]>(() => {
    const b = this.batch();
    return b
      ? [
          { domain: 'import_batch', status: b.status },
          { label: 'File', value: b.file_name },
          { label: 'Rows', value: b.row_count },
        ]
      : [{ label: 'Previous imports', value: this.past().length }];
  });

  constructor() {
    toObservable(this.projectId).subscribe(() => void this.loadPast());
  }

  async loadPast(): Promise<void> {
    try {
      this.past.set(await this.api.listImports(this.tenantId(), this.projectId()));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  private setBatch(b: ImportBatchOut): void {
    this.batch.set(b);
    this.mapping = Object.fromEntries(
      (b.targets ?? []).map((t) => [t, (b.mapping ?? {})[t] ?? null]),
    );
    const o = (b.options ?? {}) as Partial<ImportOptions>;
    this.options = {
      decimal_separator: o.decimal_separator ?? '.',
      thousands_separator: o.thousands_separator ?? '',
      confirm_zero_price: o.confirm_zero_price ?? false,
    };
    this.filter.set(this.summary()?.errors ? 'error' : 'changed');
  }

  async upload(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    await this.run(async () =>
      this.setBatch(await this.api.uploadImport(this.tenantId(), this.projectId(), file)),
    );
    input.value = '';
  }

  async open(id: string): Promise<void> {
    await this.run(async () => this.setBatch(await this.api.getImport(this.tenantId(), id)));
  }

  dryRun(): Promise<void> {
    const mapping = Object.fromEntries(
      Object.entries(this.mapping).filter(([, h]) => !!h),
    ) as Record<string, string>;
    return this.run(async () =>
      this.setBatch(
        await this.api.dryRunImport(this.tenantId(), this.batch()!.id, mapping, this.options),
      ),
    );
  }

  apply(): Promise<void> {
    return this.run(async () => {
      try {
        this.setBatch(
          await this.api.applyImport(this.tenantId(), this.batch()!.id, this.skipInvalid),
        );
        this.toast.ok(`${this.batch()?.change_count ?? 0} change(s) applied`);
      } catch (e) {
        if ((e as { status?: number }).status === 409) {
          this.error.set(
            'The inventory changed since the dry run. The dry run was repeated: review the differences and apply again.',
          );
          await this.dryRun();
          return;
        }
        throw e;
      }
      await this.loadPast();
    });
  }

  async discard(): Promise<void> {
    const ok = await this.dialogs.confirm({
      title: 'Discard this import?',
      message: 'The uploaded file and its dry run are thrown away. No unit was changed.',
      confirmLabel: 'Discard',
      tone: 'bad',
    });
    if (!ok) return;
    return this.run(async () => {
      await this.api.discardImport(this.tenantId(), this.batch()!.id);
      this.batch.set(null);
      this.toast.ok('Import discarded');
      await this.loadPast();
    });
  }

  private async run(fn: () => Promise<unknown>): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await fn();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
