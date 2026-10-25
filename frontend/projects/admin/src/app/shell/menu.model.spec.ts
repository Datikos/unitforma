import { MeOut, ProjectOut, TenantOut } from 'api-client';
import { GUIDE } from '../guide/guide-content';
import { PROJECT_MENU, PROJECT_SEGMENT, buildMenu } from './menu.model';

const me = (platform: boolean): MeOut => ({
  user_id: 'u1',
  email: 'a@b.c',
  email_verified: true,
  is_platform_admin: platform,
  aal: 'aal1',
  memberships: [],
});
const tenant = {
  id: 't1',
  slug: 'acme',
  name: 'Acme',
  status: 'active',
  default_currency: 'EUR',
  branding: {},
  settings: {},
} as unknown as TenantOut;
const project = {
  id: 'p1',
  tenant_id: 't1',
  slug: 'hills',
  name: 'Hills',
  status: 'active',
  currency: 'EUR',
  code_pattern: 'A-1-01',
} as unknown as ProjectOut;

describe('buildMenu', () => {
  it('shows the Project section only when a project is loaded', () => {
    expect(buildMenu(me(false), tenant, null).map((s) => s.key)).toEqual(['workspace']);
    expect(buildMenu(me(false), tenant, project).map((s) => s.key)).toEqual([
      'workspace',
      'project',
    ]);
  });

  it('shows the Platform section only for platform admins', () => {
    expect(buildMenu(me(false), tenant, null).some((s) => s.key === 'platform')).toBe(false);
    expect(buildMenu(me(true), tenant, null)[0].key).toBe('platform');
    expect(buildMenu(me(true), null, null).map((s) => s.key)).toEqual(['platform']);
  });

  it('every project menu entry links under the project and has a guide entry', () => {
    const sections = buildMenu(me(false), tenant, project);
    const items = sections.find((s) => s.key === 'project')!.groups.flatMap((g) => g.items);
    for (const i of items) {
      expect(i.link.slice(0, 4), i.key).toEqual(['/t', 't1', 'projects', 'p1']);
      expect(i.key in GUIDE, `guide entry for ${i.key}`).toBe(true);
    }
    expect(items.map((i) => i.key)).toEqual(PROJECT_MENU.flatMap((g) => g.items.map((i) => i.key)));
    expect(Object.keys(PROJECT_SEGMENT).sort()).toEqual(items.map((i) => i.key).sort());
  });

  it('workspace entries have icons registered in the vocabulary file', () => {
    const items = buildMenu(me(true), tenant, project).flatMap((s) =>
      s.groups.flatMap((g) => g.items),
    );
    for (const i of items) expect(i.icon, i.key).toMatch(/^lucide[A-Z]/);
  });
});
