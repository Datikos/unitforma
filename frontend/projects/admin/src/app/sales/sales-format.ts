/** Formatting and parsing helpers shared by the sales pages (plan §6.2). */

export const AVAILABILITY = ['available', 'reserved', 'sold', 'withdrawn'] as const;

export const PUBLIC_FIELDS: { key: string; label: string }[] = [
  { key: 'list_price', label: 'Price' },
  { key: 'payment_plan', label: 'Payment plan' },
  { key: 'promotions', label: 'Promotions' },
  { key: 'description', label: 'Description' },
  { key: 'areas', label: 'Areas' },
  { key: 'rooms', label: 'Room counts' },
  { key: 'media', label: 'Media' },
];

/** "USD 245 000.00": currency always explicit, never a bare symbol. Empty price → null. */
export function formatPrice(amount: string | number | null | undefined, currency: string | null | undefined): string | null {
  if (amount === null || amount === undefined || amount === '') return null;
  const n = Number(amount);
  const s = n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }).replace(/,/g, ' ');
  return `${currency ?? ''} ${s}`.trim();
}

/** User input → decimal string with at most two decimals; '' → null; invalid → undefined. */
export function parsePriceInput(v: unknown): string | null | undefined {
  if (v === null || v === undefined) return null;
  let s = String(v).trim().replace(/[\s  ]/g, '');
  if (s === '') return null;
  if (!s.includes('.') && /,\d{1,2}$/.test(s)) s = s.replace(',', '.');
  s = s.replace(/,/g, '');
  return /^\d+(\.\d{1,2})?$/.test(s) ? s : undefined;
}

export function problemBody(e: unknown): Record<string, unknown> | null {
  const err = (e as { error?: unknown })?.error;
  return err && typeof err === 'object' ? (err as Record<string, unknown>) : null;
}

export function httpStatus(e: unknown): number | undefined {
  return (e as { status?: number })?.status;
}
