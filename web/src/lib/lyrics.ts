// Line-synced words, as in Apple Music. A line is lit from its start until the next one starts; when a pause follows it
// (the next start more than GAP away) only for its own length: the end marked by hand, or else the typical spacing
// between lines. The rest of the pause, and the intro, show as dots before the next line, filling as it goes.

/** s: two starts further apart than this have a pause between them */
export const GAP = 6;

/** the typical spacing between consecutive lines (s): a line's own length when a pause follows it */
export function lineLen(starts: number[]): number {
  const d = starts.slice(1).map((s, i) => s - starts[i]).filter((x) => x > 0).sort((a, b) => a - b);
  return Math.min(GAP, d[d.length >> 1] ?? 4);
}

/** where the song is at `now`: the line lit (-1: none), or the pause before line `next` and how far into it (p, 0..1) */
export function lyricAt(starts: number[], ends: (number | null)[], now: number, songEnd: number, len = lineLen(starts)) {
  let i = -1;
  for (let k = 0; k < starts.length; k++) if (starts[k] <= now) i = k;
  const endOf = (k: number) => {
    const next = starts[k + 1] ?? songEnd;
    return Math.min(ends[k] ?? (next - starts[k] > GAP ? starts[k] + len : next), next);
  };
  if (i >= 0 && now < endOf(i)) return { line: i, next: -1, p: 0 };
  const n = i + 1, from = i >= 0 ? endOf(i) : 0, span = (starts[n] ?? 0) - from;
  // after the last line nothing; a dark moment too short for the dots stays plain
  return n < starts.length && span >= 2 ? { line: -1, next: n, p: Math.min(1, (now - from) / span) } : { line: -1, next: -1, p: 0 };
}

/** within a lit line, `x` s after its start: the word being sung (its starts after the line's in `o`) and how far into
 *  it (f, 0..1); the last word fills until `span` (the line's lit length), at most HOLD */
export const HOLD = 1.2;
export function wordAt(o: number[], x: number, span: number) {
  let w = 0;
  while (w + 1 < o.length && o[w + 1] <= x) w++;
  const to = w + 1 < o.length ? o[w + 1] : Math.min(span, o[w] + HOLD);
  return { w, f: Math.min(1, Math.max(0, (x - o[w]) / Math.max(0.05, to - o[w]))) };
}
