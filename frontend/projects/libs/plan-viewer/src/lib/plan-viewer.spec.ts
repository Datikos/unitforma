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
    expect(c.toPoints([[0, 0], [0.5, 0.5], [1, 1]])).toBe('0,0 500,250 1000,500');
    expect(c.centroid([[0, 0], [1, 0], [1, 1], [0, 1]])).toEqual([500, 250]);
  });

  it('emits a closed polygon without the duplicated double-click vertex', async () => {
    const c = await create();
    const drawn: Ring[] = [];
    c.polygonDrawn.subscribe((r) => drawn.push(r));
    c.draft.set([[0.1, 0.1], [0.4, 0.1], [0.4, 0.4], [0.4, 0.4]]);
    c.finishPolygon();
    expect(drawn).toEqual([[[0.1, 0.1], [0.4, 0.1], [0.4, 0.4]]]);
    expect(c.draft()).toEqual([]);
    // two vertices are not a polygon
    c.draft.set([[0.1, 0.1], [0.4, 0.1]]);
    c.finishPolygon();
    expect(drawn.length).toBe(1);
  });
});
