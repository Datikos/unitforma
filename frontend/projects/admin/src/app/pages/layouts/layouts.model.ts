import { LayoutOut, LayoutUnitOut } from 'api-client';

/** Pure model of the Layouts page (ADR-0022): form shape, validation and summaries. */
export interface LayoutForm {
  code: string;
  name: string;
}

export function blankLayoutForm(): LayoutForm {
  return { code: '', name: '' };
}

export function formOf(l: LayoutOut): LayoutForm {
  return { code: l.code, name: l.name ?? '' };
}

/** The backend refuses these too; the message appears before the request is sent. */
export function validateCode(
  code: string,
  existing: LayoutOut[],
  selfId: string | null = null,
): string | null {
  const c = code.trim();
  if (!c) return 'Code is required';
  if (c.length > 40) return 'Code is limited to 40 characters';
  const taken = existing.find((l) => l.id !== selfId && l.code.toLowerCase() === c.toLowerCase());
  return taken ? `Code ${taken.code} already exists in this project` : null;
}

export function availabilityCounts(units: LayoutUnitOut[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const u of units) out[u.availability] = (out[u.availability] ?? 0) + 1;
  return out;
}

/** One line under a layout card: "3 units · 2 available · 1 sold · 2 public media". */
export function layoutSummary(l: LayoutOut): string {
  const n = l.units.length;
  const counts = availabilityCounts(l.units);
  const parts = [`${n} ${n === 1 ? 'unit' : 'units'}`];
  if (l.status === 'proposed') {
    const iou = l.match?.['iou_min'];
    parts.push(
      `proposed by the solver${typeof iou === 'number' ? ` (outlines match ${iou.toFixed(2)})` : ''}`,
    );
  }
  for (const k of ['available', 'reserved', 'sold', 'withdrawn']) {
    if (counts[k]) parts.push(`${counts[k]} ${k}`);
  }
  parts.push(
    l.media_count ? `${l.public_media_count} public of ${l.media_count} media` : 'no media yet',
  );
  return parts.join(' · ');
}

/** Header facts of the page: layouts, linked units, layouts without any public media, proposed. */
export function registryFacts(list: LayoutOut[]): {
  layouts: number;
  linked: number;
  withoutMedia: number;
  proposed: number;
} {
  return {
    layouts: list.length,
    linked: list.reduce((a, l) => a + l.units.length, 0),
    withoutMedia: list.filter((l) => l.public_media_count === 0).length,
    proposed: list.filter((l) => l.status === 'proposed').length,
  };
}

/** Proposed layouts first (they wait for a decision), then by code. */
export function orderLayouts(list: LayoutOut[]): LayoutOut[] {
  return [...list].sort((a, b) => {
    if (a.status !== b.status) return a.status === 'proposed' ? -1 : 1;
    return a.code.localeCompare(b.code, undefined, { numeric: true });
  });
}
