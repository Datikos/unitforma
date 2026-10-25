import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { App } from './app';
import { routes } from './app.routes';

describe('Portal App', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [App],
      providers: [provideRouter(routes), provideHttpClient(), provideHttpClientTesting()],
    }).compileComponents();
  });

  it('shows the "not set up" page for an unknown host', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    http
      .expectOne('/api/v1/portal/site')
      .flush({ type: 'https://unitforma.com/problems/portal-not-configured', title: 'Portal not configured', status: 404 }, { status: 404, statusText: 'Not Found' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('This address is not set up');
  });

  it('applies tenant branding and shows "coming soon" when nothing is published', async () => {
    const fixture = TestBed.createComponent(App);
    const http = TestBed.inject(HttpTestingController);
    http.expectOne('/api/v1/portal/site').flush({
      tenant: { name: 'Riverside Homes', slug: 'riverside' },
      branding: { primary_color: '#0f766e', display_name: 'Riverside', contact_email: 'sales@example.com' },
      mode: 'tenant',
      projects: [],
      status: 'coming_soon',
    });
    await TestBed.inject(Router).navigateByUrl('/');
    await fixture.whenStable();
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Riverside');
    expect(text).toContain('Coming soon');
    expect(document.documentElement.style.getPropertyValue('--uf-primary')).toBe('#0f766e');
  });
});
