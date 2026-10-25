import { Component, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { MatButtonModule } from '@angular/material/button';
import { MAT_DIALOG_DATA, MatDialogModule, MatDialogRef } from '@angular/material/dialog';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatInputModule } from '@angular/material/input';

export interface PromptOptions {
  title: string;
  message?: string;
  label: string;
  value?: string;
  placeholder?: string;
  hint?: string;
  required?: boolean;
  multiline?: boolean;
  confirmLabel?: string;
}

@Component({
  selector: 'uf-prompt-dialog',
  imports: [FormsModule, MatDialogModule, MatButtonModule, MatFormFieldModule, MatInputModule],
  template: `
    <h2 mat-dialog-title>{{ data.title }}</h2>
    <mat-dialog-content>
      @if (data.message) {
        <p class="msg">{{ data.message }}</p>
      }
      <mat-form-field appearance="outline" class="field">
        <mat-label>{{ data.label }}</mat-label>
        @if (data.multiline) {
          <textarea
            matInput
            rows="3"
            [ngModel]="value()"
            (ngModelChange)="value.set($event)"
            [placeholder]="data.placeholder ?? ''"
            cdkFocusInitial
          ></textarea>
        } @else {
          <input
            matInput
            [ngModel]="value()"
            (ngModelChange)="value.set($event)"
            [placeholder]="data.placeholder ?? ''"
            (keyup.enter)="ok()"
            cdkFocusInitial
          />
        }
        @if (data.hint) {
          <mat-hint>{{ data.hint }}</mat-hint>
        }
      </mat-form-field>
    </mat-dialog-content>
    <mat-dialog-actions align="end">
      <button mat-button type="button" (click)="ref.close(null)">Cancel</button>
      <button
        mat-flat-button
        type="button"
        [disabled]="data.required && !value().trim()"
        (click)="ok()"
      >
        {{ data.confirmLabel ?? 'OK' }}
      </button>
    </mat-dialog-actions>
  `,
  styles: `
    .msg {
      margin: 0 0 0.75rem;
      max-width: 52ch;
    }
    .field {
      width: min(100%, 28rem);
      display: block;
    }
  `,
})
export class PromptDialogComponent {
  readonly data = inject<PromptOptions>(MAT_DIALOG_DATA);
  readonly ref = inject(MatDialogRef<PromptDialogComponent, string | null>);
  readonly value = signal(this.data.value ?? '');

  ok(): void {
    if (this.data.required && !this.value().trim()) return;
    this.ref.close(this.value());
  }
}
