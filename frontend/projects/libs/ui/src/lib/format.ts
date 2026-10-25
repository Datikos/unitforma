/** Formatting shared by both apps: dates as "2026-10-25 14:03" and relative "2 h ago". */
export function whenShort(iso: string | null | undefined): string {
  if (!iso) return '—';
  return iso.slice(0, 16).replace('T', ' ');
}

export function dayOf(iso: string | null | undefined): string {
  return iso ? iso.slice(0, 10) : '—';
}

export function ago(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return '';
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return '';
  const s = Math.max(0, Math.round((now.getTime() - t) / 1000));
  if (s < 60) return 'just now';
  const m = Math.round(s / 60);
  if (m < 60) return `${m} min ago`;
  const h = Math.round(m / 60);
  if (h < 48) return `${h} h ago`;
  const d = Math.round(h / 24);
  if (d < 60) return `${d} d ago`;
  return dayOf(iso);
}

/** "1 234.5" style thousands with a thin space; `null` stays empty. */
export function num(v: string | number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || v === '') return '';
  return Number(v).toLocaleString('en-US', { maximumFractionDigits: digits }).replace(/,/g, ' ');
}

export function kb(bytes: number | null | undefined): string {
  if (!bytes) return '';
  return bytes < 1024 * 1024
    ? `${Math.round(bytes / 1024)} kB`
    : `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
