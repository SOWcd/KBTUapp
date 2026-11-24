import { describe, expect, it } from 'vitest';
import type { AlbumPhoto } from './api';
import { bySite, exifGps, placeOf, sited } from './place';

/** A JPEG's head with an EXIF block: taken at `when`, at lat/lon (degrees, minutes, seconds as the camera writes them). */
function jpeg(lat: number, lon: number, when = '2026:11:20 19:30:00'): ArrayBuffer {
  const tiff = new DataView(new ArrayBuffer(178));
  const u16 = (o: number, x: number) => tiff.setUint16(o, x, true), u32 = (o: number, x: number) => tiff.setUint32(o, x, true);
  const entry = (o: number, tag: number, type: number, n: number, val: number) => { u16(o, tag); u16(o + 2, type); u32(o + 4, n); u32(o + 8, val); };
  const dms = (o: number, x: number) => {
    const a = Math.abs(x), d = Math.floor(a), m = Math.floor((a - d) * 60), s = Math.round(((a - d) * 60 - m) * 60 * 1000);
    [[d, 1], [m, 1], [s, 1000]].forEach(([p, q], k) => { u32(o + k * 8, p); u32(o + k * 8 + 4, q); });
  };
  u16(0, 0x4949); u16(2, 42); u32(4, 8);
  u16(8, 2); entry(10, 0x8769, 4, 1, 38); entry(22, 0x8825, 4, 1, 56);
  u16(38, 1); entry(40, 0x9003, 2, 20, 110);
  u16(56, 4); entry(58, 1, 2, 2, (lat < 0 ? 'S' : 'N').charCodeAt(0)); entry(70, 2, 5, 3, 130); entry(82, 3, 2, 2, (lon < 0 ? 'W' : 'E').charCodeAt(0)); entry(94, 4, 5, 3, 154);
  [...when].forEach((c, k) => tiff.setUint8(110 + k, c.charCodeAt(0)));
  dms(130, lat); dms(154, lon);
  return new Uint8Array([0xff, 0xd8, 0xff, 0xe1, 0, 186, 0x45, 0x78, 0x69, 0x66, 0, 0, ...new Uint8Array(tiff.buffer), 0xff, 0xd9]).buffer;
}
describe('place', () => {
  it('names the campus by the spot, anything else is away', () => {
    expect(placeOf(43.2553, 76.9431)).toBe('main');
    expect(placeOf(43.2546, 76.944)).toBe('main'); // across the yard
    expect(placeOf(43.253443, 76.909355)).toBe('b2');
    expect(placeOf(43.2385, 76.9456)).toBe('away'); // two kilometres south
    expect(placeOf(51.5, -0.12)).toBe('away');
  });
  it('reads a GPS spot from EXIF and lets photos without one through', () => {
    const got = exifGps(jpeg(43.25345, 76.90935));
    expect(got?.[0]).toBeCloseTo(43.25345, 4);
    expect(got?.[1]).toBeCloseTo(76.90935, 4);
    expect(exifGps(jpeg(-33.8568, -151.2153))?.[0]).toBeLessThan(0);
    expect(exifGps(new Uint8Array([0xff, 0xd8, 0xff, 0xdb, 0, 4, 1, 2]).buffer)).toBeUndefined();
    expect(exifGps(jpeg(43.25, 76.9).slice(0, 60))).toBeUndefined();
  });
  it('returns only the place label from a file with GPS and a capture time', async () => {
    expect(await sited(new Blob([jpeg(43.2385, 76.9456)]))).toBe('away');
    expect(await sited(new Blob([jpeg(0, 0)]))).toBeUndefined();
  });
  it('sorts by place, the unnamed last', () => {
    const p = (id: number, place?: AlbumPhoto['place']) => ({ id, place }) as AlbumPhoto;
    expect(bySite([p(5), p(4, 'away'), p(3, 'main'), p(2, 'b2'), p(1, 'main')]).map((s) => [s.key, s.photos.map((x) => x.id)]))
      .toEqual([['main', [3, 1]], ['b2', [2]], ['away', [4]], ['none', [5]]]);
  });
});
