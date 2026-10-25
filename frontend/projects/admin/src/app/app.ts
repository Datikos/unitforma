import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatToolbarModule } from '@angular/material/toolbar';
import { Router, RouterLink, RouterOutlet } from '@angular/router';
import { KratosService, SessionStore } from 'auth-staff';

@Component({
  selector: 'uf-root',
  imports: [RouterOutlet, RouterLink, MatToolbarModule, MatButtonModule],
  template: `
    <mat-toolbar class="uf-topbar">
      <a routerLink="/" class="uf-brand">Unitforma</a>
      <span class="uf-spacer"></span>
      @if (session.me(); as me) {
        @if (me.is_platform_admin) {
          <a mat-button routerLink="/platform/tenants">Platform</a>
        }
        <span class="uf-user">{{ me.email }}</span>
        <button mat-button (click)="logout()">Sign out</button>
      }
    </mat-toolbar>
    <main class="uf-main"><router-outlet /></main>
  `,
  styles: `
    .uf-brand { color: inherit; text-decoration: none; font-weight: 600; letter-spacing: 0.02em; }
    .uf-spacer { flex: 1; }
    .uf-user { font-size: 0.875rem; opacity: 0.8; margin-right: 0.5rem; }
    .uf-main { padding: 1rem; max-width: 1200px; margin: 0 auto; }
  `,
})
export class App {
  protected readonly session = inject(SessionStore);
  private readonly kratos = inject(KratosService);
  private readonly router = inject(Router);

  async logout(): Promise<void> {
    try {
      await this.kratos.logout();
    } finally {
      this.session.clear();
      await this.router.navigate(['/login']);
    }
  }
}
