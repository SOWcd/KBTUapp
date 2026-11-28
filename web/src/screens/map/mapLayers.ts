// What MapLibre draws for the campus map (CampusMap.svelte): the floor's tiles, the labels, the pins' places. Plain
// builders of MapLibre's sources, layers and paint, from the map's version, frame and look; CampusMap gives them to
// the map and gives them again when one of those changes.
import type { GeoJSONSource, ImageSource, LayerSpecification, Map as GLMap, SourceSpecification } from 'maplibre-gl';
import { FRAMES, Z0, LEVELS, SCAN_AT, lngLat, scan, zoomFor, widthAt, tilesOf, tileSize, type Frame, type Ver } from '../../lib/mapgl';

export type RasterPaint = 'raster-brightness-min' | 'raster-brightness-max' | 'raster-hue-rotate';
const INVERT: Record<RasterPaint, number> = { 'raster-brightness-min': 0.95, 'raster-brightness-max': 0.05, 'raster-hue-rotate': 180 }; // as the CSS did: invert(0.95) hue-rotate(180deg), the colours keep their hue
const PLAIN: Record<RasterPaint, number> = { 'raster-brightness-min': 0, 'raster-brightness-max': 1, 'raster-hue-rotate': 0 };
/** Uni-Q's plans and the 2023 one are black on white paper: the dark look inverts them; ours is drawn twice */
export const inkOf = (ver: Ver, dark: boolean) => (ver !== 'kbtu' && dark ? INVERT : PLAIN);

/** the floor's tiles, inside the plan's bounds */
export function planSource(fr: Frame, ver: Ver, dark: boolean, floor: number): SourceSpecification {
  const [w, n] = lngLat(fr, 0, 0), [e, s] = lngLat(fr, 1, 1);
  return { type: 'raster', tiles: [tilesOf(ver, dark, floor)], tileSize: tileSize(devicePixelRatio || 1), minzoom: Z0, maxzoom: Z0 + LEVELS, bounds: [w, s, e, n] };
}
export const planLayer = (ink: Record<RasterPaint, number>): LayerSpecification => ({ id: 'plan', type: 'raster', source: 'plan', paint: { ...ink, 'raster-fade-duration': 300 } });

/** the labels: one layer a tier (always; from mid zoom; up close: far off the small ones were specks).
 *  Each is printed on the plan: its size (lib/mapgl.ts, in units of a 1000-wide plan) grows with the
 *  plan, and it fades in as it gets big enough to read. Uni-Q's numbers stand on a plate of the paper's colour over the
 *  tiny printed ones, and fade away as those get big enough to read (the plan 720 to 920 px wide: printed digits 5 to
 *  6.5 px tall, still under the plate), so a number is never seen twice. A value of both the zoom and a label's own
 *  data MapLibre reads at whole zooms only (between them it blends): Uni-Q's hand-over is by zoom alone */
const ZS = [-1, 0, 1, 2, 3, 4].map((n) => Z0 + n);
// a number never leaves its room's walls and never swells into a giant: the plan's own size (fitted to
// the room, lib/mapgl.ts) up to a reading size and no further; one too small to read yet waits for the pinch
// (an area's name, tier 3, is the one that grows with the plan unbounded: it spans its wing)
const px = (fr: Frame, z: number) => ['min', ['case', ['==', ['get', 'tier'], 3], 999, ['<=', ['get', 'rank'], 1], 17, 14], ['*', ['get', 's'], widthAt(fr, z) / 1000]];
// the size by two stops round every zoom the map goes to: MapLibre sizes a label between the stops round its tile's
// zoom and holds it past them, so stops a zoom apart froze labels of a tile kept from another zoom at a wrong size
export function wordSize(fr: Frame) { return ['interpolate', ['exponential', 2], ['zoom'], ZS[0], px(fr, ZS[0]), ZS[5], px(fr, ZS[5])]; }
function wordFade(fr: Frame, ver: Ver): { 'text-opacity': unknown; 'icon-opacity': unknown } {
  // gone under 6 px, whole from 8 px (blended between the stops); Uni-Q's also hand over to the printed digits
  const seen = (z: number) => ['*', ['get', 'alpha'], ['max', 0, ['min', 1, ['/', ['-', px(fr, z), 6], 2]]]];
  if (ver !== 'main') return { 'text-opacity': ['interpolate', ['linear'], ['zoom'], ...ZS.flatMap((z) => [z, seen(z)])], 'icon-opacity': 0 };
  const a = zoomFor(FRAMES.main, 720), b = zoomFor(FRAMES.main, 920), zs = [...ZS.filter((z) => z < a), a, b, ...ZS.filter((z) => z > b)];
  const by = (top: number) => ['interpolate', ['linear'], ['zoom'], ...zs.flatMap((z) => [z, z >= b ? 0 : ['*', top, seen(z)]])];
  return { 'text-opacity': by(1), 'icon-opacity': by(0.92) };
}
/** an area's name: seen whole while the plan is about the screen's size, gone once one zooms in to its rooms */
const areaFade = (fr: Frame) => ({ 'text-opacity': ['interpolate', ['linear'], ['zoom'], ...ZS.flatMap((z) => [z, widthAt(fr, z) <= 1100 ? ['get', 'alpha'] : 0])], 'icon-opacity': 0 });
export const fadeOf = (fr: Frame, ver: Ver, tier: number) => (tier === 3 ? areaFade(fr) : wordFade(fr, ver));
export const TIERS = [3, 0, 1, 2]; // an area's name under the rest, in no one's way
export function wordLayers(fr: Frame, ver: Ver): LayerSpecification[] {
  const f = FRAMES.old;
  return TIERS.map((tier) => ({
    id: `words${tier}`, type: 'symbol', source: 'words', filter: ['==', ['get', 'tier'], tier], minzoom: tier === 1 ? zoomFor(f, 700) : tier === 2 ? zoomFor(f, 1100) : 0,
    layout: {
      ...(tier === 3 ? { 'text-allow-overlap': true, 'text-ignore-placement': true } : {}),
      'text-field': ['get', 't'], 'text-font': ['Inter Variable Semibold', 'Inter Variable'], 'text-size': wordSize(fr), // the first names the weight, the second the family: the glyphs are drawn from the page's own fonts
      'text-rotate': ['get', 'turn'], 'text-anchor': ['case', ['get', 'left'], 'left', 'center'], 'text-line-height': 1.1,
      'text-letter-spacing': ['get', 'space'], 'text-max-width': 60, 'text-padding': 1, 'symbol-sort-key': ['get', 'rank'],
      'icon-image': ['case', ['get', 'plate'], 'plate', ''], 'icon-text-fit': 'both', 'icon-text-fit-padding': [1, 3, 1, 3],
    },
    paint: {
      'text-color': ['get', 'color'], 'text-halo-color': ['case', ['==', ['get', 'halo'], ''], 'rgba(0,0,0,0)', ['to-color', ['get', 'halo']]], 'text-halo-width': 1.3,
      'icon-color': ['get', 'halo'], ...fadeOf(fr, ver, tier),
    },
  }) as unknown as LayerSpecification);
}

/** my flaws' pins win over the labels: each holds its place among them as an empty mark, so a label
 *  under a pin gives way */
export const pinData = (fr: Frame, pts: { u: number; v: number }[]) => ({ type: 'FeatureCollection' as const, features: pts
  .map(({ u, v }) => ({ type: 'Feature' as const, properties: {}, geometry: { type: 'Point' as const, coordinates: lngLat(fr, u, v) } })) });
export const pinLayer = { id: 'pins', type: 'symbol', source: 'pins', layout: { 'icon-image': 'pin', 'icon-allow-overlap': true } } as LayerSpecification;

/** what the map should show now; `wk` keys the labels' data, `sc` the 2023 plan's floor laid over (0: none) */
export type Want = { ver: Ver; cur: number; dark: boolean; fr: Frame; wk: string; sc: number; words: () => Parameters<GeoJSONSource['setData']>[0] };

/** the state the map was last given; whatever changed since (the floor, the version, the look, the language, the
 *  original) is given again: the source anew for other tiles, paint for the look, the labels' data */
export function styleSync(map: () => GLMap, gone: () => boolean) {
  let planKey = '', inkKey = '', wordsKey = '', fadeVer = '', scanOn = 0, scanT = 0;
  const keys = (w: Pick<Want, 'ver' | 'cur' | 'dark'>) => [`${w.ver}|${w.cur}|${w.ver === 'kbtu' && w.dark}`, `${w.ver}|${w.dark}`];
  /** the map was just made from this state */
  function seed(w: Pick<Want, 'ver' | 'cur' | 'dark' | 'wk'>) { [planKey, inkKey] = keys(w); wordsKey = w.wk; fadeVer = w.ver; }
  function sync(w: Want) {
    const m = map(), { ver, cur, dark, fr, wk, sc } = w, [pk, ik] = keys(w), ink = inkOf(ver, dark);
    const inked = (layer: string) => { for (const [k, v] of Object.entries(ink)) m.setPaintProperty(layer, k as RasterPaint, v); };
    const corner = (u: number, v: number) => lngLat(fr, u, v);
    if (pk !== planKey) { planKey = pk; inkKey = ik; m.removeLayer('plan'); m.removeSource('plan'); m.addSource('plan', planSource(fr, ver, dark, cur)); m.addLayer(planLayer(ink), m.getLayer('scan') ? 'scan' : 'words3'); }
    else if (ik !== inkKey) { inkKey = ik; inked('plan'); }
    if (ver !== fadeVer) { fadeVer = ver; for (const tier of TIERS) { for (const [k, v] of Object.entries(fadeOf(fr, ver, tier))) m.setPaintProperty(`words${tier}`, k as 'text-opacity', v as number); m.setLayoutProperty(`words${tier}`, 'text-size', wordSize(fr) as unknown as number); } }
    if (wk !== wordsKey) { wordsKey = wk; (m.getSource('words') as GeoJSONSource).setData(w.words()); }
    if (sc !== scanOn) {
      clearTimeout(scanT);
      const [l, tp, r, bt] = SCAN_AT[sc || scanOn];
      const at = { url: scan(sc || scanOn), coordinates: [corner(l, tp), corner(r, tp), corner(r, bt), corner(l, bt)] as [[number, number], [number, number], [number, number], [number, number]] };
      const src = m.getSource('scan') as ImageSource | undefined;
      if (!sc) { m.setPaintProperty('scan', 'raster-opacity', 0); scanT = window.setTimeout(() => { m.removeLayer('scan'); m.removeSource('scan'); }, 350); } // fades out, then goes
      else if (src) { src.updateImage(at); m.setPaintProperty('scan', 'raster-opacity', 1); }
      else {
        m.addSource('scan', { type: 'image', ...at });
        m.addLayer({ id: 'scan', type: 'raster', source: 'scan', paint: { ...ink, 'raster-opacity': 0, 'raster-opacity-transition': { duration: 300, delay: 0 }, 'raster-fade-duration': 0 } }, 'words3');
        requestAnimationFrame(() => { if (!gone() && m.getLayer('scan') && scanOn) m.setPaintProperty('scan', 'raster-opacity', 1); });
      }
      scanOn = sc;
    }
    if (m.getLayer('scan')) inked('scan');
  }
  return { seed, sync, stop: () => clearTimeout(scanT) };
}
