import { ChangeDetectionStrategy, Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { EmptyStateComponent, SectionCardComponent, StatusChipComponent, UF_ICONS } from 'ui';
import { MEDIA_KINDS, MediaKind, mediaKindLabel } from './unit-sales.model';
import { UnitSalesStore } from './unit-sales.store';

/** Renders, photos and documents of a unit: upload, order, visibility, AI disclosure. */
@Component({
  selector: 'uf-unit-media',
  imports: [
    FormsModule,
    MatButtonModule,
    MatCheckboxModule,
    MatFormFieldModule,
    MatInputModule,
    MatSelectModule,
    MatSlideToggleModule,
    NgIcon,
    SectionCardComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <uf-section-card
      title="Media"
      tone="warning"
      icon="lucideImage"
      [count]="store.media().length"
      [summary]="summary()"
      storageKey="unit-media"
    >
      <div class="uf-form-row">
        <mat-form-field appearance="outline" subscriptSizing="dynamic"
          ><mat-label>Kind</mat-label>
          <mat-select [ngModel]="kind()" (ngModelChange)="kind.set($event)" name="newKind">
            @for (k of kinds; track k.value) {
              <mat-option [value]="k.value">{{ k.label }}</mat-option>
            }
          </mat-select>
        </mat-form-field>
        <mat-checkbox [ngModel]="isPublic()" (ngModelChange)="isPublic.set($event)" name="newPublic"
          >Public</mat-checkbox
        >
        <mat-checkbox [ngModel]="ai()" (ngModelChange)="ai.set($event)" name="newAi"
          >AI-generated</mat-checkbox
        >
        <label class="upload" [class.is-busy]="store.busy()">
          <ng-icon name="lucideUpload" /> Choose a file…
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,video/mp4,application/pdf"
            (change)="onFile($event)"
            [disabled]="store.busy()"
            hidden
          />
        </label>
      </div>
      <p class="uf-hint">
        Public files reach the portal with the next publication; AI-generated ones carry a label.
      </p>
      @for (m of store.media(); track m.id; let i = $index) {
        <div class="item" [class.item--hidden]="!m.is_public">
          @if (m.url && m.mime.startsWith('image/')) {
            <img [src]="m.url" [alt]="m.alt_text ?? m.file_name" />
          } @else {
            <div class="ph"><ng-icon name="lucideFileText" />{{ label(m.kind) }}</div>
          }
          <div class="meta">
            <div class="uf-row">
              <strong>{{ m.file_name }}</strong>
              <span class="uf-chip">{{ label(m.kind) }}</span>
              <uf-status-chip domain="media" [value]="m.status" />
              @if (m.is_ai_generated) {
                <span class="uf-chip uf-tone-pending" [title]="m.ai_disclosure_text ?? ''"
                  ><ng-icon name="lucideSparkles" />AI-generated</span
                >
              }
            </div>
            <mat-form-field appearance="outline" subscriptSizing="dynamic" class="alt"
              ><mat-label>Alt text</mat-label
              ><input
                matInput
                [ngModel]="m.alt_text"
                (change)="store.patchMedia(m, { alt_text: $any($event.target).value || null })"
            /></mat-form-field>
            <div class="uf-row">
              <mat-slide-toggle
                [checked]="m.is_public"
                (change)="store.patchMedia(m, { is_public: $event.checked })"
                >Public</mat-slide-toggle
              >
              <mat-slide-toggle
                [checked]="m.is_ai_generated"
                (change)="store.patchMedia(m, { is_ai_generated: $event.checked })"
                >AI-generated</mat-slide-toggle
              >
              <span class="uf-spacer"></span>
              <button
                mat-icon-button
                [disabled]="i === 0"
                (click)="store.move(i, -1)"
                aria-label="Move up"
                title="Move up"
              >
                <ng-icon name="lucideChevronDown" class="up" />
              </button>
              <button
                mat-icon-button
                [disabled]="i === store.media().length - 1"
                (click)="store.move(i, 1)"
                aria-label="Move down"
                title="Move down"
              >
                <ng-icon name="lucideChevronDown" />
              </button>
              <button mat-button (click)="store.remove(m)">
                <ng-icon name="lucideTrash2" /> Delete
              </button>
            </div>
          </div>
        </div>
      } @empty {
        <uf-empty-state
          icon="lucideImage"
          title="No media yet"
          text="Add renders or photos; the first public image is the unit's cover on the portal."
          [compact]="true"
        />
      }
    </uf-section-card>
  `,
  styles: `
    .upload {
      display: inline-flex;
      align-items: center;
      gap: 0.4rem;
      padding: 0.5rem 0.9rem;
      border: 1px dashed var(--uf-border-strong);
      border-radius: var(--uf-radius-sm);
      cursor: pointer;
      color: var(--uf-primary);
      font-weight: 600;
    }
    .upload.is-busy {
      opacity: 0.5;
      pointer-events: none;
    }
    .item {
      display: flex;
      gap: 0.75rem;
      align-items: flex-start;
      border: 1px solid var(--uf-border);
      border-radius: var(--uf-radius-sm);
      padding: 0.5rem;
    }
    .item--hidden {
      opacity: 0.75;
    }
    .item img,
    .ph {
      width: 160px;
      height: 110px;
      object-fit: cover;
      border-radius: 6px;
      background: var(--uf-surface-2);
      display: grid;
      place-items: center;
      flex: none;
      color: var(--uf-muted);
      font-size: 0.8rem;
    }
    .meta {
      display: grid;
      gap: 0.4rem;
      flex: 1;
      min-width: 0;
    }
    .alt {
      max-width: 32rem;
    }
    .up {
      transform: rotate(180deg);
    }
    button ng-icon {
      vertical-align: -0.15em;
    }
  `,
})
export class UnitMediaComponent {
  protected readonly store = inject(UnitSalesStore);
  readonly kinds = MEDIA_KINDS;
  readonly kind = signal<MediaKind>('photo');
  readonly isPublic = signal(false);
  readonly ai = signal(false);
  label = mediaKindLabel;

  summary(): string {
    const m = this.store.media();
    const pub = m.filter((x) => x.is_public).length;
    return m.length ? `${pub} public · ${m.length - pub} internal` : 'nothing uploaded';
  }

  async onFile(ev: Event): Promise<void> {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    await this.store.upload(file, this.kind(), this.isPublic(), this.ai());
    input.value = '';
  }
}
