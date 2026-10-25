import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { TenantContext } from './tenant-context';

const tenant = {
  id: 't1',
  slug: 'acme',
  name: 'Acme',
  status: 'active',
  default_currency: 'EUR',
  branding: {},
  settings: {},
};

describe('TenantContext', () => {
  let ctx: TenantContext;
  let http: HttpTestingController;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [provideHttpClient(), provideHttpClientTesting()],
    });
    ctx = TestBed.inject(TenantContext);
    http = TestBed.inject(HttpTestingController);
  });

  it('loads the tenant and its projects once for repeated navigations with the same id', async () => {
    const p1 = ctx.load('t1');
    http.expectOne('/api/v1/admin/tenants/t1').flush(tenant);
    http.expectOne('/api/v1/admin/tenants/t1/projects').flush([{ id: 'p1', name: 'Hills' }]);
    await p1;
    expect(ctx.tenant()?.name).toBe('Acme');
    expect(ctx.projects().length).toBe(1);
    await ctx.load('t1');
    http.expectNone('/api/v1/admin/tenants/t1');
  });

  it('switching tenants clears the previous one and fetches again; clear() empties everything', async () => {
    const p1 = ctx.load('t1');
    http.expectOne('/api/v1/admin/tenants/t1').flush(tenant);
    http.expectOne('/api/v1/admin/tenants/t1/projects').flush([]);
    await p1;
    const p2 = ctx.load('t2');
    expect(ctx.tenant()).toBeNull();
    http.expectOne('/api/v1/admin/tenants/t2').flush({ ...tenant, id: 't2', name: 'Beta' });
    http.expectOne('/api/v1/admin/tenants/t2/projects').flush([]);
    await p2;
    expect(ctx.name()).toBe('Beta');
    ctx.clear();
    expect(ctx.tenantId()).toBeNull();
    expect(ctx.tenant()).toBeNull();
  });

  it('keeps the error and allows a retry when the tenant call fails', async () => {
    const p = ctx.load('t1');
    http
      .expectOne('/api/v1/admin/tenants/t1')
      .flush({ title: 'Forbidden' }, { status: 403, statusText: 'Forbidden' });
    http.expectOne('/api/v1/admin/tenants/t1/projects').flush([]);
    await p;
    expect(ctx.error()).toBeTruthy();
    const retry = ctx.load('t1');
    http.expectOne('/api/v1/admin/tenants/t1').flush(tenant);
    http.expectOne('/api/v1/admin/tenants/t1/projects').flush([]);
    await retry;
    expect(ctx.tenant()?.name).toBe('Acme');
  });
});
