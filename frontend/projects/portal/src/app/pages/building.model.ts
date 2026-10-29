import { Availability, FloorDoc, FloorUnit } from '../core/portal-api';
import { typeLabel } from '../core/format';

/** Units of one kind on a floor, in natural code order (A-2 before A-17). */
export interface UnitGroup {
  type: string;
  label: string;
  units: FloorUnit[];
  available: number;
}

const byCode = new Intl.Collator('en', { numeric: true, sensitivity: 'base' });

/** One list per unit type, apartments first by label, codes in natural order inside each group. */
export function groupUnitsByType(units: readonly FloorUnit[]): UnitGroup[] {
  const groups = new Map<string, FloorUnit[]>();
  for (const u of units) {
    const list = groups.get(u.unit_type) ?? [];
    list.push(u);
    groups.set(u.unit_type, list);
  }
  return [...groups.entries()]
    .map(([type, list]) => ({
      type,
      label: typeLabel(type),
      units: [...list].sort((a, b) => byCode.compare(a.code, b.code)),
      available: list.filter((u) => u.availability === 'available').length,
    }))
    .sort((a, b) => a.label.localeCompare(b.label));
}

/** How many units of the floor sit in each availability state; every state is present, zero included. */
export function countByAvailability(units: readonly FloorUnit[]): Record<Availability, number> {
  const out: Record<Availability, number> = { available: 0, reserved: 0, sold: 0, withdrawn: 0 };
  for (const u of units) out[u.availability] += 1;
  return out;
}

/**
 * The building opens whole and is cut open at a floor only once the buyer chose one: a `?floor=`
 * or `?unit=` in the link, a floor on the left, a band on the facade or a unit on the 3D model
 * (ADR-0036 #D3). Without that choice the plan below still shows the first floor.
 */
export function floorChosen(floor: string | undefined, unit: string | undefined): boolean {
  return !!floor || !!unit;
}

/**
 * A unit tapped on the 3D model: selected in place when the model is already cut open at its
 * floor, else the page moves to its floor with it preselected (which cuts the model there).
 */
export function tapOnModel(chosen: boolean, level: number, unitLevel: number): 'select' | 'go' {
  return chosen && unitLevel === level ? 'select' : 'go';
}

/** What a buyer most likely came for, first: flats, then shops, then any floor with units. */
const FIRST_FLOOR_TYPES = ['apartment', 'commercial'];

/**
 * The floor the plan shows before the buyer chose one (ADR-0036 #D5): the lowest floor with an
 * apartment, else with a commercial unit, else with any unit, else the lowest floor. A parking
 * level under the building is not where a buyer starts.
 */
export function defaultFloor(floors: readonly Pick<FloorDoc, 'level' | 'units'>[]): number | null {
  const byLevel = [...floors].sort((a, b) => a.level - b.level);
  for (const type of FIRST_FLOOR_TYPES) {
    const f = byLevel.find((x) => x.units.some((u) => u.unit_type === type));
    if (f) return f.level;
  }
  return (byLevel.find((x) => x.units.length) ?? byLevel[0])?.level ?? null;
}
