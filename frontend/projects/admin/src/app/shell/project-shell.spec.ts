import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { Component, input } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  Router,
  RouterOutlet,
  provideRouter,
  withComponentInputBinding,
  withRouterConfig,
} from '@angular/router';
import { ProjectContext } from '../core/project-context';
import { ProjectShellComponent } from './project-shell.component';
import { TenantShellComponent } from './tenant-shell.component';

@Component({ selector: 'uf-probe', template: '{{ tenantId() }}/{{ projectId() }}' })
class Probe {
  readonly tenantId = input.required<string>();
  readonly projectId = input.required<string>();
}

@Component({ imports: [RouterOutlet], template: '<router-outlet />' })
class Host {}

describe('ProjectShell under TenantShell', () => {
  it('a page nested in both shells receives tenantId and projectId through input binding and the project context loads', async () => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter(
          [
            {
              path: 't/:tenantId',
              component: TenantShellComponent,
              children: [
                {
                  path: 'projects/:projectId',
                  component: ProjectShellComponent,
                  children: [{ path: 'documents', component: Probe }],
                },
              ],
            },
          ],
          withComponentInputBinding(),
          withRouterConfig({ paramsInheritanceStrategy: 'always' }),
        ),
      ],
    });
    const fixture = TestBed.createComponent(Host);
    const http = TestBed.inject(HttpTestingController);
    await TestBed.inject(Router).navigateByUrl('/t/t1/projects/p1/documents');
    fixture.detectChanges();
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('t1/p1');
    http
      .expectOne('/api/v1/admin/tenants/t1')
      .flush({
        id: 't1',
        slug: 'a',
        name: 'Acme',
        status: 'active',
        default_currency: 'EUR',
        branding: {},
        settings: {},
      });
    http.expectOne('/api/v1/admin/tenants/t1/projects').flush([]);
    http
      .expectOne('/api/v1/admin/tenants/t1/projects/p1')
      .flush({
        id: 'p1',
        tenant_id: 't1',
        slug: 'hills',
        name: 'Hills',
        status: 'active',
        currency: 'EUR',
        code_pattern: 'A-1-01',
      });
    await fixture.whenStable();
    expect(TestBed.inject(ProjectContext).project()?.name).toBe('Hills');
  });
});
