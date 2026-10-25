import { Injectable, inject } from '@angular/core';
import { MatSnackBar } from '@angular/material/snack-bar';

/** Result of an action lands here; errors that belong to a form stay inline next to it. */
@Injectable({ providedIn: 'root' })
export class ToastService {
  private readonly bar = inject(MatSnackBar);

  ok(message: string): void {
    this.bar.open(message, undefined, { duration: 3500, panelClass: 'uf-toast--ok' });
  }

  info(message: string, action?: string): Promise<boolean> {
    const ref = this.bar.open(message, action, { duration: action ? 8000 : 4000 });
    return new Promise((resolve) =>
      ref.afterDismissed().subscribe((d) => resolve(d.dismissedByAction)),
    );
  }

  fail(message: string): void {
    this.bar.open(message, 'Dismiss', { duration: 8000, panelClass: 'uf-toast--bad' });
  }
}
