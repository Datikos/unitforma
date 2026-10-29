import { UnitMedia } from '../core/portal-api';

/** The unit's 3D plan views (generated or uploaded `plan_render` images), in publication order;
 * they lead the unit page as one pager, the rest of the media stays in the gallery. */
export function planViews(media: readonly UnitMedia[]): UnitMedia[] {
  return media.filter((m) => m.kind === 'plan_render' && m.mime.startsWith('image/'));
}

/** The next index of a pager of `count` items, wrapping at both ends. */
export function stepIndex(index: number, count: number, delta: number): number {
  if (count <= 0) return 0;
  return (((index + delta) % count) + count) % count;
}

/** A horizontal swipe of at least this many CSS pixels turns the page. */
export const SWIPE_MIN_PX = 40;

/** -1 (previous), 1 (next) or 0 for a pointer moved by `dx`, `dy`: horizontal and long enough. */
export function swipeDirection(dx: number, dy: number): -1 | 0 | 1 {
  if (Math.abs(dx) < SWIPE_MIN_PX || Math.abs(dx) < Math.abs(dy)) return 0;
  return dx < 0 ? 1 : -1;
}
