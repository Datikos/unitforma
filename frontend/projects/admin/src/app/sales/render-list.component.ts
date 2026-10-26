import { ChangeDetectionStrategy, Component, computed, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { NgIcon } from '@ng-icons/core';
import { RendersOut } from 'api-client';
import { SectionCardComponent, StatusChipComponent } from 'ui';

export interface RenderGenerate {
  note: string;
  /** Unit mode: the neighbour to join with; layout mode: the member unit whose plan is cropped. */
  withId: string | null;
}

/**
 * Generated 3D plan renders of one owner (ADR-0017 Decision 3, ADR-0022 Decision 4): request,
 * watch, review. In `unit` mode the picker joins a neighbour; in `layout` mode it picks the
 * member unit whose outline is cropped.
 */
@Component({
  selector: 'uf-render-list',
  imports: [
    FormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    NgIcon,
    SectionCardComponent,
    StatusChipComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <uf-section-card
      title="3D plan render (generated)"
      tone="pending"
      icon="lucideSparkles"
      [count]="items().length"
      [summary]="summary()"
      [storageKey]="storageKey()"
    >
      @if (renders(); as r) {
        <p class="uf-hint">{{ hint() }}</p>
        @if (!r.enabled) {
          <div class="uf-alert uf-alert--info">
            <span
              >Not enabled on this installation: set <code>UF_AI_IMAGE_PROVIDER=gemini</code> and
              the <code>ai_image_api_key</code> secret (ADR-0017).</span
            >
          </div>
        } @else {
          <div class="uf-form-row">
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="note">
              <mat-label>Note for the model (optional)</mat-label>
              <input
                matInput
                [ngModel]="note()"
                (ngModelChange)="note.set($event)"
                name="renderNote"
                maxlength="500"
                placeholder="e.g. oak floors, grey kitchen"
              />
            </mat-form-field>
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="join">
              <mat-label>{{ mode() === 'layout' ? 'Plan from unit' : 'Join with' }}</mat-label>
              <mat-select
                [ngModel]="withId()"
                (ngModelChange)="withId.set($event)"
                name="renderWith"
              >
                <mat-option [value]="null">{{
                  mode() === 'layout' ? '— first unit with an outline —' : '— this unit only —'
                }}</mat-option>
                @for (c of choices(); track c.id) {
                  <mat-option [value]="c.id">{{ c.code }}</mat-option>
                }
              </mat-select>
            </mat-form-field>
            <button
              mat-flat-button
              [disabled]="busy() || active() || r.used_today >= r.daily_limit"
              (click)="generate.emit({ note: note(), withId: withId() })"
            >
              <ng-icon name="lucideSparkles" /> Generate 3D plan render
            </button>
            <span class="uf-muted small">{{ costLine() }}</span>
          </div>
          @if (inReview()) {
            <p class="uf-hint">
              Approve only when walls, doors, windows and rooms match the plan; Reject deletes the
              image.
            </p>
          }
        }
        @for (it of r.items; track it.id) {
          <div class="item">
            @if (it.url) {
              <a [href]="it.url" target="_blank" rel="noopener" class="thumb">
                <img [src]="it.url" alt="Generated 3D plan" loading="lazy" />
              </a>
            } @else {
              <div class="ph"><ng-icon name="lucideImage" /></div>
            }
            <div class="meta uf-stack">
              <div class="uf-row">
                <uf-status-chip domain="render" [value]="it.status" />
                <span class="uf-muted small">{{ it.model }} · {{ when(it.created_at) }}</span>
                @if (it.cost_usd) {
                  <span class="uf-muted small">· \${{ it.cost_usd }}</span>
                }
              </div>
              @if (it.partner_code) {
                <div class="small">Joined with {{ it.partner_code }}: one enlarged apartment.</div>
              }
              @if (mode() === 'layout' && it.source_code) {
                <div class="small">Plan cropped from {{ it.source_code }}.</div>
              }
              @if (it.note) {
                <div class="small clamp" [title]="it.note">Note: {{ it.note }}</div>
              }
              @if (it.error) {
                <div class="uf-alert uf-alert--bad small">{{ it.error }}</div>
              }
              <div class="uf-row">
                @if (it.status === 'review') {
                  <button mat-flat-button [disabled]="busy()" (click)="approve.emit(it.id)">
                    <ng-icon name="lucideCheck" /> Approve and publish
                  </button>
                  <button mat-stroked-button [disabled]="busy()" (click)="reject.emit(it.id)">
                    <ng-icon name="lucideX" /> Reject
                  </button>
                }
                @if (it.status === 'failed') {
                  <button mat-button [disabled]="busy()" (click)="reject.emit(it.id)">Clear</button>
                }
                @if (it.status === 'queued' || it.status === 'running') {
                  <span class="uf-muted small"
                    >Working… usually 10 to 60 seconds; this list refreshes itself.</span
                  >
                }
              </div>
            </div>
          </div>
        } @empty {
          <p class="uf-muted">No render requested yet.</p>
        }
      } @else {
        <p class="uf-muted">Loading…</p>
      }
    </uf-section-card>
  `,
  styles: [
    `
      .note {
        flex: 1 1 16rem;
      }
      .join {
        flex: 0 1 14rem;
      }
      .item {
        display: grid;
        grid-template-columns: 9rem 1fr;
        gap: 0.75rem;
        padding: 0.6rem 0;
        border-top: 1px solid var(--uf-border);
      }
      .thumb img {
        width: 9rem;
        aspect-ratio: 4 / 3;
        object-fit: cover;
        border-radius: var(--uf-radius-sm);
        border: 1px solid var(--uf-border);
        background: #fff;
      }
      .ph {
        width: 9rem;
        aspect-ratio: 4 / 3;
        display: grid;
        place-items: center;
        color: var(--uf-text-muted);
        background: var(--uf-surface-2);
        border-radius: var(--uf-radius-sm);
      }
      .small {
        font-size: 0.85rem;
      }
      .clamp {
        display: -webkit-box;
        -webkit-line-clamp: 2;
        /* autoprefixer: ignore next */
        -webkit-box-orient: vertical;
        overflow: hidden;
        max-height: 2.8em;
      }
    `,
  ],
})
export class RenderListComponent {
  readonly renders = input.required<RendersOut | null>();
  readonly busy = input(false);
  readonly mode = input<'unit' | 'layout'>('unit');
  /** Unit mode: the neighbours on the same floor; layout mode: the member units. */
  readonly choices = input<{ id: string; code: string }[]>([]);
  readonly storageKey = input<string | null>(null);
  readonly hint = input(
    'A furnished 3D view made from the plan crop; private until approved, then labelled "AI generated".',
  );
  readonly generate = output<RenderGenerate>();
  readonly approve = output<string>();
  readonly reject = output<string>();

  readonly note = signal('');
  readonly withId = signal<string | null>(null);
  readonly items = computed(() => this.renders()?.items ?? []);
  readonly inReview = computed(() => this.items().some((i) => i.status === 'review'));
  readonly active = computed(() =>
    this.items().some((i) => i.status === 'queued' || i.status === 'running'),
  );
  readonly summary = computed(() => {
    const items = this.items();
    const review = items.filter((i) => i.status === 'review').length;
    const approved = items.filter((i) => i.status === 'approved').length;
    if (review) return `${review} awaiting review`;
    if (approved) return `${approved} approved`;
    return items.length ? 'none approved' : 'none yet';
  });
  readonly costLine = computed(() => {
    const r = this.renders();
    if (!r) return '';
    const cost =
      r.cost_per_image_usd != null ? `about $${r.cost_per_image_usd.toFixed(3)} per image · ` : '';
    return `${cost}${r.used_today} of ${r.daily_limit} today`;
  });

  when(iso: string): string {
    return new Date(iso).toLocaleString();
  }
}
