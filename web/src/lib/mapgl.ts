// The campus map's frame for MapLibre (a ready, fast library moves the map, not our own pan and zoom).
// No geography: every map is a square sheet, one web-mercator tile at zoom Z0 right and down of the world's middle,
// 8192 px at its finest level, cut in tiles (tools/map/tiles.mjs) under public/map/<cut>/. A plan is the sheet's top
// left part: `fx` of its width, `ar` its height to its width; a point of it is (u, v), fractions of its own width and
// height, as everywhere else in the map (rooms, routes, flaws). Nothing here needs MapLibre: the tests run it.
import labels from '../assets/map/labels.json';
import uniq from '../assets/map/uniq-tiles.json';
import uniqRooms from '../assets/map/uniq-rooms.json';
import boxes from '../assets/map/boxes.json';
import { SPOTS, normRoom } from './map';

export const Z0 = 6, LEVELS = 4, SHEET = 8192;
export type Ver = 'main' | 'kbtu' | 'old';
export type Frame = { fx: number; ar: number };
export const FRAMES: Record<Ver, Frame> = { main: { fx: uniq.w / SHEET, ar: uniq.h / uniq.w }, kbtu: { fx: 1, ar: 1 }, old: { fx: 1, ar: 1 } };
/** the floors each map has: Uni-Q's the basement too */
export const HAS: Record<Ver, number[]> = { main: [0, 1, 2, 3, 4, 5], kbtu: [1, 2, 3, 4, 5], old: [1, 2, 3, 4, 5] };

const K = 2 ** -Z0;
/** a plan's point as MapLibre's [lng, lat] */
export function lngLat(f: Frame, u: number, v: number): [number, number] {
  const x = 0.5 + u * f.fx * K, y = 0.5 + v * f.ar * f.fx * K;
  return [(x - 0.5) * 360, (360 / Math.PI) * Math.atan(Math.exp((0.5 - y) * 2 * Math.PI)) - 90];
}
/** and back: [u, v] */
export function uvOf(f: Frame, lng: number, lat: number): [number, number] {
  const x = lng / 360 + 0.5, y = 0.5 - Math.log(Math.tan(Math.PI / 4 + (lat * Math.PI) / 360)) / (2 * Math.PI);
  return [(x - 0.5) / (f.fx * K), (y - 0.5) / (f.ar * f.fx * K)];
}
/** the zoom at which the plan is `px` CSS pixels wide, and the width at a zoom (MapLibre's world is 512 px at zoom 0) */
export const zoomFor = (f: Frame, px: number): number => Z0 + Math.log2(px / (512 * f.fx));
export const widthAt = (f: Frame, zoom: number): number => 512 * f.fx * 2 ** (zoom - Z0);

/** the tiles: public/map, next to index.html; a cut's folder (dark: our map is drawn twice) */
export const MAPS = `${import.meta.env.BASE_URL}map/`;
export const cutOf = (ver: Ver, dark: boolean): string => (ver === 'main' ? 'u2' : ver === 'old' ? 'o2' : dark ? 'k2d' : 'k2');
export const tilesOf = (ver: Ver, dark: boolean, floor: number): string => `${MAPS}${cutOf(ver, dark)}/f${floor}/{z}/{x}_{y}.webp`;
/** a floor's whole sheet in one small picture (its coarsest tile): what shows the moment the map opens */
export const overview = (ver: Ver, dark: boolean, floor: number): string =>
  tilesOf(ver, dark, floor).replace('{z}', String(Z0)).replace('{x}_{y}', `${2 ** (Z0 - 1)}_${2 ** (Z0 - 1)}`);
/** the 2023 plan as it was given, a picture a floor (to compare the redraw with) */
export const scan = (floor: number): string => `${MAPS}p1/f${floor}.webp`;
/** where each floor's picture lies in the redraw's frame, [left, top, right, bottom] as fractions of it: the redraw put
 *  all floors into one frame, the given pictures each have their own (fitted by the red walls' extent in both) */
export const SCAN_AT: Record<number, number[]> = {
  1: [-0.009, -0.0009, 1.0107, 1.0181], 2: [0, 0, 1, 1], 3: [0.0282, 0.0255, 0.9583, 0.9559], 4: [0.0022, -0.0012, 0.9986, 0.9954], 5: [-0.0031, -0.0045, 1.0023, 1.001],
};
/** a tile's side on screen: 512 px tiles shown small enough for the screen's density (a level may stretch 1.4 times,
 *  as the map before MapLibre let it) */
export const tileSize = (dpr: number): number => Math.round((512 * 1.4) / Math.min(3, Math.max(1, dpr)));

// ---- the words ----
type Row = [number, number, string, string, number, number, number, number, string, string, string, string, number, number];
const DRAWN = labels as unknown as Record<'old' | 'kbtu', Record<string, Row[]>>;
const ROOMS = uniqRooms as unknown as Record<string, number[][]>[];
const isRoom = (r: Row) => /^r\d/.test(r[3]) || /^\d{2,3}[a-z\u0430-\u0433]?$/i.test(r[2]); // a letter after the number, Latin or Cyrillic (as escapes)
const roomName = (r: Row) => normRoom(r[3] ? r[3].slice(1) : r[2]);
/** how big a room is drawn on our map (its number is fitted to its box): the bigger win a place among the labels */
const BIG: Record<string, number> = {};
for (const rows of Object.values(DRAWN.kbtu)) for (const r of rows) if (isRoom(r)) BIG[roomName(r)] = r[4];
const HALL = new Set(SPOTS.filter((s) => s.room).map((s) => s.room!));
const rankOf = (room: string) => (HALL.has(room) ? 0 : 20 - (BIG[room] ?? 9));

/** where a room's number stands on a floor of a map: [[u, v]] (none: the plan doesn't number it) */
export function roomAt(ver: Ver, floor: number, room: string): number[][] {
  if (ver === 'main') return ROOMS[floor]?.[room] ?? [];
  return (DRAWN[ver][floor] ?? []).filter((r) => isRoom(r) && roomName(r) === room).map((r) => [r[0], r[1]]);
}

export type Label = { u: number; v: number; t: string; s: number; turn: number; left: boolean; tier: number; color: string; halo: string; space: number; alpha: number; rank: number; plate: boolean };
const INK = ['#1c1c1e', '#e5e5ea'], PAPER = ['#ffffff', '#0d0d0d'];

// ---- a label printed inside its own room (labels "pasted on top" ran over walls) ----
type Box = number[]; // tools/map/boxes.mjs: [l, r] free along the words for each band of half-height BANDS[i]
const BOXES = boxes as unknown as { kbtu: Record<string, Box[]>; old: Record<string, Box[]>; main: Record<string, Record<string, Box[]>> };
const BANDS = [3, 5, 8, 12, 18];
/** a text's width in em, Inter Semibold near enough (no font to measure in the tests): a margin covers the rest */
export function ems(t: string, space = 0): number {
  let w = 0;
  for (const c of t) w += /\d/.test(c) ? 0.6 : c === ' ' ? 0.27 : /[.,:;'"\u00ab\u00bb\u201c\u201d#()-]/.test(c) ? 0.32 : /[A-Z\u0410-\u042f\u0401]/.test(c) ? 0.7
    : /[\u0436\u0448\u0449\u044b\u044e\u043c\u0444mw]/.test(c) ? 0.78 : 0.57;
  return w + space * [...t].length;
}
/** the biggest size (in units of a 1000-wide plan) the words take inside their box, and the words as they stand: on
 *  one line, or two when that makes them much bigger. low: only the length counts (Uni-Q's plate covers the
 *  printed number round it). 0: they fit nowhere */
export function fit(t: string, box: Box, left: boolean, space = 0, low = false): [number, string] {
  const size = (lines: string[]) => {
    const w = Math.max(...lines.map((l) => ems(l, space))) * 1.1, half = 0.5 + 0.6 * (lines.length - 1);
    let best = 0;
    BANDS.forEach((h, i) => {
      const room = left ? box[i * 2 + 1] : 2 * Math.min(box[i * 2], box[i * 2 + 1]);
      best = Math.max(best, Math.min(low ? Infinity : h / half, room / w));
    });
    return best;
  };
  const one = size([t]), cut = t.lastIndexOf(' ', t.length / 2) + 1 || t.indexOf(' ') + 1;
  if (!cut || low) return [one, t];
  const two = [t.slice(0, cut - 1), t.slice(cut)], s2 = size(two);
  return s2 > one * 1.15 ? [s2, two.join('\n')] : [one, t];
}
/** a label's size: as big as its room lets it, never more than CAP times its print; a box that read nothing (the
 *  point on a piece of furniture) leaves the print as drawn */
const CAP = 2.5, MAXS = 30;
function sized(t: string, box: Box | undefined, print: number, left: boolean, space: number, low = false): [number, string] {
  if (!box || box.every((n) => !n)) return [print, t];
  const [s, words] = fit(t, box, left, space, low);
  return [Math.min(s, CAP * print, MAXS), words];
}

/** A floor's labels, printed on the plan: each in its own room at the biggest size the room takes,
 *  growing and shrinking with the plan as one zooms, gone while too small to read (CampusMap's layers). The collision
 *  of labels still decides between two that meet, halls and bigger rooms first. Room numbers and names always; the
 *  small print of our map (a legend, a two-line name) from mid zoom. word: a kmap.* key in the UI's language;
 *  sought: the room looked for, placed first */
export function labelsOf(ver: Ver, floor: number, dark: boolean, word: (key: string) => string, sought = ''): Label[] {
  const d = dark ? 1 : 0, rank = (room: string) => (room === sought ? -1 : rankOf(room));
  if (ver === 'main') return Object.entries(ROOMS[floor] ?? {}).flatMap(([room, at]) => at.map(([u, v], i) => {
    const [s, t] = sized(room, BOXES.main[floor]?.[room]?.[i], 16, false, 0, true);
    return { u, v, t, s, turn: 0, left: false, tier: 0, color: INK[d], halo: PAPER[d], space: 0, alpha: 1, rank: rank(room), plate: true };
  }));
  const bx = BOXES[ver][floor] ?? [];
  return (DRAWN[ver][floor] ?? []).map((r, i) => {
    const room = isRoom(r), street = r[4] >= 30 || r[12] > 0.2, small = !room && !street && (r[4] < 9 || /^(level0|staff)$/.test(r[3]));
    const [s, t] = sized(r[3] ? word(r[3]) : r[2], bx[i], r[4], r[6] === 1, r[12]);
    return { u: r[0], v: r[1], t, s, turn: r[5], left: r[6] === 1, tier: room ? 0 : small ? Math.max(1, r[7]) : r[7],
      color: (r[8 + d] as string) || INK[d], halo: (r[10 + d] as string) || (ver === 'old' ? PAPER[d] : ''),
      space: r[12], alpha: r[13], rank: room ? rank(roomName(r)) : street ? 40 : small ? 30 : 1, plate: false };
  });
}
/** the labels as GeoJSON for the map's symbol layer */
export function labelData(f: Frame, list: Label[]) {
  return { type: 'FeatureCollection' as const, features: list.map(({ u, v, ...p }) => ({ type: 'Feature' as const, properties: p, geometry: { type: 'Point' as const, coordinates: lngLat(f, u, v) } })) };
}
