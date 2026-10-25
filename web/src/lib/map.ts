// Campus map (CONTEXT), two versions. Main: UNI-Q's plans of floors 0-5 (another team's work, credited
// on the map), cut into an overview and tiles (design/map/tools/uniq) under public/map/u1, which the server caches for
// a year; their rooms' numbers and where they sit on the plan, read off it, so the map glides to a room. Old: our
// vector redraw, floors 1-5 from the 2023 plans (design/map/tools: walls on a shared grid, the rotunda in polar
// coordinates, the labels as real text checked by eye, one frame for all floors), the basement (0) from UNI-Q's plan
// (design/map/tools/basement). A Mini App always loads from the network, so the promise is "opens at once", not
// "offline": the main map's overviews are fetched quietly soon after the first launch.
import ru from './i18n/ru';
import { KK_SPOTS, EN_SPOTS } from './i18n/spots';
import f1 from '../assets/map/floor-1.svg?url';
import f2 from '../assets/map/floor-2.svg?url';
import f3 from '../assets/map/floor-3.svg?url';
import f4 from '../assets/map/floor-4.svg?url';
import f5 from '../assets/map/floor-5.svg?url';

/** The old map's floors by number; 0, the basement, is the main map's only (the old one's was copied off UNI-Q's) */
export const FLOORS = [null, f1, f2, f3, f4, f5];

const loaded = new Map<number, Promise<string>>();
/** A floor's SVG markup (0..5); fetched once per launch, a failed fetch is tried again next time. */
export function loadFloor(n: number): Promise<string> {
  let p = loaded.get(n);
  if (!p) {
    p = fetch(FLOORS[n]!).then((r) => (r.ok ? r.text() : Promise.reject(new Error(String(r.status)))));
    loaded.set(n, p);
    p.catch(() => loaded.delete(n));
  }
  return p;
}

/** The main-building room in a place: "Aud. 305" (in Russian), "305", "Room 412", "251a" → "305", "305", "412", "251a".
 *  Only a room at the start counts, so a street address ("Abaya 150") never sends anyone to the KBTU map. A letter
 *  right after the number is part of the room: 251a is another room than 251, Cyrillic or Latin.
 *  The escapes are the Russian for auditorium and cabinet (aud, auditoriya, kab, kabinet), kept out of the source as letters. */
const ROOM = /^(?:(?:\u0430\u0443\u0434(?:\u0438\u0442\u043e\u0440\u0438\u044f)?|\u043a\u0430\u0431(?:\u0438\u043d\u0435\u0442)?|room)\.?\s*\u2116?\s*)?([1-57]\d{2})([a-c\u0430-\u0432](?![a-z\u0430-\u044f]))?(?!\d)/i;
/** A room as the maps name it: "251A", Cyrillic "251a" → "251a" (the Cyrillic a, b, v, s become Latin) */
export const normRoom = (s: string): string =>
  s.trim().toLowerCase().replace(/[\u0430\u0431\u0432\u0441]/g, (c) => 'abvc'['\u0430\u0431\u0432\u0441'.indexOf(c)]);
/** Halls the portal names instead of numbering them (the Kunaev hall is 400a). A name with a digit in it is
 *  an address, never a hall: Kunaev is a street in Almaty too. The escapes: Kunaev in Russian and in Kazakh. */
const HALLS: [RegExp, string][] = [[/\u043a\u0443\u043d\u0430\u0435\u0432|\u049b\u043e\u043d\u0430\u0435\u0432|kunay?e?v/i, '400a'],
  // Al-Farabi Hall: 470. The escape: "farabi" in Russian and Kazakh.
  [/\u0444\u0430\u0440\u0430\u0431\u0438|farabi/i, '470']];
/** Independence Hall (not 726, the round hall in the middle of floor 2). The escapes: "nezavisim" in
 *  Russian, "tauelsiz" in Kazakh. */
const INDEP = /\u043d\u0435\u0437\u0430\u0432\u0438\u0441\u0438\u043c|\u0442\u04d9\u0443\u0435\u043b\u0441\u0456\u0437|independence/i;
/** Places people know by name, buttons on "Help me get out" and words in "from/to": a hall is its room;
 *  the canteen and Halyk Co-working have no number, so a point on the main map's plan (read off it). The escapes: the
 *  Russian and Kazakh for canteen, the Russian for co-working and Halyk. */
export type Spot = { k: string; re?: RegExp; room?: string; f?: number; u?: number; v?: number; adm?: boolean }; // adm: offices, a group of their own
export const SPOTS: Spot[] = [
  { k: 'canteen', re: /\u0441\u0442\u043e\u043b\u043e\u0432|\u0430\u0441\u0445\u0430\u043d|canteen|cafeteria/i, f: 0, u: 0.552, v: 0.602 },
  { k: 'cowork', re: /\u043a\u043e\u0432\u043e\u0440\u043a|\u0445\u0430\u043b\u044b\u043a|co-?work|halyk/i, f: 1, u: 0.496, v: 0.457 },
  { k: 'kunaev', re: HALLS[0][0], room: '400a' },
  { k: 'farabi', re: HALLS[1][0], room: '470' },
  { k: 'indep', re: INDEP, f: 2, u: 0.498, v: 0.613 },
  // UNI-Q's named rooms (all of them in Places, to route to and from; short names), known by name in any language
  { k: 'library', room: '158' },
  { k: 'career', room: '152' },
  { k: 'students', room: '155' },
  { k: 'site', room: '180' },
  { k: 'energy', room: '356' },
  { k: 'marine', room: '255' },
  { k: 'gamedev', room: '47' },
  { k: 'honeywell', room: '140' },
  { k: 'security', room: '250a', adm: true },
  { k: 'dispatch', room: '1', adm: true },
  { k: 'rector', room: '466', adm: true },
  { k: 'vrScience', room: '415', adm: true },
  { k: 'vrSocial', room: '472', adm: true },
  { k: 'legal', room: '503', adm: true },
  { k: 'accounting', room: '523', adm: true },
];
/** The named place a text means: "Canteen", "halyk co-working"; a number in it is a room or an address, never a spot */
const named = (s: Spot) => [ru, KK_SPOTS, EN_SPOTS].map((d) => d[`route.spot.${s.k}` as 'route.spot.canteen'] as string);
export const spotOf = (text: string): Spot | null =>
  /\d/.test(text) ? null : SPOTS.find((s) => s.re?.test(text) || named(s).includes(text.trim())) ?? null;
/** Floor 4's south side (Tole bi) is the administration, shut to students; Al-Farabi Hall (470) is not */
export const adminZone = (room: string | null | undefined): boolean => !!room && /^(?:46[2-8]|47[1-6]|41[6-8])$/.test(room);
/** A basement room: 1-99, maybe with a letter, as the whole place, so a
 *  short number in an address ("12 mkr") never counts; a leading zero is dropped ("045" → "45"). */
const BASEMENT = /^(?:(?:\u0430\u0443\u0434(?:\u0438\u0442\u043e\u0440\u0438\u044f)?|\u043a\u0430\u0431(?:\u0438\u043d\u0435\u0442)?|room)\.?\s*\u2116?\s*)?0?([1-9]\d?[a-g\u0430-\u0433]?)$/i;
export function roomOf(place: string | null | undefined): string | null {
  if (atBldg2(place)) return null; // "312" there is not the main building's 312
  const p = place?.trim() ?? '', m = p.match(ROOM), b = p.match(BASEMENT);
  if (m) return normRoom(m[1] + (m[2] ?? ''));
  if (b) return normRoom(b[1]);
  return /\d/.test(p) ? null : HALLS.find(([re]) => re.test(p))?.[1] ?? null;
}
/** Its floor: the room's first digit (or a named place's floor) ("305" → 3), 0 for the basement's 1-99; 7xx is
 *  Independence Hall's wing on floor 2. Compare with null: 0 is a floor. */
export function floorOf(place: string | null | undefined): number | null {
  const r = roomOf(place);
  if (r == null) return place && spotOf(place)?.k === 'indep' ? 2 : null; // the schedule's Independence Hall; not any "Halyk" or "canteen" (an arena, a home)
  return /^7\d\d/.test(r) ? 2 : /^\d{3}/.test(r) ? Number(r[0]) : 0;
}

/** The dormitory: the portal names classes held there "DMiS ..." (PE: "DMiS OFP (Rugby)..."); the schedule shows a
 *  small "Dorm" that opens it in 2GIS instead (the official card of KBTU's Dorm No. 3). The escapes are the Russian letters of DMiS. */
export const DORM_2GIS = 'https://2gis.kz/almaty/geo/9429940001182035';
export const atDorm = (place: string | null | undefined): boolean => !!place && /\u0434\u043c\u0438\u0441/i.test(place);

/** KBTU's second building, away from the main one: the portal writes "312 (Korpus No. 2 ...)". It has no
 *  map here, so its rooms never open the main one; the schedule shows "312 · B2" that opens it in 2GIS.
 *  The escape is "korpus", in Russian and Kazakh alike. */
export const BLDG2_2GIS = 'https://2gis.kz/almaty/geo/70000001117579717/76.909355,43.253443';
const BLDG2 = /(?:\u043a\u043e\u0440\u043f\u0443\u0441|building)\s*(?:\u2116|no\.?)?\s*2(?!\d)|(?<!\d)2\s*-?\s*\u043a\u043e\u0440\u043f\u0443\u0441/i;
export const atBldg2 = (place: string | null | undefined): boolean => !!place && BLDG2.test(place);
/** Its room as the schedule shows it: the number before the building or right after it ("312 (Korpus No. 2)",
 *  "Korpus No. 2, 312", "2 korpus, 312" → "312"), never the building's own 2 or a street's number */
const BLDG2_LEAD = new RegExp(`^(?:${BLDG2.source})[\\s,.:-]*`, 'i');
export const bldg2Room = (place: string): string | null => place.trim().replace(BLDG2_LEAD, '').match(/^\d+[^\s(,]*/)?.[0] ?? null;

/** The main map's tiles: public/map/u1, next to index.html */
export const TILES = `${import.meta.env.BASE_URL}map/u1/`;

/** Fetch the main map's floor overviews once the app has settled (about 0.6 MB, once: the server caches them a year) */
export function warmMap(): void {
  FLOORS.forEach((_, n) => fetch(`${TILES}f${n}/o.webp`).catch(() => {}));
}

/** A room the plan doesn't number: the nearest numbers below and above it on its floor (within 10), both when they sit
 *  close together, else the nearer one ("376 isn't there but 377 is: zoom there"; routes lead there too). rooms: the floor's room -> where its number is printed; ar: the plan's height to its width. [room, [u, v]] */
export function nearRooms(rooms: Record<string, number[][]>, room: string, ar: number): [string, number[]][] {
  const n = parseInt(room, 10), by = Object.entries(rooms)
    .map(([k, at]) => ({ k, d: parseInt(k, 10) - n, at: at[0] })).filter((x) => x.d && Math.abs(x.d) <= 10);
  const lo = by.filter((x) => x.d < 0).sort((a, b) => b.d - a.d)[0], hi = by.filter((x) => x.d > 0).sort((a, b) => a.d - b.d)[0];
  const one = (x: { k: string; at: number[] }): [string, number[]] => [x.k, x.at];
  if (!lo || !hi) return lo || hi ? [one((lo ?? hi)!)] : [];
  return Math.hypot(lo.at[0] - hi.at[0], (lo.at[1] - hi.at[1]) * ar) < 0.25 ? [one(lo), one(hi)] : [one(-lo.d <= hi.d ? lo : hi)];
}
