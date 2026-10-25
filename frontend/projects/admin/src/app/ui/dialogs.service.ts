import { Injectable, inject } from '@angular/core';
import { MatDialog } from '@angular/material/dialog';
import { firstValueFrom } from 'rxjs';
import { ConfirmDialogComponent, ConfirmOptions } from './confirm-dialog.component';
import { PromptDialogComponent, PromptOptions } from './prompt-dialog.component';

/** Replaces `window.confirm` / `window.prompt` (ADR-0009 Decision 6). */
@Injectable({ providedIn: 'root' })
export class DialogsService {
  private readonly dialog = inject(MatDialog);

  async confirm(opts: ConfirmOptions): Promise<boolean> {
    const ref = this.dialog.open<ConfirmDialogComponent, ConfirmOptions, boolean>(
      ConfirmDialogComponent,
      { data: opts, autoFocus: 'first-tabbable', restoreFocus: true, maxWidth: '32rem' },
    );
    return (await firstValueFrom(ref.afterClosed())) === true;
  }

  async prompt(opts: PromptOptions): Promise<string | null> {
    const ref = this.dialog.open<PromptDialogComponent, PromptOptions, string | null>(
      PromptDialogComponent,
      { data: opts, autoFocus: 'first-tabbable', restoreFocus: true, maxWidth: '34rem' },
    );
    const v = await firstValueFrom(ref.afterClosed());
    return v === undefined ? null : v;
  }
}
