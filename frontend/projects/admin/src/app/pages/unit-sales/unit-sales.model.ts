import {
  BoundaryOut,
  InventoryRow,
  MediaCreate,
  SalesChanges,
  SalesHistoryOut,
  SheetOut,
} from 'api-client';
import { PlanPolygon, Ring } from 'plan-viewer';
import { formatPrice, parsePriceInput } from '../../sales/sales-format';

export interface Form {
  availability: InventoryRow['availability'];
  list_price: string;
  currency: string;
  price_on_request: boolean;
  price_area_type: string | null;
  payment_plan_id: string | null;
  promotion_ids: string[];
  rooms: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  orientation: string;
  layout: string;
  wall_colour: string;
  entrance: string;
  public_description: string;
  internal_notes: string;
}

export type FormKey = keyof Form;

export interface TimelineEntry {
  at: string;
  text: string;
  reason?: string | null;
  tone: 'good' | 'warning' | 'bad' | 'neutral';
  icon: string;
}

export type MediaKind = NonNullable<MediaCreate['kind']>;
export const MEDIA_KINDS: { value: MediaKind; label: string }[] = [
  { value: 'plan_render', label: 'Plan render' },
  { value: 'interior_render', label: 'Interior render' },
  { value: 'exterior_render', label: 'Exterior render' },
  { value: 'photo', label: 'Photo' },
  { value: 'video', label: 'Video' },
  { value: 'document', label: 'Document' },
];

export function mediaKindLabel(k: string): string {
  return MEDIA_KINDS.find((m) => m.value === k)?.label ?? k;
}

export function blankForm(): Form {
  return {
    availability: 'available',
    list_price: '',
    currency: '',
    price_on_request: false,
    price_area_type: null,
    payment_plan_id: null,
    promotion_ids: [],
    rooms: null,
    bedrooms: null,
    bathrooms: null,
    orientation: '',
    layout: '',
    wall_colour: '',
    entrance: '',
    public_description: '',
    internal_notes: '',
  };
}

export function formFrom(r: InventoryRow): Form {
  return {
    availability: r.availability,
    list_price: r.list_price ?? '',
    currency: r.currency,
    price_on_request: r.price_on_request,
    price_area_type: r.price_area_type_override ?? null,
    payment_plan_id: r.payment_plan_id ?? null,
    promotion_ids: [...(r.promotion_ids ?? [])],
    rooms: r.rooms ?? null,
    bedrooms: r.bedrooms ?? null,
    bathrooms: r.bathrooms ?? null,
    orientation: r.orientation ?? '',
    layout: r.layout ?? '',
    wall_colour: r.wall_colour ?? '',
    entrance: r.entrance ?? '',
    public_description: r.public_description ?? '',
    internal_notes: r.internal_notes ?? '',
  };
}

/** Keys whose value differs from the saved row (what `.uf-changed` marks). */
export function changedKeys(form: Form, row: InventoryRow): FormKey[] {
  const base = formFrom(row);
  return (Object.keys(form) as FormKey[]).filter(
    (k) => JSON.stringify(form[k] ?? null) !== JSON.stringify(base[k] ?? null),
  );
}

/** Only the fields the user changed are sent, so a save never overwrites unrelated edits. Throws on a bad price. */
export function diffChanges(form: Form, row: InventoryRow): SalesChanges {
  const out: Record<string, unknown> = {};
  for (const k of changedKeys(form, row)) out[k] = form[k];
  if ('list_price' in out) {
    const p = parsePriceInput(out['list_price']);
    if (p === undefined) throw new Error('The price must be digits with at most two decimals');
    out['list_price'] = p;
  }
  for (const k of [
    'orientation',
    'entrance',
    'layout',
    'wall_colour',
    'public_description',
    'internal_notes',
  ])
    if (k in out && out[k] === '') out[k] = null;
  if ('currency' in out) out['currency'] = String(out['currency']).toUpperCase();
  for (const k of ['rooms', 'bedrooms', 'bathrooms'])
    if (k in out) out[k] = out[k] === null || out[k] === '' ? null : Number(out[k]);
  return out as SalesChanges;
}

export function timelineOf(h: SalesHistoryOut | null): TimelineEntry[] {
  if (!h) return [];
  const out: TimelineEntry[] = [
    ...h.prices.map((p) => ({
      at: p.changed_at,
      text: `Price ${formatPrice(p.old_price, p.old_currency) ?? 'on request'} → ${formatPrice(p.new_price, p.new_currency) ?? 'on request'}${p.import_batch_id ? ' (import)' : ''}`,
      reason: p.reason,
      tone: 'neutral' as const,
      icon: 'lucideCoins',
    })),
    ...h.availability.map((a) => ({
      at: a.changed_at,
      text: `Availability ${a.old_availability ?? '∅'} → ${a.new_availability}`,
      reason: a.reason,
      tone:
        a.new_availability === 'sold'
          ? ('bad' as const)
          : a.new_availability === 'available'
            ? ('good' as const)
            : ('warning' as const),
      icon: 'lucideTag',
    })),
    ...h.audit
      .filter(
        (a) => !['list_price', 'currency', 'availability'].some((k) => a.after && k in a.after),
      )
      .map((a) => ({
        at: a.at,
        text: `${a.action} ${a.entity_type} ${summarise(a.before)} → ${summarise(a.after)}`,
        reason: null,
        tone: 'neutral' as const,
        icon: 'lucidePencil',
      })),
  ];
  return out.sort((x, y) => y.at.localeCompare(x.at));
}

function summarise(v: Record<string, unknown> | null | undefined): string {
  if (!v) return '∅';
  return Object.entries(v)
    .filter(([k]) => !['code', 'import_batch_id', 'reason', 'media_id'].includes(k))
    .map(([k, x]) => `${k}=${typeof x === 'object' ? JSON.stringify(x) : x}`)
    .join(', ');
}

/** Availability colours on the floor plan, the same as the buyer portal's. */
export const AVAILABILITY_FILL: Record<string, { label: string; fill: string; stroke: string }> = {
  available: { label: 'Available', fill: 'rgba(16,185,129,0.28)', stroke: '#047857' },
  reserved: { label: 'Reserved', fill: 'rgba(245,158,11,0.3)', stroke: '#b45309' },
  sold: { label: 'Sold', fill: 'rgba(239,68,68,0.28)', stroke: '#b91c1c' },
  withdrawn: { label: 'Not for sale', fill: 'rgba(148,163,184,0.3)', stroke: '#475569' },
};

/** The sheet that carries the unit's current outline, with every current outline on it. */
export interface UnitPlan {
  sheetId: string;
  src: string;
  width: number;
  height: number;
  focus: Ring;
  polygons: PlanPolygon[];
  /** Other units drawn on the same sheet. */
  others: number;
}

export function ringOf(b: BoundaryOut): Ring {
  return ((b.polygon as { ring?: Ring } | null)?.ring ?? []) as Ring;
}

function isCurrent(b: BoundaryOut): boolean {
  return b.is_current && b.status !== 'superseded' && ringOf(b).length >= 3;
}

export function currentBoundary(boundaries: BoundaryOut[]): BoundaryOut | null {
  return boundaries.find(isCurrent) ?? null;
}

/** Polygons for the plan card: every current outline on the sheet coloured by availability, this unit selected. */
export function planOf(
  unitId: string,
  sheet: SheetOut,
  boundaries: BoundaryOut[],
  rows: InventoryRow[],
): UnitPlan | null {
  const mine = boundaries.find((b) => b.unit_id === unitId && isCurrent(b));
  if (!mine || !sheet.raster_url) return null;
  const byUnit = new Map(rows.map((r) => [r.unit_id, r]));
  const polygons: PlanPolygon[] = boundaries.filter(isCurrent).map((b) => {
    const row = b.unit_id ? byUnit.get(b.unit_id) : undefined;
    const tone = row ? AVAILABILITY_FILL[row.availability] : undefined;
    return {
      id: b.unit_id ?? b.id,
      ring: ringOf(b),
      label: row?.code ?? b.label ?? undefined,
      selected: b.unit_id === unitId,
      fill: tone?.fill,
      stroke: tone?.stroke,
      title: row ? `${row.code} · ${tone?.label ?? row.availability}` : undefined,
      locked: true,
    };
  });
  return {
    sheetId: sheet.id,
    src: sheet.raster_url,
    width: sheet.raster_width ?? 1000,
    height: sheet.raster_height ?? 700,
    focus: ringOf(mine),
    polygons,
    others: polygons.length - 1,
  };
}

/** The price per m² the typed price gives on the unit's pricing area, before saving. */
export function perM2(form: Form, row: InventoryRow): { text: string; verified: boolean } | null {
  const p = parsePriceInput(form.list_price);
  const area = Number(row.price_area_m2);
  if (!p || !area || form.price_on_request) return null;
  const v = Number(p) / area;
  if (!Number.isFinite(v) || v <= 0) return null;
  const amount = formatPrice(v.toFixed(2), form.currency || row.currency) ?? v.toFixed(2);
  return {
    text: `${amount} per m² of ${(row.price_area_type ?? 'the pricing').replace(/_/g, ' ')} area`,
    verified: !!row.price_area_verified,
  };
}
