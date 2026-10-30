import { BuildingDoc } from '../core/portal-api';

const SCHEMATIC = 'Schematic model generated from floor plans — not an architectural model';

/**
 * The site view's disclaimer (plan §7.3) when some buildings are the architect's model on the
 * site and the others schematic (ADR-0037 Decision 3): which is which, in one line.
 */
export function siteBadge(
  buildings: readonly Pick<BuildingDoc, 'code' | 'name' | 'model' | 'floors'>[],
): string {
  const placed = buildings.filter((b) => b.model?.site_matrix?.length === 16);
  if (!placed.length) return SCHEMATIC;
  const others = buildings.filter(
    (b) => !placed.includes(b) && b.floors.some((f) => f.units.length),
  );
  if (!others.length) return placed[0].model!.disclaimer;
  const names = placed.map((b) => b.name || `Building ${b.code}`).join(', ');
  return `${names}: the architect's model; the others are schematic, generated from floor plans`;
}
