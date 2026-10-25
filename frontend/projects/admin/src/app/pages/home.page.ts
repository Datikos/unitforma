import { Component, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatListModule } from '@angular/material/list';
import { RouterLink } from '@angular/router';
import { SessionStore } from 'auth-staff';

@Component({
  selector: 'uf-home-page',
  imports: [MatCardModule, MatListModule, MatButtonModule, RouterLink],
  template: `
    <div class="uf-page">
      <h1>Your workspaces</h1>
      @if (session.me(); as me) {
        @if (me.memberships.length === 0 && !me.is_platform_admin) {
          <mat-card appearance="outlined"><mat-card-content>
            <p>You are signed in as {{ me.email }} but are not a member of any developer workspace yet.</p>
            <p class="uf-muted">Ask your administrator for an invitation link.</p>
          </mat-card-content></mat-card>
        }
        <mat-nav-list>
          @for (m of me.memberships; track m.tenant_id) {
            <a mat-list-item [routerLink]="['/t', m.tenant_id]">
              <span matListItemTitle>{{ m.tenant_name }}</span>
              <span matListItemLine>{{ m.role }} · {{ m.all_projects ? 'all projects' : 'selected projects' }}</span>
            </a>
          }
        </mat-nav-list>
        @if (me.is_platform_admin) {
          <a mat-stroked-button routerLink="/platform/tenants">Manage tenants (platform)</a>
        }
      }
    </div>
  `,
})
export class HomePage {
  protected readonly session = inject(SessionStore);
}
