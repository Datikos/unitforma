import { Component } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter, withRouterConfig } from '@angular/router';
import { RouteInfo } from './route-info';

@Component({ template: '' })
class Blank {}

describe('RouteInfo (breadcrumb and guide keys)', () => {
  it('exposes the deepest route data, inherited from the parent when the leaf has none, and clears the leaf on navigation', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter(
          [
            {
              path: 't/:tenantId',
              component: Blank,
              data: { guide: 'projects' },
              children: [
                { path: 'projects', component: Blank, data: { breadcrumb: 'Projects' } },
                {
                  path: 'members',
                  component: Blank,
                  data: { guide: 'members', breadcrumb: 'Members' },
                },
              ],
            },
          ],
          withRouterConfig({ paramsInheritanceStrategy: 'always' }),
        ),
      ],
    });
    const info = TestBed.inject(RouteInfo);
    const router = TestBed.inject(Router);
    await router.navigateByUrl('/t/t1/projects');
    expect(info.str('breadcrumb')).toBe('Projects');
    expect(info.str('guide')).toBe('projects');
    info.setLeaf('Page 3');
    expect(info.leaf()).toBe('Page 3');
    await router.navigateByUrl('/t/t1/members');
    expect(info.str('guide')).toBe('members');
    expect(info.leaf()).toBeNull();
    expect(info.url()).toBe('/t/t1/members');
  });
});
