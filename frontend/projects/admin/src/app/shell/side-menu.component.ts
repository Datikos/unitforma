import { ChangeDetectionStrategy, Component, computed, inject, output } from '@angular/core';
import { Router, RouterLink, RouterLinkActive } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { SessionStore } from 'auth-staff';
import { StatusChipComponent, UF_ICONS } from 'ui';
import { ProjectContext } from '../core/project-context';
import { TenantContext } from '../core/tenant-context';
import { buildMenu } from './menu.model';

/** Left navigation: brand, tenant switcher, sections with icons, project switcher, user. */
@Component({
  selector: 'uf-side-menu',
  imports: [RouterLink, RouterLinkActive, NgIcon, StatusChipComponent],
  viewProviders: [provideIcons(UF_ICONS)],
  changeDetection: ChangeDetectionStrategy.OnPush,
  template: `
    <div class="nav">
      <a routerLink="/" class="nav__brand" (click)="navigated.emit()">
        <span class="nav__logo" aria-hidden="true">U</span>
        <span>Unitforma</span>
      </a>

      @if (memberships().length > 0) {
        <label class="nav__switch">
          <span class="nav__switch-label">Workspace</span>
          <span class="nav__select">
            <ng-icon name="lucideBuilding2" aria-hidden="true" />
            <select
              [value]="tenantCtx.tenantId() ?? ''"
              (change)="switchTenant(sel($event))"
              aria-label="Switch workspace"
            >
              @if (!tenantCtx.tenantId()) {
                <option value="">Choose a workspace…</option>
              }
              @for (m of memberships(); track m.tenant_id) {
                <option [value]="m.tenant_id" [selected]="m.tenant_id === tenantCtx.tenantId()">
                  {{ m.tenant_name }}
                </option>
              }
            </select>
            <ng-icon name="lucideChevronsUpDown" class="nav__caret" aria-hidden="true" />
          </span>
          @if (tenantCtx.tenant(); as t) {
            <span class="nav__sub">{{ t.slug }}.unitforma.com</span>
          }
        </label>
      }

      @for (s of sections(); track s.key) {
        <div class="nav__section">
          <div class="nav__title">
            <span>{{ s.title }}</span>
            @if (s.key === 'project' && projectCtx.project(); as p) {
              <uf-status-chip domain="project" [value]="p.status" />
            }
          </div>
          @if (s.key === 'project') {
            <label class="nav__switch nav__switch--project">
              <span class="nav__select">
                <ng-icon name="lucideFolderKanban" aria-hidden="true" />
                <select
                  [value]="projectCtx.projectId() ?? ''"
                  (change)="switchProject(sel($event))"
                  aria-label="Switch project"
                >
                  @for (p of tenantCtx.projects(); track p.id) {
                    <option [value]="p.id" [selected]="p.id === projectCtx.projectId()">
                      {{ p.name }}
                    </option>
                  }
                </select>
                <ng-icon name="lucideChevronsUpDown" class="nav__caret" aria-hidden="true" />
              </span>
            </label>
          }
          @for (g of s.groups; track $index) {
            @if (g.title) {
              <div class="nav__group">{{ g.title }}</div>
            }
            @for (i of g.items; track i.key) {
              <a
                class="nav__item"
                [routerLink]="i.link"
                routerLinkActive="is-active"
                [routerLinkActiveOptions]="{ exact: !!i.exact }"
                ariaCurrentWhenActive="page"
                (click)="navigated.emit()"
              >
                <ng-icon [name]="i.icon" aria-hidden="true" />
                <span>{{ i.label }}</span>
              </a>
            }
          }
        </div>
      } @empty {
        @if (session.me()) {
          <p class="nav__hint">Pick a workspace above, or open one from the home page.</p>
        }
      }

      <div class="nav__spacer"></div>
      <a
        class="nav__item"
        routerLink="/guide"
        routerLinkActive="is-active"
        (click)="navigated.emit()"
      >
        <ng-icon name="lucideBookOpen" aria-hidden="true" /><span>Guide</span>
      </a>
      @if (session.me(); as me) {
        <div class="nav__user">
          <ng-icon name="lucideCircleUser" aria-hidden="true" />
          <span class="nav__email" [title]="me.email">{{ me.email }}</span>
          <button
            type="button"
            class="nav__icon-btn"
            (click)="signOut.emit()"
            title="Sign out"
            aria-label="Sign out"
          >
            <ng-icon name="lucideLogOut" />
          </button>
        </div>
      }
    </div>
  `,
})
export class SideMenuComponent {
  protected readonly session = inject(SessionStore);
  protected readonly tenantCtx = inject(TenantContext);
  protected readonly projectCtx = inject(ProjectContext);
  private readonly router = inject(Router);
  readonly navigated = output<void>();
  readonly signOut = output<void>();
  protected readonly memberships = computed(() => this.session.me()?.memberships ?? []);
  protected readonly sections = computed(() =>
    buildMenu(this.session.me(), this.tenantCtx.tenant(), this.projectCtx.project()),
  );

  sel(e: Event): string | null {
    return (e.target as HTMLSelectElement).value || null;
  }

  switchTenant(id: string | null): void {
    if (id && id !== this.tenantCtx.tenantId()) void this.router.navigate(['/t', id]);
  }

  switchProject(id: string | null): void {
    const t = this.tenantCtx.tenantId();
    if (id && t && id !== this.projectCtx.projectId()) {
      // keep the same section when switching projects (documents → documents)
      const section = this.router.url.split('/projects/')[1]?.split('/')[1]?.split('?')[0];
      const keep = section && !/^[0-9a-f-]{36}$/.test(section) ? [section] : [];
      void this.router.navigate(['/t', t, 'projects', id, ...keep]);
    }
  }
}
