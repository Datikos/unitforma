import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { Tone, UF_ICONS } from 'ui';

export interface ConfirmOptions {
  title: string;
  message: string;
  /** One sentence on what happens next, shown under the message ("Buyers stop seeing the project"). */
  consequence?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  /** `bad` paints the confirm button red for destructive actions. */
  tone?: Tone;
  icon?: string;
}

@Component({
  selector: 'uf-confirm-dialog',
  imports: [MatDialogModule, MatButtonModule, NgIcon],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <h2 mat-dialog-title class="dlg__title">
      <ng-icon
        [name]="data.icon ?? (data.tone === 'bad' ? 'lucideTriangleAlert' : 'lucideCircleHelp')"
        class="dlg__icon dlg__icon--{{ data.tone ?? 'info' }}"
        aria-hidden="true"
      />
      {{ data.title }}
    </h2>
    <mat-dialog-content>
      <p class="dlg__msg">{{ data.message }}</p>
      @if (data.consequence) {
        <p class="uf-hint">{{ data.consequence }}</p>
      }
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" (click)="ref.close(false)">
        {{ data.cancelLabel ?? 'Cancel' }}
      </button>
      <button
        mat-flat-button
        type="button"
        cdkFocusInitial
        [class.dlg__danger]="data.tone === 'bad'"
        (click)="ref.close(true)"
      >
        {{ data.confirmLabel ?? 'Confirm' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    .dlg__title {
      display: flex;
      align-items: center;
      gap: 0.5rem;
    }
    .dlg__icon--bad {
      color: var(--uf-tone-bad-fg);
    }
    .dlg__icon--warning {
      color: var(--uf-tone-warning-fg);
    }
    .dlg__icon--info,
    .dlg__icon--neutral,
    .dlg__icon--good,
    .dlg__icon--pending {
      color: var(--uf-primary);
    }
    .dlg__msg {
      margin: 0;
      max-width: 52ch;
    }
    .dlg__danger {
      --mat-button-filled-container-color: var(--uf-tone-bad-fg);
      --mat-button-filled-label-text-color: #fff;
    }
  `,
})
export class ConfirmDialogComponent {
  readonly data = inject<ConfirmOptions>(MAT_DIALOG_DATA);
  readonly ref = inject(MatDialogRef<ConfirmDialogComponent, boolean>);
}
