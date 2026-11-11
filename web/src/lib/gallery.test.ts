import { expect, test } from 'vitest';
import type { AlbumPhoto } from './api';
import { groups, justify } from './gallery';
import { at } from './time';

const ph = (id: number, when?: number, w = 4, h = 3): AlbumPhoto => ({ id, url: '', thumb: '', w, h, blur: '', canDelete: false, by: null, mine: false, ...(when ? { at: when } : {}) });
const NOW = at(2026, 10, 11, 12); // 11 November, noon in Almaty

test('stretches of time, in Almaty days; an album photo sits with its newer neighbour', () => {
  const g = groups([ph(9, at(2026, 10, 11, 0, 5)), ph(8), ph(7, at(2026, 10, 10, 23, 55)), ph(6, at(2026, 10, 7, 9)), ph(5, at(2026, 10, 4, 9)),
    ph(4, at(2026, 9, 30, 9)), ph(3, at(2025, 11, 30, 9))], NOW);
  expect(g.map((x) => x.rows.flatMap((r) => r.tiles.map((c) => c.p.id)))).toEqual([[9, 8], [7], [6], [5], [4], [3]]);
  expect(g.map((x) => x.key.split(':')[0])).toEqual(['today', 'yesterday', 'week', '2026-10', '2026-9', '2025-11']);
  expect(g[5].label).toMatch(/2025$/);
  expect(new Set(g.map((x) => x.key)).size).toBe(g.length);
  // no time anywhere (the albums alone): one set without a header; ones before the first time join it
  expect(groups([ph(2), ph(1)], NOW).map((x) => x.label)).toEqual(['']);
  expect(groups([ph(3), ph(2, NOW), ph(1)], NOW)[0].rows.flatMap((r) => r.tiles).length).toBe(3);
  expect(groups([{ ...ph(-1), pending: true }, ph(1, NOW - 86400)], NOW).map((x) => x.key.split(':')[0])).toEqual(['today', 'yesterday']);
});

test('rows: a lead, three portraits once, pairs, a lone one capped; every photo once, in order', () => {
  const tiles = (ars: number[]) => ars.map((ar, i) => ({ p: ph(i), i, ar }));
  const lens = (ars: number[], lead = false) => justify(tiles(ars), lead).map((r) => r.tiles.length);
  expect(lens([1.3, 0.75, 0.75, 0.75, 0.75, 0.75, 0.75, 1.3, 1.3], true)).toEqual([1, 3, 2, 2, 1]);
  const lead = justify(tiles([0.7, 1.3]), true);
  expect(lead[0]).toMatchObject({ lead: true, tiles: [{ ar: 1.5 }] });
  expect(lead[1].tiles[0].ar).toBeCloseTo(4 / 3); // alone: never taller than 4:3
  expect(justify(tiles([0.7]))[0].tiles[0].ar).toBeCloseTo(4 / 3);
  expect(justify(tiles([2.2]))[0].tiles[0].ar).toBe(2.2);
  expect(justify(tiles([1.5, 1.5, 1.5, 1.5]))).toMatchObject([{ tiles: [{ ar: 1.35 }, { ar: 1.35 }] }, { tiles: [{ ar: 1.35 }, { ar: 1.35 }] }]); // wide ones pair, cut
  expect(lens([1.78, 1.78, 1.3])).toEqual([1, 1, 1]); // a panorama keeps its row
  expect(lens([1.3, 1.3, 1])).toEqual([2, 1]);  // too wide for three
  expect(lens([1, 1, 1])).toEqual([3]);          // the last three together: nobody ends alone
  const all = justify(tiles([1.5, 0.7, 0.7, 2, 2, 0.8, 1]), true).flatMap((r) => r.tiles.map((c) => c.i));
  expect(all).toEqual([0, 1, 2, 3, 4, 5, 6]);
});
