import {
  CATALOGUE,
  Layout,
  MAX_PIECES,
  ROOMS,
  catalogueItem,
  countByRoom,
  decodeLayout,
  encodeLayout,
  layoutFromFragment,
  layoutKey,
  loadLayout,
  outlineCentre,
  pieceLabel,
  pieceRing,
  pieceSize,
  planFrame,
  readLayout,
  saveLayout,
  shapeRing,
  swatch,
} from './playground.model';

describe('pieceLabel (furniture at true scale, ADR-0017 E6 / ADR-0020 A2)', () => {
  it('names the piece with its size in whole centimetres', () => {
    expect(pieceLabel({ name: 'Bed', w: 1.6, d: 2.0 })).toBe('Bed 160×200 cm');
    expect(pieceLabel({ name: 'Bathtub', w: 1.7, d: 0.75 })).toBe('Bathtub 170×75 cm');
  });

  it('rounds floating-point metres, so 0.9 m is 90 cm and not 90.00000000000001', () => {
    expect(pieceLabel({ name: 'Sofa', w: 2.2, d: 0.9 })).toBe('Sofa 220×90 cm');
    expect(pieceSize({ w: 2.2, d: 0.9 })).toBe('220×90 cm');
  });

  it('quotes a round piece by its diameter', () => {
    expect(pieceSize({ w: 1.1, d: 1.1, shape: 'round' })).toBe('Ø110 cm');
  });
});

describe('the code catalogue (ADR-0020 A2)', () => {
  it('has 25 to 40 pieces with unique ids, every room represented, no piece without a room', () => {
    expect(CATALOGUE.length).toBeGreaterThanOrEqual(25);
    expect(CATALOGUE.length).toBeLessThanOrEqual(40);
    expect(new Set(CATALOGUE.map((c) => c.id)).size).toBe(CATALOGUE.length);
    for (const r of ROOMS) expect(CATALOGUE.some((c) => c.room === r.key)).toBe(true);
    for (const c of CATALOGUE) expect(ROOMS.some((r) => r.key === c.room)).toBe(true);
  });

  it('counts the placed pieces per room', () => {
    const counts = countByRoom([
      { item: 'bed-160', cx_m: 1, cy_m: 1, rot: 0, flip: false },
      { item: 'wardrobe-200', cx_m: 1, cy_m: 1, rot: 0, flip: false },
      { item: 'bathtub', cx_m: 1, cy_m: 1, rot: 0, flip: false },
    ]);
    expect(counts.bedroom).toBe(2);
    expect(counts.bathroom).toBe(1);
    expect(counts.living).toBe(0);
  });
});

describe('shapeRing: outlines in metres under rotation and flip', () => {
  it('draws a rectangle around its centre and swaps width and depth at 90°', () => {
    const desk = catalogueItem('desk')!; // 1.2 × 0.6
    expect(shapeRing(desk)).toEqual([
      [-0.6, -0.3],
      [0.6, -0.3],
      [0.6, 0.3],
      [-0.6, 0.3],
    ]);
    const xs = shapeRing(desk, 90).map((p) => p[0]);
    const ys = shapeRing(desk, 90).map((p) => p[1]);
    expect(Math.max(...xs) - Math.min(...xs)).toBeCloseTo(0.6);
    expect(Math.max(...ys) - Math.min(...ys)).toBeCloseTo(1.2);
  });

  it('cuts the inner corner of an L sofa and mirrors it on flip', () => {
    const sofa = catalogueItem('sofa-l')!; // 2.6 × 1.6; the seat is capped at half the depth, 0.8
    const ring = shapeRing(sofa);
    expect(ring).toHaveLength(6);
    expect(ring).toContainEqual([-0.5, 0.8]); // the leg's inner edge runs on the left
    const flipped = shapeRing(sofa, 0, true);
    expect(flipped).toContainEqual([0.5, 0.8]); // and on the right after the flip
  });

  it('makes a round table a 20-gon of its diameter', () => {
    const ring = shapeRing(catalogueItem('dining-round')!);
    expect(ring).toHaveLength(20);
    for (const [x, y] of ring) expect(Math.hypot(x, y)).toBeCloseTo(0.55, 1); // points are rounded to the centimetre
  });
});

describe('planFrame and pieceRing: metres on the plan', () => {
  // A 10 × 5 m unit drawn as a 400 × 200 px box on a 1000 × 1000 px plan: 40 px per metre.
  const plan = {
    width: 1000,
    height: 1000,
    ring: [
      [0.1, 0.2],
      [0.5, 0.2],
      [0.5, 0.4],
      [0.1, 0.4],
    ] as [number, number][],
  };

  it('takes the scale from the outline area and the largest stated area', () => {
    const f = planFrame(plan, { net: '45', gross: '50' })!;
    expect(f.k).toBeCloseTo(40);
    expect(f.x0).toBe(0.1);
    expect(f.y0).toBe(0.2);
  });

  it('is null without an outline or without a stated area, so the editor stays off', () => {
    expect(planFrame(plan, {})).toBeNull();
    expect(planFrame({ ...plan, ring: null }, { net: '50' })).toBeNull();
    expect(planFrame(plan, { net: 'unknown' })).toBeNull();
  });

  it('places a piece in normalised plan coordinates from the box corner', () => {
    const f = planFrame(plan, { net: '50' })!;
    const ring = pieceRing({ item: 'desk', cx_m: 5, cy_m: 2.5, rot: 0, flip: false }, f);
    // centre at (0.1 + 5·40/1000, 0.2 + 2.5·40/1000) = (0.3, 0.3); half size 0.6 m = 0.024, 0.3 m = 0.012
    expect(ring[0][0]).toBeCloseTo(0.3 - 0.024);
    expect(ring[0][1]).toBeCloseTo(0.3 - 0.012);
    expect(ring[2][0]).toBeCloseTo(0.3 + 0.024);
    expect(ring[2][1]).toBeCloseTo(0.3 + 0.012);
    expect(outlineCentre(plan.ring, f)).toEqual([5, 2.5]);
  });

  it('gives an unknown item an empty ring instead of throwing', () => {
    const f = planFrame(plan, { net: '50' })!;
    expect(pieceRing({ item: 'gone', cx_m: 1, cy_m: 1, rot: 0, flip: false }, f)).toEqual([]);
  });
});

const thirty: Layout = {
  v: 1,
  wall_colour: '#e6d2b5',
  pieces: Array.from({ length: 30 }, (_, i) => ({
    item: CATALOGUE[i % CATALOGUE.length].id,
    cx_m: Math.round(i * 37) / 100,
    cy_m: Math.round(i * 53) / 100,
    rot: ([0, 90, 180, 270] as const)[i % 4],
    flip: i % 3 === 0,
  })),
};

describe('share link (ADR-0020 Decision 8, E1)', () => {
  it('round-trips a 30-piece arrangement under 2 kB', () => {
    const text = encodeLayout(thirty);
    expect(text.length).toBeLessThan(2000);
    expect(text).toMatch(/^[A-Za-z0-9_-]+$/);
    expect(decodeLayout(text)).toEqual(thirty);
    expect(layoutFromFragment(`l=${text}`)).toEqual(thirty);
  });

  it('rejects garbage, an unknown piece, a bad rotation, a non-finite number and too many pieces', () => {
    expect(decodeLayout('not base64!')).toBeNull();
    expect(decodeLayout(encodeLayout({ v: 1, pieces: [] }).slice(0, 5))).toBeNull();
    expect(layoutFromFragment(null)).toBeNull();
    expect(layoutFromFragment('x=1')).toBeNull();
    const bad = (rows: unknown[]) => {
      const json = JSON.stringify({ v: 1, p: rows });
      return decodeLayout(btoa(json).replace(/=+$/, ''));
    };
    expect(bad([['no-such-item', 1, 1, 0, 0]])).toBeNull();
    expect(bad([['desk', 1, 1, 45, 0]])).toBeNull();
    expect(bad([['desk', 'x', 1, 0, 0]])).toBeNull();
    expect(bad([['desk', 1]])).toBeNull();
    expect(bad(Array.from({ length: MAX_PIECES + 1 }, () => ['desk', 1, 1, 0, 0]))).toBeNull();
    expect(bad([['desk', 1.234, 2, 90, 1]])).toEqual({
      v: 1,
      wall_colour: undefined,
      pieces: [{ item: 'desk', cx_m: 1.23, cy_m: 2, rot: 90, flip: true }],
    });
  });

  it('keeps only a 6-digit hex wall colour', () => {
    expect(
      decodeLayout(encodeLayout({ v: 1, wall_colour: '#abc', pieces: [] }))?.wall_colour,
    ).toBeUndefined();
    expect(
      decodeLayout(encodeLayout({ v: 1, wall_colour: '#aabbcc', pieces: [] }))?.wall_colour,
    ).toBe('#aabbcc');
  });
});

describe('browser storage (ADR-0020 Decision 5, A4)', () => {
  const key = layoutKey('lisi.example', 'permit-1', 'A-12');

  afterEach(() => localStorage.removeItem(key));

  it('reads back the stored v:1 shape and drops a stored shape it does not know', () => {
    expect(saveLayout(key, thirty)).toBe(true);
    expect(loadLayout(key)).toEqual(thirty);
    localStorage.setItem(key, JSON.stringify({ v: 2, pieces: [] }));
    expect(loadLayout(key)).toBeNull();
    localStorage.setItem(key, '{broken');
    expect(loadLayout(key)).toBeNull();
  });

  it('reads the documented example of the stored shape', () => {
    // The example of ADR-0020 Decision 5; a later release must still read it (my-release).
    const stored = {
      v: 1,
      wall_colour: '#f1ece1',
      pieces: [{ item: 'bed-160', cx_m: 3.2, cy_m: 2.1, rot: 90, flip: false }],
    };
    expect(readLayout(stored)).toEqual(stored);
    expect(
      readLayout({ v: 1, pieces: [{ item: 'bed-160', cx_m: 1, cy_m: 1, rot: 90 }] })?.pieces[0]
        .flip,
    ).toBe(false);
    expect(
      readLayout({ v: 1, pieces: [{ item: 'bed-160', cx_m: 1, cy_m: 1, rot: 90, flip: 1 }] })
        ?.pieces[0].flip,
    ).toBe(true);
  });

  it('removes the key when the arrangement is emptied', () => {
    saveLayout(key, thirty);
    saveLayout(key, { v: 1, pieces: [] });
    expect(localStorage.getItem(key)).toBeNull();
  });

  it('survives an unavailable storage', () => {
    const original = Storage.prototype.setItem;
    Storage.prototype.setItem = () => {
      throw new Error('QuotaExceededError');
    };
    try {
      expect(saveLayout(key, thirty)).toBe(false);
    } finally {
      Storage.prototype.setItem = original;
    }
  });
});

describe('swatch', () => {
  it('maps hex and common RAL codes, transparent otherwise', () => {
    expect(swatch('#ABC')).toBe('#abc');
    expect(swatch('RAL 9010')).toBe('#f1ece1');
    expect(swatch('9010')).toBe('#f1ece1');
    expect(swatch('eggshell')).toBe('transparent');
  });
});
