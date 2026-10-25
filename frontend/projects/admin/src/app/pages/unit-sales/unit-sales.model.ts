import { InventoryRow, MediaCreate, SalesChanges, SalesHistoryOut } from 'api-client';
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
  for (const k of ['orientation', 'entrance', 'public_description', 'internal_notes'])
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
