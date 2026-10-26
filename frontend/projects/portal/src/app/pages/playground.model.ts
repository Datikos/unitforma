import type { Point, Ring } from 'plan-viewer';

/**
 * Renovation playground (ADR-0020 Phase A): the catalogue of true-scale pieces, the arrangement a
 * buyer makes on the unit plan, its browser storage and its share link. Pure functions; the
 * component (`unit-playground.component.ts`) owns the state.
 */

export type RoomKey = 'bedroom' | 'living' | 'kitchen' | 'bathroom' | 'hall' | 'balcony';

export interface Room {
  key: RoomKey;
  label: string;
  icon: string;
}

export const ROOMS: readonly Room[] = [
  { key: 'bedroom', label: 'Bedroom', icon: 'lucideBedDouble' },
  { key: 'living', label: 'Living', icon: 'lucideSofa' },
  { key: 'kitchen', label: 'Kitchen', icon: 'lucideRefrigerator' },
  { key: 'bathroom', label: 'Bathroom', icon: 'lucideBath' },
  { key: 'hall', label: 'Hall', icon: 'lucideDoorOpen' },
  { key: 'balcony', label: 'Balcony', icon: 'lucideSun' },
];

export type Shape = 'rect' | 'round' | 'l';

/** A catalogue piece: width and depth in metres; `round` uses the width as its diameter. */
export interface CatalogueItem {
  id: string;
  name: string;
  room: RoomKey;
  icon: string;
  w: number;
  d: number;
  shape: Shape;
}

/** Depth of the seat of an L-shaped sofa, metres. */
const SEAT = 0.9;

/** The platform's pieces, common retail sizes; a tenant's own rows come in ADR-0020 Phase C. */
export const CATALOGUE: readonly CatalogueItem[] = [
  {
    id: 'bed-180',
    name: 'Double bed',
    room: 'bedroom',
    icon: 'lucideBedDouble',
    w: 1.8,
    d: 2.0,
    shape: 'rect',
  },
  {
    id: 'bed-160',
    name: 'Double bed',
    room: 'bedroom',
    icon: 'lucideBedDouble',
    w: 1.6,
    d: 2.0,
    shape: 'rect',
  },
  {
    id: 'bed-140',
    name: 'Bed',
    room: 'bedroom',
    icon: 'lucideBedDouble',
    w: 1.4,
    d: 2.0,
    shape: 'rect',
  },
  {
    id: 'bed-90',
    name: 'Single bed',
    room: 'bedroom',
    icon: 'lucideBedSingle',
    w: 0.9,
    d: 2.0,
    shape: 'rect',
  },
  { id: 'cot', name: 'Cot', room: 'bedroom', icon: 'lucideBaby', w: 0.6, d: 1.2, shape: 'rect' },
  {
    id: 'nightstand',
    name: 'Nightstand',
    room: 'bedroom',
    icon: 'lucideLamp',
    w: 0.45,
    d: 0.4,
    shape: 'rect',
  },
  {
    id: 'wardrobe-200',
    name: 'Wardrobe',
    room: 'bedroom',
    icon: 'lucideShirt',
    w: 2.0,
    d: 0.6,
    shape: 'rect',
  },
  {
    id: 'wardrobe-150',
    name: 'Wardrobe',
    room: 'bedroom',
    icon: 'lucideShirt',
    w: 1.5,
    d: 0.6,
    shape: 'rect',
  },
  {
    id: 'chest',
    name: 'Chest of drawers',
    room: 'bedroom',
    icon: 'lucideArchive',
    w: 1.0,
    d: 0.45,
    shape: 'rect',
  },
  {
    id: 'desk',
    name: 'Desk',
    room: 'bedroom',
    icon: 'lucideLampDesk',
    w: 1.2,
    d: 0.6,
    shape: 'rect',
  },
  { id: 'sofa-3', name: 'Sofa', room: 'living', icon: 'lucideSofa', w: 2.2, d: 0.9, shape: 'rect' },
  { id: 'sofa-2', name: 'Sofa', room: 'living', icon: 'lucideSofa', w: 1.6, d: 0.9, shape: 'rect' },
  {
    id: 'sofa-l',
    name: 'Corner sofa',
    room: 'living',
    icon: 'lucideSofa',
    w: 2.6,
    d: 1.6,
    shape: 'l',
  },
  {
    id: 'armchair',
    name: 'Armchair',
    room: 'living',
    icon: 'lucideArmchair',
    w: 0.9,
    d: 0.9,
    shape: 'rect',
  },
  {
    id: 'coffee',
    name: 'Coffee table',
    room: 'living',
    icon: 'lucideTable2',
    w: 1.0,
    d: 0.6,
    shape: 'rect',
  },
  { id: 'tv', name: 'TV stand', room: 'living', icon: 'lucideTv', w: 1.6, d: 0.45, shape: 'rect' },
  {
    id: 'bookcase',
    name: 'Bookcase',
    room: 'living',
    icon: 'lucideLibrary',
    w: 0.8,
    d: 0.3,
    shape: 'rect',
  },
  {
    id: 'dining-4',
    name: 'Dining table',
    room: 'living',
    icon: 'lucideUtensils',
    w: 1.2,
    d: 0.8,
    shape: 'rect',
  },
  {
    id: 'dining-6',
    name: 'Dining table',
    room: 'living',
    icon: 'lucideUtensils',
    w: 1.8,
    d: 0.9,
    shape: 'rect',
  },
  {
    id: 'dining-round',
    name: 'Round table',
    room: 'living',
    icon: 'lucideCircle',
    w: 1.1,
    d: 1.1,
    shape: 'round',
  },
  {
    id: 'chair',
    name: 'Chair',
    room: 'living',
    icon: 'lucideSquare',
    w: 0.45,
    d: 0.45,
    shape: 'rect',
  },
  {
    id: 'piano',
    name: 'Upright piano',
    room: 'living',
    icon: 'lucidePiano',
    w: 1.5,
    d: 0.6,
    shape: 'rect',
  },
  {
    id: 'kitchen-run',
    name: 'Kitchen units',
    room: 'kitchen',
    icon: 'lucideGrid2x2',
    w: 2.4,
    d: 0.6,
    shape: 'rect',
  },
  {
    id: 'island',
    name: 'Island',
    room: 'kitchen',
    icon: 'lucideSquare',
    w: 1.2,
    d: 0.9,
    shape: 'rect',
  },
  {
    id: 'fridge',
    name: 'Fridge',
    room: 'kitchen',
    icon: 'lucideRefrigerator',
    w: 0.6,
    d: 0.65,
    shape: 'rect',
  },
  {
    id: 'cooker',
    name: 'Cooker',
    room: 'kitchen',
    icon: 'lucideCookingPot',
    w: 0.6,
    d: 0.6,
    shape: 'rect',
  },
  {
    id: 'washer',
    name: 'Washing machine',
    room: 'kitchen',
    icon: 'lucideWashingMachine',
    w: 0.6,
    d: 0.6,
    shape: 'rect',
  },
  {
    id: 'bathtub',
    name: 'Bathtub',
    room: 'bathroom',
    icon: 'lucideBath',
    w: 1.7,
    d: 0.75,
    shape: 'rect',
  },
  {
    id: 'shower',
    name: 'Shower',
    room: 'bathroom',
    icon: 'lucideShowerHead',
    w: 0.9,
    d: 0.9,
    shape: 'rect',
  },
  {
    id: 'wc',
    name: 'Toilet',
    room: 'bathroom',
    icon: 'lucideToilet',
    w: 0.4,
    d: 0.65,
    shape: 'rect',
  },
  {
    id: 'basin',
    name: 'Washbasin',
    room: 'bathroom',
    icon: 'lucideDroplet',
    w: 0.6,
    d: 0.45,
    shape: 'rect',
  },
  {
    id: 'shoes',
    name: 'Shoe cabinet',
    room: 'hall',
    icon: 'lucidePackage',
    w: 1.0,
    d: 0.35,
    shape: 'rect',
  },
  {
    id: 'coats',
    name: 'Coat rack',
    room: 'hall',
    icon: 'lucideShirt',
    w: 0.8,
    d: 0.4,
    shape: 'rect',
  },
  {
    id: 'hall-wardrobe',
    name: 'Hall wardrobe',
    room: 'hall',
    icon: 'lucideDoorClosed',
    w: 1.2,
    d: 0.6,
    shape: 'rect',
  },
  {
    id: 'bistro',
    name: 'Bistro table',
    room: 'balcony',
    icon: 'lucideSun',
    w: 0.6,
    d: 0.6,
    shape: 'round',
  },
  {
    id: 'lounger',
    name: 'Sun lounger',
    room: 'balcony',
    icon: 'lucideUmbrella',
    w: 2.0,
    d: 0.7,
    shape: 'rect',
  },
  {
    id: 'planter',
    name: 'Planter',
    room: 'balcony',
    icon: 'lucideSprout',
    w: 0.8,
    d: 0.3,
    shape: 'rect',
  },
];

const BY_ID = new Map(CATALOGUE.map((c) => [c.id, c]));

export function catalogueItem(id: string): CatalogueItem | undefined {
  return BY_ID.get(id);
}

export type Rotation = 0 | 90 | 180 | 270;

/** A piece on the plan: its centre in metres from the top-left corner of the unit outline's box. */
export interface PlacedPiece {
  item: string;
  cx_m: number;
  cy_m: number;
  rot: Rotation;
  flip: boolean;
}

/** What the browser keeps and, in Phase D, what a redesign inquiry carries (ADR-0020 Decision 5). */
export interface Layout {
  v: 1;
  /** The buyer's wall colour as hex, when it differs from the stated one. */
  wall_colour?: string;
  pieces: PlacedPiece[];
}

export const MAX_PIECES = 200;

/** "160×200 cm": the size in whole centimetres, the unit buyers quote (0.9 m is 90, not 90.00000000000001). */
export function pieceSize(p: { w: number; d: number; shape?: Shape }): string {
  const w = Math.round(p.w * 100);
  return p.shape === 'round' ? `Ø${w} cm` : `${w}×${Math.round(p.d * 100)} cm`;
}

/** "Bed 160×200 cm": the name with the size. */
export function pieceLabel(p: { name: string; w: number; d: number; shape?: Shape }): string {
  return `${p.name} ${pieceSize(p)}`;
}

/** The piece's outline in metres around its centre, after flip and rotation. */
export function shapeRing(item: CatalogueItem, rot: Rotation = 0, flip = false): Point[] {
  const { w, d } = item;
  let pts: Point[];
  if (item.shape === 'round') {
    const r = w / 2;
    pts = Array.from({ length: 20 }, (_, i) => {
      const a = (i / 20) * Math.PI * 2;
      return [r * Math.cos(a), r * Math.sin(a)] as Point;
    });
  } else if (item.shape === 'l') {
    const s = Math.min(SEAT, w / 2, d / 2);
    pts = [
      [-w / 2, -d / 2],
      [w / 2, -d / 2],
      [w / 2, -d / 2 + s],
      [-w / 2 + s, -d / 2 + s],
      [-w / 2 + s, d / 2],
      [-w / 2, d / 2],
    ];
  } else {
    pts = [
      [-w / 2, -d / 2],
      [w / 2, -d / 2],
      [w / 2, d / 2],
      [-w / 2, d / 2],
    ];
  }
  const a = (rot * Math.PI) / 180;
  const cos = Math.round(Math.cos(a));
  const sin = Math.round(Math.sin(a));
  return pts.map(([x, y]) => {
    const fx = flip ? -x : x;
    return [round(fx * cos - y * sin), round(fx * sin + y * cos)] as Point;
  });
}

/** Where metres land on the plan: the outline's box corner (normalised) and the pixels per metre. */
export interface PlanFrame {
  x0: number;
  y0: number;
  /** plan pixels per metre */
  k: number;
  width: number;
  height: number;
}

/**
 * Plan pixels per metre from the unit's outline and its largest stated area, and the box corner the
 * pieces are measured from; null without an outline or an area (the editor then stays off).
 */
export function planFrame(
  plan: { width: number; height: number; ring: Point[] | null } | undefined,
  areas: Record<string, string | number> | undefined,
): PlanFrame | null {
  const ring = plan?.ring;
  const values = Object.values(areas ?? {})
    .map(Number)
    .filter((x) => Number.isFinite(x) && x > 0);
  if (!plan || !ring || ring.length < 3 || !values.length) return null;
  const { width: w, height: h } = plan;
  let a = 0;
  for (let i = 0; i < ring.length; i++) {
    const [x0, y0] = ring[i];
    const [x1, y1] = ring[(i + 1) % ring.length];
    a += x0 * w * y1 * h - x1 * w * y0 * h;
  }
  const px2 = Math.abs(a) / 2;
  if (px2 <= 0) return null;
  return {
    x0: Math.min(...ring.map((p) => p[0])),
    y0: Math.min(...ring.map((p) => p[1])),
    k: Math.sqrt(px2 / Math.max(...values)),
    width: w,
    height: h,
  };
}

/** The piece's outline in normalised plan coordinates. */
export function pieceRing(piece: PlacedPiece, frame: PlanFrame): Ring {
  const item = catalogueItem(piece.item);
  if (!item) return [];
  return shapeRing(item, piece.rot, piece.flip).map(
    ([x, y]) =>
      [
        frame.x0 + ((piece.cx_m + x) * frame.k) / frame.width,
        frame.y0 + ((piece.cy_m + y) * frame.k) / frame.height,
      ] as Point,
  );
}

/** The centre of the outline in metres from its box corner: where a new piece lands. */
export function outlineCentre(ring: Point[], frame: PlanFrame): [number, number] {
  const cx = ring.reduce((s, p) => s + p[0], 0) / ring.length;
  const cy = ring.reduce((s, p) => s + p[1], 0) / ring.length;
  return [
    round(((cx - frame.x0) * frame.width) / frame.k),
    round(((cy - frame.y0) * frame.height) / frame.k),
  ];
}

export function countByRoom(pieces: readonly PlacedPiece[]): Record<RoomKey, number> {
  const out: Record<RoomKey, number> = {
    bedroom: 0,
    living: 0,
    kitchen: 0,
    bathroom: 0,
    hall: 0,
    balcony: 0,
  };
  for (const p of pieces) {
    const item = catalogueItem(p.item);
    if (item) out[item.room]++;
  }
  return out;
}

function round(x: number): number {
  return Math.round(x * 100) / 100;
}

/** Approximate sRGB of the RAL classic codes developers quote most (RAL colour charts). */
const RAL: Record<string, string> = {
  '1013': '#e3d9c6',
  '1015': '#e6d2b5',
  '3000': '#a72920',
  '5010': '#0e294b',
  '6005': '#0f4336',
  '7016': '#383e42',
  '7035': '#cbd0cc',
  '7040': '#9da3a6',
  '8017': '#44322d',
  '9001': '#e9e0d2',
  '9002': '#d7d5cb',
  '9003': '#ecece7',
  '9004': '#2b2b2c',
  '9005': '#0e0e10',
  '9010': '#f1ece1',
  '9016': '#f1f0ea',
};

/** A swatch for a hex colour or one of the common RAL codes; transparent otherwise. */
export function swatch(code: string): string {
  const c = code.trim().toLowerCase();
  if (/^#([0-9a-f]{3}|[0-9a-f]{6})$/.test(c)) return c;
  const ral = c.replace(/^ral\s*/, '');
  return RAL[ral] ?? 'transparent';
}

const HEX6 = /^#[0-9a-f]{6}$/;

// --- validation shared by storage and the share link

function readPiece(x: unknown): PlacedPiece | null {
  if (!x || typeof x !== 'object') return null;
  const o = x as Record<string, unknown>;
  return piece(o['item'], o['cx_m'], o['cy_m'], o['rot'], o['flip']);
}

function piece(
  item: unknown,
  cx: unknown,
  cy: unknown,
  rot: unknown,
  flip: unknown,
): PlacedPiece | null {
  if (typeof item !== 'string' || !BY_ID.has(item)) return null;
  if (
    typeof cx !== 'number' ||
    !Number.isFinite(cx) ||
    typeof cy !== 'number' ||
    !Number.isFinite(cy)
  )
    return null;
  if (rot !== 0 && rot !== 90 && rot !== 180 && rot !== 270) return null;
  return { item, cx_m: round(cx), cy_m: round(cy), rot, flip: flip === true || flip === 1 };
}

function wallColour(x: unknown): string | undefined {
  return typeof x === 'string' && HEX6.test(x) ? x : undefined;
}

/** A layout from untrusted JSON (storage or a link): null when it is not a `v: 1` layout. */
export function readLayout(raw: unknown): Layout | null {
  if (!raw || typeof raw !== 'object') return null;
  const o = raw as Record<string, unknown>;
  if (o['v'] !== 1 || !Array.isArray(o['pieces']) || o['pieces'].length > MAX_PIECES) return null;
  const pieces = o['pieces'].map(readPiece);
  if (pieces.some((p) => p === null)) return null;
  return { v: 1, wall_colour: wallColour(o['wall_colour']), pieces: pieces as PlacedPiece[] };
}

// --- browser storage (ADR-0020 Decision 5): per host, project and unit

export function layoutKey(host: string, slug: string, code: string): string {
  return `uf:layout:${host}:${slug}:${code}`;
}

export function loadLayout(key: string): Layout | null {
  try {
    const raw = localStorage.getItem(key);
    return raw ? readLayout(JSON.parse(raw)) : null;
  } catch {
    return null;
  }
}

/** Writes the layout, or removes the key when it is empty; false when storage is unavailable. */
export function saveLayout(key: string, layout: Layout): boolean {
  try {
    if (!layout.pieces.length && !layout.wall_colour) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(layout));
    return true;
  } catch {
    return false;
  }
}

// --- share link (ADR-0020 Decision 8): the same layout in a compact form in the URL fragment

type Packed = { v: 1; w?: string; p: [string, number, number, number, 0 | 1][] };

export function encodeLayout(layout: Layout): string {
  const packed: Packed = {
    v: 1,
    p: layout.pieces.map((p) => [p.item, p.cx_m, p.cy_m, p.rot, p.flip ? 1 : 0]),
  };
  if (layout.wall_colour) packed.w = layout.wall_colour;
  const bytes = new TextEncoder().encode(JSON.stringify(packed));
  let bin = '';
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function decodeLayout(text: string): Layout | null {
  try {
    const b64 = text.replace(/-/g, '+').replace(/_/g, '/');
    const bin = atob(b64 + '='.repeat((4 - (b64.length % 4)) % 4));
    const bytes = Uint8Array.from(bin, (c) => c.charCodeAt(0));
    const o = JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>;
    if (!o || o['v'] !== 1 || !Array.isArray(o['p']) || o['p'].length > MAX_PIECES) return null;
    const pieces = (o['p'] as unknown[]).map((row) =>
      Array.isArray(row) && row.length === 5 ? piece(row[0], row[1], row[2], row[3], row[4]) : null,
    );
    if (pieces.some((p) => p === null)) return null;
    return { v: 1, wall_colour: wallColour(o['w']), pieces: pieces as PlacedPiece[] };
  } catch {
    return null;
  }
}

/** The `l` value of a URL fragment such as `#l=...`, or null. */
export function layoutFromFragment(fragment: string | null | undefined): Layout | null {
  const m = /(?:^|&)l=([A-Za-z0-9_-]+)/.exec(fragment ?? '');
  return m ? decodeLayout(m[1]) : null;
}
