import { describe, expect, it } from 'vitest';
import { attach, openAt, routes, type Graph } from './route';

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
});
