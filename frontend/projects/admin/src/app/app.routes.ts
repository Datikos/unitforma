import { Routes } from '@angular/router';
import { platformAdminGuard, staffAuthGuard } from 'auth-staff';

/**
 * URLs are unchanged from before ADR-0009; two layout routes were added: `t/:tenantId` (tenant
 * shell) and `projects/:projectId` (project shell). `data.guide` names the guide entry,
 * `data.breadcrumb` the section crumb, `data.shell = 'bare'` hides the shell.
 */
export const routes: Routes = [
  {
    path: 'login',
    data: { shell: 'bare' },
    loadComponent: () => import('./pages/login.page').then((m) => m.LoginPage),
  },
  {
    path: 'invite/:token',
    data: { shell: 'bare' },
    canActivate: [staffAuthGuard],
    loadComponent: () => import('./pages/invite-accept.page').then((m) => m.InviteAcceptPage),
  },
  {
    path: '',
    canActivate: [staffAuthGuard],
    data: { guide: 'home' },
    loadComponent: () => import('./pages/home.page').then((m) => m.HomePage),
    pathMatch: 'full',
  },
  {
    path: 'guide',
    canActivate: [staffAuthGuard],
    data: { breadcrumb: 'Guide' },
    loadComponent: () => import('./guide/guide.page').then((m) => m.GuidePage),
  },
  {
    path: 'guide/:key',
    canActivate: [staffAuthGuard],
    data: { breadcrumb: 'Guide' },
    loadComponent: () => import('./guide/guide.page').then((m) => m.GuidePage),
  },
  {
    path: 'platform/tenants',
    canActivate: [staffAuthGuard, platformAdminGuard],
    data: { guide: 'platform-tenants', breadcrumb: 'Tenants' },
    loadComponent: () => import('./pages/platform-tenants.page').then((m) => m.PlatformTenantsPage),
  },
  {
    path: 't/:tenantId',
    canActivate: [staffAuthGuard],
    loadComponent: () =>
      import('./shell/tenant-shell.component').then((m) => m.TenantShellComponent),
    children: [
      { path: '', redirectTo: 'projects', pathMatch: 'full' },
      {
        path: 'projects',
        data: { guide: 'projects', breadcrumb: 'Projects' },
        loadComponent: () => import('./pages/projects.page').then((m) => m.ProjectsPage),
      },
      {
        path: 'projects/:projectId',
        loadComponent: () =>
          import('./shell/project-shell.component').then((m) => m.ProjectShellComponent),
        children: [
          {
            path: '',
            data: { guide: 'project-overview', breadcrumb: 'Overview' },
            loadComponent: () =>
              import('./pages/project-detail.page').then((m) => m.ProjectDetailPage),
          },
          {
            path: 'setup',
            data: { guide: 'setup', breadcrumb: 'Setup checklist' },
            loadComponent: () => import('./pages/setup.page').then((m) => m.SetupPage),
          },
          {
            path: 'documents',
            data: { guide: 'documents', breadcrumb: 'Documents' },
            loadComponent: () => import('./pages/documents.page').then((m) => m.DocumentsPage),
          },
          {
            path: 'sheets/:sheetId',
            data: { guide: 'sheet', breadcrumb: 'Sheet' },
            loadComponent: () => import('./pages/sheet/sheet.page').then((m) => m.SheetPage),
          },
          {
            path: 'units',
            data: { guide: 'units', breadcrumb: 'Units & lineage' },
            loadComponent: () => import('./pages/units.page').then((m) => m.UnitsPage),
          },
          {
            path: 'proposals',
            data: { guide: 'proposals', breadcrumb: 'Revision diffs' },
            loadComponent: () => import('./pages/proposals.page').then((m) => m.ProposalsPage),
          },
          {
            path: 'proposals/:proposalId',
            data: { guide: 'proposal', breadcrumb: 'Revision diff' },
            loadComponent: () => import('./pages/proposal.page').then((m) => m.ProposalPage),
          },
          {
            path: 'placement',
            data: { guide: 'placement', breadcrumb: 'Site placement' },
            loadComponent: () => import('./pages/placement.page').then((m) => m.PlacementPage),
          },
          {
            path: 'massing',
            data: { guide: 'massing', breadcrumb: '3D massing' },
            loadComponent: () => import('./pages/massing.page').then((m) => m.MassingPage),
          },
          {
            path: 'inventory',
            data: { guide: 'inventory', breadcrumb: 'Inventory & prices' },
            loadComponent: () =>
              import('./pages/inventory/inventory.page').then((m) => m.InventoryPage),
          },
          {
            path: 'inventory/:unitId',
            data: { guide: 'unit-sales', breadcrumb: 'Inventory & prices' },
            loadComponent: () =>
              import('./pages/unit-sales/unit-sales.page').then((m) => m.UnitSalesPage),
          },
          {
            path: 'layouts',
            data: { guide: 'layouts', breadcrumb: 'Layouts & renders' },
            loadComponent: () => import('./pages/layouts/layouts.page').then((m) => m.LayoutsPage),
          },
          {
            path: 'imports',
            data: { guide: 'imports', breadcrumb: 'Import prices' },
            loadComponent: () => import('./pages/import.page').then((m) => m.ImportPage),
          },
          {
            path: 'publish',
            data: { guide: 'publish', breadcrumb: 'Publish' },
            loadComponent: () => import('./pages/publish.page').then((m) => m.PublishPage),
          },
          {
            path: 'sales-setup',
            data: { guide: 'sales-setup', breadcrumb: 'Plans & promotions' },
            loadComponent: () => import('./pages/sales-setup.page').then((m) => m.SalesSetupPage),
          },
        ],
      },
      {
        path: 'members',
        data: { guide: 'members', breadcrumb: 'Members' },
        loadComponent: () => import('./pages/members.page').then((m) => m.MembersPage),
      },
      {
        path: 'tokens',
        data: { guide: 'tokens', breadcrumb: 'API tokens' },
        loadComponent: () => import('./pages/tokens.page').then((m) => m.TokensPage),
      },
      {
        path: 'audit',
        data: { guide: 'audit', breadcrumb: 'Audit log' },
        loadComponent: () => import('./pages/audit.page').then((m) => m.AuditPage),
      },
    ],
  },
  { path: '**', redirectTo: '' },
];
