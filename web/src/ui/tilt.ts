// The tilt math of the glass light (glass.ts), apart so it can be tested without a page.
const clamp = (v: number) => Math.max(-1, Math.min(1, v));

/** "Up" in the phone's frame (x right, y to its top, z out of the screen) from beta/gamma (W3C, radians) */
export const upOf = (b: number, g: number) => [-Math.cos(b) * Math.sin(g), Math.sin(b), Math.cos(b) * Math.cos(g)];

/** The turn from neutral `n` to `u` as the light's tilt (-1..1), on the screen's axes (`angle`: screen.orientation).
 *  Neutral × up is the turn's axis (its length the sine of the angle): a roll round the screen's normal, which is
 *  all that lying on one's side or landscape adds, reads as nothing. 2.2: the old beta/gamma scale, the same feel */
export function tiltFrom(n: number[], u: number[], angle: number): [number, number] {
  const ax = n[1] * u[2] - n[2] * u[1], ay = n[2] * u[0] - n[0] * u[2];
  const a = (angle * Math.PI) / 180, c = Math.cos(a), s = Math.sin(a);
  return [clamp(-(ay * c - ax * s) * 2.2), clamp(-(ax * c + ay * s) * 2.2)];
}

/** One step of a damped spring pulling `p` toward `to` (the award medal's pendulum, coin3d.ts), tuned per 60 Hz frame
 *  and scaled by `k`, the frames' worth of time that passed: per frame alone, a 120 Hz screen swung it twice as fast and
 *  a dropped frame slowed it. k = 1 is the original step exactly. */
export function springStep(p: { x: number; v: number }, to: number, k: number): void {
  p.v = (p.v + (to - p.x) * 0.045 * k) * 0.92 ** k;
  p.x += p.v * k;
}
