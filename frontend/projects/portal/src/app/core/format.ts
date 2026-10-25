import { Availability, ConstructionStatus, Money } from './portal-api';

/** Currency is always explicit ("EUR 180 000"), never derived from the locale (plan §11.4). */
export function money(m: Money | null | undefined, digits = 0): string | null {
  if (!m || m.amount === null || m.amount === undefined) return null;
  const n = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
    .format(Number(m.amount))
    .replace(/,/g, ' ');
  return `${m.currency} ${n}`;
}

export function area(v: string | number | null | undefined): string | null {
  if (v === null || v === undefined || v === '') return null;
  return `${Number(v).toLocaleString('en-US', { maximumFractionDigits: 1 })} m²`;
}

export function areaRange(
  min: string | null | undefined,
  max: string | null | undefined,
): string | null {
  if (!min) return null;
  return !max || Number(min) === Number(max) ? area(min) : `${area(min)} – ${area(max)}`;
}

/** Availability colours are always paired with a text label (WCAG, plan §7.5). */
export const AVAILABILITY: Record<
  Availability,
  { label: string; fill: string; stroke: string; solid: string }
> = {
  available: {
    label: 'Available',
    fill: 'rgba(16,185,129,0.28)',
    stroke: '#047857',
    solid: '#34d399',
  },
  reserved: {
    label: 'Reserved',
    fill: 'rgba(245,158,11,0.30)',
    stroke: '#b45309',
    solid: '#fbbf24',
  },
  sold: { label: 'Sold', fill: 'rgba(239,68,68,0.25)', stroke: '#b91c1c', solid: '#f87171' },
  withdrawn: {
    label: 'Not for sale',
    fill: 'rgba(107,114,128,0.25)',
    stroke: '#4b5563',
    solid: '#9ca3af',
  },
};

export const UNIT_TYPES: Record<string, string> = {
  apartment: 'Apartment',
  commercial: 'Commercial',
  parking: 'Parking',
  storage: 'Storage',
};

export function typeLabel(t: string): string {
  return UNIT_TYPES[t] ?? t;
}

/** Site-plan colours per construction status (ADR-0014 Decision 3); the tones of `libs/ui`. */
export const CONSTRUCTION: Record<
  ConstructionStatus,
  { label: string; fill: string; stroke: string }
> = {
  planned: {
    label: 'Planned',
    fill: 'color-mix(in srgb, var(--uf-tone-neutral-fg) 30%, transparent)',
    stroke: 'var(--uf-tone-neutral-fg)',
  },
  under_construction: {
    label: 'Under construction',
    fill: 'color-mix(in srgb, var(--uf-tone-warning-fg) 35%, transparent)',
    stroke: 'var(--uf-tone-warning-fg)',
  },
  completed: {
    label: 'Completed',
    fill: 'color-mix(in srgb, var(--uf-tone-good-fg) 35%, transparent)',
    stroke: 'var(--uf-tone-good-fg)',
  },
};
