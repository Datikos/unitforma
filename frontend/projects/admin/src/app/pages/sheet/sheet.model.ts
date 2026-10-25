import { SuggestionOut, UnitOut } from 'api-client';
import { Point, Ring } from 'plan-viewer';

export type UnitType = 'apartment' | 'commercial' | 'parking' | 'storage';
export const UNIT_TYPES: { value: UnitType; label: string }[] = [
  { value: 'apartment', label: 'Apartment' },
  { value: 'commercial', label: 'Commercial' },
  { value: 'parking', label: 'Parking' },
  { value: 'storage', label: 'Storage' },
];

export interface FloorOption {
  id: string;
  label: string;
}

/** Typed, labelled outlines the engine is sure of: drawing zones and whole loops (≥ 85 %). */
export function confident(c: SuggestionOut): boolean {
  return !!c.label && !!c.unit_type && c.confidence >= 0.85;
}

export function centroidOf(ring: Ring): Point {
  const n = ring.length || 1;
  return [ring.reduce((a, p) => a + p[0], 0) / n, ring.reduce((a, p) => a + p[1], 0) / n];
}

/** Ray-casting point-in-polygon on normalised coordinates. */
export function inside(pt: Point, ring: Ring): boolean {
  let hit = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > pt[1] !== yj > pt[1] && pt[0] < ((xj - xi) * (pt[1] - yi)) / (yj - yi) + xi)
      hit = !hit;
  }
  return hit;
}

export function methodLabel(m: string | undefined): string {
  return m === 'fill'
    ? 'drawing zone'
    : m === 'grown'
      ? 'rooms merged to printed area'
      : 'closed loop';
}

interface Hints {
  levels?: string[];
  level_markers?: { text: string }[];
  scales?: number[];
  apartment_labels?: string[];
  unit_labels?: Record<string, string[]>;
  duplicate_of?: number;
}

/** What the worker read on the sheet, as one line. */
export function hintsText(hints: unknown): string {
  const h = (hints ?? {}) as Hints;
  const parts: string[] = [];
  if (h.level_markers?.length)
    parts.push(`level markers ${h.level_markers.map((m) => m.text).join(', ')}`);
  else if (h.levels?.length) parts.push(`levels ${h.levels.join(', ')}`);
  if (h.scales?.length) parts.push(`scale 1:${h.scales.join('/')}`);
  const kinds: Record<string, string> = {
    apartment: 'apartment',
    parking: 'parking',
    storage: 'storage',
    commercial: 'commercial',
    numbered: 'numbered room',
  };
  const labels = Object.entries(
    h.unit_labels ?? (h.apartment_labels?.length ? { apartment: h.apartment_labels } : {}),
  );
  for (const [k, v] of labels)
    if (v.length) parts.push(`${v.length} ${kinds[k] ?? k} label${v.length === 1 ? '' : 's'}`);
  return parts.join(' · ') || 'no hints';
}

export function duplicateOf(hints: unknown): number | null {
  return ((hints ?? {}) as Hints).duplicate_of ?? null;
}

/** The architect's printed area (documented, source drawing_schedule). */
export function printedArea(u: UnitOut) {
  return (u.areas ?? []).find((a) => a.source === 'drawing_schedule' && a.is_current);
}

export function measuredArea(u: UnitOut) {
  return (u.areas ?? []).find((a) => a.source === 'drawing_measured');
}
