<script lang="ts" module>
  import { setWorkerUrl, prewarm } from 'maplibre-gl';
  // MapLibre's worker as a file of ours (it looks for one next to itself, which a bundle doesn't have); through the
  // build, so its syntax is lowered for old iOS like the rest
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
  import { overview as sheet, tilesOf as tilesAt, Z0 as SHEET_Z } from '../../lib/mapgl';
  setWorkerUrl(workerUrl);
  const warmed: HTMLImageElement[] = [];
  /** Ahead of the first tap (lib/map.ts warmMap, in an idle moment after the app starts; owner, Nov 15: the first tap
   *  opens the map at once): MapLibre's workers started, the floor the map opens on by default decoded as its overview,
   *  its first tiles in the browser's cache. This chunk itself is loaded by whoever calls this */
  export function warm(): void {
    if (warmed.length) return;
    prewarm();
    const im = new Image(); im.src = sheet('main', false, 1); void im.decode().catch(() => {}); warmed.push(im);
    const at = 2 ** SHEET_Z;
    for (const x of [at, at + 1]) for (const y of [at, at + 1]) fetch(tilesAt('main', false, 1).replace('{z}', String(SHEET_Z + 1)).replace('{x}_{y}', `${x}_${y}`)).catch(() => {});
  }
</script>

<script lang="ts">
  // The campus map (CONTEXT): a floor of the main building full screen, pinch to zoom and drag to look around, a
  // double tap zooms in or out, the floors 0–5 at the bottom under the thumb. Three versions, picked from a list at the top left
  // (owner, Oct 6 and Oct 27): ours, KBTU App's, the main one, Uni-Q's plans (credited under the map), and the old one, our redraw of
  // the 2023 plans (floors 1-5, which nobody updates, so it says so; every wall one ink, and a switch lays the plan as it was given over it: owner, Nov 15). Opens on a room's floor ("Aud. 305"
  // → 3), rings the room's number and glides in to it (owner, Oct 5: "show where the room is"); a room the plan
  // doesn't number frames its nearest numbers on the floor, "somewhere here, look yourself", or just says it couldn't
  // find it (the old plan won't have it either: owner, Oct 6).
  // MapLibre GL moves and draws it (owner, Nov 15: a ready, fast library, not our own pan and zoom): each plan is a
  // pyramid of tiles (lib/mapgl.ts), the level the size on screen needs fading in over the coarser one, and the room
  // numbers are its labels, at a size one can read at any zoom, as many as fit without touching, halls and bigger rooms
  // first, fading in and out (owner, Nov 15: "zoomed out the map is empty"). Opened on a room, the whole floor shows
  // first, then it flies in (owner, Oct 12: "show the whole map first, then zoom"). The main plans are black on white: the dark look inverts them (the
  // colours keep their hue). The capsule says "Map · floor 3", or "Room 305 · floor 3" (SPEC §8.2). The magnifier at the top
  // turns the whole top row into a search box (owner, Oct 12: one row, not a big box), which finds a room by its number or a hall by its name (roomOf), goes to its floor and glides to it (owner, Oct 12).
  // The sun/moon at the top right turns the map light or dark (owner, Oct 5: "let the student pick right on the map"),
  // the map only and for this look: the app keeps its own theme, and the map opens in it again next time (owner: "I
  // turn white on, look at it, and that's it; the app stays dark"). The panel carries the theme as a class (tokens.css).
  import { onMount, tick, untrack } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import Check from '@lucide/svelte/icons/check';
  import Search from '@lucide/svelte/icons/search';
  import Sun from '@lucide/svelte/icons/sun';
  import Moon from '@lucide/svelte/icons/moon';
  import { theme, reveal, paintFor, type Theme } from '../../lib/state/theme.svelte';
  import MapIcon from '@lucide/svelte/icons/map';
  import Layers from '@lucide/svelte/icons/layers';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { haptic, inTelegram } from '../../lib/tg';
  import { SPOTS, roomOf, floorOf, nearRooms, spotOf } from '../../lib/map';
  import { FRAMES, HAS, Z0, LEVELS, lngLat, uvOf, zoomFor, widthAt, tilesOf, overview, scan, SCAN_AT, tileSize, roomAt, labelsOf, labelData, type Ver } from '../../lib/mapgl';
  import { Map as GLMap, LngLat, type MapMouseEvent, type StyleSpecification, type SourceSpecification, type LayerSpecification, type GeoJSONSource, type ImageSource } from 'maplibre-gl';
  import 'maplibre-gl/dist/maplibre-gl.css';
  import uniq from '../../assets/map/uniq-tiles.json';
  import uniqRooms from '../../assets/map/uniq-rooms.json';
  import { glass, jelly } from '../../ui/glass';
  import RouteIcon from '@lucide/svelte/icons/route';
  import MapPad, { placeGroups, exitTiles, doorHint, adminNote, type PadCheck } from './MapPad.svelte';
  import DoorOpen from '@lucide/svelte/icons/door-open';
  import RouteUI, { type RouteView } from './RouteUI.svelte';
  import { api } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { mapFrom, copyCap, type CapCopy } from '../../lib/state/sheets';
  import { roomNow, type RoomWeek } from '../../lib/rooms';
  import { nowTs } from '../../lib/time';

  let { overlay, place, exit = false }: { overlay: Overlay; place?: string; exit?: boolean } = $props();
  const ROOMS = uniqRooms as unknown as Record<string, number[][]>[]; // by floor: room → where its number is printed
  let room = $state(untrack(() => roomOf(place)));
  let cur = $state(untrack(() => floorOf(place) ?? 1)); // the floor it opens on; the switcher takes over from there
  const roomFloor = $derived(floorOf(room)); // 0: the basement's 1-99
  const onRoomFloor = $derived(!!room && cur === roomFloor);
  const title = $derived(cur === 0 ? t('map.basement') : t('map.title', { n: cur }));
  // on the way: where from and where to, in the header (owner, Oct 15)
  $effect(() => { overlay.title = rt.route && rt.ends ? `${rt.ends[0]} → ${rt.ends[1]}` : onRoomFloor ? (cur ? t('map.room', { room: room!, n: cur }) : t('map.roomBasement', { room: room! })) : title; overlay.icon = MapIcon; });
  let own = $state<Theme | null>(null); // the map's theme while it is open; null: the app's
  const look = $derived(own ?? theme.current);
  $effect(() => { overlay.theme = own ?? undefined; }); // the capsule above the map goes along
  // which map (owner, Oct 27: a list at the top left): Uni-Q's, ours (floors 1 and 2 so far, not the default yet), the 2023 plan
  const VERS: Ver[] = ['kbtu', 'main', 'old']; // ours first in the list (owner, Oct 28); Uni-Q stays the default for now
  let ver = $state<Ver>('main');
  let menu = $state(false);
  let rt = $state<RouteView>({ graph: null, route: null, step: 0 });
  let routing = $state(false);
  let leaving = $state(untrack(() => exit)); // opened by the "help me get out" link: everyone gets that one (owner, Oct 15)
  async function openRoute() {
    haptic.tap();
    if (ver !== 'main') setVer('main');
    if (!rt.graph) rt.graph = await api.mapGraph().catch(() => null);
    if (!rt.graph) { say(t('route.noGraph'), 'pleading_face_3d'); return; }
    routing = true;
  }
  if (untrack(() => exit)) void openRoute();
  /** show a step: its floor, framed */
  async function go(f: number, pts: { u: number; v: number }[]) {
    if (f !== cur) { halt(); cur = f; touched++; }
    framed = pts.map((p) => [p.u, p.v]);
    await tick(); // the step's card, not the tall one it replaces (owner, Oct 15: the first step was framed far off)
    reframe();
  }
  // the step on screen: framed again whenever the stage changes size (the keyboard going away after "Lead me out" grows
  // it: owner, Oct 15, the way sat small at the top) until a finger moves the map
  let framed: number[][] | null = null, reframeT = 0;
  function reframe() { if (!framed || !rt.route) return; glided = false; clearTimeout(glideT); frame(framed); }
  const legsHere = $derived(rt.route ? rt.route.legs.map((l, i) => ({ ...l, i })).filter((l) => l.f === cur) : []);
  const routeFloors = $derived(new Set(rt.route?.legs.map((l) => l.f) ?? []));
  const line = (pts: { u: number; v: number }[]) => pts.map((p) => `${p.u * 1000},${p.v * 1000 * AR}`).join(' ');
  const AR = $derived(FRAMES[ver].ar); // the plan's height to its width
  let panel: HTMLDivElement;
  let stage: HTMLDivElement;
  let gl: HTMLDivElement;
  let first: HTMLDivElement;
  let plan: HTMLDivElement;
  let gone = false;

  // The camera is MapLibre's (owner, Nov 15: our own pan and zoom "perceived gestures badly"): it draws the floor's tiles
  // of the level the size on screen needs, a finer level fading in over the coarser one, and the labels, which fade in
  // and out as they find room. Here the plan's scale is 1 when it is as wide as the stage, up to MAX; a place on it is
  // (u, v), fractions of its width and height (lib/mapgl.ts turns those into MapLibre's own).
  let map: GLMap;
  let ready = $state(false);
  const fr = $derived(FRAMES[ver]);
  const MAX = 8;
  const W = () => stage.clientWidth, H = () => stage.clientHeight;
  const scale = () => widthAt(fr, map.getZoom()) / W();
  /** the camera that shows the plan at scale k with its (u, v) at the stage's (sx, sy) */
  function cam(k: number, u: number, v: number, sx = W() / 2, sy = H() / 2) {
    const pw = W() * k;
    return { center: lngLat(fr, u + (W() / 2 - sx) / pw, v + (H() / 2 - sy) / (pw * AR)), zoom: zoomFor(fr, pw) };
  }
  /** the plan's point under a point of the stage */
  function uvAt(px: number, py: number): [number, number] { const at = map.unproject([px, py]); return uvOf(fr, at.lng, at.lat); }
  /** the screen's middle stays on the plan, so half a screen of room past each edge: a corner, or a route under the
   *  card, can be dragged to the middle (owner, Oct 15); never smaller than the stage's width, never past MAX */
  function within(at: LngLat, zoom: number) {
    const [u, v] = uvOf(fr, at.lng, at.lat), on = (n: number) => Math.min(1, Math.max(0, n));
    return { center: new LngLat(...lngLat(fr, on(u), on(v))), zoom: Math.min(zoomFor(fr, W() * MAX), Math.max(zoomFor(fr, W()), zoom)) };
  }
  /** what stands on the plan follows the camera: the overlay as wide as the plan is on screen (its pins keep their
   *  size), the overview under the canvas by a transform alone */
  function follow() {
    const p = map.project(lngLat(fr, 0, 0)), pw = widthAt(fr, map.getZoom());
    plan.style.width = `${pw}px`; plan.style.transform = `translate3d(${p.x}px,${p.y}px,0)`;
    first.style.transform = `translate3d(${p.x}px,${p.y}px,0) scale(${pw / fr.fx / 512})`;
  }
  // the stage runs under Telegram's header (full-bleed, owner Nov 4); the plan rests below it, where .side starts
  let side: HTMLDivElement;
  const head = () => side.offsetTop - 10;
  /** the view a floor opens in: on the main map the building (u .12-.85 of Uni-Q's sheet, white margins round it) fills
   *  the width (owner, Oct 24: "why is it so far away"); the drawn plans have no margins, the whole of them */
  const homeK = () => (ver === 'main' ? 1.3 : 1);
  /** the building in the middle of what's under the header, at scale k: where the plan rests zoomed out */
  const middle = (k = homeK()) => cam(k, ver === 'main' ? 0.485 : 0.5, 0.5, W() / 2, head() + (H() - head()) / 2);
  /** zoomed out: the whole floor, where one finger turns floors and never pans (owner, Nov 15: the swipe "doesn't
   *  understand what I want"); a hair of zoom left by a pinch still counts, and the let-go takes it back (rest) */
  const NEAR = 1.15;
  const out = () => scale() < homeK() * NEAR;
  function reset() { halt(); map.jumpTo(middle()); }
  /** a running glide stops where it is on screen (a finger, a floor, the other version came) */
  const halt = () => map.stop();
  // off at once, settles without a crawl: a critically damped spring (owner, Oct 12: an easy ease was "very slow", the
  // spring "was good"; Oct 9: an ease-out one crawled at the end)
  const spring = (p: number) => (p >= 1 ? 1 : 1 - (1 + 10 * p) * Math.exp(-10 * p));
  /** fingers let the plan go: zoomed out it may rest only in the middle and goes back there, at the size they left it
   *  under the whole floor's, or at the whole floor's from a hair over it; zoomed in it stays where it was left (owner, Oct 15) */
  function rest() {
    if (fingers || !out()) return;
    const to = middle(Math.min(scale(), homeK())), a = map.project(to.center), b = map.project(map.getCenter());
    if (Math.hypot(a.x - b.x, a.y - b.y) > 0.5 || Math.abs(to.zoom - map.getZoom()) > 0.005) easeFit(to, 380);
  }
  /** a glide to the whole floor: a finger in the middle of it lands it at once (it was halfway, neither out nor in) */
  let fitting = false;
  function easeFit(to: { center: LngLat | [number, number]; zoom: number }, duration: number) {
    fitting = true; map.once('moveend', () => (fitting = false));
    map.easeTo({ ...to, duration, easing: spring });
  }

  // ---- what MapLibre draws: the floor's tiles, the 2023 plan's original over its redraw when asked, the labels ----
  type RasterPaint = 'raster-brightness-min' | 'raster-brightness-max' | 'raster-hue-rotate';
  const INVERT: Record<RasterPaint, number> = { 'raster-brightness-min': 0.95, 'raster-brightness-max': 0.05, 'raster-hue-rotate': 180 }; // as the CSS did: invert(0.95) hue-rotate(180deg), the colours keep their hue
  const PLAIN: Record<RasterPaint, number> = { 'raster-brightness-min': 0, 'raster-brightness-max': 1, 'raster-hue-rotate': 0 };
  /** Uni-Q's plans and the 2023 one are black on white paper: the dark look inverts them; ours is drawn twice */
  const ink = () => (ver !== 'kbtu' && look === 'dark' ? INVERT : PLAIN);
  const inked = (layer: string) => { for (const [k, v] of Object.entries(ink())) map.setPaintProperty(layer, k as RasterPaint, v); };
  const corner = (u: number, v: number) => lngLat(fr, u, v);
  function planSource(): SourceSpecification {
    const [w, n] = corner(0, 0), [e, s] = corner(1, 1);
    return { type: 'raster', tiles: [tilesOf(ver, look === 'dark', cur)], tileSize: tileSize(devicePixelRatio || 1), minzoom: Z0, maxzoom: Z0 + LEVELS, bounds: [w, s, e, n] };
  }
  const planLayer = (): LayerSpecification => ({ id: 'plan', type: 'raster', source: 'plan', paint: { ...ink(), 'raster-fade-duration': 300 } });
  let orig = $state(false); // the 2023 plan as it was given, over our redraw
  // the room looked for is the first to get its place among the labels: its ring is never round nothing
  const words = () => labelData(fr, orig && ver === 'old' ? [] : labelsOf(ver, cur, look === 'dark', (k) => t(`kmap.${k}` as 'kmap.canteen'), room ?? ''));
  const wordsNow = () => `${ver}|${cur}|${look}|${i18n.lang}|${orig}|${room}`;
  /** the labels: one layer a tier (always; from mid zoom; up close: owner, Oct 28, far off the small ones were specks).
   *  Each is printed on the plan (owner, Nov 15): its size (lib/mapgl.ts, in units of a 1000-wide plan) grows with the
   *  plan, and it fades in as it gets big enough to read. Uni-Q's numbers stand on a plate of the paper's colour over the
   *  tiny printed ones, and fade away as those get big enough to read (the plan 720 to 920 px wide: printed digits 5 to
   *  6.5 px tall, still under the plate), so a number is never seen twice. A value of both the zoom and a label's own
   *  data MapLibre reads at whole zooms only (between them it blends): Uni-Q's hand-over is by zoom alone */
  const ZS = [-1, 0, 1, 2, 3, 4].map((n) => Z0 + n);
  // owner, Nov 17: a number never leaves its room's walls and never swells into a giant: the plan's own size (fitted to
  // the room, lib/mapgl.ts) up to a reading size and no further; one too small to read yet waits for the pinch
  const px = (z: number) => ['min', ['case', ['<=', ['get', 'rank'], 1], 17, 14], ['*', ['get', 's'], widthAt(fr, z) / 1000]];
  // the size by two stops round every zoom the map goes to: MapLibre sizes a label between the stops round its tile's
  // zoom and holds it past them, so stops a zoom apart froze labels of a tile kept from another zoom at a wrong size
  function wordSize() { return ['interpolate', ['exponential', 2], ['zoom'], ZS[0], px(ZS[0]), ZS[5], px(ZS[5])]; }
  function wordFade(): { 'text-opacity': unknown; 'icon-opacity': unknown } {
    // gone under 6 px, whole from 8 px (blended between the stops); Uni-Q's also hand over to the printed digits
    const seen = (z: number) => ['*', ['get', 'alpha'], ['max', 0, ['min', 1, ['/', ['-', px(z), 6], 2]]]];
    if (ver !== 'main') return { 'text-opacity': ['interpolate', ['linear'], ['zoom'], ...ZS.flatMap((z) => [z, seen(z)])], 'icon-opacity': 0 };
    const a = zoomFor(FRAMES.main, 720), b = zoomFor(FRAMES.main, 920), zs = [...ZS.filter((z) => z < a), a, b, ...ZS.filter((z) => z > b)];
    const by = (top: number) => ['interpolate', ['linear'], ['zoom'], ...zs.flatMap((z) => [z, z >= b ? 0 : ['*', top, seen(z)]])];
    return { 'text-opacity': by(1), 'icon-opacity': by(0.92) };
  }
  function wordLayers(): LayerSpecification[] {
    const f = FRAMES.old;
    return [0, 1, 2].map((tier) => ({
      id: `words${tier}`, type: 'symbol', source: 'words', filter: ['==', ['get', 'tier'], tier], minzoom: tier ? zoomFor(f, tier === 1 ? 700 : 1100) : 0,
      layout: {
        'text-field': ['get', 't'], 'text-font': ['Inter Variable Semibold', 'Inter Variable'], 'text-size': wordSize(), // the first names the weight, the second the family: the glyphs are drawn from the page's own fonts
        'text-rotate': ['get', 'turn'], 'text-anchor': ['case', ['get', 'left'], 'left', 'center'], 'text-line-height': 1.1,
        'text-letter-spacing': ['get', 'space'], 'text-max-width': 60, 'text-padding': 1, 'symbol-sort-key': ['get', 'rank'],
        'icon-image': ['case', ['get', 'plate'], 'plate', ''], 'icon-text-fit': 'both', 'icon-text-fit-padding': [1, 3, 1, 3],
      },
      paint: {
        'text-color': ['get', 'color'], 'text-halo-color': ['case', ['==', ['get', 'halo'], ''], 'rgba(0,0,0,0)', ['to-color', ['get', 'halo']]], 'text-halo-width': 1.3,
        'icon-color': ['get', 'halo'], ...wordFade(),
      },
    }) as unknown as LayerSpecification);
  }
  /** my flaws' pins win over the labels (owner, Nov 15): each holds its place among them as an empty mark, so a label
   *  under a pin gives way */
  const pinData = () => ({ type: 'FeatureCollection' as const, features: [...flawsHere, ...(draft && draft.f === cur && draft.ver === ver ? [draft] : [])]
    .map(({ u, v }) => ({ type: 'Feature' as const, properties: {}, geometry: { type: 'Point' as const, coordinates: lngLat(fr, u, v) } })) });
  const pinLayer = { id: 'pins', type: 'symbol', source: 'pins', layout: { 'icon-image': 'pin', 'icon-allow-overlap': true } } as LayerSpecification;
  $effect(() => { const d = pinData(); if (ready) untrack(() => (map.getSource('pins') as GeoJSONSource).setData(d)); });
  // the state the map was last given; whatever changed since (the floor, the version, the look, the language, the
  // original) is given again: the source anew for other tiles, paint for the look, the labels' data
  let planKey = '', inkKey = '', wordsKey = '', fadeVer = '', scanOn = 0, scanT = 0;
  $effect(() => {
    if (!ready) return;
    const dark = look === 'dark', pk = `${ver}|${cur}|${ver === 'kbtu' && dark}`, ik = `${ver}|${dark}`, wk = wordsNow(), sc = ver === 'old' && orig ? cur : 0;
    untrack(() => {
      if (pk !== planKey) { planKey = pk; inkKey = ik; map.removeLayer('plan'); map.removeSource('plan'); map.addSource('plan', planSource()); map.addLayer(planLayer(), map.getLayer('scan') ? 'scan' : 'words0'); }
      else if (ik !== inkKey) { inkKey = ik; inked('plan'); }
      if (ver !== fadeVer) { fadeVer = ver; for (const tier of [0, 1, 2]) { for (const [k, v] of Object.entries(wordFade())) map.setPaintProperty(`words${tier}`, k as 'text-opacity', v as number); map.setLayoutProperty(`words${tier}`, 'text-size', wordSize() as unknown as number); } }
      if (wk !== wordsKey) { wordsKey = wk; (map.getSource('words') as GeoJSONSource).setData(words()); }
      if (sc !== scanOn) {
        clearTimeout(scanT);
        const [l, tp, r, bt] = SCAN_AT[sc || scanOn];
        const at = { url: scan(sc || scanOn), coordinates: [corner(l, tp), corner(r, tp), corner(r, bt), corner(l, bt)] as [[number, number], [number, number], [number, number], [number, number]] };
        const src = map.getSource('scan') as ImageSource | undefined;
        if (!sc) { map.setPaintProperty('scan', 'raster-opacity', 0); scanT = window.setTimeout(() => { map.removeLayer('scan'); map.removeSource('scan'); }, 350); } // fades out, then goes
        else if (src) { src.updateImage(at); map.setPaintProperty('scan', 'raster-opacity', 1); }
        else {
          map.addSource('scan', { type: 'image', ...at });
          map.addLayer({ id: 'scan', type: 'raster', source: 'scan', paint: { ...ink(), 'raster-opacity': 0, 'raster-opacity-transition': { duration: 300, delay: 0 }, 'raster-fade-duration': 0 } }, 'words0');
          requestAnimationFrame(() => { if (!gone && map.getLayer('scan') && scanOn) map.setPaintProperty('scan', 'raster-opacity', 1); });
        }
        scanOn = sc;
      }
      if (map.getLayer('scan')) inked('scan');
      follow();
    });
  });
  // ---- fingers: MapLibre drags, pinches around the fingers' middle and takes the wheel. Ours on top of it: a hold in
  // place, the taps, and the floor swipe while zoomed out ----
  let fingers = 0, held = false;
  let lastTap = 0, tapAt = { x: 0, y: 0 };
  const local = (e: PointerEvent) => { const r = stage.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  let press: { x: number; y: number } | null = null; // the first finger down, for a hold in place
  // a long press in place: "something's wrong here" (owner, Oct 29: the map's flaws marked in the app, not by screenshots),
  // a line of text, the spot to the admin's list with its floor and the plan's units
  let holdT: ReturnType<typeof setTimeout> | undefined;
  // where it was marked (Nov 7: the spot was saved, but nothing showed where): a pin at the pressed point while the note
  // is written, a check on it once saved, and my own open ones on the floor as small pins; a tap on one shows its words.
  // Only mine, never anyone else's (the admin's list has all of them)
  type Flaw = { id: number; ver: string; floor: number; u: number; v: number; px: number | null; py: number | null; body: string };
  let mine = $state<Flaw[]>([]);
  let draft = $state<{ ver: Ver; f: number; u: number; v: number } | null>(null);
  let okId = $state(0), seen = $state(0), okT = 0;
  const canFlaw = () => !!session.me?.student && session.board; // where the policy's section 12 is in force (BOARD), for everyone it covers
  $effect(() => { if (canFlaw()) api.mapFlawsMine().then((l) => (mine = l), () => {}); });
  // "free now" by the timetable (lib/rooms): fetched as the map opens, nothing of it shows until it comes or if the
  // server has no timetable (404); the rooms the main map numbers, tinted where their number is printed
  let week = $state<Record<string, RoomWeek> | null>(null), freeOn = $state(false), clock = $state(nowTs());
  // Office-hour rooms and rooms 310-318 stay on the map but must not be advertised as free.
  const noFreeHighlight = new Set([
    '0', '5', '9', '15', '45', '47', '58', '69', '77', '87', '102', '112',
    '120', '140', '178', '179', '180', '181', '184', '215', '216a', '216b', '217', '218',
    '219', '220', '228', '249', '251', '251a', '251b', '257', '268', '270', '271', '272',
    '274', '275', '277', '278', '279', '281', '283', '284', '310', '311', '312', '313',
    '314', '315', '316', '317', '318', '319', '321', '324', '325', '327', '328', '331',
    '335', '336', '337', '345', '346', '348', '349', '355', '356', '357', '359', '365',
    '372', '376', '377', '381a', '381b', '383', '384', '385', '386', '388', '389', '400a',
    '403', '406', '409', '410', '410a', '411', '419', '420', '422', '427', '432', '433',
    '436', '447', '454', '456', '458', '459', '473', '509', '513',
  ]);
  api.mapRooms().then((r) => (week = r.rooms), () => {});
  const freeHere = $derived(!week || !freeOn || ver !== 'main' ? [] : Object.entries(ROOMS[cur] ?? {}).flatMap(([r, ps]) => {
    if (!week![r]) return [];
    const free = roomNow(week![r], clock).free;
    return free && noFreeHighlight.has(r) ? [] : ps.map(([u, v]) => ({ r, u, v, free }));
  }));
  const roomLine = $derived.by(() => {
    const w = room && week?.[room];
    if (!w) return '';
    const n = roomNow(w, clock), time = `${String(n.until).padStart(2, '0')}:00`;
    if (n.free && noFreeHighlight.has(room as string)) return ''; // an office: its card doesn't say "free" either
    return (n.free ? (n.until == null ? t('map.freeEvening') : t('map.freeUntil', { time })) : t('map.busyUntil', { time })) + ' \u00b7 ' + t('map.byTimetable');
  });
  function toggleFree() { haptic.select(); freeOn = !freeOn; clock = nowTs(); if (freeOn) say(t('map.freeHint'), 'sparkles_3d'); }
  /** mine on this floor of this map: its own spot, or on another map through the 2023 plan's units */
  const flawsHere = $derived(mine.flatMap((m) => {
    if (m.floor !== cur) return [];
    const [u, v] = m.ver === ver ? [m.u, m.v] : m.px != null && m.py != null ? fromPlan(ver, m.px, m.py) : [-1, -1];
    return u >= 0 && u <= 1 && v >= 0 && v <= 1 ? [{ id: m.id, u, v, body: m.body }] : [];
  }));
  function flaw(at: { x: number; y: number }): boolean {
    const [u, v] = uvAt(at.x, at.y);
    if (u < 0 || u > 1 || v < 0 || v > 1 || !canFlaw()) return false;
    haptic.soft(); held = true; press = null; lastTap = 0; seen = 0;
    const [px, py] = toPlan(ver, u, v), f = cur, vr = ver;
    draft = { ver: vr, f, u, v };
    // zoomed in, a spot low on the screen comes up above the sheet the note is written in
    if (!out() && at.y > H() * 0.4) map.panBy([0, at.y - H() * 0.3], { duration: 420 });
    void sheets.askText({ title: t('map.flawTitle'), text: t('map.flawText', { floor: f }), ok: t('map.flawSend'), cancel: t('common.cancel'), placeholder: t('map.flawPh'), max: 300 })
      .then((body) => body ? api.mapFlaw({ ver: vr, floor: f, u, v, px, py, body }).then(() => {
        haptic.ok(); say(t('map.flawThanks'), 'sparkles_3d');
        const id = -Date.now(); // the server answers 204: mine until the next visit lists it with its own id
        mine = [...mine, { id, ver: vr, floor: f, u, v, px, py, body }];
        okId = id; clearTimeout(okT); okT = window.setTimeout(() => (okId = 0), 1400);
      }) : undefined)
      .catch(() => say(t('common.error'), 'warning_3d'))
      .finally(() => (draft = null));
    return true;
  }
  function down(e: PointerEvent) {
    menu = false; clearTimeout(glideT); touched++; framed = null; // a finger first: the glide gives way
    if (fitting && e.isPrimary) { fitting = false; map.jumpTo(middle(Math.min(scale(), homeK()))); } else halt();
    clearTimeout(holdT); held = false;
    // the first finger of a new touch: any finger still counted is stale (iOS sends no up for one held while the flaw's
    // sheet opened over it, so every later press read as a second finger and never held: owner, Nov 15)
    fingers = e.isPrimary ? 1 : fingers + 1;
    if (!e.isPrimary) { press = null; swipeEnd(true); map.dragPan.enable(); return; } // a second finger: a pinch, never a hold or a floor
    const at = (press = local(e)), id = e.pointerId;
    if (rt.route) return;
    // held: the finger is the stage's from here on, and the click its let-go may bring is swallowed, so neither lands
    // on the note's sheet that has just opened under the finger and shuts it
    holdT = setTimeout(() => {
      if (!flaw(at)) return;
      try { stage.setPointerCapture(id); } catch { /* the finger is gone */ }
      window.addEventListener('click', eat, { capture: true, once: true });
    }, 600);
    // zoomed out one finger is ours alone: MapLibre doesn't pan (the plan would only spring back), a sideways move turns
    // the floor; a second finger gives the map back its pinch and pan
    if (out()) { map.dragPan.disable(); swipeStart(e.clientX, e.clientY); }
  }
  function move(e: PointerEvent) {
    if (!e.isPrimary || !press) return;
    const p = local(e);
    if (Math.hypot(p.x - press.x, p.y - press.y) > 8) clearTimeout(holdT); // it moved: not a hold
    if (swipeMove(e.clientX, e.clientY)) lastTap = 0;
  }
  const eat = (e: Event) => { e.stopPropagation(); e.preventDefault(); };
  function up(e: PointerEvent) {
    clearTimeout(holdT);
    if (held) setTimeout(() => window.removeEventListener('click', eat, true), 350); // no click came: the next one is a real one
    fingers = Math.max(0, fingers - 1);
    if (e.isPrimary) { press = null; swipeEnd(); map.dragPan.enable(); }
  }
  /** a tap (MapLibre's click: a finger that didn't move): my own pin shows what I wrote there, a tinted room opens its
   *  card, a second tap within 300 ms of the first and near it zooms in, or back out to the whole floor */
  function tap(e: MapMouseEvent) {
    if (held) { held = false; return; } // the let-go of a hold
    const el = e.originalEvent.target as Element, p = e.point, now = performance.now();
    const pin = Number(el.closest<HTMLElement>('[data-flaw]')?.dataset.flaw ?? 0), tinted = el.closest<HTMLElement>('[data-room]')?.dataset.room ?? '';
    if (pin || seen) { if (pin) haptic.tap(); seen = pin && pin !== seen ? pin : 0; }
    if (pin) return;
    // a tap on a tinted room: its card, with when it is free (no glide: it is on screen already)
    if (tinted) { haptic.tap(); at = null; room = tinted; glided = true; lastTap = 0; return; }
    if (lastTap && now - lastTap < 300 && Math.hypot(p.x - tapAt.x, p.y - tapAt.y) < 40) {
      haptic.tap(); lastTap = 0;
      if (scale() > 1.5) fit();
      else map.easeTo({ zoom: map.getZoom() + Math.log2(2.5), around: map.unproject(p), duration: 380, easing: spring });
    } else { lastTap = now; tapAt = p; }
  }
  /** the circle grows from the switch, as the app's does; Telegram's bars follow once it has covered the screen */
  function flip(from: Element) {
    haptic.select();
    const next = look === 'dark' ? 'light' : 'dark';
    reveal(() => (own = next), () => { if (!gone) paintFor(next); }, from);
  }

  // another floor keeps the view: the floors share one frame, so the same part of the building stays on screen and
  // only the tiles change (owner, Oct 6: "switching floors resets the map's size")
  // ---- floors (PLAN 97; owner's iPhone videos IMG_6661/6663, Oct 25): a tap on the rail, a drag along it, or a sideways
  // swipe on the map while it's zoomed out. The owner's model is the route card's floor row: the plan changes floor in
  // place, the same frame (no sliding pictures: "disgusting"), and the knob springs over with the jelly squash. The knob
  // follows the finger while it drags (on the map: a page turn, the finger to the left goes a floor up); the floor
  // changes on the let-go.
  let knob = $state<HTMLSpanElement>();
  let kp = $state(0), dragging = $state(false);
  let sw: { x0: number; y0: number; dx: number; on: boolean; hist: [number, number][]; rail: boolean; k0: number } | null = null;
  const idxOf = (n: number) => railFloors.indexOf(n);
  // the knob goes wherever the floor comes from (a tap, a search, a route step, the old plan's narrower rail)
  $effect(() => { const i = idxOf(cur); if (!untrack(() => dragging)) { kp = i; jelly(untrack(() => knob)); } });
  // the change itself (owner, Oct 25: "the picture just swaps, give it a push so you feel the floor changed"): a lift's
  // depth. Going up, the floor you leave sinks away under you and the new one comes down from above, settling to size;
  // going down, the other way. Both pictures scale about the middle of the screen; opacity and transform only.
  let ghost = $state<string | null>(null), ghostEl = $state<HTMLImageElement>();
  async function goTo(n: number) {
    if (n === cur) return;
    haptic.select(); halt();
    const up = Math.sign(idxOf(n) - idxOf(cur));
    ghost = overview(ver, look === 'dark', cur); // the floor being left, as its overview
    cur = n; touched++;
    await tick();
    if (!ghostEl) return;
    const m = new DOMMatrix(getComputedStyle(first).transform), o = `${(W() / 2 - m.e) / m.a}px ${(H() / 2 - m.f) / m.a}px`;
    const fresh = first.querySelector<HTMLImageElement>('img:not(.ghost)');
    const ease = { duration: 480, easing: 'cubic-bezier(.3, .75, .25, 1)' }, come = { transform: [`scale(${up > 0 ? 1.08 : 0.93})`, 'scale(1)'], opacity: [0, 1] };
    const el = ghostEl, src = ghost;
    el.style.transformOrigin = o;
    el.animate({ transform: ['scale(1)', `scale(${up > 0 ? 0.9 : 1.1})`], opacity: [1, 0.5, 0] }, { ...ease, fill: 'forwards' }).finished.catch(() => {}).finally(() => { if (ghost === src) ghost = null; });
    if (fresh) { fresh.style.transformOrigin = o; fresh.animate(come, ease); }
    map.getCanvas().animate(come, ease); // the new floor's tiles and labels come with its overview, about the screen's middle
  }
  // the floors next to this one decoded ahead (each one's overview: its coarsest tile), so the new one is there the
  // moment the floor changes (a swipe goes one floor; a far one on the rail decodes from the cache under the
  // cross-fade). Only the neighbours: all six were ~60 MB of decoded pixels kept for the whole visit (the glass went grey, Oct 31)
  $effect(() => {
    const i = railFloors.indexOf(cur), dark = ver === 'kbtu' && look === 'dark';
    const held = railFloors.slice(Math.max(0, i - 1), i + 2).map((f) => { const im = new Image(); im.src = overview(ver, dark, f); void im.decode().catch(() => {}); return im; });
    return () => { held.length = 0; };
  });
  function pick(n: number) { void goTo(n); }
  function swipeStart(px: number, py: number, rail = false) { sw = { x0: px, y0: py, dx: 0, on: false, hist: [], rail, k0: idxOf(cur) }; }
  /** a finger moved: true once it's a floor swipe (the caller then neither pans nor taps) */
  function swipeMove(px: number, py: number): boolean {
    if (!sw) return false;
    const dx = px - sw.x0, dy = py - sw.y0;
    if (!sw.on) {
      if (dx * dx + dy * dy < 100) return false;
      // on the map more sideways than up or down is a floor (a natural swipe runs a bit diagonal); up or down, nothing:
      // zoomed out the plan has nowhere to go. Along the rail only a clear drag
      if (Math.abs(dx) <= Math.abs(dy) * (sw.rail ? 2 : 1)) { sw = null; return false; }
      sw.on = true; dragging = true;
    }
    sw.dx = dx;
    const now = performance.now();
    sw.hist.push([now, dx]);
    while (sw.hist.length > 2 && now - sw.hist[0][0] > 90) sw.hist.shift();
    const last = railFloors.length - 1, fb = knob?.offsetWidth || 42;
    // on the rail the knob stays under the finger; on the map a half screen's swipe is one floor, the other way
    let p = sw.rail ? sw.k0 + dx / fb : sw.k0 - Math.max(-1, Math.min(1, dx / (W() / 2)));
    if (p < 0) p = -(1 - 1 / (1 - p * 0.6)); else if (p > last) p = last + (1 - 1 / (1 + (p - last) * 0.6)); // a rubber band at the ends
    kp = p;
    return true;
  }
  /** the finger let go (or a second came): to the nearest floor, a flick carrying it one further */
  function swipeEnd(cancel = false) {
    const z = sw; sw = null;
    if (!z?.on) return;
    dragging = false;
    const h = z.hist, last = railFloors.length - 1;
    const vx = h.length > 1 ? (h[h.length - 1][1] - h[0][1]) / Math.max(16, h[h.length - 1][0] - h[0][0]) : 0;
    const fling = Math.abs(vx) > 0.4 ? Math.sign(vx) * (z.rail ? 0.4 : -0.6) : 0;
    const step = Math.round(kp + fling) - z.k0, far = Math.abs(kp - z.k0) > 0.5 || fling !== 0;
    const i = cancel ? z.k0 : Math.max(0, Math.min(last, z.rail ? z.k0 + step : far ? z.k0 + Math.sign(kp + fling - z.k0) : z.k0)); // the map: one floor a swipe
    if (i === z.k0) { if (!cancel && (kp < -0.15 || kp > last + 0.15)) haptic.rigid(); kp = i; jelly(knob); return; }
    void goTo(railFloors[i]);
  }
  // the rail: a drag along it, or a tap on a floor (a drag's let-go isn't a tap)
  let railSwiped = false;
  function railDown(e: PointerEvent) { if (rt.route) return; railSwiped = false; swipeStart(e.clientX, e.clientY, true); }
  function railMove(e: PointerEvent) {
    if (!swipeMove(e.clientX, e.clientY)) return;
    // held only once it's a drag: captured from the start, a tap's click would go to the rail, not the floor's button
    if (!railSwiped) (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    railSwiped = true;
  }
  function railUp() { swipeEnd(); }
  function swipeable(el: HTMLElement) { // listeners in code: the rail stays a plain tablist for the screen reader
    const on = [['pointerdown', railDown], ['pointermove', railMove], ['pointerup', railUp], ['pointercancel', railUp]] as const;
    on.forEach(([k, f]) => el.addEventListener(k, f as EventListener));
    return { destroy: () => on.forEach(([k, f]) => el.removeEventListener(k, f as EventListener)) };
  }
  // the frames in plan units (the 2023 plan's): the old map is the plan itself, ours a 1000-unit square cut of it at
  // (120, 130), Uni-Q's sheet fitted to it by its room numbers (design/map/tools/clean, median error ~9 units)
  const FIT = [[0.186469, 0.000447], [-0.001899, 0.196124], [9.528454, 5.881245]];
  const UNITS: Record<Ver, number> = { main: uniq.w * FIT[0][0], old: 1240, kbtu: 1000 }; // the sheet's width
  function toPlan(v: Ver, u: number, w: number): [number, number] {
    if (v === 'old') return [u * 1240, w * 1240];
    if (v === 'kbtu') return [120 + u * 1000, 130 + w * 1000];
    const px = u * uniq.w, py = w * uniq.h;
    return [px * FIT[0][0] + py * FIT[1][0] + FIT[2][0], px * FIT[0][1] + py * FIT[1][1] + FIT[2][1]];
  }
  function fromPlan(v: Ver, X: number, Y: number): [number, number] {
    if (v === 'old') return [X / 1240, Y / 1240];
    if (v === 'kbtu') return [(X - 120) / 1000, (Y - 130) / 1000];
    const [[a, c], [b, d], [e, f]] = FIT, X0 = X - e, Y0 = Y - f, det = a * d - b * c;
    return [(d * X0 - b * Y0) / det / uniq.w, (a * Y0 - c * X0) / det / uniq.h];
  }
  /** another map: the same part of the building stays on screen at the same size (owner, Oct 27: it zoomed out) */
  function setVer(v: Ver) {
    if (v === ver) return;
    haptic.select(); halt();
    const zoomed = !out(), P = toPlan(ver, ...uvAt(W() / 2, H() / 2)), k = scale() * UNITS[v] / UNITS[ver];
    ver = v; orig = false; if (!HAS[v].includes(cur)) cur = 1; glided = false; clearTimeout(glideT); touched++;
    if (!zoomed) { reset(); return; }
    const [u, w] = fromPlan(v, ...P);
    map.jumpTo(cam(Math.min(MAX, Math.max(homeK(), k)), u, w));
  }

  // the room: its number ringed wherever the plan has it, and once, a beat after the floor shows, a glide in to it
  let glided = false, glideT = 0, touched = 0;
  // the map's controls (owner, Oct 24, mockup design/mock/map.html): the search bar and the exit at the bottom, the floors as
  // a lift panel on the right with the look button above it; every input is our keypad (MapPad), no system keyboard
  let pad = $state(false);
  // a found place without a number (canteen, Independence Hall); the schedule can open the map on one
  let at = $state<{ f: number; u: number; v: number; label: string } | null>(untrack(() => {
    const sp = place && !room ? spotOf(place) : null;
    return sp?.f != null ? { f: sp.f, u: sp.u!, v: sp.v!, label: t(`route.spot.${sp.k}` as 'route.spot.canteen') } : null;
  }));
  const floorName = (n: number) => (n ? t('route.floor', { n }) : t('route.basement'));
  // the entrances on B too (owner, Oct 24); the graph has them, fetched when the keypad opens
  const doorNamed = (text: string) => rt.graph?.n.find((n) => n.k === 'x' && n.name === text) ?? null;
  async function openPad() {
    haptic.tap(); pad = true;
    if (!rt.graph) rt.graph = await api.mapGraph().catch(() => null);
  }
  function checkFind(text: string): PadCheck {
    const dn = doorNamed(text);
    if (dn) return { ok: true, tone: 'ok', hint: doorHint(dn, floorName(dn.f)) };
    const sp = spotOf(text);
    if (sp) return { ok: true, tone: 'ok', hint: floorName(sp.f ?? floorOf(sp.room) ?? 0) + adminNote(sp.room) };
    const r = roomOf(text), f = floorOf(r);
    if (!r || f == null) return text.length >= 3 || /[^\d\u0430-\u0433]/.test(text) ? { ok: false, tone: 'no', hint: t('pad.noRoom') } : { ok: false, hint: t('pad.roomHint') };
    return ROOMS[f]?.[r] ? { ok: true, tone: 'ok', hint: floorName(f) + adminNote(r) } : { ok: true, hint: t('pad.near', { room: r }) };
  }
  /** the keypad's answer: to its floor, ringed, glided to (the room's own effect below), the card under it */
  function found(text: string) {
    haptic.tap(); pad = false; clearTimeout(glideT);
    const dn = doorNamed(text), sp = dn ? { f: dn.f, u: dn.u, v: dn.v } : spotOf(text);
    if (sp && sp.f != null) {
      room = null; at = { f: sp.f, u: sp.u!, v: sp.v!, label: text }; glided = false;
      if (ver !== 'main') { ver = 'main'; reset(); }
      if (sp.f !== cur) { halt(); cur = sp.f; touched++; }
      glideTo(sp.u!, sp.v!, 3.2, true);
      return;
    }
    const r = roomOf(text) ?? spotOf(text)?.room ?? null; // a named room: Uni-Q's library is 158
    if (!r) return;
    at = null; glided = r === room; // the same room again: stay
    room = r;
    const f = floorOf(r)!;
    if (ver === 'kbtu' || (!f && ver === 'old')) { ver = 'main'; reset(); } // rooms are ringed on Uni-Q's; the basement is there only
    if (f !== cur) { halt(); cur = f; touched++; }
  }
  const dest = $derived(room ?? at?.label ?? null);
  const cardTitle = $derived(at ? at.label : room ? (SPOTS.find((x) => x.room === room) ? t(`route.spot.${SPOTS.find((x) => x.room === room)!.k}` as 'route.spot.canteen') : t('map.roomTitle', { room })) : '');
  const card = $derived(!pad && !routing && !!dest);
  function clearFound() { haptic.tap(); room = null; at = null; glided = false; clearTimeout(glideT); fit(); }
  /** the whole floor again, gliding */
  function fit() { halt(); framed = null; easeFit(middle(), 420); }
  const railFloors = $derived(HAS[ver]);
  /** the glide, to a point of the plan as fractions of its width and height, at least at `zoom` */
  function glideTo(u: number, v: number, zoom = 3.2, fit = false) {
    if (glided) return;
    glided = true;
    glideT = window.setTimeout(async () => { // after onMount: the stage has its size
      if (gone) return;
      const ns = fit ? zoom : Math.max(scale(), zoom), { top, bottom } = fit ? free() : { top: head(), bottom: 0 };
      const to = cam(ns, u, v, W() / 2, (top + H() - bottom) / 2);
      // just opened: the whole floor for a blink (owner, Oct 12: "you can't see where it came from"; "less than a tenth of
      // a second", no waiting for tiles); the landing's tiles come while it moves, over the coarser ones
      const t0 = ++touched;
      await new Promise((done) => setTimeout(done, Math.max(0, shownAt + 90 - performance.now())));
      await new Promise((done) => requestAnimationFrame(done));
      if (gone || touched !== t0) return; // a finger, a floor or the other version came first
      map.easeTo({ ...to, duration: 800, easing: spring }); // the spring: an easy ease (0.95 s, then 0.62 s) was "very slow", 0.52 s "too fast" (owner, Oct 12)
    });
  }
  // where the room's number stands on this map (Uni-Q's: read off the plan; the drawn ones: their own labels); 251a is
  // another room than 251. A named place is a point of Uni-Q's plan
  const spots = $derived(onRoomFloor ? roomAt(ver, cur, room!) : ver === 'main' && at && at.f === cur ? [[at.u, at.v]] : []);
  // not numbered on the plan: its nearest numbers show roughly where it is (nearRooms)
  const near = $derived(ver !== 'main' || !onRoomFloor || spots.length ? [] : nearRooms(ROOMS[cur], room!, AR).map(([, at]) => at));
  /** the stage's part nothing covers: above the bottom card or sheet (data-cover); measured, so the card's height and
   *  the safe areas count. One place for every framing */
  function free() {
    // offsets, not rects: a card still rising (a transform) would measure short
    const H = panel.clientHeight; let bottom = 0;
    panel.querySelectorAll<HTMLElement>('[data-cover]').forEach((el) => { bottom = Math.max(bottom, H - el.offsetTop); });
    return { top: head() + 64, bottom: bottom ? bottom + 12 : 0 }; // under the floors row
  }
  /** glide to show all of `pts`, between the buttons at the top and `inset` px at the bottom (a route's card): the whole
   *  step, never closer than it fits (owner, Oct 15: the way didn't fit and he had to find himself) */
  function frame(pts: number[][]) {
    const { top, bottom } = free(), us = pts.map((p) => p[0]), vs = pts.map((p) => p[1]), W = stage.clientWidth, H = stage.clientHeight - top - bottom;
    const bw = Math.max(...us) - Math.min(...us) + 0.08, bh = (Math.max(...vs) - Math.min(...vs)) * AR + 0.08;
    glideTo((Math.min(...us) + Math.max(...us)) / 2, (Math.min(...vs) + Math.max(...vs)) / 2, Math.min(3.2, Math.max(1, Math.min(1 / bw, H / (bh * W)))), true);
  }
  $effect(() => {
    if (!onRoomFloor) return;
    if (spots.length) glideTo(spots[0][0], spots[0][1], 3.2, true); // framed above the room's card
    else if (glided) return;
    else if (ver === 'main' && near.length) { say(t('map.lookHere', { room: room! }), 'pleading_face_3d'); frame(near); }
    else { glided = true; say(t(ver === 'main' ? 'map.notFound' : 'map.noRoom', { room: room! }), 'pleading_face_3d'); } // the old plan won't have it either
  });
  // the panel shows at once, or with its glide when it opens on a room (glideTo; a nearly transparent panel still gets painted)
  let appeared = false, shownAt = 0, undoChrome = () => {};
  function appear() {
    if (appeared || gone) return;
    appeared = true; shownAt = performance.now();
    undoChrome = hideChrome();
    if (!iris) {
      panel.animate([{ opacity: 0, transform: 'scale(0.97)' }, { opacity: 1, transform: 'none' }], { duration: 260, easing: 'cubic-bezier(.2,.9,.25,1)' });
      return;
    }
    const o = { duration: 560, easing: 'cubic-bezier(.32, .8, .3, 1)' }, far = reach(iris.at);
    panel.animate({ clipPath: [iris(iris.at.r), iris(far)] }, o);
    // the map's own round button grows out of the one tapped (owner, Oct 31: from the slim bar the small button and
    // the big one read as two buttons): it starts on the tapped one's place and size and settles on its own
    const shut = panel.querySelector<HTMLElement>('.shut'), sb = shut?.getBoundingClientRect();
    if (shut && sb?.width) shut.animate({ transform: [`translate(${iris.at.x - sb.left - sb.width / 2}px, ${iris.at.y - sb.top - sb.height / 2}px) scale(${(iris.at.r * 2) / sb.width})`, 'none'] }, o);
    // Telegram's Close turns into Back a moment into the circle, not at the tap nor at its end (owner, PLAN 80)
    setTimeout(() => (overlay.holdBack = false), BACK_AFTER);
    // the map breathes out to meet you: a touch larger at first, it settles as the circle opens
    stage.animate({ transform: ['scale(1.08)', 'none'], transformOrigin: [`${iris.at.x}px ${iris.at.y - stage.offsetTop}px`, `${iris.at.x}px ${iris.at.y - stage.offsetTop}px`] }, o);
    // the page under it steps back (iOS's way): it stays put under the map, so it's clear the map came over it
    underEl = document.querySelector<HTMLElement>('.app > .tab.on');
    under = underEl?.animate(
      { transform: ['none', 'scale(0.94)'], opacity: [1, 0.45], transformOrigin: [`${iris.at.x}px ${iris.at.y}px`, `${iris.at.x}px ${iris.at.y}px`] }, { ...o, fill: 'forwards' }) ?? null;
    // once covered, the page under isn't drawn at all: held as a scaled, faded layer it kept its pictures and glass
    // composited under the map the whole visit; it shows again the moment the map starts closing
    under?.finished.then(() => { if (!gone && underEl) underEl.style.visibility = 'hidden'; }, () => {});
    const h = halo(30, far, o, [1, 1, 1, 0]);
    // the capsule is cut by the circle (owner, Oct 25): inside it already says "Map", outside it's still the old one
    if (iris.cap) split(h, iris.cap, false);
  }
  let under: Animation | null = null, underEl: HTMLElement | null = null;
  // opened from the nav's round button (owner, Oct 25: "one with the bar"): the map grows out of that circle and
  // shrinks back into it; clip-path only, the map under it is painted once
  const reach = ({ x, y }: { x: number; y: number }) => Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  const iris = (() => {
    const { at, cap, el } = mapFrom; mapFrom.at = mapFrom.cap = mapFrom.el = null;
    if (!at || matchMedia('(prefers-reduced-motion: reduce)').matches) return null;
    return Object.assign((r: number) => `circle(${r}px at ${at.x}px ${at.y}px)`, { at, cap, el });
  })();
  const BACK_AFTER = 180; // ms into the iris. Owner, Oct 26: exactly right, lands on the animation: keep it for good
  untrack(() => { if (iris) overlay.holdBack = true; }); // until a moment into the circle (appear); set before the first frame
  // the map's own capsule, copied whenever it changes (the floor), for the way back: closing, the real one is the
  // old page's at once, the copy shows inside the shrinking circle
  let mapCap: CapCopy | null = null;
  $effect(() => {
    void overlay.title; void own;
    if (iris && !gone) void tick().then(() => requestAnimationFrame(() => { if (!gone) mapCap = copyCap(); }));
  });
  // two capsules meet on the circle's edge: the real one and a still copy, each masked to its side, every frame
  function split(h: HTMLElement, copy: CapCopy, copyInside: boolean, c: { x: number; y: number } = iris!.at) {
    const real = document.querySelector<HTMLElement>('.cap');
    const w = document.createElement('div');
    w.className = copy.theme;
    w.style.cssText = 'display:block;position:fixed;inset:0;z-index:9998;pointer-events:none';
    w.setAttribute('aria-hidden', 'true');
    w.append(copy.node);
    document.body.append(w);
    const side = (el: HTMLElement, inside: boolean, r: number) => {
      const b = el.getBoundingClientRect(), [i, o] = inside ? ['#000', 'transparent'] : ['transparent', '#000'];
      const m = `radial-gradient(circle at ${c.x - b.left}px ${c.y - b.top}px, ${i} ${r}px, ${o} ${r}px)`;
      el.style.setProperty('mask', m); el.style.setProperty('-webkit-mask', m);
    };
    const frame = () => {
      if (!h.isConnected || !real) { real?.style.removeProperty('mask'); real?.style.removeProperty('-webkit-mask'); w.remove(); return; }
      const r = h.offsetWidth / 2;
      side(real, !copyInside, r); side(copy.node, copyInside, r);
      requestAnimationFrame(frame);
    };
    frame();
  }
  // the circle's edge lit like the glass (owner, Oct 25: without it the map "just takes over like a picture"): a ring
  // of its own over the panel, its size animated with the clip (a scaled ring would thicken its line)
  function halo(from: number, to: number, o: KeyframeAnimationOptions, opacity: number[], c: { x: number; y: number } = iris!.at): HTMLElement {
    const h = document.createElement('i');
    h.className = 'map-halo';
    h.style.cssText = `left:${c.x}px;top:${c.y}px`;
    document.body.append(h);
    h.animate({ width: [`${from * 2}px`, `${to * 2}px`], height: [`${from * 2}px`, `${to * 2}px`], opacity }, o).finished.catch(() => {}).finally(() => h.remove());
    return h;
  }

  onMount(() => {
    const dark = look === 'dark';
    planKey = `${ver}|${cur}|${ver === 'kbtu' && dark}`; inkKey = `${ver}|${dark}`; wordsKey = wordsNow(); fadeVer = ver;
    map = new GLMap({
      container: gl, ...middle(), attributionControl: false, renderWorldCopies: false, fadeDuration: 250,
      dragRotate: false, pitchWithRotate: false, touchPitch: false, keyboard: false, boxZoom: false, doubleClickZoom: false,
      pixelRatio: Math.min(3, devicePixelRatio || 1), transformConstrain: within,
      style: { version: 8, sources: { plan: planSource(), words: { type: 'geojson', data: words() }, pins: { type: 'geojson', data: pinData() } }, layers: [planLayer(), ...wordLayers(), pinLayer] } as StyleSpecification,
    });
    map.touchZoomRotate.disableRotation();
    map.getCanvasContainer().append(plan); // over the canvas, inside what MapLibre listens on
    // a label's plate (Uni-Q's numbers cover the tiny printed ones): one flat square, coloured and stretched by the layer
    map.once('style.load', () => {
      map.addImage('plate', { width: 4, height: 4, data: new Uint8Array(64).fill(255) }, { sdf: true });
      map.addImage('pin', { width: 24, height: 24, data: new Uint8Array(24 * 24 * 4) }); // a pin's place, drawn by the overlay
    });
    map.on('move', follow); map.on('resize', follow);
    map.on('moveend', (e) => { if ((e as { originalEvent?: Event }).originalEvent) rest(); });
    map.on('click', tap);
    map.once('load', () => { ready = true; });
    // the first frame with the floor's tiles in it, for the QA scripts' "tap to plan" time (the overview is there from frame one)
    const drawn = () => { if (map.areTilesLoaded()) { map.off('render', drawn); performance.mark('map-drawn'); } };
    map.on('render', drawn);
    follow();
    if (at) glideTo(at.u, at.v, 3.2, true);
    appear();
    const ro = new ResizeObserver(() => { clearTimeout(reframeT); reframeT = window.setTimeout(reframe, 200); });
    const d = document.documentElement.dataset;
    d.map = ''; // the toast drops under the floor row there (Toast.svelte)
    ro.observe(stage);
    const clockT = setInterval(() => (clock = nowTs()), 60_000); // "free now" moves on with the hour
    return () => { clearInterval(clockT); delete d.map; underEl?.style.removeProperty('visibility'); ro.disconnect(); clearTimeout(glideT); clearTimeout(scanT); undoChrome(); map.remove(); if (own) paintFor(theme.current); };
  });

  function leave() {
    if (gone) return;
    gone = true;
    if (!appeared) { removeOverlay(overlay.id); return; } // closed before it showed
    let a: Animation;
    if (iris) {
      // eases out into the button (owner's video, Oct 25: an ease-in close was fastest at its last frame and "hit like a
      // hammer"); the page under comes back on the same curve. Owner, Oct 25: it shrank off the button's centre (the nav
      // slides back in as it closes, the opening's point was stale) and the button didn't react: it closes on where the
      // button comes to rest, to the button's own size, and the button takes the ring's glow, then lets it fade
      const o = { duration: 480, easing: 'cubic-bezier(.45, 0, .2, 1)' };
      // back into the control it opened from (owner, Nov 17: opened from Afisha's header, it closed into the bar's corner,
      // KRI's by then); that control gone from the page: the point it opened at. Only the bar's own button slides with its dock
      const b = iris.el?.isConnected ? iris.el : null, dock = b?.classList.contains('mapb') ? b.parentElement : null;
      const bt = b?.getBoundingClientRect(), dm = dock && getComputedStyle(dock).transform !== 'none' ? new DOMMatrix(getComputedStyle(dock).transform) : null;
      const c = bt ? { x: bt.left + bt.width / 2 - (dm?.e ?? 0), y: bt.top + bt.height / 2 - (dm?.f ?? 0) } : iris.at;
      const end = bt ? Math.min(bt.width, bt.height) / 2 : iris.at.r, far = reach(c);
      // the map's own button goes back into the one it came from (owner, Oct 31: the bar stays as it was, slim or full)
      const shut = panel.querySelector<HTMLElement>('.shut'), sb = shut?.getBoundingClientRect();
      if (shut && sb?.width) shut.animate({ transform: ['none', `translate(${c.x - sb.left - sb.width / 2}px, ${c.y - sb.top - sb.height / 2}px) scale(${(end * 2) / sb.width})`] }, { ...o, fill: 'forwards' });
      const circle = (r: number) => `circle(${r}px at ${c.x}px ${c.y}px)`;
      const h = halo(far, end, o, [1, 1, 1], c); // held to the end: the ripples take over from it at the button's size
      if (mapCap) split(h, mapCap, true, c);
      undoChrome(); undoChrome = () => {}; // the capsule and the nav come back now, the circle uncovers them
      stage.animate({ transform: ['none', 'scale(1.06)'] }, { ...o, fill: 'forwards' });
      underEl?.style.removeProperty('visibility');
      const page = document.querySelector<HTMLElement>('.app > .tab.on');
      if (under && page) {
        const u = under;
        page.animate({ transform: ['scale(0.94)', 'none'], opacity: [0.45, 1], transformOrigin: [`${c.x}px ${c.y}px`, `${c.x}px ${c.y}px`] }, o);
        u.cancel(); // the forwards hold goes, the new animation starts where it left the page
      }
      a = panel.animate({ clipPath: [circle(far), circle(end)], opacity: [1, 1, 0] }, { ...o, fill: 'forwards' });
      // the button catches it (owner, Oct 25: "smoother, more alive, more professional"): the ring lands on the button's
      // rim and goes on out as two soft ripples, the button gives under it and springs back, a glow swells inside it and
      // fades. Only opacity and transform move (the stepped box-shadow repainted every frame and read as steps).
      setTimeout(() => {
        haptic.tap();
        for (const [d, k] of [[0, 1.55], [130, 1.9]] as const) {
          const r = document.createElement('i');
          r.className = 'map-halo';
          r.style.cssText = `left:${c.x}px;top:${c.y}px;width:${end * 2}px;height:${end * 2}px`;
          document.body.append(r);
          r.animate({ transform: ['scale(1)', `scale(${k})`], opacity: [d ? 0.55 : 1, 0] }, { duration: 760, delay: d, easing: 'cubic-bezier(.2, .7, .3, 1)', fill: 'both' })
            .finished.catch(() => {}).finally(() => r.remove());
        }
        const g = document.createElement('i');
        g.className = 'map-glow';
        g.style.cssText = `left:${c.x}px;top:${c.y}px;width:${end * 3}px;height:${end * 3}px`;
        document.body.append(g);
        g.animate({ transform: ['scale(.5)', 'scale(1)', 'scale(1.15)'], opacity: [0, 1, 0], offset: [0, 0.3, 1] }, { duration: 820, easing: 'ease-out' })
          .finished.catch(() => {}).finally(() => g.remove());
        b?.animate([
          { transform: 'scale(1)' }, { transform: 'scale(.9)', offset: 0.22 }, { transform: 'scale(1.06)', offset: 0.55 },
          { transform: 'scale(.99)', offset: 0.8 }, { transform: 'scale(1)' },
        ], { duration: 680, easing: 'cubic-bezier(.3, .7, .4, 1)' });
      }, o.duration * 0.94);
    } else a = panel.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });
</script>

<div class="panel theme-{look}" class:main={ver !== 'kbtu'} class:kbtu={ver === 'kbtu'} bind:this={panel}>
  {#if !inTelegram}<button class="x" onclick={() => close(overlay.id)} aria-label={t('common.close')}><X size={22} /></button>{/if}
  <div class="stage" bind:this={stage} role="img" aria-label={title}
       onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}>
    <div class="first" bind:this={first}>{#if ghost}{#key ghost}<img class="ghost" bind:this={ghostEl} src={ghost} alt="" draggable="false" />{/key}{/if}{#key `${ver}${cur}`}<img src={overview(ver, look === 'dark', cur)} alt="" draggable="false" />{/key}</div>
    <div class="gl" bind:this={gl}></div>
    <div class="plan" bind:this={plan} style:aspect-ratio="1 / {AR}">
        {#each spots as [u, v], i (i)}<span class="spot" style:left="{u * 100}%" style:top="{v * 100}%"></span>
          {#if i === 0 && card}<span class="pin flag" style:left="{u * 100}%" style:top="{v * 100}%">{cardTitle}</span>{/if}{/each}
        {#each near as [u, v], i (i)}<span class="spot near" style:left="{u * 100}%" style:top="{v * 100}%"></span>{/each}
        {#each freeHere as f (f.r + f.u + f.v)}<span class="room" class:free={f.free} data-room={f.r} style:left="{f.u * 100}%" style:top="{f.v * 100}%"></span>{/each}
        {#if legsHere.length}
          <svg class="way" viewBox="0 0 1000 {1000 * AR}" preserveAspectRatio="none" aria-hidden="true">
            <!-- the way (owner, Oct 24: "chic"): a soft glow, the line, white dots running along the step on screen -->
            {#each legsHere as l (l.i)}
              {#if l.i === rt.step}<polyline class="glow" points={line(l.pts)} />{/if}
              <polyline points={line(l.pts)} class:now={l.i === rt.step} />
              {#if l.i === rt.step}<polyline class="run" points={line(l.pts)} />{/if}
            {/each}
          </svg>
        {/if}
        {#each legsHere as l (l.i)}
          {@const a = l.pts[0]}
          {@const b = l.pts[l.pts.length - 1]}
          {#if l.i === 0}
            <!-- where you are: a dot and "You are here" above it (the mockup the owner liked, Oct 24) -->
            <span class="pin me" style:left="{a.u * 100}%" style:top="{a.v * 100}%"></span>
            <span class="pin tag" style:left="{a.u * 100}%" style:top="{a.v * 100}%">{t('route.here')}</span>
          {:else}<span class="pin start" class:now={l.i === rt.step} style:left="{a.u * 100}%" style:top="{a.v * 100}%"></span>{/if}
          {#if l.to != null}<span class="pin badge" style:left="{b.u * 100}%" style:top="{b.v * 100}%">{l.to > l.f ? '\u2191' : '\u2193'} {floorName(l.to)}</span>
          {:else}<span class="pin end" style:left="{b.u * 100}%" style:top="{b.v * 100}%"></span>
            {#if rt.ends}<span class="pin flag" style:left="{b.u * 100}%" style:top="{b.v * 100}%">{rt.ends[1]}</span>{/if}{/if}
        {/each}
      {#each flawsHere as m (m.id)}
        <span class="pin mark" class:ok={m.id === okId} data-flaw={m.id} style:left="{m.u * 100}%" style:top="{m.v * 100}%"><Check size={11} strokeWidth={3.4} /></span>
        {#if m.id === seen}<span class="pin memo" style:left="{m.u * 100}%" style:top="{m.v * 100}%">{m.body}</span>{/if}
      {/each}
      {#if draft && draft.f === cur && draft.ver === ver}<span class="pin mark draft" style:left="{draft.u * 100}%" style:top="{draft.v * 100}%"></span>{/if}
    </div>
  </div>
  <!-- the top row: the floors, the map's look at its end (owner, Oct 24: a lift panel on the right covered the plan) -->
  <div class="side" bind:this={side}>
    <!-- the maps: a tap lists them (owner, Oct 27; it was a toggle to the 2023 plan) -->
    <div class="maps" class:away={!!rt.route}>
      <button class="rb glass glass-pill" class:on={menu} use:glass onclick={() => { haptic.tap(); menu = !menu; }}
        aria-label={t('map.maps')} aria-expanded={menu} aria-haspopup="menu"><Layers size={20} /></button>
      {#if menu}
        <div class="menu glass glass-sheet" use:glass role="menu">
          {#each VERS as v (v)}<button role="menuitemradio" aria-checked={ver === v} class:on={ver === v} onclick={() => { menu = false; setVer(v); }}>{t(`map.ver.${v}` as 'map.ver.main')}</button>{/each}
        </div>
      {/if}
    </div>
    <!-- on the way only the look button stays: the floors move into the step card (owner, Oct 24) -->
    <div class="rail glass glass-pill" class:away={!!rt.route} class:dragging inert={!!rt.route} use:glass use:swipeable role="tablist" aria-label={t('map.floors')} style:--kp={kp}>
      <!-- the knob: a clear glass lens, the rail's numbers again inside it, magnified around its middle (owner, Oct 25) -->
      <span class="knob" bind:this={knob} aria-hidden="true"><span class="mag">{#each [0, 1, 2, 3, 4, 5] as n (n)}<i class:gone={!railFloors.includes(n)}>{n || t('map.bShort')}</i>{/each}</span></span>
      <!-- all six always there: the old map's missing basement folds away in step with the knob, so the rail narrows
           instead of jumping (owner, Oct 24 video) -->
      {#each [0, 1, 2, 3, 4, 5] as n (n)}{@const gone = !railFloors.includes(n)}<button role="tab" aria-selected={cur === n} class:on={cur === n}
        class:r={routeFloors.has(n)} class:gone tabindex={gone ? -1 : undefined} aria-hidden={gone || undefined} onclick={() => { if (!railSwiped) pick(n); }}
        aria-label={floorName(n)}>{n || t('map.bShort')}</button>{/each}
    </div>
    <!-- a tap turns the map light or dark at once (owner, Oct 24: the menu it opened looked foreign and lagged) -->
    <button class="rb glass glass-pill" use:glass onclick={(e) => flip(e.currentTarget)} aria-label={t('map.theme')}>
      {#if look === 'dark'}<Moon size={20} />{:else}<Sun size={20} />{/if}</button>
  </div>
  <!-- "free now": under the maps button, on the main map only (its rooms' numbers are where the tint goes) -->
  {#if week && ver === 'main'}
    <button class="freeb glass glass-pill" class:on={freeOn} class:away={!!rt.route} use:glass onclick={toggleFree} aria-pressed={freeOn}>
      <i aria-hidden="true"></i>{t('map.freeNow')}</button>
  {/if}
  <!-- the 2023 plan as it was given, over our redraw of it, to compare (owner, Nov 15) -->
  {#if ver === 'old'}
    <button class="freeb glass glass-pill" class:on={orig} use:glass onclick={() => { haptic.select(); orig = !orig; }} aria-pressed={orig}>
      <i aria-hidden="true"></i>{t('map.orig')}</button>
  {/if}
  <!-- the credit, and the old plan for who wants it, under the map as before the redo -->
  <p class="note" class:away={pad || card || routing}>{ver === 'main' ? t('map.noteMain') : ver === 'kbtu' ? t('map.noteKbtu') : t('map.note')}</p>
  <!-- the bottom, under the thumb (owner's layout, Oct 26): the way out small on the left, the search, and on the right
       the app's own map button, lit: a tap there closes the map, as the button opened it -->
  <div class="dock" class:away={pad || card || routing} inert={pad || card || routing}>
    <button class="exit glass glass-pill" use:glass onclick={() => { leaving = true; void openRoute(); }} aria-label={t('route.out')}><DoorOpen size={22} /></button>
    <button class="bar glass glass-pill" use:glass onclick={openPad}><Search size={20} /><span class="ellipsis">{t('map.find')}</span></button>
    <button class="shut glass glass-pill" use:glass onclick={() => close(overlay.id)} aria-label={t('common.close')}><MapIcon size={22} strokeWidth={1.9} /></button>
  </div>
  {#if card}
    <div class="rcard" data-cover>
      <span class="grab" aria-hidden="true"></span>
      <!-- the place itself is the way to another one (owner, Oct 24: an "Other" button beside the route looked wrong) -->
      <div class="rhead"><button class="rfind" onclick={openPad} aria-label={t('map.other')}>
          <span class="ptb" aria-hidden="true">{t('pad.b')}</span><span class="rt"><b>{cardTitle}</b><small>{floorName(at ? at.f : (roomFloor ?? 0))}</small></span>
          <Search size={18} /></button>
        <button class="xb" onclick={clearFound} aria-label={t('common.close')}><X size={18} /></button></div>
      {#if roomLine}<p class="fl">{roomLine}</p>{/if}
      <button class="go" onclick={() => { leaving = false; void openRoute(); }}><RouteIcon size={20} />{t('map.routeHere')}</button>
    </div>
  {/if}
  {#if pad}<MapPad title={t('pad.findTitle')} go={t('pad.find')} point="b" placeTab={t('pad.entranceOrPlace')} groups={[{ title: t('pad.entrances'), tiles: exitTiles(rt.graph) }, ...placeGroups()]} check={checkFind} onsubmit={found} onclose={() => (pad = false)} />{/if}
  {#if routing}
    <RouteUI {rt} {cur} {pick} ar={AR} rooms={ROOMS} to={dest} {go} out={leaving} onclose={() => { routing = false; leaving = false; rt.route = null; }} />
  {/if}
</div>

<style>
  :global(.map-halo) {
    position: fixed; z-index: 9999; translate: -50% -50%; border-radius: 50%; pointer-events: none;
    /* clear, not heavy (owner, Oct 25: thin was lost, 3.5 px "even too much"); the glow is stepped rings with no blur,
       a blurred shadow repainted the whole growing circle every frame and the opening stuttered */
    box-shadow: 0 0 0 2.5px rgba(255, 255, 255, 0.95), 0 0 0 5px rgba(150, 180, 255, 0.5), 0 0 0 9px rgba(130, 165, 255, 0.24),
      0 0 0 14px rgba(120, 160, 255, 0.1), inset 0 0 0 4px rgba(150, 180, 255, 0.3), inset 0 0 0 9px rgba(130, 165, 255, 0.12);
  }
  /* the glow the map button takes as it catches the closing circle: a soft light, faded in and out (opacity only) */
  :global(.map-glow) { position: fixed; z-index: 9998; translate: -50% -50%; border-radius: 50%; pointer-events: none;
    background: radial-gradient(circle, rgba(170, 195, 255, 0.55), rgba(120, 160, 255, 0.22) 45%, transparent 70%); }
  .panel { position: absolute; inset: 0; z-index: var(--z-sheet); background: var(--bg); overflow: hidden; }
  /* on the way the floors are the step card's last row (owner, Oct 15: one panel, not two) */
  /* the paper all round: white, or inverted with the plan in the dark look (Uni-Q's and the 2023 plan); ours has its ground */
  .panel.main { background: #fff; }
  .panel.main.theme-dark { background: #0d0d0d; }
  .panel.kbtu { background: #DCE0EA; }
  .panel.kbtu.theme-dark { background: #0A0B10; }
  .x { position: absolute; z-index: 2; left: 12px; top: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2)); width: 38px; height: 38px;
    border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--surface-solid); color: var(--text); }
  .stage { position: absolute; inset: 0; overflow: hidden; touch-action: none; }
  .rail { touch-action: none; }
  /* MapLibre's canvas, clear where it has drawn nothing yet: the floor's overview shows through from under it */
  .gl { position: absolute; inset: 0; }
  .gl :global(canvas) { touch-action: none; outline: none; }
  /* the floor's whole sheet in one small picture, there from the first frame and under the tiles ever after; it
     follows the camera by a transform alone */
  .first { position: absolute; left: 0; top: 0; width: 512px; height: 512px; transform-origin: 0 0; will-change: transform; pointer-events: none; }
  .first img { position: absolute; inset: 0; width: 100%; height: 100%; display: block; -webkit-user-drag: none; }
  /* on the picture itself: iOS stopped drawing a filter on its parent once the iris animated the panel and the stage
     over it (owner's screenshot, Oct 26: a white plan in the dark look). The tiles are inverted the same in MapLibre */
  .theme-dark.main .first img { filter: invert(0.95) hue-rotate(180deg); }
  /* what stands on the plan (rings, pins, the way): laid over the canvas inside MapLibre's own container, so a finger
     on a pin still moves the map; as wide as the plan is on screen, moved with the camera */
  .plan { position: absolute; left: 0; top: 0; width: 100%; transform-origin: 0 0; pointer-events: none;
    user-select: none; -webkit-user-select: none; -webkit-touch-callout: none; }
  /* the room found: a ring that breathes out, its name in a blue flag above (mockup, Oct 24) */
  .spot { position: absolute; width: 3.4%; aspect-ratio: 1; border-radius: 50%; transform: translate(-50%, -50%); pointer-events: none;
    border: 3px solid var(--accent-text); background: rgba(59, 107, 255, 0.14); box-shadow: 0 0 22px rgba(59, 107, 255, 0.6); }
  .spot::before, .spot::after { content: ''; position: absolute; inset: -3px; border-radius: 50%; border: 3px solid var(--accent-text); animation: ripple 2s var(--ease-spring) infinite; }
  .spot::after { animation-delay: 1s; }
  @keyframes ripple { from { transform: scale(1); opacity: 0.9; } to { transform: scale(2.2); opacity: 0; } }
  .spot.near { border-style: dashed; border-color: var(--text-3); background: none; box-shadow: none; } /* a neighbour, for bearings */
  .spot.near::before, .spot.near::after { display: none; }
  /* "free now": a green disc over a free room's number, a grey one dims a busy room's; a tap opens its card */
  .room { position: absolute; width: 3.4%; aspect-ratio: 1; border-radius: 50%; transform: translate(-50%, -50%); pointer-events: auto;
    background: rgba(142, 142, 147, 0.28); }
  .room.free { background: rgba(48, 209, 88, 0.3); box-shadow: inset 0 0 0 2px rgba(48, 209, 88, 0.85); }
  /* the way: a soft glow under the step on screen, the line, white dots running along it (owner, Oct 24: "chic") */
  .way { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; overflow: visible; }
  .way polyline { fill: none; stroke: var(--accent); stroke-opacity: 0.35; stroke-width: 5; stroke-linecap: round; stroke-linejoin: round; vector-effect: non-scaling-stroke; }
  .way polyline.now { stroke: #6e92ff; stroke-opacity: 1; stroke-width: 7; }
  .way polyline.glow { stroke: var(--accent); stroke-opacity: 0.22; stroke-width: 20; }
  .way polyline.run { stroke: #fff; stroke-opacity: 1; stroke-width: 2.6; stroke-dasharray: 1 13; animation: run 0.9s linear infinite; }
  @keyframes run { to { stroke-dashoffset: -14; } }
  .pin { position: absolute; transform: translate(-50%, -50%); pointer-events: none; }
  .pin.start { width: 14px; height: 14px; border-radius: 50%; background: var(--bg); border: 3px solid var(--accent); opacity: 0.5; }
  .pin.start.now { opacity: 1; }
  .pin.me { width: 22px; height: 22px; border-radius: 50%; background: #fff; display: grid; place-items: center; box-shadow: 0 0 0 6px rgba(255, 255, 255, 0.22), 0 4px 14px rgba(0, 0, 0, 0.5); }
  .pin.me::after { content: ''; width: 12px; height: 12px; border-radius: 50%; background: #2fc277; } /* A is green, B blue (owner, Oct 24) */
  .pin.tag { transform: translate(-50%, calc(-100% - 20px)); padding: 6px 10px; border-radius: 10px; background: #fff; color: #0a0f24; font: 750 12px/1 var(--font-text); white-space: nowrap;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35); }
  .pin.end { width: 18px; height: 18px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 4px #fff, 0 6px 18px rgba(59, 107, 255, 0.8); }
  .pin.end::before { content: ''; position: absolute; inset: -4px; border-radius: 50%; border: 3px solid var(--accent-text); animation: ripple 2s var(--ease-spring) infinite; }
  .pin.flag { transform: translate(-50%, calc(-100% - 24px)); padding: 7px 12px; border-radius: 12px; white-space: nowrap; background: var(--accent); color: #fff;
    font: 750 14px/1 var(--font-text); box-shadow: 0 8px 22px -6px rgba(59, 107, 255, 0.8); animation: flagIn 0.5s var(--ease-bounce) backwards 0.2s; }
  .pin.flag::after { content: ''; position: absolute; left: 50%; bottom: -5px; width: 10px; height: 10px; background: inherit; border-radius: 2px; transform: translateX(-50%) rotate(45deg); }
  @keyframes flagIn { from { opacity: 0; transform: translate(-50%, calc(-100% - 10px)) scale(0.7); } }
  .pin.badge { transform: translate(-50%, -130%); padding: 5px 9px; border-radius: 10px; background: #f5b13d; color: #1d1300; font: 800 13px/1 var(--font-text); white-space: nowrap;
    box-shadow: 0 6px 16px -4px rgba(245, 177, 61, 0.7); }
  /* "something's wrong here": the spot being marked, a check once it's sent, then a small dot of mine (a 28 px target) */
  .pin.mark { width: 28px; height: 28px; display: grid; place-items: center; pointer-events: auto; color: white; }
  .pin.mark::before { content: ''; position: absolute; inset: 9px; border-radius: 50%; background: var(--warning); box-shadow: 0 0 0 2px white, 0 1px 5px rgba(0, 0, 0, 0.35); transition: inset 0.45s var(--ease-spring); }
  .pin.mark :global(svg) { position: relative; opacity: 0; transform: scale(0.4); transition: opacity 0.2s, transform 0.35s var(--ease-spring); }
  .pin.mark.ok::before, .pin.mark.draft::before { inset: 3px; box-shadow: 0 0 0 3px white, 0 4px 14px rgba(0, 0, 0, 0.35); }
  .pin.mark.ok :global(svg) { opacity: 1; transform: none; }
  .pin.mark.draft { pointer-events: none; animation: drop 0.45s var(--ease-bounce); }
  .pin.mark.draft::after { content: ''; position: absolute; inset: 3px; border-radius: 50%; border: 2px solid var(--warning); animation: ripple 1.8s var(--ease-spring) infinite; }
  @keyframes drop { from { opacity: 0; transform: translate(-50%, -50%) scale(0.3); } }
  .pin.memo { transform: translate(-50%, calc(-100% - 12px)); width: max-content; max-width: 220px; padding: 8px 11px; border-radius: var(--r-s); background: var(--surface-solid); color: var(--text);
    font: 600 var(--fs-sub)/1.35 var(--font-text); text-align: center; overflow-wrap: anywhere; box-shadow: 0 6px 20px -4px rgba(0, 0, 0, 0.35); animation: noteIn 0.3s var(--ease-spring); }
  @keyframes noteIn { from { opacity: 0; transform: translate(-50%, calc(-100% - 6px)) scale(0.92); } }
  :global(html.lowfx) .pin.mark.draft::after,
  :global(html.lowfx) .way polyline.run, :global(html.lowfx) .spot::before, :global(html.lowfx) .spot::after, :global(html.lowfx) .pin.end::before { animation: none; }
  @media (prefers-reduced-motion: reduce) { .way polyline.run, .spot::before, .spot::after, .pin.end::before, .pin.flag, .pin.mark.draft::after { animation: none; } }

  /* right edge: the look button, the floors as a lift panel, "whole floor" (owner, Oct 24 mockup) */
  .side { position: absolute; z-index: 2; left: 12px; right: 12px; top: calc(max(48px, var(--top)) + 10px); display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .rb { position: relative; flex: none; width: 46px; height: 46px; border-radius: 50%; display: grid; place-items: center; color: var(--text); transition: transform 0.45s var(--ease-bounce), opacity 0.3s; }
  .rb.on { background: var(--accent); color: #fff; }
  .rb.away, .maps.away { opacity: 0; pointer-events: none; }
  .maps { position: relative; flex: none; transition: opacity 0.3s; }
  .menu { position: absolute; left: 0; top: 54px; min-width: 190px; padding: 6px; border-radius: 22px; display: grid; gap: 2px; }
  .menu button { text-align: left; padding: 11px 14px; border-radius: 16px; font: inherit; font-weight: 600; color: var(--text); }
  .menu button.on { background: var(--accent); color: #fff; }
  .rb:active { transform: scale(0.92); transition-duration: 80ms; }
  /* a floor button shrinks on a narrow phone so the row fits (two 46px buttons, two 10px gaps, 12px sides) */
  .rail { --fb: min(42px, calc((100vw - 144px) / 6)); position: relative; display: flex; padding: 4px; border-radius: 26px; transition: opacity 0.3s, transform 0.5s var(--ease-spring), --kp 420ms var(--ease-spring); }
  .rail.dragging { transition: opacity 0.3s, transform 0.5s var(--ease-spring), --kp 0s; }
  .rail.away { opacity: 0; transform: translateY(-30px); pointer-events: none; }
  /* the knob's place: one registered number, so its spring moves the lens and the magnified copy inside in one step */
  @property --kp { syntax: '<number>'; inherits: true; initial-value: 0; }
  .rail .knob { position: absolute; z-index: 2; left: 4px; top: 4px; bottom: 4px; width: var(--fb); border-radius: 21px; overflow: hidden; pointer-events: none;
    translate: calc(var(--kp) * var(--fb)) 0;
    /* clear glass: the rail's own colour through it, the plain numbers under it blurred away, a bright rim, a bent edge */
    background: rgba(255, 255, 255, 0.08); backdrop-filter: blur(5px) saturate(1.7); -webkit-backdrop-filter: blur(5px) saturate(1.7);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.5), inset 0 1.5px 1px rgba(255, 255, 255, 0.9), inset 0 -3px 6px rgba(255, 255, 255, 0.16),
      inset 3px 0 6px -3px rgba(120, 170, 255, 0.6), inset -3px 0 6px -3px rgba(255, 140, 190, 0.55), 0 0 0 0.5px rgba(0, 0, 0, 0.08), 0 6px 16px -6px rgba(0, 0, 0, 0.35); }
  .rail .mag { position: absolute; left: 0; top: 0; height: 42px; display: flex;
    transform-origin: calc(var(--kp) * var(--fb) + var(--fb) / 2) 50%; transform: translate3d(calc(var(--kp) * var(--fb) * -1), 0, 0) scale(1.28); }
  .rail .mag i { width: var(--fb); flex: none; display: grid; place-items: center; font: 750 16px/1 var(--font-display); font-style: normal; color: var(--text);
    text-shadow: -0.7px 0 rgba(255, 90, 150, 0.55), 0.7px 0 rgba(90, 170, 255, 0.55); transition: width 0.5s var(--ease-spring); }
  .rail .mag i.gone { width: 0; overflow: hidden; }
  .rail button.on { color: var(--text-2); }
  .rail button { position: relative; width: var(--fb); height: 42px; border-radius: 21px; display: grid; place-items: center; font: 750 16px/1 var(--font-display); color: var(--text-2); transition: color 0.25s, width 0.5s var(--ease-spring), opacity 0.3s; }
  .rail button.gone { width: 0; opacity: 0; overflow: hidden; pointer-events: none; }
  .rail button.r::after { content: ''; position: absolute; bottom: 3px; left: 50%; width: 6px; height: 6px; margin-left: -3px; border-radius: 50%; background: #6e92ff; box-shadow: 0 0 8px #6e92ff; }
  .freeb { position: absolute; z-index: 1; left: 12px; top: calc(max(48px, var(--top)) + 66px); height: 36px; padding: 0 14px 0 12px; border-radius: var(--r-full);
    display: flex; align-items: center; gap: 8px; font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text); transition: transform 0.45s var(--ease-bounce), opacity 0.3s; }
  .freeb i { width: 10px; height: 10px; border-radius: 50%; box-shadow: inset 0 0 0 2px var(--success); transition: background 0.2s; }
  .freeb.on i { background: var(--success); }
  .freeb:active { transform: scale(0.94); transition-duration: 80ms; }
  .freeb.away { opacity: 0; pointer-events: none; }
  .fl { margin: 10px 4px 0; font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  .note { position: absolute; z-index: 1; left: 0; right: 0; bottom: calc(var(--safe-bottom) + 84px); margin: 0; text-align: center; font: 550 12px/1.3 var(--font-text); color: var(--text-3);
    transition: opacity 0.25s; }
  .note.away { opacity: 0; pointer-events: none; }
  /* the bottom: the search bar and the exit */
  /* where the app's nav and its map button stand (Nav.svelte), so the closing circle ends on this one */
  .dock { position: absolute; z-index: 2; left: 16px; right: 16px; bottom: calc(var(--safe-bottom) + 10px); display: flex; align-items: center; gap: 8px; transition: transform 0.55s var(--ease-spring), opacity 0.25s; }
  .dock.away { transform: translateY(130%); opacity: 0; pointer-events: none; }
  .bar { position: relative; flex: 1; min-width: 0; height: 60px; border-radius: 30px; display: flex; align-items: center; gap: 10px; padding: 0 16px; font: 600 16px/1 var(--font-text); color: var(--text-2); }
  .bar :global(svg) { color: var(--text); flex: none; }
  .exit { position: relative; width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; color: var(--success); flex: none; }
  /* the same glass as its neighbours, lit from inside in the accent: this is where you are (owner, Oct 29: the solid
     white disc was too loud) */
  .shut { position: relative; width: 54px; height: 54px; border-radius: 50%; display: grid; place-items: center; flex: none; color: var(--accent); }
  .shut::before { content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none;
    background: radial-gradient(circle at 50% 60%, color-mix(in srgb, var(--accent) 28%, transparent), transparent 70%);
    box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--accent) 55%, transparent); }
  .shut > :global(svg) { position: relative; }
  .bar, .exit, .shut { transition: transform 0.45s var(--ease-bounce); }
  .bar:active, .exit:active, .shut:active { transform: scale(0.95); transition-duration: 80ms; }
  /* the room found: a short panel with the way to it */
  .rcard { position: absolute; z-index: 4; left: 0; right: 0; bottom: 0; padding: 8px 16px calc(var(--safe-bottom) + 16px); border-radius: 36px 36px 0 0; background: var(--surface-solid); color: var(--text);
    box-shadow: 0 -20px 60px -20px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.08); animation: rise 0.6s var(--ease-spring); }
  @keyframes rise { from { transform: translate3d(0, 105%, 0); } }
  .grab { display: block; width: 38px; height: 5px; border-radius: 3px; background: var(--line-2); margin: 0 auto 10px; }
  .rhead { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .ptb { width: 28px; height: 28px; border-radius: 50%; display: inline-grid; place-items: center; margin-right: 10px; vertical-align: 2px; background: var(--accent); color: #fff;
    font: 800 15px/1 var(--font-display); box-shadow: 0 0 0 4px rgba(59, 107, 255, 0.25); }
  .rfind { flex: 1; min-width: 0; display: flex; align-items: center; gap: 12px; padding: 10px 14px 10px 10px; border-radius: 22px; background: var(--surface-2); color: var(--text-2); text-align: left; }
  .rfind:active { transform: scale(0.98); }
  .rfind .rt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .rfind b { font: 800 22px/1.15 var(--font-display); letter-spacing: -0.01em; color: var(--text); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .rfind small { font: 550 14px/1.2 var(--font-text); color: var(--text-2); }
  .rfind .ptb { margin: 0; vertical-align: 0; flex: none; }
  .xb { width: 36px; height: 36px; border-radius: 50%; background: var(--surface-2); display: grid; place-items: center; color: var(--text-2); flex: none; }
  .go { width: 100%; margin-top: 12px; height: 56px; border-radius: 28px; display: flex; align-items: center; justify-content: center; gap: 8px; font: 750 17px/1 var(--font-text); color: #fff;
    background: linear-gradient(180deg, #5c85ff, #3b6bff 55%, #3457e0); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 10px 24px -8px rgba(59, 107, 255, 0.8); }
  @media (prefers-reduced-motion: reduce) { .rcard { animation: none; } }
</style>
