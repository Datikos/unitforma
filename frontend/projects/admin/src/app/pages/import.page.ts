import { SlicePipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatButtonToggleModule } from '@angular/material/button-toggle';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { RouterLink } from '@angular/router';
import { ImportBatchOut, ImportOptions, UnitformaApi, problemMessage } from 'api-client';

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
  imports: [FormsModule, SlicePipe, RouterLink, MatButtonModule, MatButtonToggleModule, MatCardModule, MatCheckboxModule, MatFormFieldModule, MatSelectModule],
  template: `
    <div class="uf-page">
      <div class="uf-page-header"><h2>Import prices &amp; terms</h2><a mat-stroked-button routerLink="../inventory">Inventory</a></div>
      @if (error()) { <p class="uf-error" role="alert">{{ error() }}</p> }

      <mat-card appearance="outlined">
        <mat-card-header><mat-card-title>1 · File</mat-card-title><mat-card-subtitle>CSV or XLSX, first row = column names. An inventory export is a ready-made template.</mat-card-subtitle></mat-card-header>
        <mat-card-content class="uf-row">
          <input type="file" accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" (change)="upload($event)" [disabled]="busy()" />
          @if (batch(); as b) { <span class="uf-muted">{{ b.file_name }} · {{ b.row_count }} rows · {{ b.status }}</span> }
        </mat-card-content>
      </mat-card>

      @if (batch(); as b) {
        <mat-card appearance="outlined">
          <mat-card-header><mat-card-title>2 · Columns</mat-card-title><mat-card-subtitle>Unmapped columns are ignored; the mapping is remembered for this project</mat-card-subtitle></mat-card-header>
          <mat-card-content>
            <div class="uf-map">
              @for (t of b.targets; track t) {
                <mat-form-field appearance="outline">
                  <mat-label>{{ t }}</mat-label>
                  <mat-select [(ngModel)]="mapping[t]" [name]="'m' + t" [disabled]="b.status === 'applied'">
                    <mat-option [value]="null">— not imported —</mat-option>
                    @for (h of b.headers; track h) { @if (h) { <mat-option [value]="h">{{ h }}</mat-option> } }
                  </mat-select>
                  @if (help[t]) { <mat-hint>{{ help[t] }}</mat-hint> }
                </mat-form-field>
              }
            </div>
            <div class="uf-row uf-opts">
              <mat-form-field appearance="outline"><mat-label>Decimal separator</mat-label>
                <mat-select [(ngModel)]="options.decimal_separator" name="dec"><mat-option value=".">. (1234.50)</mat-option><mat-option value=",">, (1234,50)</mat-option></mat-select>
              </mat-form-field>
              <mat-form-field appearance="outline"><mat-label>Thousands separator</mat-label>
                <mat-select [(ngModel)]="options.thousands_separator" name="thou">
                  <mat-option value="">none</mat-option><mat-option value=" ">space</mat-option><mat-option value=",">,</mat-option><mat-option value=".">.</mat-option><mat-option value="'">'</mat-option>
                </mat-select>
              </mat-form-field>
              <mat-checkbox [(ngModel)]="options.confirm_zero_price" name="zero">Accept price 0 where price_on_request is false</mat-checkbox>
              <button mat-flat-button [disabled]="busy() || b.status === 'applied'" (click)="dryRun()">Dry run</button>
            </div>
          </mat-card-content>
        </mat-card>
      }

      @if (summary(); as s) {
        <mat-card appearance="outlined">
          <mat-card-header><mat-card-title>3 · Dry run</mat-card-title><mat-card-subtitle>Nothing has been written yet</mat-card-subtitle></mat-card-header>
          <mat-card-content>
            <div class="uf-stats">
              <span><strong>{{ s.rows }}</strong> rows</span>
              <span class="uf-ok"><strong>{{ s.changed }}</strong> units change ({{ s.total_changes }} values)</span>
              <span><strong>{{ s.unchanged }}</strong> unchanged</span>
              <span class="uf-bad"><strong>{{ s.errors }}</strong> with errors</span>
              <span><strong>{{ s.warnings }}</strong> with warnings</span>
            </div>
            @if (s.unknown_codes.length) { <p class="uf-bad">Unknown codes: {{ s.unknown_codes.slice(0, 30).join(', ') }}@if (s.unknown_codes.length > 30) { … }</p> }
            <p class="uf-muted">@for (f of fieldCounts(); track f[0]) { {{ f[0] }}: {{ f[1] }} · }</p>
            <mat-button-toggle-group [value]="filter()" (valueChange)="filter.set($event)">
              <mat-button-toggle value="error">Errors</mat-button-toggle>
              <mat-button-toggle value="changed">Changes</mat-button-toggle>
              <mat-button-toggle value="all">All rows</mat-button-toggle>
            </mat-button-toggle-group>
            <table class="uf-report">
              <thead><tr><th>Row</th><th>Unit</th><th>Result</th><th>Details</th></tr></thead>
              <tbody>
                @for (r of visibleRows(); track r.row) {
                  <tr [class.uf-err]="r.status === 'error'">
                    <td>{{ r.row }}</td>
                    <td>{{ r.code ?? '—' }}</td>
                    <td>{{ r.status }}</td>
                    <td>
                      @for (e of r.errors; track $index) { <div class="uf-bad">{{ e }}</div> }
                      @for (w of r.warnings; track $index) { <div class="uf-warn">{{ w }}</div> }
                      @for (c of r.changes; track $index) { <span class="uf-chg">{{ c.field }}: {{ c.old ?? '∅' }} → {{ c.new ?? '∅' }}</span> }
                    </td>
                  </tr>
                } @empty { <tr><td colspan="4" class="uf-muted">No rows in this view.</td></tr> }
              </tbody>
            </table>
            @if (filteredCount() > visibleRows().length) { <p class="uf-muted">Showing {{ visibleRows().length }} of {{ filteredCount() }}.</p> }
          </mat-card-content>
          <mat-card-actions>
            @if (batch()?.status === 'dry_run') {
              <mat-checkbox [(ngModel)]="skipInvalid" name="skip" [disabled]="!s.errors">Skip the {{ s.errors }} row(s) with errors</mat-checkbox>
              <button mat-flat-button [disabled]="busy() || (s.errors > 0 && !skipInvalid) || s.total_changes === 0" (click)="apply()">Apply {{ s.total_changes }} change(s)</button>
              <button mat-button [disabled]="busy()" (click)="discard()">Discard</button>
            } @else if (batch()?.status === 'applied') {
              <span class="uf-ok">Applied {{ batch()?.change_count }} change(s) {{ batch()?.applied_at | slice: 0 : 16 }}. Every change is in the audit log with this import's id.</span>
            }
          </mat-card-actions>
        </mat-card>
      }

      <mat-card appearance="outlined">
        <mat-card-header><mat-card-title>Previous imports</mat-card-title></mat-card-header>
        <mat-card-content>
          <ul class="uf-list">
            @for (h of past(); track h.id) {
              <li><button mat-button (click)="open(h.id)">{{ h.file_name }}</button> <span class="uf-muted">{{ h.created_at | slice: 0 : 16 }} · {{ h.status }} · {{ h.row_count }} rows · {{ h.change_count }} changes · {{ h.error_count }} errors</span></li>
            } @empty { <li class="uf-muted">None yet.</li> }
          </ul>
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: `
    .uf-row { display: flex; gap: 0.75rem; align-items: center; flex-wrap: wrap; }
    .uf-map { display: grid; grid-template-columns: repeat(auto-fill, minmax(230px, 1fr)); gap: 0 0.75rem; }
    .uf-opts { margin-top: 1rem; }
    .uf-stats { display: flex; gap: 1.5rem; flex-wrap: wrap; margin-bottom: 0.5rem; }
    .uf-ok { color: #047857; }
    .uf-bad { color: var(--mat-sys-error); }
    .uf-warn { color: #b45309; }
    .uf-report { width: 100%; border-collapse: collapse; margin-top: 0.75rem; }
    .uf-report th, .uf-report td { text-align: left; padding: 0.3rem 0.5rem; border-bottom: 1px solid #e5e7eb; vertical-align: top; font-size: 0.85rem; }
    .uf-err { background: #fef2f2; }
    .uf-chg { display: inline-block; margin-right: 0.75rem; }
    .uf-list { list-style: none; padding: 0; }
  `,
})
export class ImportPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly batch = signal<ImportBatchOut | null>(null);
  readonly past = signal<ImportBatchOut[]>([]);
  readonly filter = signal<'error' | 'changed' | 'all'>('error');
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly help = FIELD_HELP;
  mapping: Record<string, string | null> = {};
  options: ImportOptions = { decimal_separator: '.', thousands_separator: '', confirm_zero_price: false };
  skipInvalid = false;

  readonly summary = computed(() => (this.batch()?.report?.['summary'] as Summary | undefined) ?? null);
  private readonly reportRows = computed(() => (this.batch()?.report?.['rows'] as ReportRow[] | undefined) ?? []);
  private readonly filtered = computed(() => {
    const f = this.filter();
    return this.reportRows().filter((r) => f === 'all' || r.status === f);
  });
  readonly filteredCount = computed(() => this.filtered().length);
  readonly visibleRows = computed(() => this.filtered().slice(0, 500));
  readonly fieldCounts = computed(() => Object.entries(this.summary()?.changes_by_field ?? {}));

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
    this.mapping = Object.fromEntries((b.targets ?? []).map((t) => [t, (b.mapping ?? {})[t] ?? null]));
    const o = (b.options ?? {}) as Partial<ImportOptions>;
    this.options = { decimal_separator: o.decimal_separator ?? '.', thousands_separator: o.thousands_separator ?? '', confirm_zero_price: o.confirm_zero_price ?? false };
    this.filter.set(this.summary()?.errors ? 'error' : 'changed');
  }

  async upload(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    await this.run(async () => this.setBatch(await this.api.uploadImport(this.tenantId(), this.projectId(), file)));
    input.value = '';
  }

  async open(id: string): Promise<void> {
    await this.run(async () => this.setBatch(await this.api.getImport(this.tenantId(), id)));
  }

  dryRun(): Promise<void> {
    const mapping = Object.fromEntries(Object.entries(this.mapping).filter(([, h]) => !!h)) as Record<string, string>;
    return this.run(async () => this.setBatch(await this.api.dryRunImport(this.tenantId(), this.batch()!.id, mapping, this.options)));
  }

  apply(): Promise<void> {
    return this.run(async () => {
      try {
        this.setBatch(await this.api.applyImport(this.tenantId(), this.batch()!.id, this.skipInvalid));
      } catch (e) {
        if ((e as { status?: number }).status === 409) {
          this.error.set('The inventory changed since the dry run. The dry run was repeated: review the differences and apply again.');
          await this.dryRun();
          return;
        }
        throw e;
      }
      await this.loadPast();
    });
  }

  discard(): Promise<void> {
    return this.run(async () => {
      await this.api.discardImport(this.tenantId(), this.batch()!.id);
      this.batch.set(null);
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
