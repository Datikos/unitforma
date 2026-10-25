/** "12-51, 7" → [7, 12, 13, …, 51]; anything else is ignored. At most 2000 pages. */
export function parsePages(text: string | null | undefined): number[] {
  const out = new Set<number>();
  for (const part of (text ?? '').split(/[,;\s]+/)) {
    const m = part.match(/^(\d+)(?:-(\d+))?$/);
    if (!m) continue;
    const a = Number(m[1]);
    const b = m[2] ? Number(m[2]) : a;
    for (let p = Math.min(a, b); p <= Math.max(a, b) && out.size < 2000; p++) if (p > 0) out.add(p);
  }
  return [...out].sort((x, y) => x - y);
}
