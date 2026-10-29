import { FloorUnit } from '../core/portal-api';
import { countByAvailability, floorChosen, groupUnitsByType, tapOnModel } from './building.model';

function unit(code: string, unit_type: string, availability: FloorUnit['availability']): FloorUnit {
  return { id: code, code, unit_type, availability, ring: null };
}

describe('groupUnitsByType (building page unit list)', () => {
  it('groups by type with the label sorted alphabetically and counts the available ones', () => {
    const groups = groupUnitsByType([
      unit('P-1', 'parking', 'available'),
      unit('A-1', 'apartment', 'sold'),
      unit('A-2', 'apartment', 'available'),
    ]);
    expect(groups.map((g) => g.label)).toEqual(['Apartment', 'Parking']);
    expect(groups[0].available).toBe(1);
    expect(groups[1].units.map((u) => u.code)).toEqual(['P-1']);
  });

  it('orders codes naturally, so A-2 comes before A-17 and not after A-1x', () => {
    const groups = groupUnitsByType([
      unit('A-17', 'apartment', 'available'),
      unit('A-2', 'apartment', 'available'),
      unit('A-1', 'apartment', 'available'),
      unit('A-10', 'apartment', 'available'),
    ]);
    expect(groups[0].units.map((u) => u.code)).toEqual(['A-1', 'A-2', 'A-10', 'A-17']);
  });

  it('returns no groups for an empty floor', () => {
    expect(groupUnitsByType([])).toEqual([]);
  });
});

describe('countByAvailability (building page legend)', () => {
  it('lists every state, zero included, so the legend never loses a colour', () => {
    expect(
      countByAvailability([
        unit('A-1', 'apartment', 'available'),
        unit('P-1', 'parking', 'reserved'),
      ]),
    ).toEqual({ available: 1, reserved: 1, sold: 0, withdrawn: 0 });
  });
});

describe('whole building until a floor is chosen (ADR-0036 #D3)', () => {
  it('opens whole without a floor or unit in the link', () => {
    expect(floorChosen(undefined, undefined)).toBe(false);
    expect(floorChosen('', undefined)).toBe(false);
    expect(floorChosen('2', undefined)).toBe(true);
    expect(floorChosen(undefined, 'A-02-11')).toBe(true);
  });

  it('selects a tapped unit in place only on the floor already cut open', () => {
    expect(tapOnModel(true, 2, 2)).toBe('select');
    expect(tapOnModel(true, 2, 1)).toBe('go');
    // the whole building shows the first floor's plan, but a tap there still cuts the model
    expect(tapOnModel(false, -2, -2)).toBe('go');
  });
});
