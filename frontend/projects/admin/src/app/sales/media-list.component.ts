import { ChangeDetectionStrategy, Component, input, output, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MatCheckboxModule } from '@angular/material/checkbox';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';
import { MatSelectModule } from '@angular/material/select';
import { MatSlideToggleModule } from '@angular/material/slide-toggle';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { MediaCreate, MediaOut, MediaUpdate } from 'api-client';
import { EmptyStateComponent, SectionCardComponent, StatusChipComponent, UF_ICONS } from 'ui';

export type MediaKind = NonNullable<MediaCreate['kind']>;
export const MEDIA_KINDS: { value: MediaKind; label: string }[] = [
  { value: 'plan_render', label: '3D plan render' },
  { value: 'interior_render', label: 'Interior render' },
  { value: 'exterior_render', label: 'Exterior render' },
  { value: 'photo', label: 'Photo' },
  { value: 'video', label: 'Video' },
  { value: 'document', label: 'Document' },
];
export function mediaKindLabel(k: string): string {
  return MEDIA_KINDS.find((m) => m.value === k)?.label ?? k;
}

export interface MediaUpload {
  file: File;
  kind: MediaKind;
  isPublic: boolean;
  ai: boolean;
}

/**
 * Renders, photos and documents of one owner (a unit or a layout, ADR-0022): upload, order,
 * visibility, AI disclosure. The owner's store does the API calls; this card only shows and asks.
 */
@Component({
  selector: 'uf-media-list',
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
      [title]="title()"
      tone="warning"
      icon="lucideImage"
      [count]="media().length"
      [summary]="summary()"
      [storageKey]="storageKey()"
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
        <label class="upload" [class.is-busy]="busy()">
          <ng-icon name="lucideUpload" /> Choose a file…
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,video/mp4,application/pdf"
            (change)="onFile($event)"
            [disabled]="busy()"
            hidden
          />
        </label>
      </div>
      <p class="uf-hint">{{ hint() }}</p>
      @for (m of media(); track m.id; let i = $index) {
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
                (change)="patch.emit({ m, body: { alt_text: $any($event.target).value || null } })"
            /></mat-form-field>
            <div class="uf-row">
              <mat-slide-toggle
                [checked]="m.is_public"
                (change)="patch.emit({ m, body: { is_public: $event.checked } })"
                >Public</mat-slide-toggle
              >
              <mat-slide-toggle
                [checked]="m.is_ai_generated"
                (change)="patch.emit({ m, body: { is_ai_generated: $event.checked } })"
                >AI-generated</mat-slide-toggle
              >
              <span class="uf-spacer"></span>
              <button
                mat-icon-button
                [disabled]="i === 0"
                (click)="move.emit({ i, delta: -1 })"
                aria-label="Move up"
                title="Move up"
              >
                <ng-icon name="lucideChevronDown" class="up" />
              </button>
              <button
                mat-icon-button
                [disabled]="i === media().length - 1"
                (click)="move.emit({ i, delta: 1 })"
                aria-label="Move down"
                title="Move down"
              >
                <ng-icon name="lucideChevronDown" />
              </button>
              <button mat-button (click)="remove.emit(m)">
                <ng-icon name="lucideTrash2" /> Delete
              </button>
            </div>
          </div>
        </div>
      } @empty {
        <uf-empty-state
          icon="lucideImage"
          title="No media yet"
          [text]="emptyText()"
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
export class MediaListComponent {
  readonly media = input.required<MediaOut[]>();
  readonly busy = input(false);
  readonly title = input('Media');
  readonly storageKey = input<string | null>(null);
  readonly hint = input(
    'Public files reach the portal with the next publication; AI-generated ones carry a label.',
  );
  readonly emptyText = input(
    'Add renders or photos; the first public image is the cover on the portal.',
  );
  readonly upload = output<MediaUpload>();
  readonly patch = output<{ m: MediaOut; body: Omit<MediaUpdate, 'version'> }>();
  readonly move = output<{ i: number; delta: number }>();
  readonly remove = output<MediaOut>();

  readonly kinds = MEDIA_KINDS;
  readonly kind = signal<MediaKind>('photo');
  readonly isPublic = signal(false);
  readonly ai = signal(false);
  label = mediaKindLabel;

  summary(): string {
    const m = this.media();
    const pub = m.filter((x) => x.is_public).length;
    return m.length ? `${pub} public · ${m.length - pub} internal` : 'nothing uploaded';
  }

  onFile(ev: Event): void {
    const input = ev.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    this.upload.emit({ file, kind: this.kind(), isPublic: this.isPublic(), ai: this.ai() });
    input.value = '';
  }
}
