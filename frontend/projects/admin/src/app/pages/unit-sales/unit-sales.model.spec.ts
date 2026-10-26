import { BoundaryOut, InventoryRow, SheetOut } from 'api-client';
import { describe, expect, it } from 'vitest';
import { blankForm, currentBoundary, perM2, planOf } from './unit-sales.model';

const ring = (x: number): [number, number][] => [
  [x, 0.1],
  [x + 0.1, 0.1],
  [x + 0.1, 0.2],
  [x, 0.2],
];

function boundary(
  id: string,
  unitId: string,
  x: number,
  extra: Partial<BoundaryOut> = {},
): BoundaryOut {
  return {
    id,
    unit_id: unitId,
    sheet_id: 'sheet-1',
    polygon: { ring: ring(x) },
    polygon_m: null,
    source: 'manual',
    status: 'approved',
    is_current: true,
    label: null,
    version: 1,
    ...extra,
  } as BoundaryOut;
}

const sheet = {
  id: 'sheet-1',
  raster_url: 'https://files.example/sheet-1.png',
  raster_width: 2000,
  raster_height: 1400,
} as SheetOut;

function row(
  unitId: string,
  code: string,
  availability: InventoryRow['availability'],
): InventoryRow {
  return { unit_id: unitId, code, availability } as InventoryRow;
}

describe('planOf: the floor plan card around one unit', () => {
  it('selects the unit, colours every outline by availability and counts the others', () => {
    const plan = planOf(
      'u1',
      sheet,
      [boundary('b1', 'u1', 0.1), boundary('b2', 'u2', 0.3), boundary('b3', 'u3', 0.5)],
      [row('u1', 'A-26', 'available'), row('u2', 'A-27', 'sold')],
    );
    expect(plan).not.toBeNull();
    expect(plan!.others).toBe(2);
    expect(plan!.focus).toEqual(ring(0.1));
    const mine = plan!.polygons.find((p) => p.id === 'u1')!;
    const sold = plan!.polygons.find((p) => p.id === 'u2')!;
    const unknown = plan!.polygons.find((p) => p.id === 'u3')!;
    expect(mine.selected).toBe(true);
    expect(mine.label).toBe('A-26');
    expect(mine.stroke).toBe('#047857');
    expect(sold.selected).toBe(false);
    expect(sold.stroke).toBe('#b91c1c');
    expect(sold.title).toBe('A-27 · Sold');
    expect(unknown.fill).toBeUndefined();
  });

  it('is null without a current outline of the unit or without a raster', () => {
    const superseded = boundary('b1', 'u1', 0.1, { status: 'superseded' });
    const old = boundary('b2', 'u1', 0.1, { is_current: false });
    expect(planOf('u1', sheet, [superseded, old, boundary('b3', 'u2', 0.3)], [])).toBeNull();
    expect(currentBoundary([superseded, old])).toBeNull();
    expect(
      planOf('u1', { ...sheet, raster_url: null }, [boundary('b1', 'u1', 0.1)], []),
    ).toBeNull();
  });
});

describe('perM2: the live price per m² while typing', () => {
  const base = {
    price_area_m2: '50',
    price_area_type: 'net_internal',
    price_area_verified: true,
    currency: 'EUR',
  } as unknown as InventoryRow;

  it('divides the typed price by the pricing area in the typed currency', () => {
    const r = perM2({ ...blankForm(), list_price: '100 000', currency: 'USD' }, base);
    expect(r).toEqual({ text: 'USD 2 000.00 per m² of net internal area', verified: true });
  });

  it('flags an unverified area and is empty on request, on a bad price or without an area', () => {
    const unverified = { ...base, price_area_verified: false } as InventoryRow;
    expect(
      perM2({ ...blankForm(), list_price: '100000', currency: 'EUR' }, unverified)!.verified,
    ).toBe(false);
    expect(
      perM2({ ...blankForm(), list_price: '100000', price_on_request: true }, base),
    ).toBeNull();
    expect(perM2({ ...blankForm(), list_price: 'abc' }, base)).toBeNull();
    expect(
      perM2({ ...blankForm(), list_price: '100000' }, {
        ...base,
        price_area_m2: null,
      } as InventoryRow),
    ).toBeNull();
  });
});
