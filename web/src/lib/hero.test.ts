import { describe, expect, it } from 'vitest';
import { fresh, rank, score, shown, stale, tapped, type Pick } from './hero';

const D = 20000;
const keys = (xs: Pick[]) => xs.map((x) => x.key);
const items: Pick[] = [
  { key: 'c1', kind: 'class' },
  { key: 'e1', kind: 'friends' }, { key: 'e2', kind: 'friends' },
  { key: 'e1', kind: 'club' }, { key: 'e3', kind: 'club' },
  { key: 'p1', kind: 'news' },
];

describe('hero rank', () => {
  it('a new person: the base order, one card per kind, an item once', () => {
    expect(keys(rank(items, fresh(), D))).toEqual(['e1', 'e3', 'p1']);
    expect(keys(rank(items, fresh(), D, 9))).toEqual(['e1', 'e3', 'p1', 'c1']);
  });
  it('my ticket for today leads whatever the taps say', () => {
    const m = fresh();
    m.t.class = 50;
    const r = rank([...items, { key: 'e9', kind: 'ticket', today: true }], m, D);
    expect(keys(r)).toEqual(['e9', 'c1', 'e1']);
  });
  it('taps lift a kind, shows without taps sink it: (taps+1)/(shows+3) x base', () => {
    const m = fresh();
    m.s.friends = 30; m.s.club = 30; m.t.news = 4; m.s.news = 5;
    expect(score('news', m)).toBeCloseTo((5 / 8) * 4);
    expect(keys(rank(items, m, D))).toEqual(['p1', 'c1', 'e1']);
  });
  it("yesterday's untapped hero is skipped today; its kind gives its next item", () => {
    const m = fresh();
    shown(m, { key: 'e1', kind: 'friends' }, D - 1, true);
    expect(stale(m, D)).toBe('e1');
    expect(keys(rank(items, m, D))).toEqual(['e3', 'e2', 'p1']); // yesterday's show counts too: friends 1/4 x 6 < club 1/3 x 5
    shown(m, { key: 'e2', kind: 'friends' }, D, true); // today rolled: yesterday's still counts
    expect(stale(m, D)).toBe('e1');
    expect(stale(m, D + 1)).toBe('e2');
  });
  it('tapped, it may come back; an older day does not count', () => {
    const m = fresh();
    shown(m, { key: 'e1', kind: 'friends' }, D - 1, true);
    tapped(m, { key: 'e1', kind: 'friends' }, D - 1);
    expect(stale(m, D)).toBe('');
    const old = fresh();
    shown(old, { key: 'e1', kind: 'friends' }, D - 2, true);
    expect(stale(old, D)).toBe('');
  });
  it('a show and a tap count once a day per item; a swiped-to card is not the hero', () => {
    const m = fresh(), x: Pick = { key: 'p1', kind: 'news' };
    expect(shown(m, x, D, false)).toBe(true);
    expect(shown(m, x, D, false)).toBe(false);
    expect(m.k).toBe('');
    expect(tapped(m, x, D)).toBe(true);
    expect(tapped(m, x, D)).toBe(false);
    expect([m.s.news, m.t.news]).toEqual([1, 1]);
    expect(shown(m, x, D + 1, true)).toBe(true);
    expect([m.s.news, m.k, m.pd]).toEqual([2, 'p1', D]);
  });
});
