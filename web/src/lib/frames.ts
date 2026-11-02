// The frame rate of a run of idle frames, for power saving (state/power.svelte.ts). iOS caps a page at 30 fps in Low
// Power Mode and when the phone is hot, and a cap is steady: nearly every frame takes the same time. A busy moment (a
// sheet opening, a list rendering) makes frames longer and uneven, never shorter.

export type Rate = { fps: number; steady: boolean } | null;

/** The rate of 24 idle frames, or null when none came for 2.5 s (hidden). */
export function measure(): Promise<Rate> {
  return new Promise((done) => {
    const at: number[] = [];
    let over = false;
    const end = (r: Rate) => { if (!over) { over = true; done(r); } };
    setTimeout(() => end(null), 2500);
    const frame = (ts: number) => {
      if (over) return;
      at.push(ts);
      if (at.length > 24) end(rateOf(at.slice(1).map((x, i) => x - at[i])));
      else requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  });
}

/** The median rate of the gaps between frames (ms), and whether 70% of them sit within a fifth of the median; null
 *  for fewer than 8. */
export function rateOf(gaps: number[]): Rate {
  if (gaps.length < 8) return null;
  const d = [...gaps].sort((a, b) => a - b), mid = d[d.length >> 1];
  return { fps: 1000 / mid, steady: d.filter((g) => Math.abs(g - mid) < mid * 0.2).length >= d.length * 0.7 };
}

/** Capped (true: about 30 fps), free (false: 60 or more), or can't tell (null). Free needs only the median over 50 fps:
 *  half the frames that fast mean no cap, however uneven the rest (a busy moment; 120 Hz, which jitters more; Safari
 *  draws pages at 60 even on 120 Hz iPhones unless a flag is off). Capped needs steady frames under 40 fps too. */
export function capped(r: Rate): boolean | null {
  return !r ? null : r.fps > 50 ? false : r.fps < 40 && r.steady ? true : null;
}
