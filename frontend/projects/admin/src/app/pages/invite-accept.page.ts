import { Component, inject, input, signal } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { Router, RouterLink } from '@angular/router';
import { UnitformaApi, problemMessage } from 'api-client';
import { SessionStore } from 'auth-staff';

/** Accept a staff invitation: the signed-in user's verified email must match the invitation. */
@Component({
  selector: 'uf-invite-accept-page',
  imports: [MatCardModule, MatButtonModule, RouterLink],
  template: `
    <div class="uf-invite">
      <a routerLink="/" class="brand"
        ><span class="brand__logo" aria-hidden="true">U</span>Unitforma</a
      >
      <mat-card appearance="outlined">
        <mat-card-header><mat-card-title>Join a workspace</mat-card-title></mat-card-header>
        <mat-card-content>
          <p>
            You are signed in as <strong>{{ session.me()?.email }}</strong
            >. Accept the invitation issued to this address?
          </p>
          @if (error()) {
            <p class="uf-error">{{ error() }}</p>
          }
        </mat-card-content>
        <mat-card-actions
          ><button mat-flat-button [disabled]="busy()" (click)="accept()">
            Accept invitation
          </button></mat-card-actions
        >
      </mat-card>
    </div>
  `,
  styles: `
    .uf-invite {
      max-width: 480px;
      margin: 8vh auto;
      display: grid;
      gap: 1rem;
    }
    .brand {
      display: flex;
      align-items: center;
      gap: 0.6rem;
      justify-content: center;
      color: var(--uf-text);
      text-decoration: none;
      font-weight: 700;
      font-size: 1.25rem;
    }
    .brand__logo {
      display: grid;
      place-items: center;
      width: 2.2rem;
      height: 2.2rem;
      border-radius: 9px;
      background: linear-gradient(135deg, #6366f1, #2563eb);
      color: #fff;
      font-weight: 800;
    }
  `,
})
export class InviteAcceptPage {
  private readonly api = inject(UnitformaApi);
  private readonly router = inject(Router);
  protected readonly session = inject(SessionStore);
  readonly token = input.required<string>();
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  async accept(): Promise<void> {
    this.busy.set(true);
    this.error.set(null);
    try {
      const m = await this.api.acceptInvitation(this.token());
      await this.session.refresh();
      await this.router.navigate(['/t', m.tenant_id]);
    } catch (e) {
      this.error.set(problemMessage(e));
    } finally {
      this.busy.set(false);
    }
  }
}
