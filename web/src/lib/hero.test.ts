import { describe, expect, it } from 'vitest';
import { fresh, lead, rank, score, shown, stale, tapped, SOON, type Pick } from './hero';
import { OFFSET } from './time';

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

describe('hero lead', () => {
  const H = 3600, noon = D * 86400 - OFFSET + 12 * H; // local noon of day D
  type E = Parameters<typeof lead>[0][number];
  const ev = (id: number, at: number, taken: number, x: Partial<E> = {}): E =>
    ({ id, startsAt: at, endsAt: null, taken, friends: [], cover: null, status: 'published', my: null, ...x });
  const ids = (xs: E[], now: number, no = '') => { const r = lead(xs, now, no); return r && [r.kind, r.e.id]; };
  const week = ev(1, noon + 3 * 86400, 90), tonight = ev(2, noon + 7 * H, 20), small = ev(3, noon + 2 * H, 5);
  const mine = ev(4, noon + 5 * H, 1, { my: { status: 'going' } });

  it("my ticket within SOON leads, then today's biggest, then the week's most popular", () => {
    const all = [week, tonight, small, mine];
    expect(ids(all, noon)).toEqual(['today', 2]); // my ticket is 5 h away: not yet
    expect(ids(all, mine.startsAt - SOON)).toEqual(['ticket', 4]); // the clock moves it in
    expect(ids(all, mine.startsAt + H)).toEqual(['ticket', 4]); // on now
    expect(ids([week, small], small.startsAt + 3 * H + 1)).toEqual(['week', 1]); // today's are over
    expect(ids([], noon)).toBeNull();
  });
  it("a festival of days I'm in isn't 'soon' all week; a meeting or a team's event is no one's biggest", () => {
    const fest = ev(5, noon - 2 * 86400, 1, { endsAt: noon + 86400, my: { status: 'going' } });
    expect(ids([fest, tonight], noon)).toEqual(['today', 2]);
    expect(ids([ev(6, noon + H, 500, { meeting: true }), ev(7, noon + H, 400, { visibility: 'members' }), small], noon)).toEqual(['today', 3]);
  });
  it("ties: friends, a cover, the sooner; yesterday's untapped hero steps aside, never my ticket", () => {
    expect(ids([ev(8, noon + 4 * H, 5), ev(9, noon + 5 * H, 5, { friends: [1] })], noon)).toEqual(['today', 9]);
    expect(ids([ev(8, noon + 4 * H, 5), ev(9, noon + 5 * H, 5, { cover: {} })], noon)).toEqual(['today', 9]);
    expect(ids([ev(8, noon + 4 * H, 5), ev(9, noon + 5 * H, 5)], noon)).toEqual(['today', 8]);
    expect(ids([week, ev(10, noon + 86400, 3)], noon, 'e1')).toEqual(['week', 10]);
    expect(ids([mine], mine.startsAt - H, 'e4')).toEqual(['ticket', 4]);
  });
  it('cancelled and drafts never lead', () => {
    expect(ids([ev(11, noon + H, 99, { status: 'cancelled' }), ev(12, noon + H, 99, { status: 'draft' })], noon)).toBeNull();
  });
});
