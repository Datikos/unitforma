import { TestBed } from '@angular/core/testing';
import { PlanViewerComponent, Ring } from './plan-viewer';

describe('PlanViewerComponent', () => {
  async function create(): Promise<PlanViewerComponent> {
    await TestBed.configureTestingModule({ imports: [PlanViewerComponent] }).compileComponents();
    const fixture = TestBed.createComponent(PlanViewerComponent);
    fixture.componentRef.setInput('width', 1000);
    fixture.componentRef.setInput('height', 500);
    fixture.detectChanges();
    return fixture.componentInstance;
  }

  it('maps normalised rings to raster pixels', async () => {
    const c = await create();
    expect(
      c.toPoints([
        [0, 0],
        [0.5, 0.5],
        [1, 1],
      ]),
    ).toBe('0,0 500,250 1000,500');
    expect(
      c.centroid([
        [0, 0],
        [1, 0],
        [1, 1],
        [0, 1],
      ]),
    ).toEqual([500, 250]);
  });

  it('emits a closed polygon without the duplicated double-click vertex', async () => {
    const c = await create();
    const drawn: Ring[] = [];
    c.polygonDrawn.subscribe((r) => drawn.push(r));
    c.draft.set([
      [0.1, 0.1],
      [0.4, 0.1],
      [0.4, 0.4],
      [0.4, 0.4],
    ]);
    c.finishPolygon();
    expect(drawn).toEqual([
      [
        [0.1, 0.1],
        [0.4, 0.1],
        [0.4, 0.4],
      ],
    ]);
    expect(c.draft()).toEqual([]);
    // two vertices are not a polygon
    c.draft.set([
      [0.1, 0.1],
      [0.4, 0.1],
    ]);
    c.finishPolygon();
    expect(drawn.length).toBe(1);
  });

  it('draws floor regions but never selects them', async () => {
    const c = await create();
    const picked: string[] = [];
    c.polygonSelected.subscribe((id) => picked.push(id));
    const ev = new MouseEvent('click');
    c.select(
      {
        id: 'region:f1',
        ring: [
          [0, 0],
          [0.5, 0],
          [0.5, 1],
        ],
        kind: 'region',
      },
      ev,
    );
    c.select(
      {
        id: 'u1',
        ring: [
          [0, 0],
          [0.2, 0],
          [0.2, 0.2],
        ],
      },
      ev,
    );
    expect(picked).toEqual(['u1']);
  });

  it('draws the selected unit on top with a halo and dims the others (ADR-0017)', async () => {
    await TestBed.configureTestingModule({ imports: [PlanViewerComponent] }).compileComponents();
    const fixture = TestBed.createComponent(PlanViewerComponent);
    fixture.componentRef.setInput('width', 1000);
    fixture.componentRef.setInput('height', 500);
    const square = (x: number): Ring => [
      [x, 0.1],
      [x + 0.2, 0.1],
      [x + 0.2, 0.4],
      [x, 0.4],
    ];
    fixture.componentRef.setInput('polygons', [
      { id: 'a', ring: square(0.1), label: 'A-1', fill: 'rgb(16, 185, 129)' },
      { id: 'b', ring: square(0.5), label: 'A-2', fill: 'rgb(16, 185, 129)', selected: true },
      { id: 'f', ring: square(0.0), kind: 'footprint', selected: true },
    ]);
    fixture.detectChanges();
    const host: HTMLElement = fixture.nativeElement;
    expect(fixture.componentInstance.selectedPolygon()?.id).toBe('b'); // never the footprint
    expect(host.querySelector('.pv')?.classList.contains('pv--has-selection')).toBe(true);
    const outline = host.querySelector('.pv__poly--outline');
    expect(outline?.getAttribute('points')).toBe('500,50 700,50 700,200 500,200');
    expect(host.querySelector('.pv__poly--halo')).not.toBeNull();
    // the overlay comes after every unit polygon, so it paints over their inline colours
    const polys = Array.from(host.querySelectorAll('polygon'));
    expect(polys.indexOf(outline as SVGPolygonElement)).toBe(polys.length - 1);
    expect(host.querySelector('.pv__label--selected')?.textContent?.trim()).toBe('A-2');
    fixture.componentRef.setInput('polygons', [{ id: 'a', ring: square(0.1), label: 'A-1' }]);
    fixture.detectChanges();
    expect(host.querySelector('.pv--has-selection')).toBeNull();
    expect(host.querySelector('.pv__poly--outline')).toBeNull();
  });

  it('shrinks the label of a narrow parking stall so it stays inside the polygon', async () => {
    await TestBed.configureTestingModule({ imports: [PlanViewerComponent] }).compileComponents();
    const fixture = TestBed.createComponent(PlanViewerComponent);
    fixture.componentRef.setInput('width', 3000);
    fixture.componentRef.setInput('height', 2000);
    const c = fixture.componentInstance;
    expect(c.labelSize()).toBe(50);
    // a 2.5 m × 5 m stall on a sheet where 1 m is 24 px: 60 × 120 px
    const stall: Ring = [
      [0.1, 0.1],
      [0.12, 0.1],
      [0.12, 0.16],
      [0.1, 0.16],
    ];
    const flat: Ring = [
      [0.3, 0.1],
      [0.5, 0.1],
      [0.5, 0.2],
      [0.3, 0.2],
    ];
    fixture.componentRef.setInput('polygons', [
      { id: 'p10', ring: stall, label: 'P-10' },
      { id: 'a1', ring: flat, label: 'A-1' },
      { id: 'band', ring: flat, label: 'Floor 1 · 3 of 11' },
    ]);
    fixture.detectChanges();
    const sizes = Array.from(fixture.nativeElement.querySelectorAll('text')).map((t) =>
      Number((t as SVGTextElement).getAttribute('font-size')),
    );
    // 0.85 × 60 px / (0.6 em × 4 chars) = 21.25 px: the four glyphs fit the 60 px stall
    expect(sizes[0]).toBeCloseTo(21.25, 0);
    expect(sizes[0] * 0.6 * 4).toBeLessThan(60);
    expect(sizes[1]).toBe(50); // a wide room keeps the sheet size
    expect(sizes[2]).toBe(50); // 17 glyphs × 0.6 em × 50 px = 510 px fit the 600 px band
    // selecting the stall must not push its label out again
    fixture.componentRef.setInput('polygons', [
      { id: 'p10', ring: stall, label: 'P-10', selected: true },
      { id: 'a1', ring: flat, label: 'A-1', selected: true },
    ]);
    fixture.detectChanges();
    const selected = Array.from(fixture.nativeElement.querySelectorAll('text')).map((t) =>
      Number((t as SVGTextElement).getAttribute('font-size')),
    );
    expect(selected[0]).toBeCloseTo(21.25, 0);
    expect(selected[1]).toBe(65);
  });
});
