import { MeOut, ProjectOut, TenantOut } from 'api-client';

export interface MenuItem {
  key: string;
  label: string;
  icon: string;
  link: string[];
  /** Match the URL exactly (for section roots such as the project overview). */
  exact?: boolean;
}

export interface MenuSection {
  key: 'platform' | 'workspace' | 'project';
  title: string;
  /** Sub-groups inside the project section ("Intake", "Site & 3D", "Sales"). */
  groups: { title: string | null; items: MenuItem[] }[];
}

/** The project section mirrors the order of work: structure → intake → site → units → sales → publish. */
export const PROJECT_MENU: { title: string | null; items: Omit<MenuItem, 'link'>[] }[] = [
  {
    title: null,
    items: [
      {
        key: 'project-overview',
        label: 'Overview & structure',
        icon: 'lucideLayoutDashboard',
        exact: true,
      },
    ],
  },
  {
    title: 'Intake',
    items: [
      { key: 'documents', label: 'Documents', icon: 'lucideFileText' },
      { key: 'proposals', label: 'Revision diffs', icon: 'lucideGitCompare' },
    ],
  },
  {
    title: 'Site & 3D',
    items: [
      { key: 'placement', label: 'Site placement', icon: 'lucideMap' },
      { key: 'massing', label: '3D massing', icon: 'lucideBox' },
    ],
  },
  { title: null, items: [{ key: 'units', label: 'Units & lineage', icon: 'lucideLayers' }] },
  {
    title: 'Sales',
    items: [
      { key: 'inventory', label: 'Inventory & prices', icon: 'lucideTable' },
      { key: 'imports', label: 'Import prices', icon: 'lucideFileSpreadsheet' },
      { key: 'sales-setup', label: 'Plans & promotions', icon: 'lucideHandCoins' },
    ],
  },
  { title: null, items: [{ key: 'publish', label: 'Publish', icon: 'lucideRocket' }] },
];

/** Route segment under `projects/:projectId` for each project menu key. */
export const PROJECT_SEGMENT: Record<string, string> = {
  'project-overview': '',
  documents: 'documents',
  proposals: 'proposals',
  placement: 'placement',
  massing: 'massing',
  units: 'units',
  inventory: 'inventory',
  imports: 'imports',
  'sales-setup': 'sales-setup',
  publish: 'publish',
};

/**
 * Pure: the menu for the signed-in user, the open tenant and the open project. Roles are not
 * enforced here (the backend enforces only `is_platform_admin` today, ADR-0009 Context); every
 * tenant entry is visible and the guide states who may use what.
 */
export function buildMenu(
  me: MeOut | null,
  tenant: TenantOut | null,
  project: ProjectOut | null,
): MenuSection[] {
  const sections: MenuSection[] = [];
  if (me?.is_platform_admin) {
    sections.push({
      key: 'platform',
      title: 'Platform',
      groups: [
        {
          title: null,
          items: [
            {
              key: 'platform-tenants',
              label: 'Tenants',
              icon: 'lucideLandmark',
              link: ['/platform', 'tenants'],
            },
          ],
        },
      ],
    });
  }
  if (tenant) {
    const t = ['/t', tenant.id];
    sections.push({
      key: 'workspace',
      title: 'Workspace',
      groups: [
        {
          title: null,
          items: [
            {
              key: 'projects',
              label: 'Projects',
              icon: 'lucideFolderKanban',
              link: [...t, 'projects'],
              exact: true,
            },
            { key: 'members', label: 'Members', icon: 'lucideUsers', link: [...t, 'members'] },
            { key: 'tokens', label: 'API tokens', icon: 'lucideKeyRound', link: [...t, 'tokens'] },
            { key: 'audit', label: 'Audit log', icon: 'lucideScrollText', link: [...t, 'audit'] },
          ],
        },
      ],
    });
    if (project) {
      const p = [...t, 'projects', project.id];
      sections.push({
        key: 'project',
        title: 'Project',
        groups: PROJECT_MENU.map((g) => ({
          title: g.title,
          items: g.items.map((i) => ({
            ...i,
            link: PROJECT_SEGMENT[i.key] ? [...p, PROJECT_SEGMENT[i.key]] : p,
          })),
        })),
      });
    }
  }
  return sections;
}
