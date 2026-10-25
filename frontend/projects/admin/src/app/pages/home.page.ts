import { Component, computed, inject } from '@angular/core';
import { MatButtonModule } from '@angular/material/button';
import { RouterLink } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { SessionStore } from 'auth-staff';
import { EmptyStateComponent, PageHeaderComponent, StatusChipComponent, UF_ICONS } from 'ui';

/** Workspace picker: one card per membership (plan §2.2). */
@Component({
  selector: 'uf-home-page',
  imports: [
    MatButtonModule,
    RouterLink,
    NgIcon,
    PageHeaderComponent,
    StatusChipComponent,
    EmptyStateComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    <div class="uf-page">
      <uf-page-header
        title="Your workspaces"
        icon="lucideHouse"
        [kicker]="session.me()?.email ?? null"
        [facts]="[{ label: 'Workspaces', value: memberships().length }]"
      >
        <ng-container actions>
          @if (session.me()?.is_platform_admin) {
            <a mat-stroked-button routerLink="/platform/tenants"
              ><ng-icon name="lucideLandmark" /> Manage tenants (platform)</a
            >
          }
        </ng-container>
      </uf-page-header>
      @if (session.me(); as me) {
        <div class="uf-grid3">
          @for (m of memberships(); track m.tenant_id) {
            <a class="uf-card ws uf-quiet" [routerLink]="['/t', m.tenant_id]">
              <div class="ws__head">
                <span class="ws__logo" aria-hidden="true">{{
                  m.tenant_name.slice(0, 1).toUpperCase()
                }}</span>
                <div class="ws__names">
                  <strong>{{ m.tenant_name }}</strong>
                  <span class="uf-muted uf-small">{{ m.tenant_slug }}.unitforma.com</span>
                </div>
              </div>
              <div class="uf-chips">
                <uf-status-chip domain="role" [value]="m.role" />
                <span class="uf-chip"
                  ><ng-icon name="lucideFolderKanban" />{{
                    m.all_projects ? 'all projects' : 'selected projects'
                  }}</span
                >
                @if (m.status !== 'active') {
                  <uf-status-chip domain="member" [value]="m.status" />
                }
              </div>
              <span class="ws__go">Open workspace <ng-icon name="lucideArrowRight" /></span>
            </a>
          } @empty {
            <uf-empty-state
              icon="lucideBuilding2"
              title="You are not a member of any workspace yet"
              [text]="
                'You are signed in as ' +
                me.email +
                '. Ask the workspace administrator for an invitation link; it is tied to this address.'
              "
            />
          }
        </div>
      }
    </div>
  `,
  styles: `
    .ws {
      display: grid;
      gap: 0.75rem;
      align-content: start;
      transition:
        box-shadow 0.15s,
        border-color 0.15s;
    }
    .ws:hover {
      box-shadow: var(--uf-shadow-lg);
      border-color: var(--uf-primary);
    }
    .ws__head {
      display: flex;
      gap: 0.75rem;
      align-items: center;
    }
    .ws__logo {
      display: grid;
      place-items: center;
      width: 2.5rem;
      height: 2.5rem;
      border-radius: 10px;
      background: linear-gradient(135deg, #6366f1, #2563eb);
      color: #fff;
      font-weight: 800;
      font-size: 1.1rem;
      flex: none;
    }
    .ws__names {
      display: grid;
      min-width: 0;
    }
    .ws__go {
      color: var(--uf-primary);
      font-weight: 600;
      font-size: 0.85rem;
      display: inline-flex;
      align-items: center;
      gap: 0.25rem;
    }
    a ng-icon {
      vertical-align: -0.15em;
    }
  `,
})
export class HomePage {
  protected readonly session = inject(SessionStore);
  protected readonly memberships = computed(() => this.session.me()?.memberships ?? []);
}
