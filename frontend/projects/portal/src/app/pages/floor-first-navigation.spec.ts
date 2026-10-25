import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { Router, provideRouter, withComponentInputBinding } from '@angular/router';
import { ProjectDoc } from '../core/portal-api';
import { BuildingPage } from './building.page';
import { ProjectPage } from './project.page';

/** A published project with one building of two floors (ADR-0006 Decision 6 tests). */
const DOC: ProjectDoc = {
  publication: { id: 'p1', version_no: 1, status: 'published', built_at: '2026-10-25T00:00:00Z' },
  tenant: { name: 'Riverside Homes', slug: 'riverside' },
  branding: { display_name: 'Riverside' },
  project: {
    slug: 'park',
    name: 'Park Residence',
    address: {},
    currency: 'GEL',
    area_definitions: [],
    price_area_type: 'net',
  },
  stats: {
    units: 3,
    available: 2,
    price_from: null,
    area_min: null,
    area_max: null,
    rooms: [],
    unit_types: ['apartment'],
  },
  site: null,
  buildings: [
    {
      code: 'A',
      name: 'Block A',
      kind: 'building',
      floors: [
        {
          level: 1,
          name: 'Floor 1',
          plan: null,
          units: [
            {
              id: 'u11',
              code: 'A-11',
              unit_type: 'apartment',
              availability: 'available',
              ring: null,
            },
          ],
        },
        {
          level: 2,
          name: 'Floor 2',
          plan: null,
          units: [
            { id: 'u21', code: 'A-21', unit_type: 'apartment', availability: 'sold', ring: null },
            {
              id: 'u22',
              code: 'A-22',
              unit_type: 'apartment',
              availability: 'available',
              ring: null,
            },
          ],
        },
      ],
    },
  ],
  massing: {
    url: '/api/v1/portal/projects/park/assets/massing.glb',
    units: 3,
    bytes: 1000,
    disclaimer: 'Schematic',
  },
  payment_plans: [],
  promotions: [],
  preview: false,
};

/** Starts the page's project load, answers it with DOC and lets the promise chain settle. */
async function loadProject(fixture: ComponentFixture<BuildingPage>): Promise<void> {
  fixture.detectChanges();
  TestBed.inject(HttpTestingController).expectOne('/api/v1/portal/projects/park').flush(DOC);
  await new Promise((r) => setTimeout(r, 0));
  fixture.detectChanges();
}

describe('Floor-first navigation (ADR-0006 Decision 6)', () => {
  beforeEach(async () => {
    await TestBed.configureTestingModule({
      providers: [
        provideRouter(
          [
            { path: 'projects/:slug', component: ProjectPage },
            { path: 'projects/:slug/buildings/:code', component: BuildingPage },
          ],
          withComponentInputBinding(),
        ),
        provideHttpClient(),
        provideHttpClientTesting(),
      ],
    }).compileComponents();
  });

  it('a 3D pick on the project page opens the building on that floor with the unit preselected', async () => {
    const fixture = TestBed.createComponent(ProjectPage);
    fixture.componentRef.setInput('slug', 'park');
    const router = TestBed.inject(Router);
    fixture.componentInstance.openUnit({
      unit_id: 'u21',
      code: 'A-21',
      unit_type: 'apartment',
      building_code: 'A',
      floor_level: 2,
    });
    await fixture.whenStable();
    expect(router.url).toBe('/projects/park/buildings/A?floor=2&unit=A-21');
  });

  it('the building page lands on the floor and unit from the URL and shows the unit card', async () => {
    const fixture = TestBed.createComponent(BuildingPage);
    fixture.componentRef.setInput('slug', 'park');
    fixture.componentRef.setInput('code', 'A');
    fixture.componentRef.setInput('floor', '2');
    fixture.componentRef.setInput('unit', 'A-21');
    await loadProject(fixture);
    fixture.detectChanges();
    const page = fixture.componentInstance;
    expect(page.level()).toBe(2);
    expect(page.selectedUnit()?.code).toBe('A-21');
    const status = fixture.nativeElement.querySelector('[role="status"]') as HTMLElement;
    expect(status.textContent).toContain('A-21');
    expect(status.textContent).toContain('Floor 2');
    expect(status.textContent).toContain('Sold');
  });

  it('a unit alone in the URL picks its floor; a plan tap replaces the preselection', async () => {
    const fixture = TestBed.createComponent(BuildingPage);
    fixture.componentRef.setInput('slug', 'park');
    fixture.componentRef.setInput('code', 'A');
    fixture.componentRef.setInput('unit', 'a-22');
    await loadProject(fixture);
    fixture.detectChanges();
    const page = fixture.componentInstance;
    expect(page.level()).toBe(2);
    expect(page.selected()).toBe('u22');
    page.selected.set('u21');
    expect(page.selectedUnit()?.code).toBe('A-21');
  });

  it('a 3D pick on another floor moves the floor and preselects the unit; on the same floor it selects in place', async () => {
    await TestBed.inject(Router).navigateByUrl('/projects/park/buildings/A?floor=1');
    const fixture = TestBed.createComponent(BuildingPage);
    fixture.componentRef.setInput('slug', 'park');
    fixture.componentRef.setInput('code', 'A');
    fixture.componentRef.setInput('floor', '1');
    await loadProject(fixture);
    const page = fixture.componentInstance;
    expect(page.level()).toBe(1);
    page.pick3d({
      unit_id: 'u11',
      code: 'A-11',
      unit_type: 'apartment',
      building_code: 'A',
      floor_level: 1,
    });
    expect(page.selected()).toBe('u11');
    page.pick3d({
      unit_id: 'u22',
      code: 'A-22',
      unit_type: 'apartment',
      building_code: 'A',
      floor_level: 2,
    });
    await fixture.whenStable();
    expect(TestBed.inject(Router).url).toBe('/projects/park/buildings/A?floor=2&unit=A-22');
  });
});
