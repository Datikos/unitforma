import { levelShiftLine, realignedLine } from './ifc-plan-fit';

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

describe('the note when floors were aligned after the conversion (ADR-0030 #D3)', () => {
  it('names the realigned levels in order and says what a re-run does', () => {
    const line = realignedLine([3, -2, 1, 2]);
    expect(line.startsWith('Levels -2, 1, 2 and 3 were aligned on the drawing')).toBe(true);
    expect(line).toContain('Re-run the conversion');
    expect(line).toContain('go back to suggested');
    expect(realignedLine([1]).startsWith('Level 1 was aligned')).toBe(true);
  });

  it('says nothing when no floor moved since the conversion', () => {
    expect(realignedLine([])).toBe('');
  });
});
