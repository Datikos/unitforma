import {
  CUT_VIEW_ELEVATION_DEG,
  OTHER_FLOOR_HOVER_OPACITY,
  PLAN_CUT_M,
  SELECTED_GLASS_OPACITY,
  SECTION_BELOW_BASE_M,
  SPACE_GLASS_OPACITY,
  aimOverFloor,
  cutHeight,
  ifcSpaceOpacity,
  pickedHit,
  sectionBand,
  takesSectionFill,
} from './floor-cut';

describe('cutHeight (ADR-0036 Decision 2)', () => {
  it('cuts a floor at plan height above its lowest space', () => {
    const floor = [
      { minY: 6.0, maxY: 9.0 },
      { minY: 6.05, maxY: 9.0 },
    ];
    expect(cutHeight(floor)).toBeCloseTo(6.0 + PLAN_CUT_M, 6);
  });

  it('cuts a low floor at half its height, so the cut never reaches the slab above', () => {
    expect(cutHeight([{ minY: 0, maxY: 2.0 }])).toBeCloseTo(1.0, 6);
  });

  it('does not cut a floor without spaces', () => {
    expect(cutHeight([])).toBeNull();
  });
});

describe('ifcSpaceOpacity (ADR-0036 Decisions 3 and 4)', () => {
  it('draws every space as glass when no floor is picked', () => {
    expect(ifcSpaceOpacity(null, null)).toBe(SPACE_GLASS_OPACITY);
    expect(SPACE_GLASS_OPACITY).toBeLessThan(1);
  });

  it('draws the picked floor as glass and the selected unit stronger', () => {
    expect(ifcSpaceOpacity(true, null)).toBe(SPACE_GLASS_OPACITY);
    expect(ifcSpaceOpacity(true, 'selected')).toBe(SELECTED_GLASS_OPACITY);
    expect(ifcSpaceOpacity(true, 'hover')).toBeGreaterThan(SPACE_GLASS_OPACITY);
  });

  it('hides the other floors until one is hovered', () => {
    expect(ifcSpaceOpacity(false, null)).toBe(0);
    expect(ifcSpaceOpacity(false, 'selected')).toBe(0);
    expect(ifcSpaceOpacity(false, 'hover')).toBe(OTHER_FLOOR_HOVER_OPACITY);
  });
});

describe('aimOverFloor (ADR-0036 Decision 5)', () => {
  it('keeps the azimuth of the current view and looks down at the cut elevation', () => {
    const p = aimOverFloor([100, 30, 0], [0, 10, 0], [5, 6, 5], 40);
    const dx = p[0] - 5;
    const dy = p[1] - 6;
    const dz = p[2] - 5;
    expect(Math.atan2(dx, dz)).toBeCloseTo(Math.PI / 2, 6);
    expect(Math.hypot(dx, dy, dz)).toBeCloseTo(40, 6);
    expect((Math.atan2(dy, Math.hypot(dx, dz)) * 180) / Math.PI).toBeCloseTo(
      CUT_VIEW_ELEVATION_DEG,
      6,
    );
  });

  it('picks a diagonal view when the camera stands over the target', () => {
    const p = aimOverFloor([0, 50, 0], [0, 0, 0], [0, 0, 0], 10);
    expect(p[0]).toBeCloseTo(p[2], 6);
    expect(p[0]).toBeGreaterThan(0);
  });
});

describe('section fill of cut elements (ADR-0036 #D2)', () => {
  it('fills from just under the floor base up to the cut', () => {
    const band = sectionBand([{ minY: 6.0, maxY: 9.0 }]);
    expect(band![0]).toBeCloseTo(6.0 - SECTION_BELOW_BASE_M, 6);
    expect(band![1]).toBeCloseTo(6.0 + PLAN_CUT_M, 6);
  });

  it('fills nothing when the floor is not cut', () => {
    expect(sectionBand([])).toBeNull();
  });

  it('fills opaque elements only, never glass or a plan space', () => {
    expect(takesSectionFill({ transparent: false, opacity: 1 }, false)).toBe(true);
    expect(takesSectionFill({ transparent: true, opacity: 0.4 }, false)).toBe(false);
    expect(takesSectionFill({ transparent: false, opacity: 1 }, true)).toBe(false);
  });
});

describe('pickedHit (ADR-0036 Decision 4, #D4)', () => {
  // N4: level 1's spaces end at 11.6 m where level 2's begin, so a tap on a level 2 flat hits
  // both faces at the same distance, in either order
  it('takes the picked floor on a tie with the floor below', () => {
    const hits = [
      { y: 13.5, level: 2 },
      { y: 11.6, level: 1 },
      { y: 11.6, level: 2 },
    ];
    expect(pickedHit(hits, 12.8, 2)).toBe(2);
  });

  it('takes another floor below the cut when the ray misses the picked one', () => {
    expect(pickedHit([{ y: 8.4, level: 0 }], 12.8, 2)).toBe(0);
  });

  it('counts nothing above the cut', () => {
    expect(pickedHit([{ y: 13.5, level: 2 }], 12.8, 2)).toBe(-1);
  });

  it('takes the nearest hit when nothing is cut', () => {
    expect(
      pickedHit(
        [
          { y: 17.9, level: 3 },
          { y: 14.8, level: 2 },
        ],
        null,
        null,
      ),
    ).toBe(0);
    expect(pickedHit([], null, null)).toBe(-1);
  });
});
