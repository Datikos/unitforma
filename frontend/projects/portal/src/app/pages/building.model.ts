import { Availability, FloorUnit } from '../core/portal-api';
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
