import { JsonPipe, SlicePipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { toObservable } from '@angular/core/rxjs-interop';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { RouterLink } from '@angular/router';
import { InventoryRow, MediaCreate, MediaOut, MediaUpdate, PaymentPlanOut, PromotionOut, SalesChanges, SalesHistoryOut, UnitformaApi, problemMessage } from 'api-client';
import { AVAILABILITY, PUBLIC_FIELDS, formatPrice, httpStatus, parsePriceInput, problemBody } from '../sales/sales-format';

interface Form {
  availability: InventoryRow['availability'];
  list_price: string;
  currency: string;
  price_on_request: boolean;
  price_area_type: string | null;
  payment_plan_id: string | null;
  promotion_ids: string[];
  rooms: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  orientation: string;
  public_description: string;
  internal_notes: string;
}

interface TimelineEntry {
  at: string;
  text: string;
  reason?: string | null;
}

type MediaKind = NonNullable<MediaCreate['kind']>;

/** Unit commercial detail (plan §11.2 "Unit detail"): pricing & terms, publication fields, media, history. */
@Component({
  selector: 'uf-unit-sales-page',
  imports: [FormsModule, JsonPipe, SlicePipe, RouterLink, MatButtonModule, MatCardModule, MatCheckboxModule, MatFormFieldModule, MatInputModule, MatSelectModule, MatSlideToggleModule],
  template: `
    <div class="uf-page">
      <div class="uf-page-header">
        <h2>@if (row(); as r) { {{ r.code }} · {{ r.unit_type }} · level {{ r.floor_level }} }</h2>
        <a mat-stroked-button routerLink="..">Inventory</a>
      </div>
      @if (error()) { <p class="uf-error" role="alert">{{ error() }}</p> }
      @if (conflict(); as c) {
        <mat-card appearance="outlined" class="uf-conflict" role="alert">
          <mat-card-content>
            <strong>Someone else changed this unit</strong> (now version {{ c.version }}). Fields you edited:
            @for (k of conflictKeys(); track k) {
              <div><span class="uf-muted">{{ k }}</span>: yours <code>{{ show(pending(), k) }}</code> · current <code>{{ show(c, k) }}</code></div>
            }
          </mat-card-content>
          <mat-card-actions>
            <button mat-flat-button (click)="saveOnTop()">Apply mine on top of the current version</button>
            <button mat-button (click)="discardMine()">Load the current values</button>
          </mat-card-actions>
        </mat-card>
      }
      @if (row(); as r) {
        <div class="uf-grid2">
          <mat-card appearance="outlined">
            <mat-card-header>
              <mat-card-title>Pricing &amp; terms</mat-card-title>
              <mat-card-subtitle>
                version {{ r.version }} · {{ r.verification_status }} · {{ r.publication_status }}
                @if (r.price_per_m2) { · {{ fmt(r.price_per_m2, r.currency) }} per m² {{ r.price_area_type }} ({{ r.price_area_verified ? 'verified' : 'unverified' }}) }
              </mat-card-subtitle>
            </mat-card-header>
            <mat-card-content class="uf-form">
              <div class="uf-row">
                <mat-form-field appearance="outline"><mat-label>Availability</mat-label>
                  <mat-select [(ngModel)]="form.availability" name="availability">
                    @for (a of availability; track a) { <mat-option [value]="a">{{ a }}</mat-option> }
                  </mat-select>
                </mat-form-field>
                <mat-form-field appearance="outline" class="uf-grow"><mat-label>Reason for the change</mat-label><input matInput [(ngModel)]="reason" name="reason" [placeholder]="r.availability === 'sold' ? 'required when a sold unit changes' : 'optional'" /></mat-form-field>
              </div>
              <div class="uf-row">
                <mat-form-field appearance="outline"><mat-label>Price</mat-label><input matInput [(ngModel)]="form.list_price" name="price" placeholder="empty = on request" /></mat-form-field>
                <mat-form-field appearance="outline" class="uf-ccy"><mat-label>Currency</mat-label><input matInput [(ngModel)]="form.currency" name="currency" maxlength="3" /></mat-form-field>
                <mat-checkbox [(ngModel)]="form.price_on_request" name="por">Price on request</mat-checkbox>
                <mat-checkbox [(ngModel)]="confirmZero" name="zero">Price 0 is intended</mat-checkbox>
              </div>
              <div class="uf-row">
                <mat-form-field appearance="outline"><mat-label>Price per m² based on</mat-label>
                  <mat-select [(ngModel)]="form.price_area_type" name="pat">
                    <mat-option [value]="null">Project default</mat-option>
                    @for (a of areaDefs(); track a.key) { <mat-option [value]="a.key">{{ a.label ?? a.key }}</mat-option> }
                  </mat-select>
                </mat-form-field>
                <mat-form-field appearance="outline"><mat-label>Payment plan</mat-label>
                  <mat-select [(ngModel)]="form.payment_plan_id" name="plan">
                    <mat-option [value]="null">— none —</mat-option>
                    @for (p of plans(); track p.id) { <mat-option [value]="p.id">{{ p.name }}@if (!p.is_public) { (internal) }</mat-option> }
                  </mat-select>
                </mat-form-field>
                <mat-form-field appearance="outline"><mat-label>Promotions</mat-label>
                  <mat-select [(ngModel)]="form.promotion_ids" name="promos" multiple>
                    @for (p of promotions(); track p.id) { <mat-option [value]="p.id">{{ p.name }}</mat-option> }
                  </mat-select>
                </mat-form-field>
              </div>
              <div class="uf-row">
                <mat-form-field appearance="outline" class="uf-num"><mat-label>Rooms</mat-label><input matInput type="number" min="0" [(ngModel)]="form.rooms" name="rooms" /></mat-form-field>
                <mat-form-field appearance="outline" class="uf-num"><mat-label>Bedrooms</mat-label><input matInput type="number" min="0" [(ngModel)]="form.bedrooms" name="bedrooms" /></mat-form-field>
                <mat-form-field appearance="outline" class="uf-num"><mat-label>Bathrooms</mat-label><input matInput type="number" min="0" [(ngModel)]="form.bathrooms" name="bathrooms" /></mat-form-field>
                <mat-form-field appearance="outline" class="uf-num"><mat-label>Orientation</mat-label><input matInput [(ngModel)]="form.orientation" name="orientation" maxlength="20" /></mat-form-field>
              </div>
              <mat-form-field appearance="outline"><mat-label>Public description</mat-label><textarea matInput rows="3" [(ngModel)]="form.public_description" name="pd"></textarea></mat-form-field>
              <mat-form-field appearance="outline"><mat-label>Internal notes (never published)</mat-label><textarea matInput rows="2" [(ngModel)]="form.internal_notes" name="notes"></textarea></mat-form-field>
            </mat-card-content>
            <mat-card-actions>
              <button mat-flat-button [disabled]="busy() || !dirty()" (click)="save()">Save {{ dirtyCount() }} change(s)</button>
              <button mat-button [disabled]="busy() || !dirty()" (click)="reset()">Undo</button>
            </mat-card-actions>
          </mat-card>

          <mat-card appearance="outlined">
            <mat-card-header><mat-card-title>Shown to buyers</mat-card-title><mat-card-subtitle>Per-unit overrides of the project defaults</mat-card-subtitle></mat-card-header>
            <mat-card-content>
              @for (f of publicFields; track f.key) {
                <div class="uf-toggle">
                  <mat-slide-toggle [checked]="r.public_fields[f.key]" (change)="togglePublic(f.key, $event.checked)">{{ f.label }}</mat-slide-toggle>
                  @if (f.key in r.public_field_overrides) { <span class="uf-muted">overridden</span> } @else { <span class="uf-muted">project default</span> }
                </div>
              }
              <button mat-button [disabled]="!hasOverrides()" (click)="clearOverrides()">Reset to project defaults</button>
              <h4>Buyer preview</h4>
              <pre class="uf-pre">{{ preview() | json }}</pre>
            </mat-card-content>
          </mat-card>
        </div>

        <mat-card appearance="outlined">
          <mat-card-header><mat-card-title>Media</mat-card-title><mat-card-subtitle>Order, visibility and AI-generated flag are stored with each file</mat-card-subtitle></mat-card-header>
          <mat-card-content>
            <div class="uf-row">
              <mat-form-field appearance="outline"><mat-label>Kind</mat-label>
                <mat-select [(ngModel)]="newKind" name="newKind">
                  @for (k of mediaKinds; track k) { <mat-option [value]="k">{{ k }}</mat-option> }
                </mat-select>
              </mat-form-field>
              <mat-checkbox [(ngModel)]="newAi" name="newAi">AI-generated</mat-checkbox>
              <mat-checkbox [(ngModel)]="newPublic" name="newPublic">Public</mat-checkbox>
              <input type="file" accept="image/jpeg,image/png,image/webp,video/mp4,application/pdf" (change)="upload($event)" [disabled]="busy()" />
            </div>
            <div class="uf-media">
              @for (m of media(); track m.id; let i = $index) {
                <div class="uf-media__item">
                  @if (m.url && m.mime.startsWith('image/')) { <img [src]="m.url" [alt]="m.alt_text ?? m.file_name" /> } @else { <div class="uf-media__ph">{{ m.kind }}</div> }
                  <div class="uf-media__meta">
                    <strong>{{ m.file_name }}</strong> <span class="uf-muted">{{ m.kind }} · {{ m.status }}</span>
                    <mat-form-field appearance="outline"><mat-label>Alt text</mat-label><input matInput [ngModel]="m.alt_text" (change)="patchMedia(m, { alt_text: $any($event.target).value || null })" /></mat-form-field>
                    <mat-slide-toggle [checked]="m.is_public" (change)="patchMedia(m, { is_public: $event.checked })">Public</mat-slide-toggle>
                    <mat-slide-toggle [checked]="m.is_ai_generated" (change)="patchMedia(m, { is_ai_generated: $event.checked })">AI-generated</mat-slide-toggle>
                    @if (m.is_ai_generated) { <span class="uf-ai">{{ m.ai_disclosure_text }}</span> }
                    <span>
                      <button mat-button [disabled]="i === 0" (click)="move(i, -1)" aria-label="Move up">↑</button>
                      <button mat-button [disabled]="i === media().length - 1" (click)="move(i, 1)" aria-label="Move down">↓</button>
                      <button mat-button (click)="remove(m)">Delete</button>
                    </span>
                  </div>
                </div>
              } @empty { <p class="uf-muted">No media yet.</p> }
            </div>
          </mat-card-content>
        </mat-card>

        <mat-card appearance="outlined">
          <mat-card-header><mat-card-title>History</mat-card-title></mat-card-header>
          <mat-card-content>
            <ul class="uf-timeline">
              @for (e of timeline(); track $index) {
                <li><code>{{ e.at | slice: 0 : 16 }}</code> {{ e.text }} @if (e.reason) { <span class="uf-muted">— {{ e.reason }}</span> }</li>
              } @empty { <li class="uf-muted">No changes yet.</li> }
            </ul>
          </mat-card-content>
        </mat-card>
      }
    </div>
  `,
  styles: `
    .uf-grid2 { display: grid; grid-template-columns: 2fr 1fr; gap: 1rem; }
    @media (max-width: 1100px) { .uf-grid2 { grid-template-columns: 1fr; } }
    .uf-form { display: grid; gap: 0.25rem; }
    .uf-row { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
    .uf-grow { flex: 1; min-width: 220px; }
    .uf-num { width: 120px; }
    .uf-ccy { width: 100px; }
    .uf-toggle { display: flex; gap: 0.75rem; align-items: center; margin: 0.25rem 0; }
    .uf-pre { background: #f9fafb; padding: 0.5rem; font-size: 0.75rem; max-height: 320px; overflow: auto; }
    .uf-conflict { border-color: #d97706; background: #fffbeb; }
    .uf-media { display: grid; gap: 0.75rem; }
    .uf-media__item { display: flex; gap: 0.75rem; align-items: flex-start; border-bottom: 1px solid #e5e7eb; padding-bottom: 0.5rem; }
    .uf-media__item img, .uf-media__ph { width: 160px; height: 110px; object-fit: cover; background: #f3f4f6; display: grid; place-items: center; }
    .uf-media__meta { display: flex; gap: 0.5rem; align-items: center; flex-wrap: wrap; }
    .uf-ai { font-size: 0.8rem; background: #ede9fe; padding: 0.1rem 0.4rem; border-radius: 4px; }
    .uf-timeline { list-style: none; padding: 0; display: grid; gap: 0.25rem; }
  `,
})
export class UnitSalesPage {
  private readonly api = inject(UnitformaApi);
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
  readonly unitId = input.required<string>();
  readonly row = signal<InventoryRow | null>(null);
  readonly plans = signal<PaymentPlanOut[]>([]);
  readonly promotions = signal<PromotionOut[]>([]);
  readonly media = signal<MediaOut[]>([]);
  readonly history = signal<SalesHistoryOut | null>(null);
  readonly preview = signal<Record<string, unknown> | null>(null);
  readonly areaDefs = signal<{ key: string; label?: string }[]>([]);
  readonly conflict = signal<InventoryRow | null>(null);
  readonly pending = signal<SalesChanges>({});
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);
  readonly availability = AVAILABILITY;
  readonly publicFields = PUBLIC_FIELDS;
  readonly mediaKinds: MediaKind[] = ['plan_render', 'interior_render', 'exterior_render', 'photo', 'video', 'document'];
  readonly conflictKeys = computed(() => Object.keys(this.pending()));
  readonly hasOverrides = computed(() => Object.keys(this.row()?.public_field_overrides ?? {}).length > 0);
  readonly timeline = computed<TimelineEntry[]>(() => {
    const h = this.history();
    if (!h) return [];
    const out: TimelineEntry[] = [
      ...h.prices.map((p) => ({ at: p.changed_at, text: `price ${formatPrice(p.old_price, p.old_currency) ?? '∅'} → ${formatPrice(p.new_price, p.new_currency) ?? '∅'}${p.import_batch_id ? ' (import)' : ''}`, reason: p.reason })),
      ...h.availability.map((a) => ({ at: a.changed_at, text: `availability ${a.old_availability ?? '∅'} → ${a.new_availability}`, reason: a.reason })),
      ...h.audit
        .filter((a) => !['list_price', 'currency', 'availability'].some((k) => a.after && k in a.after))
        .map((a) => ({ at: a.at, text: `${a.action} ${a.entity_type} ${summarise(a.before)} → ${summarise(a.after)}`, reason: null })),
    ];
    return out.sort((x, y) => y.at.localeCompare(x.at));
  });
  form: Form = blankForm();
  reason = '';
  confirmZero = false;
  newKind: MediaKind = 'photo';
  newAi = false;
  newPublic = false;

  constructor() {
    toObservable(this.unitId).subscribe(() => void this.load());
  }

  fmt(v: string | null | undefined, c: string): string {
    return formatPrice(v, c) ?? '';
  }

  show(obj: object, key: string): string {
    const v = (obj as Record<string, unknown>)[key];
    if (v === null || v === undefined || v === '') return '∅';
    return Array.isArray(v) ? v.join(', ') : String(v);
  }

  async load(): Promise<void> {
    try {
      const [row, plans, promos, media, history, preview, settings] = await Promise.all([
        this.api.getUnitSales(this.tenantId(), this.unitId()),
        this.api.listPaymentPlans(this.tenantId(), this.projectId()),
        this.api.listPromotions(this.tenantId(), this.projectId()),
        this.api.listMedia(this.tenantId(), this.unitId()),
        this.api.unitSalesHistory(this.tenantId(), this.unitId()),
        this.api.unitPublicPreview(this.tenantId(), this.unitId()),
        this.api.getSalesSettings(this.tenantId(), this.projectId()),
      ]);
      this.plans.set(plans);
      this.promotions.set(promos);
      this.media.set(media);
      this.history.set(history);
      this.preview.set(preview);
      this.areaDefs.set(settings.area_definitions as { key: string; label?: string }[]);
      this.setRow(row);
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  private setRow(row: InventoryRow): void {
    this.row.set(row);
    this.form = formFrom(row);
    this.reason = '';
    this.confirmZero = false;
  }

  /** Only the fields the user changed are sent, so a save never overwrites unrelated edits. */
  changes(): SalesChanges | null {
    const r = this.row();
    if (!r) return null;
    const base = formFrom(r);
    const out: Record<string, unknown> = {};
    for (const k of Object.keys(this.form) as (keyof Form)[]) {
      const a = JSON.stringify(this.form[k] ?? null);
      const b = JSON.stringify(base[k] ?? null);
      if (a !== b) out[k] = this.form[k];
    }
    if ('list_price' in out) {
      const p = parsePriceInput(out['list_price']);
      if (p === undefined) throw new Error('The price must be digits with at most two decimals');
      out['list_price'] = p;
    }
    for (const k of ['orientation', 'public_description', 'internal_notes']) if (k in out && out[k] === '') out[k] = null;
    if ('currency' in out) out['currency'] = String(out['currency']).toUpperCase();
    for (const k of ['rooms', 'bedrooms', 'bathrooms']) if (k in out) out[k] = out[k] === null || out[k] === '' ? null : Number(out[k]);
    return out as SalesChanges;
  }

  dirty(): boolean {
    try {
      return Object.keys(this.changes() ?? {}).length > 0;
    } catch {
      return true;
    }
  }

  dirtyCount(): number {
    try {
      return Object.keys(this.changes() ?? {}).length;
    } catch {
      return 0;
    }
  }

  reset(): void {
    const r = this.row();
    if (r) this.setRow(r);
  }

  async save(): Promise<void> {
    let changes: SalesChanges;
    try {
      changes = this.changes() ?? {};
    } catch (e) {
      this.error.set((e as Error).message);
      return;
    }
    await this.send(changes, this.row()!.version);
  }

  private async send(changes: SalesChanges, version: number): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.updateUnitSales(this.tenantId(), this.unitId(), { ...changes, version, reason: this.reason || null, confirm_zero_price: this.confirmZero });
      this.conflict.set(null);
      this.pending.set({});
      await this.load();
    } catch (e) {
      const body = problemBody(e);
      if (httpStatus(e) === 409 && body?.['current']) {
        this.pending.set(changes);
        this.conflict.set(body['current'] as InventoryRow);
      } else {
        this.error.set(problemMessage(e));
      }
    } finally {
      this.busy.set(false);
    }
  }

  saveOnTop(): Promise<void> {
    const c = this.conflict();
    return c ? this.send(this.pending(), c.version) : Promise.resolve();
  }

  discardMine(): void {
    const c = this.conflict();
    if (c) this.setRow(c);
    this.conflict.set(null);
    this.pending.set({});
  }

  togglePublic(key: string, value: boolean): Promise<void> {
    const r = this.row()!;
    return this.send({ public_fields: { ...r.public_field_overrides, [key]: value } as SalesChanges['public_fields'] }, r.version);
  }

  clearOverrides(): Promise<void> {
    return this.send({ public_fields: {} }, this.row()!.version);
  }

  async upload(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const intent = await this.api.createMedia(this.tenantId(), this.unitId(), { file_name: file.name, content_type: file.type || 'application/octet-stream', byte_size: file.size, kind: this.newKind, is_public: this.newPublic, is_ai_generated: this.newAi });
      await this.api.uploadToPresignedUrl(intent.upload_url, file, file.type);
      await this.api.completeMedia(this.tenantId(), intent.media.id);
      input.value = '';
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }

  async patchMedia(m: MediaOut, body: Omit<MediaUpdate, 'version'>): Promise<void> {
    try {
      await this.api.updateMedia(this.tenantId(), m.id, { ...body, version: m.version });
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  async move(i: number, delta: number): Promise<void> {
    const ids = this.media().map((m) => m.id);
    [ids[i], ids[i + delta]] = [ids[i + delta], ids[i]];
    try {
      this.media.set(await this.api.reorderMedia(this.tenantId(), this.unitId(), ids));
      this.preview.set(await this.api.unitPublicPreview(this.tenantId(), this.unitId()));
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }

  async remove(m: MediaOut): Promise<void> {
    if (!window.confirm(`Delete ${m.file_name}?`)) return;
    try {
      await this.api.deleteMedia(this.tenantId(), m.id);
      await this.load();
    } catch (e) {
      this.error.set(problemMessage(e));
    }
  }
}

function blankForm(): Form {
  return { availability: 'available', list_price: '', currency: '', price_on_request: false, price_area_type: null, payment_plan_id: null, promotion_ids: [], rooms: null, bedrooms: null, bathrooms: null, orientation: '', public_description: '', internal_notes: '' };
}

function formFrom(r: InventoryRow): Form {
  return {
    availability: r.availability,
    list_price: r.list_price ?? '',
    currency: r.currency,
    price_on_request: r.price_on_request,
    price_area_type: r.price_area_type_override ?? null,
    payment_plan_id: r.payment_plan_id ?? null,
    promotion_ids: [...(r.promotion_ids ?? [])],
    rooms: r.rooms ?? null,
    bedrooms: r.bedrooms ?? null,
    bathrooms: r.bathrooms ?? null,
    orientation: r.orientation ?? '',
    public_description: r.public_description ?? '',
    internal_notes: r.internal_notes ?? '',
  };
}

function summarise(v: Record<string, unknown> | null | undefined): string {
  if (!v) return '∅';
  return Object.entries(v)
    .filter(([k]) => !['code', 'import_batch_id', 'reason', 'media_id'].includes(k))
    .map(([k, x]) => `${k}=${typeof x === 'object' ? JSON.stringify(x) : x}`)
    .join(', ');
}
