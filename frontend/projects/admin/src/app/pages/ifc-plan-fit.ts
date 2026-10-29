/** One level's entry in `stats.plan_fit.per_level` (ADR-0030 Decision 4 and #D1). */
interface LevelFit {
  shift_m?: number[];
  coverage_shifted?: number;
  shift_refused?: boolean;
}

/**
 * The fit line's sentence on the levels moved onto their own slab (each floor plan sheet has its
 * own origin) and on those left as fitted because they lie more than 5 m off; '' when none.
 */
export function levelShiftLine(pf: Record<string, unknown>): string {
  const per = (pf['per_level'] ?? {}) as Record<string, LevelFit>;
  const levels = Object.keys(per).sort((a, b) => Number(a) - Number(b));
  const moved = levels
    .filter((l) => per[l].shift_m)
    .map((l) => {
      const [dx, dy] = per[l].shift_m!;
      const inside = Math.round((per[l].coverage_shifted ?? 0) * 100);
      return `level ${l} by ${Math.hypot(dx, dy).toFixed(1)} m (${inside} % inside)`;
    });
  const far = levels.filter((l) => per[l].shift_refused).map((l) => `level ${l}`);
  const parts: string[] = [];
  if (moved.length)
    parts.push(`Drawn on another sheet origin, so moved onto their own slab: ${moved.join(', ')}.`);
  if (far.length)
    parts.push(
      `More than 5 m off their slab and left as fitted: ${far.join(', ')}; check them in the model.`,
    );
  return parts.join(' ');
}

/**
 * The note when floors were aligned on the grid axes after this conversion placed its plan
 * spaces (ADR-0030 #D3): those spaces sit where the old alignment put them until a re-run;
 * '' when none.
 */
export function realignedLine(levels: readonly number[]): string {
  if (!levels.length) return '';
  const names = [...levels].sort((a, b) => a - b).map(String);
  const list =
    names.length === 1 ? names[0] : `${names.slice(0, -1).join(', ')} and ${names.at(-1)}`;
  const which = names.length === 1 ? `Level ${list} was` : `Levels ${list} were`;
  return (
    `${which} aligned on the drawing's grid axes after this conversion, so the plan spaces ` +
    `there still sit where the old alignment put them. Re-run the conversion to place them on ` +
    `the aligned floors; confirmed spaces that move go back to suggested.`
  );
}
