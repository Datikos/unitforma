/**
 * A picked floor of the IFC model is cut open (ADR-0036): one horizontal plane removes the model
 * above the floor, the floor's spaces are tinted glass and the camera looks down into it. The
 * rules are pure so they are tested without WebGL; `massing-viewer.ts` applies them.
 */

/** The cut above the picked floor's base, in metres (Decision 2). */
export const PLAN_CUT_M = 1.2;
/** Space opacities in an IFC model (Decisions 3 and 4). */
export const SPACE_GLASS_OPACITY = 0.4;
export const HOVER_GLASS_OPACITY = 0.55;
export const SELECTED_GLASS_OPACITY = 0.75;
export const OTHER_FLOOR_HOVER_OPACITY = 0.3;
/** How steeply the camera looks down into a cut floor (Decision 5). */
export const CUT_VIEW_ELEVATION_DEG = 55;
/** Where the plane sits when nothing is cut: far above any model, so no shader recompiles. */
export const NO_CUT_Y = 1e6;

/** The vertical extent of one space mesh of the picked floor, in world metres. */
export interface SpanY {
  minY: number;
  maxY: number;
}

/** The cut height for a floor's spaces; null when the floor has no space (no cut, the fade stays). */
export function cutHeight(spaces: SpanY[]): number | null {
  if (!spaces.length) return null;
  const base = Math.min(...spaces.map((s) => s.minY));
  const top = Math.max(...spaces.map((s) => s.maxY));
  return base + Math.min(PLAN_CUT_M, (top - base) / 2);
}

/**
 * Opacity of a plan space in an IFC model. `onFloor` is null with no floor picked, else whether the
 * space is on the picked floor; spaces of other floors are not drawn unless hovered.
 */
export function ifcSpaceOpacity(
  onFloor: boolean | null,
  state: 'hover' | 'selected' | null,
): number {
  if (onFloor === false) return state === 'hover' ? OTHER_FLOOR_HOVER_OPACITY : 0;
  if (state === 'selected') return SELECTED_GLASS_OPACITY;
  if (state === 'hover') return HOVER_GLASS_OPACITY;
  return SPACE_GLASS_OPACITY;
}

/** The inside of a cut element, as a plan draws cut walls (D2); an sRGB hex. */
export const SECTION_FILL = 0x3b4048;
/** How far below the picked floor's base the section fill still applies, in metres (D2). */
export const SECTION_BELOW_BASE_M = 0.5;

/** The heights between which a cut element's back faces take the fill; null with no cut. */
export function sectionBand(spaces: SpanY[]): [number, number] | null {
  const cut = cutHeight(spaces);
  if (cut === null) return null;
  return [Math.min(...spaces.map((s) => s.minY)) - SECTION_BELOW_BASE_M, cut];
}

/** Opaque IFC elements take the section fill; glass and the plan spaces keep their look (D2). */
export function takesSectionFill(
  m: { transparent: boolean; opacity: number },
  space: boolean,
): boolean {
  return !space && !m.transparent && m.opacity >= 1;
}

export type Vec3 = [number, number, number];

/**
 * The camera position over a cut floor: the azimuth of the current view around `target`, the
 * elevation `CUT_VIEW_ELEVATION_DEG`, at `distance` from `centre`.
 */
export function aimOverFloor(camera: Vec3, target: Vec3, centre: Vec3, distance: number): Vec3 {
  const dx = camera[0] - target[0];
  const dz = camera[2] - target[2];
  const azimuth = dx === 0 && dz === 0 ? Math.PI / 4 : Math.atan2(dx, dz);
  const el = (CUT_VIEW_ELEVATION_DEG * Math.PI) / 180;
  const flat = distance * Math.cos(el);
  return [
    centre[0] + flat * Math.sin(azimuth),
    centre[1] + distance * Math.sin(el),
    centre[2] + flat * Math.cos(azimuth),
  ];
}

/** One ray hit on a space mesh: its height and the floor the space belongs to. */
export interface SpaceHit {
  y: number;
  level: number | null;
}

/**
 * Index of the tapped space among ray hits sorted by distance, or -1 (Decision 4, D4). Above the
 * cut nothing is drawn, so nothing there counts. Below it the picked floor's space wins over a
 * nearer other floor: adjacent storeys' spaces share a face (one's ceiling is the next one's
 * floor), so the two tie at the same distance and only the picked floor's is drawn.
 */
export function pickedHit(hits: SpaceHit[], cut: number | null, floor: number | null): number {
  if (cut === null) return hits.length ? 0 : -1;
  const below = hits.map((h, i) => ({ ...h, i })).filter((h) => h.y <= cut + 1e-3);
  return (below.find((h) => h.level === floor) ?? below[0])?.i ?? -1;
}
