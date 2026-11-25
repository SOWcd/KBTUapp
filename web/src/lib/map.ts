// Campus map (CONTEXT): rooms, halls and places by name. The plans themselves are tiles under public/map, drawn by
// MapLibre (lib/mapgl.ts has their frame and labels, tools/map/tiles.mjs cuts them): Uni-Q's plans of floors 0-5
// (another team's work, credited on the map) with their rooms' numbers and where they sit on the plan, read off it, so
// the map glides to a room; our redraw of the 2023 plans, floors 1-5 (src/assets/map/floor-N.svg: walls on a shared
// grid, the rotunda in polar coordinates, one frame for all floors); and our own map (kbtu-N.svg, tools/map).
// A Mini App always loads from the network, so the promise is "opens at once", not "offline".
import ru from './i18n/ru';
import { KK_SPOTS, EN_SPOTS } from './i18n/spots';
import { CAMPUS_SIDES, campusPlace, type CampusPlace, type CampusSide } from './campusPlace';

/** The main-building room in a place: "Aud. 305" (in Russian), "305", "Room 412", "251a" → "305", "305", "412", "251a".
 *  Only a room at the start counts, so a street address ("Abaya 150") never sends anyone to the KBTU map. A letter
 *  right after the number is part of the room: 251a is another room than 251, Cyrillic or Latin.
 *  The escapes are the Russian for auditorium and cabinet (aud, auditoriya, kab, kabinet), kept out of the source as letters. */
const ROOM = /^(?:(?:\u0430\u0443\u0434(?:\u0438\u0442\u043e\u0440\u0438\u044f)?|\u043a\u0430\u0431(?:\u0438\u043d\u0435\u0442)?|room)[.:]?\s*\u2116?\s*)?([1-57]\d{2})([a-c\u0430-\u0432](?![a-z\u0430-\u044f]))?(?!\d)/i;
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
  // Uni-Q's named rooms (all of them in Places, to route to and from; short names), known by name in any language
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
const BASEMENT = /^(?:(?:\u0430\u0443\u0434(?:\u0438\u0442\u043e\u0440\u0438\u044f)?|\u043a\u0430\u0431(?:\u0438\u043d\u0435\u0442)?|room)[.:]?\s*\u2116?\s*)?0?([1-9]\d?[a-g\u0430-\u0433]?)$/i;
export function roomOf(place: string | null | undefined): string | null {
  if (atBldg2(place) || awayOf(place)) return null; // "312" there is not the main building's 312
  const p = place?.trim() ?? '', m = p.match(ROOM), b = p.match(BASEMENT);
  if (m) return normRoom(m[1] + (m[2] ?? ''));
  if (b) return normRoom(b[1]);
  return /\d/.test(p) ? null : HALLS.find(([re]) => re.test(p))?.[1] ?? null;
}
/** Its floor: the room's first digit (or a named place's floor) ("305" → 3), 0 for the basement's 1-99; 7xx is
 *  Independence Hall's wing on floor 2. Compare with null: 0 is a floor. */
export function floorOf(place: string | null | undefined): number | null {
  const campus = campusPlace(place);
  if (campus) return campus.floor;
  const r = roomOf(place);
  if (r == null) return place && spotOf(place)?.k === 'indep' ? 2 : null; // the schedule's Independence Hall; not any "Halyk" or "canteen" (an arena, a home)
  return /^7\d\d/.test(r) ? 2 : /^\d{3}/.test(r) ? Number(r[0]) : 0;
}

/** The dormitory: the portal names classes held there "DMiS ..." (PE: "DMiS OFP (Rugby)..."); the schedule shows a
 *  small "Dorm" that opens it in 2GIS instead (the official card of KBTU's Dorm No. 3). The escapes are the Russian letters of DMiS. */
export const DORM_2GIS = 'https://2gis.kz/almaty/geo/9429940001182035';
/** A typed street address ("Gogolya 157", "Abaya 150, 2nd floor") → 2GIS's search for it in Almaty, the route one tap
 *  away (else an address stays plain text). Not a room, a campus spot, the dorm or the
 *  second building: a word of three letters or more and a house number. */
// kbtu (ru, kk), room, a secret location, campus, hall, atrium, coworking, foyer, auditorium, room, library, canteen, yard, online, to be confirmed (ru, kk, en)
const CAMPUS_WORDS = /kbtu|[\u043a\u049b]\u0431\u0442\u0443|room|secret|campus|\u043a\u0430\u043c\u043f\u0443\u0441|hall|\u0437\u0430\u043b|\u0445\u043e\u043b\u043b|atri|\u0430\u0442\u0440\u0438\u0443\u043c|cowork|\u043a\u043e\u0432\u043e\u0440\u043a|foyer|\u0444\u043e\u0439\u0435|\u0430\u0443\u0434\u0438\u0442|\u043a\u0430\u0431\u0438\u043d\u0435\u0442|library|\u0431\u0438\u0431\u043b\u0438\u043e\u0442|\u043a\u0456\u0442\u0430\u043f\u0445\u0430\u043d|canteen|\u0441\u0442\u043e\u043b\u043e\u0432|\u0430\u0441\u0445\u0430\u043d|yard|\u0434\u0432\u043e\u0440|\u0430\u0443\u043b\u0430|online|\u043e\u043d\u043b\u0430\u0439\u043d|\u0443\u0442\u043e\u0447\u043d|tba|\u0442\u0435\u0440\u0440\u0430\u0441|\u043a\u043e\u0440\u043f\u0443\u0441|building/i;
export function addressGis(place: string, url?: string | null): string | null {
  if (campusPlace(place)) return null;
  if (url) return url;
  const p = place.trim();
  if (atDorm(p)) return DORM_2GIS; // the dorm's own card, not a search
  if (!p || roomOf(p) || spotOf(p) || atBldg2(p) || awayOf(p) || !/\p{L}{3,}/u.test(p)) return null;
  // a street address (a house number), or a named venue off campus ("Mad Murphy's Irish Pub", owner Nov 20): two words or
  // more; never with the campus's own words, so "Hall" or an assembly hall stay plain
  const address = /(^|\s)\d{1,4}[a-z\u0430-\u044f/]?(\b|$)/iu.test(p);
  if (CAMPUS_WORDS.test(p) || (!address && (/\d/.test(p) || p.split(/\s+/).filter((w) => /\p{L}{2,}/u.test(w)).length < 2))) return null;
  return `https://2gis.kz/almaty/search/${encodeURIComponent(p)}`;
}
// the portal's "DMiS", and what organizers type: dorm, obshchaga, zhatakhana (kk), Jastar City, Islam Karimov 70 (its street)
export const atDorm = (place: string | null | undefined): boolean =>
  !!place && /\u0434\u043c\u0438\u0441|dorm|\u043e\u0431\u0449\u0430\u0433|\u0436\u0430\u0442\u0430\u049b\u0445\u0430\u043d|jastar|\u0436\u0430\u0441\u0442\u0430\u0440|(islam|\u0438\u0441\u043b\u0430\u043c)\s+(karimov|\u043a\u0430\u0440\u0438\u043c\u043e\u0432)/i.test(place);

/** KBTU's second building, away from the main one: the portal writes "312 (Korpus No. 2 ...)". It has no
 *  map here, so its rooms never open the main one; the schedule shows "312 · B2" that opens it in 2GIS (the link he sent).
 *  The escape is "korpus", in Russian and Kazakh alike. */
export const BLDG2_2GIS = 'https://2gis.kz/almaty/geo/70000001117579717/76.909355,43.253443';
const BLDG2 = /(?:\u043a\u043e\u0440\u043f\u0443\u0441|building)\s*(?:\u2116|no\.?)?\s*2(?!\d)|(?:^|\D)2\s*-?\s*\u043a\u043e\u0440\u043f\u0443\u0441/i;
export const atBldg2 = (place: string | null | undefined): boolean => !!place && BLDG2.test(place);
/** Its room as the schedule shows it: the number before the building or right after it ("312 (Korpus No. 2)",
 *  "Korpus No. 2, 312", "2 korpus, 312" → "312"), never the building's own 2 or a street's number */
const BLDG2_LEAD = new RegExp(`^(?:${BLDG2.source})[\\s,.:-]*`, 'i');
export const bldg2Room = (place: string): string | null => place.trim().replace(BLDG2_LEAD, '').match(/^\d+[^\s(,]*/)?.[0] ?? null;

/** Two institutes off campus where labs are held (else they stand as plain text): the portal
 *  writes "ITKiE kab No1 (Kunaeva 142)" and "IHN No25". No map here: the schedule shows "IHN 25" that opens the
 *  institute in 2GIS (his links, without the invite marks). The escapes are the two abbreviations in Russian. */
const AWAY = [
  { k: 'itkie', re: /\u0438\u0442\u043a\u0438\u044d/i, url: 'https://2gis.kz/almaty/geo/9429940000795839' },
  { k: 'ihn', re: /\u0438\u0445\u043d/i, url: 'https://2gis.kz/almaty/geo/9429940000795852/76.953742,43.247277' },
] as const;
export function awayOf(place: string | null | undefined): { k: 'itkie' | 'ihn'; url: string; room: string | null } | null {
  const a = place && AWAY.find((x) => x.re.test(place));
  return a ? { k: a.k, url: a.url, room: place.match(/\u2116\s*(\d+[a-z\u0430-\u044f]?)/i)?.[1] ?? null } : null;
}

/** The map ahead of its first opening (the first tap opens it at once): its chunk with MapLibre, the
 *  workers, the first floor's overview and tiles (screens/map/CampusMap.svelte warm). Called in an idle moment after the
 *  app has started and again on the tap; once */
let warmed = false;
export function warmMap(): void {
  if (warmed) return;
  warmed = true;
  import('../screens/map/CampusMap.svelte').then((m) => m.warm(), () => { warmed = false; });
}

/** A room the plan doesn't number: the nearest numbers below and above it on its floor (within 10), both when they sit
 *  close together, else the nearer one ("376 isn't there but 377 is: zoom there"; routes lead
 *  there too). rooms: the floor's room -> where its number is printed; ar: the plan's height to its width. [room, [u, v]] */
export function nearRooms(rooms: Record<string, number[][]>, room: string, ar: number): [string, number[]][] {
  const n = parseInt(room, 10), by = Object.entries(rooms)
    .map(([k, at]) => ({ k, d: parseInt(k, 10) - n, at: at[0] })).filter((x) => x.d && Math.abs(x.d) <= 10);
  const lo = by.filter((x) => x.d < 0).sort((a, b) => b.d - a.d)[0], hi = by.filter((x) => x.d > 0).sort((a, b) => a.d - b.d)[0];
  const one = (x: { k: string; at: number[] }): [string, number[]] => [x.k, x.at];
  if (!lo || !hi) return lo || hi ? [one((lo ?? hi)!)] : [];
  return Math.hypot(lo.at[0] - hi.at[0], (lo.at[1] - hi.at[1]) * ar) < 0.25 ? [one(lo), one(hi)] : [one(-lo.d <= hi.d ? lo : hi)];
}

/** A point on the main map's plan (Uni-Q's: the routes' graph is drawn on it): a floor and fractions of its width and height */
type At = { f: number; u: number; v: number };
type Door = At & { k?: string; name?: string; r?: string[] };

// Side anchors on Uni-Q's floors, at the nearest stairs in map_graph.json (groups 1/10, 5, 4 and 2).
const SIDE_POINTS: Record<CampusSide, [number, number][]> = {
  tole: [[0.515, 0.737], [0.502, 0.756], [0.505, 0.749], [0.498, 0.745], [0.496, 0.772], [0.570, 0.777]],
  abylai: [[0.250, 0.617], [0.231, 0.619], [0.226, 0.615], [0.243, 0.620], [0.256, 0.598]],
  panfilov: [[0.773, 0.622], [0.764, 0.621], [0.773, 0.617], [0.758, 0.609], [0.748, 0.618]],
  kazybek: [[0.234, 0.269], [0.226, 0.251], [0.247, 0.251], [0.256, 0.235]],
};

export function campusPoint(place: CampusPlace, rooms: Record<string, number[][]>[]): At & { room: string } {
  const { side, floor: f } = place;
  const room = roomOf(place.room);
  const exact = room ? rooms[f]?.[room]?.[0] : undefined;
  const [u, v] = exact ?? SIDE_POINTS[side][f - CAMPUS_SIDES[side].min];
  return { f, u, v, room: exact && room ? room : '' };
}

/** What a typed text means on the main map, for a route's start or end and "Show on map": an entrance by its name,
 *  a named place with a point (the canteen), a room where its number is printed, else its door on the graph, else its
 *  nearest numbered neighbour ("435 isn't on the plan: somewhere here", near: the room asked for). rooms: by floor, the
 *  room → where its number is printed; doors: the graph's points; ar: the plan's height to its width */
export function locate(text: string, rooms: Record<string, number[][]>[], doors: Door[], ar: number): (At & { room: string; spot?: string; near?: string }) | null {
  const campus = campusPlace(text);
  if (campus) return campusPoint(campus, rooms);
  const x = doors.find((n) => n.k === 'x' && n.name === text.trim());
  if (x) return { f: x.f, u: x.u, v: x.v, room: x.name! };
  const s = spotOf(text);
  if (s?.f != null) return { f: s.f, u: s.u!, v: s.v!, room: s.k, spot: s.k };
  const r = roomOf(text) ?? s?.room ?? null, f = floorOf(r);
  if (!r || f == null) return null;
  const at = rooms[f]?.[r]?.[0], door = doors.find((n) => n.r?.includes(r));
  if (at) return { f, u: at[0], v: at[1], room: r };
  if (door) return { f: door.f, u: door.u, v: door.v, room: r };
  const nb = nearRooms(rooms[f] ?? {}, r, ar)[0];
  return nb ? { f, u: nb[1][0], v: nb[1][1], room: nb[0], near: r } : null;
}

/** What a tap on the main map means for a route's end: the entrance, the named place or the room whose number is
 *  nearest the finger, within reach (a fraction of the plan's width: a finger's size at the zoom on screen); else
 *  nothing, and the point itself is the end. An entrance or a named place wins over a room's number at the same reach */
export function tapAt(p: At, rooms: Record<string, number[][]>[], doors: Door[], ar: number, reach: number): { exit?: string; spot?: string; room?: string } | null {
  const d = (q: { u: number; v: number }) => Math.hypot(q.u - p.u, (q.v - p.v) * ar);
  const x = doors.filter((n) => n.k === 'x' && n.name && n.f === p.f && d(n) < reach).sort((a, b) => d(a) - d(b))[0];
  if (x) return { exit: x.name };
  const s = SPOTS.filter((s) => s.f === p.f && d({ u: s.u!, v: s.v! }) < reach).sort((a, b) => d({ u: a.u!, v: a.v! }) - d({ u: b.u!, v: b.v! }))[0];
  if (s) return { spot: s.k };
  let best = '', bd = reach;
  for (const [r, at] of Object.entries(rooms[p.f] ?? {})) for (const [u, v] of at) if (d({ u, v }) < bd) { bd = d({ u, v }); best = r; }
  return best ? { room: best } : null;
}
