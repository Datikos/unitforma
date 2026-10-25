import { BreakpointObserver } from '@angular/cdk/layout';
import { Component, computed, inject, signal } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { MatSidenavModule } from '@angular/material/sidenav';
import { Router, RouterOutlet } from '@angular/router';
import { NgIcon, provideIcons } from '@ng-icons/core';
import { KratosService, SessionStore } from 'auth-staff';
import { BreadcrumbsComponent, Crumb, UF_ICONS } from 'ui';
import { map } from 'rxjs';
import { ProjectContext } from './core/project-context';
import { RouteInfo } from './core/route-info';
import { TenantContext } from './core/tenant-context';
import { GuideDrawerComponent } from './guide/guide-drawer.component';
import { SideMenuComponent } from './shell/side-menu.component';

/**
 * Admin shell (ADR-0009 Decision 1): side menu on the left, a thin top bar with breadcrumbs and the
 * guide button, the page in the middle, the guide drawer on the right. Login and invitation routes
 * (`data.shell === 'bare'`) render without any of it.
 */
@Component({
  selector: 'uf-root',
  imports: [
    RouterOutlet,
    MatSidenavModule,
    NgIcon,
    SideMenuComponent,
    GuideDrawerComponent,
    BreadcrumbsComponent,
  ],
  viewProviders: [provideIcons(UF_ICONS)],
  template: `
    @if (bare()) {
      <main class="uf-bare"><router-outlet /></main>
    } @else {
      <mat-sidenav-container class="shell" [hasBackdrop]="!wide()">
        <mat-sidenav
          #nav
          class="shell__nav"
          [mode]="wide() ? 'side' : 'over'"
          [opened]="wide() || navOpen()"
          (closedStart)="navOpen.set(false)"
          [fixedInViewport]="true"
        >
          <uf-side-menu (navigated)="onNavigated()" (signOut)="logout()" />
        </mat-sidenav>
        <mat-sidenav
          #guide
          position="end"
          mode="over"
          class="shell__guide"
          [opened]="guideOpen()"
          (closedStart)="guideOpen.set(false)"
          [fixedInViewport]="true"
          [autoFocus]="true"
        >
          @defer (when guideOpen()) {
            <uf-guide-drawer (closed)="guideOpen.set(false)" />
          }
        </mat-sidenav>
        <mat-sidenav-content class="shell__content">
          <header class="topbar">
            @if (!wide()) {
              <button
                type="button"
                class="nav__icon-btn"
                (click)="navOpen.set(true)"
                aria-label="Open menu"
              >
                <ng-icon name="lucideMenu" />
              </button>
            }
            <uf-breadcrumbs [items]="crumbs()" class="topbar__crumbs" />
            <span class="uf-spacer"></span>
            <button
              type="button"
              class="topbar__guide"
              (click)="guideOpen.set(true)"
              [attr.aria-expanded]="guideOpen()"
              title="About this page"
            >
              <ng-icon name="lucideCircleHelp" aria-hidden="true" /><span>Guide</span>
            </button>
          </header>
          <main class="uf-main"><router-outlet /></main>
        </mat-sidenav-content>
      </mat-sidenav-container>
    }
  `,
})
export class App {
  protected readonly session = inject(SessionStore);
  private readonly kratos = inject(KratosService);
  private readonly router = inject(Router);
  private readonly route = inject(RouteInfo);
  private readonly tenantCtx = inject(TenantContext);
  private readonly projectCtx = inject(ProjectContext);
  private readonly bp = inject(BreakpointObserver);

  protected readonly wide = toSignal(
    this.bp.observe('(min-width: 1024px)').pipe(map((r) => r.matches)),
    {
      initialValue:
        typeof matchMedia === 'function' ? matchMedia('(min-width: 1024px)').matches : true,
    },
  );
  protected readonly navOpen = signal(false);
  protected readonly guideOpen = signal(false);
  protected readonly bare = computed(() => this.route.str('shell') === 'bare');

  protected readonly crumbs = computed<Crumb[]>(() => {
    const items: Crumb[] = [{ label: 'Home', link: ['/'], icon: 'lucideHouse' }];
    const url = this.route.url();
    if (url.startsWith('/platform')) items.push({ label: 'Platform' });
    if (url.startsWith('/guide')) items.push({ label: 'Guide' });
    const tid = this.tenantCtx.tenantId();
    const t = this.tenantCtx.tenant();
    if (tid) {
      items.push({ label: t?.name ?? 'Workspace', link: ['/t', tid, 'projects'] });
      const pid = this.projectCtx.projectId();
      const p = this.projectCtx.project();
      if (pid) items.push({ label: p?.name ?? 'Project', link: ['/t', tid, 'projects', pid] });
    }
    const section = this.route.str('breadcrumb');
    const leaf = this.route.leaf();
    if (section && !(section === 'Overview' && !leaf)) items.push({ label: section });
    if (leaf) items.push({ label: leaf });
    return items;
  });

  onNavigated(): void {
    if (!this.wide()) this.navOpen.set(false);
  }

  async logout(): Promise<void> {
    try {
      await this.kratos.logout();
    } finally {
      this.session.clear();
      await this.router.navigate(['/login']);
    }
  }
}
