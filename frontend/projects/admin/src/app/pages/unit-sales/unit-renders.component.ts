import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { NgIcon } from '@ng-icons/core';
import { SectionCardComponent, StatusChipComponent } from 'ui';
import { UnitSalesStore } from './unit-sales.store';

/** Generated 3D plan renders of the unit (ADR-0017 Decision 3): request, watch, review. */
@Component({
  selector: 'uf-unit-renders',
  imports: [
    FormsModule,
    MatButtonModule,
    MatFormFieldModule,
    MatInputModule,
    NgIcon,
    SectionCardComponent,
    StatusChipComponent,
  ],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <uf-section-card
      title="3D plan render (generated)"
      icon="lucideSparkles"
      [count]="items().length"
      [summary]="summary()"
      storageKey="unit-renders"
    >
      @if (store.renders(); as r) {
        <p class="uf-hint">
          The floor plan of this unit, cropped to its outline, is sent to an image model that
          returns a furnished 3D cutaway view. The result stays private until you approve it; buyers
          then see it labelled "Illustrative — AI generated", and every unit with the same layout
          code shows it too.
        </p>
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
            <button
              mat-flat-button
              [disabled]="store.busy() || active() || r.used_today >= r.daily_limit"
              (click)="generate()"
            >
              <ng-icon name="lucideSparkles" /> Generate 3D plan render
            </button>
            <span class="uf-muted small">{{ costLine() }}</span>
          </div>
          <p class="uf-hint">
            Review before approving: walls, doors, windows and rooms must match the plan; furniture
            and finishes are illustrative. Rejecting deletes the image; the request stays in the
            list.
          </p>
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
              @if (it.note) {
                <div class="small">Note: {{ it.note }}</div>
              }
              @if (it.error) {
                <div class="uf-alert uf-alert--bad small">{{ it.error }}</div>
              }
              <div class="uf-row">
                @if (it.status === 'review') {
                  <button
                    mat-flat-button
                    [disabled]="store.busy()"
                    (click)="store.approveRender(it.id)"
                  >
                    <ng-icon name="lucideCheck" /> Approve and publish
                  </button>
                  <button
                    mat-stroked-button
                    [disabled]="store.busy()"
                    (click)="store.rejectRender(it.id)"
                  >
                    <ng-icon name="lucideX" /> Reject
                  </button>
                }
                @if (it.status === 'failed') {
                  <button mat-button [disabled]="store.busy()" (click)="store.rejectRender(it.id)">
                    Clear
                  </button>
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
    `,
  ],
})
export class UnitRendersComponent {
  protected readonly store = inject(UnitSalesStore);
  readonly note = signal('');
  readonly items = computed(() => this.store.renders()?.items ?? []);
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
    const r = this.store.renders();
    if (!r) return '';
    const cost =
      r.cost_per_image_usd != null ? `about $${r.cost_per_image_usd.toFixed(3)} per image · ` : '';
    return `${cost}${r.used_today} of ${r.daily_limit} today`;
  });

  when(iso: string): string {
    return new Date(iso).toLocaleString();
  }

  async generate(): Promise<void> {
    await this.store.requestRender(this.note());
  }
}
