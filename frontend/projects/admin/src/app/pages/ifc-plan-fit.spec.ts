import { levelShiftLine } from './ifc-plan-fit';

describe('the plan fit line on the admin 3D page (ADR-0030 #D1)', () => {
  it('names the levels moved onto their own slab with the distance and the share inside', () => {
    const pf = {
      per_level: {
        '-2': { iou: 0.287, coverage: 0.978 },
        '2': { coverage: 0.854, shift_m: [0, 3.25], coverage_shifted: 0.996 },
        '1': { coverage: 0.878, shift_m: [-0.25, 2.75], coverage_shifted: 0.995 },
      },
    };
    expect(levelShiftLine(pf)).toBe(
      'Drawn on another sheet origin, so moved onto their own slab: level 1 by 2.8 m (100 % inside), level 2 by 3.3 m (100 % inside).',
    );
  });

  it('names a level left as fitted because it lies too far off', () => {
    expect(levelShiftLine({ per_level: { '3': { coverage: 0.2, shift_refused: true } } })).toBe(
      'More than 5 m off their slab and left as fitted: level 3; check them in the model.',
    );
  });

  it('says nothing when no level moved, also for a fit stored before the shifts', () => {
    expect(levelShiftLine({ per_level: { '0': { coverage: 0.98 } } })).toBe('');
    expect(levelShiftLine({})).toBe('');
  });
});
