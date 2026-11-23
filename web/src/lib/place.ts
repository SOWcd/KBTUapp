// Where a Gallery photo was taken, as one of four words: the phone reads the photo's own EXIF (its GPS spot, its
// time), names the place here and sends that word alone. The coordinates never leave this file: the upload itself is
// redrawn without EXIF (lib/photo.ts shrink). The Gallery sorts by the word (bySite); nothing else is shown.
import type { AlbumPhoto, GalleryMyEvent } from './api';
import { addressGis } from './map';

export type Place = 'main' | 'b2' | 'dorm' | 'away';
export const PLACES: Place[] = ['main', 'b2', 'dorm', 'away'];

// ponytail: a circle round one point per building. MAIN and DORM are approximate (Tole Bi 59; the dorm's spot is
// unconfirmed: the owner checks both in 2GIS); B2 is the point of lib/map.ts BLDG2_2GIS. Outlines if a neighbour's
// yard starts to count as campus.
const MAIN: [number, number] = [43.2553, 76.9431];
const B2: [number, number] = [43.253443, 76.909355];
const DORM: [number, number] = [43.2507, 76.8715];
const NEAR_M = 250; // a building's own size plus a phone's GPS error indoors
const SITES: [Place, [number, number]][] = [['main', MAIN], ['b2', B2], ['dorm', DORM]];

export function placeOf(lat: number, lon: number): Place {
  const near = SITES.find(([, [la, lo]]) => Math.hypot((lat - la) * 111_320, (lon - lo) * 111_320 * Math.cos((la * Math.PI) / 180)) <= NEAR_M);
  return near ? near[0] : 'away';
}

/** A photo file's GPS spot and the time it was taken (unix seconds), from its EXIF; {} when it says neither.
 *  JPEG and HEIC alike: the TIFF block is found by its "Exif\0\0" mark in the file's head. */
// ponytail: a scan for the mark, not a walk of JPEG segments or HEIC boxes; walk them if a file ever carries the
// mark in its pixels before its real EXIF. A time without its zone is Almaty's (as server media.taken).
export function exif(buf: ArrayBuffer): { gps?: [number, number]; taken?: number } {
  try {
    const b = new Uint8Array(buf), v = new DataView(buf);
    let t = -1;
    for (let i = 0; i + 14 < b.length && t < 0; i++) {
      if (b[i] === 0x45 && b[i + 1] === 0x78 && b[i + 2] === 0x69 && b[i + 3] === 0x66 && !b[i + 4] && !b[i + 5]
        && (b[i + 6] === 0x49 || b[i + 6] === 0x4d) && b[i + 7] === b[i + 6]) t = i + 6;
    }
    if (t < 0) return {};
    const le = b[t] === 0x49;
    const u16 = (o: number) => v.getUint16(t + o, le), u32 = (o: number) => v.getUint32(t + o, le);
    const ifd = (o: number) => new Map(Array.from({ length: u16(o) }, (_, k) => [u16(o + 2 + k * 12), o + 2 + k * 12] as const)); // tag -> its entry
    const text = (e: number | undefined, n: number) => (e == null ? '' : String.fromCharCode(...b.subarray(t + u32(e + 8), t + u32(e + 8) + n)));
    const ifd0 = ifd(u32(4)), sub = ifd0.get(0x8769), g = ifd0.get(0x8825);
    const out: { gps?: [number, number]; taken?: number } = {};
    // DateTimeOriginal, else the file's own DateTime: "2026:11:23 14:05:09"
    const m = (text(sub == null ? undefined : ifd(u32(sub + 8)).get(0x9003), 19) || text(ifd0.get(0x0132), 19)).match(/^(\d{4}):(\d\d):(\d\d) (\d\d):(\d\d):(\d\d)$/);
    if (m) out.taken = Date.UTC(+m[1], +m[2] - 1, +m[3], +m[4] - 5, +m[5], +m[6]) / 1000;
    if (g != null) {
      const gi = ifd(u32(g + 8));
      const deg = (ref: number, val: number) => { // three rationals (degrees, minutes, seconds); S and W are negative
        const r = gi.get(ref), e = gi.get(val);
        if (r == null || e == null) return NaN;
        const o = u32(e + 8), q = (k: number) => u32(o + k * 8) / u32(o + k * 8 + 4);
        return (q(0) + q(1) / 60 + q(2) / 3600) * ('SW'.includes(String.fromCharCode(b[t + r + 8])) ? -1 : 1);
      };
      const lat = deg(1, 2), lon = deg(3, 4);
      if (Number.isFinite(lat) && Number.isFinite(lon) && (lat || lon)) out.gps = [lat, lon]; // 0,0: a camera that never had a fix
    }
    return out;
  } catch {
    return {}; // a cut or broken block: no place, the photo itself is fine
  }
}

/** What goes with my photo: its place word and, taken off campus while an event of mine held elsewhere was on, that
 *  event (its album takes it; the server checks). */
// ponytail: an event has no coordinates, so "its place" is "not on campus" (a 2GIS link or a street address) and the
// match is by time; give events a point and compare it here, on the phone, if two away events ever overlap.
export async function sited(file: Blob, events: GalleryMyEvent[]): Promise<{ place?: Place; event?: GalleryMyEvent }> {
  const { gps, taken } = exif(await file.slice(0, 262144).arrayBuffer().catch(() => new ArrayBuffer(0)));
  if (!gps) return {};
  const place = placeOf(...gps);
  return { place, event: place === 'away' && taken ? eventFor(taken, events) : undefined };
}
const HOUR = 3600;
export const eventFor = (taken: number, events: GalleryMyEvent[]): GalleryMyEvent | undefined =>
  events.find((e) => (e.away || !!addressGis(e.place)) && taken >= e.at - HOUR && taken <= (e.end ?? e.at + 3 * HOUR) + HOUR);

/** The Gallery's order: the four places in turn, then the photos that name none; newest first inside each. */
export function bySite(photos: AlbumPhoto[]): { key: Place | 'none'; photos: AlbumPhoto[] }[] {
  const sets = new Map<Place | 'none', AlbumPhoto[]>([...PLACES, 'none' as const].map((k) => [k, []]));
  for (const p of photos) sets.get(p.place ?? 'none')!.push(p);
  return [...sets].filter(([, ps]) => ps.length).map(([key, ps]) => ({ key, photos: ps }));
}
