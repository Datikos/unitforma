import { Component, inject, signal } from '@angular/core';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { ActivatedRoute, Router } from '@angular/router';
import { KratosFlow, KratosFlowFormComponent, KratosService, SessionStore } from 'auth-staff';

/** Staff sign-in: Kratos browser login flow with the one-time email code (plan §8.2). */
@Component({
  selector: 'uf-login-page',
  imports: [MatCardModule, MatProgressBarModule, KratosFlowFormComponent],
  template: `
    <div class="uf-login">
      <mat-card appearance="outlined">
        <mat-card-header><mat-card-title>Sign in to Unitforma</mat-card-title></mat-card-header>
        <mat-card-content>
          @if (busy()) { <mat-progress-bar mode="indeterminate" /> }
          @if (error()) { <p class="uf-error">{{ error() }}</p> }
          @if (flow(); as f) {
            <uf-kratos-flow-form [flow]="f" [groups]="['code', 'totp']" [busy]="busy()" (submitted)="submit($event)" />
          } @else if (!busy()) {
            <p class="uf-muted">Redirecting to the sign-in flow…</p>
          }
        </mat-card-content>
      </mat-card>
    </div>
  `,
  styles: `.uf-login { max-width: 420px; margin: 4rem auto; }`,
})
export class LoginPage {
  private readonly kratos = inject(KratosService);
  private readonly session = inject(SessionStore);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  readonly flow = signal<KratosFlow | null>(null);
  readonly busy = signal(false);
  readonly error = signal<string | null>(null);

  constructor() {
    void this.init();
  }

  private async init(): Promise<void> {
    const flowId = this.route.snapshot.queryParamMap.get('flow');
    if (!flowId) {
      // Already signed in? Go home. Otherwise let Kratos create a flow and come back with ?flow=.
      if (await this.session.refresh()) {
        await this.router.navigateByUrl(this.returnTo());
        return;
      }
      this.kratos.startBrowserFlow('login', { return_to: window.location.origin + '/login' });
      return;
    }
    this.busy.set(true);
    try {
      this.flow.set(await this.kratos.getFlow('login', flowId));
    } catch {
      this.error.set('This sign-in link expired. Starting a new one…');
      this.kratos.startBrowserFlow('login');
    } finally {
      this.busy.set(false);
    }
  }

  async submit(values: Record<string, unknown>): Promise<void> {
    const f = this.flow();
    if (!f) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      const r = await this.kratos.submit(f, values);
      if ('redirect' in r) {
        window.location.assign(r.redirect);
      } else if (r.done) {
        await this.session.refresh();
        await this.router.navigateByUrl(this.returnTo());
      } else {
        this.flow.set(r.flow);
      }
    } catch {
      this.error.set('Sign-in failed. Please try again.');
    } finally {
      this.busy.set(false);
    }
  }

  private returnTo(): string {
    const rt = this.route.snapshot.queryParamMap.get('return_to') ?? '/';
    return rt.startsWith('/') && !rt.startsWith('//') ? rt : '/';
  }
}
