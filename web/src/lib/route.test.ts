import { describe, expect, it } from 'vitest';
import { attach, liftRush, openAt, routes, type Graph } from './route';
import plan from '../../../server/kbtu/map_graph.json';

// two floors: a corridor on each, the main stairs (g 1) at the left end, a backup-free side stairs (g 2) at the right, a lift (g 3)
const g: Graph = { ver: 0, e: [[1, 2], [2, 3], [11, 12], [12, 13], [3, 4], [13, 14], [2, 5], [12, 15]], n: [
  { id: 1, f: 1, u: 0.1, v: 0.5, k: 's', g: 1 }, { id: 2, f: 1, u: 0.5, v: 0.5 }, { id: 3, f: 1, u: 0.9, v: 0.5 }, { id: 4, f: 1, u: 0.95, v: 0.5, k: 's', g: 2 },
  { id: 5, f: 1, u: 0.5, v: 0.6, k: 'l', g: 3 },
  { id: 11, f: 2, u: 0.1, v: 0.5, k: 's', g: 1 }, { id: 12, f: 2, u: 0.5, v: 0.5 }, { id: 13, f: 2, u: 0.9, v: 0.5 }, { id: 14, f: 2, u: 0.95, v: 0.5, k: 's', g: 2 },
  { id: 15, f: 2, u: 0.5, v: 0.6, k: 'l', g: 3 },
] };

describe('routes', () => {
  it('stairs, lift and another staircase', () => {
    const a = { f: 1, u: 0.2, v: 0.52 }, b = { f: 2, u: 0.25, v: 0.52 };
    const r = routes(g, 1, { at: attach(g, a, 1), pt: a }, { at: attach(g, b, 1), pt: b });
    expect(r.map((x) => x.mode)).toEqual(['fast', 'lift']); // the right stairs are far more than 30% longer
    expect(r[0].via).toEqual([1, 1]);
    expect(r[0].legs.map((l) => [l.f, l.to])).toEqual([[1, 2], [2, undefined]]);
    const c = { f: 1, u: 0.5, v: 0.52 }, d = { f: 2, u: 0.5, v: 0.52 }; // halfway: both stairs are as near
    expect(routes(g, 1, { at: attach(g, c, 1), pt: c }, { at: attach(g, d, 1), pt: d }).map((x) => x.mode)).toEqual(['fast', 'lift', 'alt']);
  });
  it('same floor: one way', () => {
    const a = { f: 1, u: 0.2, v: 0.5 }, b = { f: 1, u: 0.8, v: 0.5 };
    expect(routes(g, 1, { at: attach(g, a, 1), pt: a }, { at: attach(g, b, 1), pt: b }).length).toBe(1);
  });
  it('hours', () => {
    const n = { id: 1, f: 1, u: 0, v: 0, h: ['07:00-18:00', '07:00-10:00', ''] }, night = { ...n, h: ['22:00-07:00', '22:00-07:00', '22:00-07:00'] };
    expect(openAt(n, new Date(2026, 9, 15, 17, 59))).toBe(true); // a Thursday
    expect(openAt(n, new Date(2026, 9, 15, 18, 0))).toBe(false);
    expect(openAt(n, new Date(2026, 9, 17, 11, 0))).toBe(false); // Saturday
    expect(openAt(n, new Date(2026, 9, 18, 12, 0))).toBe(false); // Sunday
    expect(openAt(night, new Date(2026, 9, 15, 23, 30))).toBe(true);
    expect(openAt(night, new Date(2026, 9, 16, 6, 0))).toBe(true);
  });
  it('the nearest exit from 424 is down the central stairs and across the yard (owner, Oct 17)', () => {
    const real = plan as unknown as Graph, ar = 2965 / 3307, p = { f: 4, u: 0.503, v: 0.4385 };
    const a = { at: attach(real, p, ar, '424'), pt: p };
    const exits = real.n.filter((x) => x.k === 'x' && !x.b).map((x) => ({ x, r: routes(real, ar, a, { at: [[x.id, 0]] })[0] }));
    const best = exits.sort((p, q) => p.r.secs - q.r.secs)[0];
    expect(best.x.id).toBe(414); // Kazybek bi, not Panfilov's by the east stairs
    expect(best.r.via[0]).toBe(8);
  });
  it('the lift way rides the lift at hand and takes the stairs by it, no walk to the far wing (owner, Oct 24)', () => {
    const real = plan as unknown as Graph, ar = 2965 / 3307, p = { f: 3, u: 0.4983, v: 0.8634 }, canteen = { f: 0, u: 0.552, v: 0.602 };
    const lift = routes(real, ar, { at: attach(real, p, ar, '351'), pt: p }, { at: attach(real, canteen, ar), pt: canteen }).find((r) => r.mode === 'lift')!;
    const ride = lift.legs.find((l) => l.up?.k === 'l')!;
    expect(ride.f).toBe(3);
    expect(ride.up!.u).toBeGreaterThan(0.5); // the central lift by 348, not a wing's
    expect(ride.up!.u).toBeLessThan(0.6);
  });
  it('a lift way to the basement corner no lift reaches: a lift, then the flight (review, Oct 24)', () => {
    const real = plan as unknown as Graph, ar = 2965 / 3307, d = real.n.find((n) => n.r?.includes('384'))!, n23 = real.n.find((n) => n.id === 23)!;
    const p = { f: d.f, u: d.u, v: d.v }, q = { f: n23.f, u: n23.u, v: n23.v };
    const lift = routes(real, ar, { at: attach(real, p, ar, '384'), pt: p }, { at: [[23, 0]], pt: q }).find((r) => r.mode === 'lift');
    expect(lift?.legs.some((l) => l.up?.k === 'l')).toBe(true);
  });
  it('lift rush only in weekday breaks between classes (owner, Oct 24)', () => {
    expect(liftRush(new Date(2026, 9, 21, 10, 50))).toBe(true); // Wednesday
    expect(liftRush(new Date(2026, 9, 21, 11, 2))).toBe(true);
    expect(liftRush(new Date(2026, 9, 21, 11, 20))).toBe(false);
    expect(liftRush(new Date(2026, 9, 21, 22, 50))).toBe(false); // night
    expect(liftRush(new Date(2026, 9, 24, 18, 50))).toBe(false); // Saturday evening (his screenshot)
    expect(liftRush(new Date(2026, 9, 25, 10, 50))).toBe(false); // Sunday
  });
});
