import { UnitMedia } from '../core/portal-api';
import { planViews, stepIndex, swipeDirection } from './unit.model';

function media(url: string, kind: string, mime = 'image/png'): UnitMedia {
  return { url, kind, mime } as UnitMedia;
}

describe('the 3D plan view pager on the unit page', () => {
  it('takes every plan render image, in order, and leaves photos and videos to the gallery', () => {
    const views = planViews([
      media('a.png', 'plan_render'),
      media('photo.jpg', 'photo', 'image/jpeg'),
      media('b.png', 'plan_render'),
      media('tour.mp4', 'plan_render', 'video/mp4'),
    ]);
    expect(views.map((m) => m.url)).toEqual(['a.png', 'b.png']);
  });

  it('wraps from the last view to the first and back', () => {
    expect(stepIndex(1, 2, 1)).toBe(0);
    expect(stepIndex(0, 2, -1)).toBe(1);
    expect(stepIndex(0, 3, 1)).toBe(1);
    expect(stepIndex(0, 0, 1)).toBe(0);
  });

  it('turns the page on a horizontal swipe only', () => {
    expect(swipeDirection(-80, 10)).toBe(1);
    expect(swipeDirection(80, 10)).toBe(-1);
    expect(swipeDirection(20, 0)).toBe(0);
    expect(swipeDirection(-60, 120)).toBe(0);
  });
});
