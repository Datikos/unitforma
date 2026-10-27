import { LayoutOut } from 'api-client';
import { layoutSummary, orderLayouts, registryFacts, validateCode } from './layouts.model';

function layout(partial: Partial<LayoutOut>): LayoutOut {
  return {
    id: 'l1',
    project_id: 'p',
    code: 'L1',
    name: null,
    status: 'confirmed',
    source: 'manual',
    match: null,
    version: 1,
    created_at: '2026-10-26T00:00:00Z',
    updated_at: '2026-10-26T00:00:00Z',
    units: [],
    media_count: 0,
    public_media_count: 0,
    cover_url: null,
    ...partial,
  };
}

describe('layouts model (ADR-0022)', () => {
  const existing = [layout({ id: 'a', code: 'L1' }), layout({ id: 'b', code: 'Type A' })];

  it('refuses a blank, an over-long and a duplicate code without case, except for itself', () => {
    expect(validateCode('  ', existing)).toBe('Code is required');
    expect(validateCode('x'.repeat(41), existing)).toContain('40');
    expect(validateCode('l1', existing)).toBe('Code L1 already exists in this project');
    expect(validateCode('type a', existing, 'b')).toBeNull();
    expect(validateCode('L2', existing)).toBeNull();
  });

  it('summarises a layout by units, availability and public media', () => {
    const l = layout({
      units: [
        {
          unit_id: '1',
          code: 'A-1',
          availability: 'available',
          building_code: 'A',
          floor_level: 1,
        },
        { unit_id: '2', code: 'A-2', availability: 'sold', building_code: 'A', floor_level: 2 },
        {
          unit_id: '3',
          code: 'A-3',
          availability: 'available',
          building_code: 'A',
          floor_level: 3,
        },
      ],
      media_count: 3,
      public_media_count: 2,
    });
    expect(layoutSummary(l)).toBe('3 units · 2 available · 1 sold · 2 public of 3 media');
    expect(layoutSummary(layout({}))).toBe('0 units · no media yet');
  });

  it('counts layouts, linked units and layouts without public media for the header', () => {
    const list = [
      layout({ id: 'a', units: [], public_media_count: 1, media_count: 1 }),
      layout({
        id: 'b',
        units: [
          {
            unit_id: '1',
            code: 'A-1',
            availability: 'available',
            building_code: 'A',
            floor_level: 1,
          },
        ],
      }),
    ];
    expect(registryFacts(list)).toEqual({ layouts: 2, linked: 1, withoutMedia: 1, proposed: 0 });
  });

  it('names a proposed layout and its match in the summary, and lists proposed ones first', () => {
    const proposed = layout({
      id: 'p',
      code: 'L2',
      status: 'proposed',
      source: 'autopilot',
      match: { iou_min: 0.973, members: 4 },
    });
    expect(layoutSummary(proposed)).toBe(
      '0 units · proposed by the solver (outlines match 0.97) · no media yet',
    );
    const list = [layout({ id: 'a', code: 'L10' }), proposed, layout({ id: 'b', code: 'L1' })];
    expect(orderLayouts(list).map((l) => l.code)).toEqual(['L2', 'L1', 'L10']);
    expect(registryFacts(list).proposed).toBe(1);
  });
});
