// After consent, name the photo's place from its GPS on the phone. Only the place label goes with the JPEG upload.
import type { AlbumPhoto } from './api';

export type Place = 'main' | 'b2' | 'dorm' | 'away';
export const PLACES: Place[] = ['main', 'b2', 'dorm', 'away'];

// ponytail: a circle round one point per building (2GIS points: Tole Bi 59, lib/map.ts BLDG2_2GIS and DORM_2GIS).
// Outlines if a neighbour's yard starts to count as campus.
const MAIN: [number, number] = [43.255628, 76.943119];
const B2: [number, number] = [43.253443, 76.909355];
const DORM: [number, number] = [43.252333, 76.882323];
const NEAR_M = 250; // a building's own size plus a phone's GPS error indoors
const SITES: [Place, [number, number]][] = [['main', MAIN], ['b2', B2], ['dorm', DORM]];

export function placeOf(lat: number, lon: number): Place {
  const near = SITES.find(([, [la, lo]]) => Math.hypot((lat - la) * 111_320, (lon - lo) * 111_320 * Math.cos((la * Math.PI) / 180)) <= NEAR_M);
  return near ? near[0] : 'away';
}

/** A photo's GPS from its EXIF, when the file head contains an "Exif\0\0" TIFF block. */
// ponytail: a scan for the mark, not a walk of JPEG segments or HEIC boxes; walk them if a file ever carries the
// mark in its pixels before its real EXIF.
export function exifGps(buf: ArrayBuffer): [number, number] | undefined {
  try {
    const b = new Uint8Array(buf), v = new DataView(buf);
    let t = -1;
    for (let i = 0; i + 14 < b.length && t < 0; i++) {
      if (b[i] === 0x45 && b[i + 1] === 0x78 && b[i + 2] === 0x69 && b[i + 3] === 0x66 && !b[i + 4] && !b[i + 5]
        && (b[i + 6] === 0x49 || b[i + 6] === 0x4d) && b[i + 7] === b[i + 6]) t = i + 6;
    }
    if (t < 0) return;
    const le = b[t] === 0x49;
    const u16 = (o: number) => v.getUint16(t + o, le), u32 = (o: number) => v.getUint32(t + o, le);
    const ifd = (o: number) => new Map(Array.from({ length: u16(o) }, (_, k) => [u16(o + 2 + k * 12), o + 2 + k * 12] as const)); // tag -> its entry
    const g = ifd(u32(4)).get(0x8825);
    if (g == null) return;
    const gi = ifd(u32(g + 8));
    const deg = (ref: number, val: number) => { // three rationals (degrees, minutes, seconds); S and W are negative
      const r = gi.get(ref), e = gi.get(val);
      if (r == null || e == null) return NaN;
      const o = u32(e + 8), q = (k: number) => u32(o + k * 8) / u32(o + k * 8 + 4);
      return (q(0) + q(1) / 60 + q(2) / 3600) * ('SW'.includes(String.fromCharCode(b[t + r + 8])) ? -1 : 1);
    };
    const lat = deg(1, 2), lon = deg(3, 4);
    if (Math.abs(lat) <= 90 && Math.abs(lon) <= 180 && (lat || lon)) return [lat, lon]; // 0,0: no fix
  } catch {
    return; // a cut or broken block: upload without a label
  }
}

export async function sited(file: Blob): Promise<Place | undefined> {
  try {
    const gps = exifGps(await file.slice(0, 262144).arrayBuffer());
    if (gps) return placeOf(...gps);
  } catch {
    return; // older webviews can still upload the photo without a label
  }
}

/** The Gallery's order: the four places in turn, then the photos that name none; newest first inside each. */
export function bySite(photos: AlbumPhoto[]): { key: Place | 'none'; photos: AlbumPhoto[] }[] {
  const sets = new Map<Place | 'none', AlbumPhoto[]>([...PLACES, 'none' as const].map((k) => [k, []]));
  for (const p of photos) sets.get(p.place ?? 'none')!.push(p);
  return [...sets].filter(([, ps]) => ps.length).map(([key, ps]) => ({ key, photos: ps }));
}
