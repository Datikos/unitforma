import { Routes } from '@angular/router';
import { platformAdminGuard, staffAuthGuard } from 'auth-staff';

export const routes: Routes = [
  { path: 'login', loadComponent: () => import('./pages/login.page').then((m) => m.LoginPage) },
  { path: 'invite/:token', canActivate: [staffAuthGuard], loadComponent: () => import('./pages/invite-accept.page').then((m) => m.InviteAcceptPage) },
  { path: '', canActivate: [staffAuthGuard], loadComponent: () => import('./pages/home.page').then((m) => m.HomePage), pathMatch: 'full' },
  {
    path: 'platform/tenants',
    canActivate: [staffAuthGuard, platformAdminGuard],
    loadComponent: () => import('./pages/platform-tenants.page').then((m) => m.PlatformTenantsPage),
  },
  {
    path: 't/:tenantId',
    canActivate: [staffAuthGuard],
    loadComponent: () => import('./pages/tenant-shell.page').then((m) => m.TenantShellPage),
    children: [
      { path: '', redirectTo: 'projects', pathMatch: 'full' },
      { path: 'projects', loadComponent: () => import('./pages/projects.page').then((m) => m.ProjectsPage) },
      { path: 'projects/:projectId', loadComponent: () => import('./pages/project-detail.page').then((m) => m.ProjectDetailPage) },
      { path: 'projects/:projectId/documents', loadComponent: () => import('./pages/documents.page').then((m) => m.DocumentsPage) },
      { path: 'projects/:projectId/sheets/:sheetId', loadComponent: () => import('./pages/sheet.page').then((m) => m.SheetPage) },
      { path: 'projects/:projectId/units', loadComponent: () => import('./pages/units.page').then((m) => m.UnitsPage) },
      { path: 'members', loadComponent: () => import('./pages/members.page').then((m) => m.MembersPage) },
      { path: 'audit', loadComponent: () => import('./pages/audit.page').then((m) => m.AuditPage) },
    ],
  },
  { path: '**', redirectTo: '' },
];
