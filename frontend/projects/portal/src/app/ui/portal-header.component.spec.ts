import { TestBed } from '@angular/core/testing';
import { Router, provideRouter } from '@angular/router';
import { Favourites } from '../core/favourites';
import { SiteStore } from '../core/site.store';
import { PortalHeaderComponent } from './portal-header.component';

describe('PortalHeaderComponent', () => {
  beforeEach(() => {
    TestBed.configureTestingModule({ providers: [provideRouter([{ path: '**', children: [] }])] });
    const store = TestBed.inject(SiteStore);
    store.site.set({
      tenant: { name: 'Riverside Homes', slug: 'riverside' },
      branding: { display_name: 'Riverside', tagline: 'Homes by the river' },
      mode: 'tenant',
      status: 'live',
      projects: [
        { slug: 'park', name: 'Park Residence' } as never,
        { slug: 'hill', name: 'Hill View' } as never,
      ],
    });
  });

  it('shows the project navigation with the saved count inside a project', async () => {
    const favs = TestBed.inject(Favourites);
    localStorage.clear();
    favs.toggle('park', 'A-1');
    favs.toggle('park', 'A-2');
    await TestBed.inject(Router).navigateByUrl('/projects/park/units');
    const fixture = TestBed.createComponent(PortalHeaderComponent);
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('Riverside');
    expect(text).toContain('Park Residence');
    expect(text).toContain('Units');
    expect(text).toContain('Saved');
    expect(fixture.nativeElement.querySelector('.hd__count')?.textContent?.trim()).toBe('2');
    expect(text).toContain('Projects');
  });

  it('shows only the how-to-use link outside a project', async () => {
    await TestBed.inject(Router).navigateByUrl('/');
    const fixture = TestBed.createComponent(PortalHeaderComponent);
    fixture.detectChanges();
    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('How to use');
    expect(text).not.toContain('Saved');
  });
});
