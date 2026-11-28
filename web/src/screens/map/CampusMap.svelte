<script lang="ts" module>
  import { setWorkerUrl, prewarm } from 'maplibre-gl';
  // MapLibre's worker as a file of ours (it looks for one next to itself, which a bundle doesn't have); through the
  // build, so its syntax is lowered for old iOS like the rest
  import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url';
  import { overview as sheet, tilesOf as tilesAt, Z0 as SHEET_Z } from '../../lib/mapgl';
  setWorkerUrl(workerUrl);
  const warmed: HTMLImageElement[] = [];
  /** Ahead of the first tap (lib/map.ts warmMap, in an idle moment after the app starts, so the first tap
   *  opens the map at once): MapLibre's workers started, the floor the map opens on by default decoded as its overview,
   *  its first tiles in the browser's cache. This chunk itself is loaded by whoever calls this */
  export function warm(): void {
    if (warmed.length) return;
    prewarm();
    const at = 2 ** SHEET_Z;
    for (const dark of [false, true]) { // ours opens by default, light or dark by the look (not known here)
      const im = new Image(); im.src = sheet('kbtu', dark, 1); void im.decode().catch(() => {}); warmed.push(im);
      for (const x of [at, at + 1]) for (const y of [at, at + 1]) fetch(tilesAt('kbtu', dark, 1).replace('{z}', String(SHEET_Z + 1)).replace('{x}_{y}', `${x}_${y}`)).catch(() => {});
    }
  }
</script>

<script lang="ts">
  // The campus map (CONTEXT): a floor of the main building full screen, pinch to zoom and drag to look around, a
  // double tap zooms in or out, the floors 0–5 at the bottom under the thumb. Three versions, picked from a list at the top left
  //: ours, KBTU App's, the main one, Uni-Q's plans (credited under the map), and the old one, our redraw of
  // the 2023 plans (floors 1-5, which nobody updates, so it says so; every wall one ink, and a switch lays the plan as it was given over it). Opens on a room's floor ("Aud. 305"
  // → 3), rings the room's number and glides in to it; a room the plan
  // doesn't number frames its nearest numbers on the floor, "somewhere here, look yourself", or just says it couldn't
  // find it (the old plan won't have it either).
  // MapLibre GL moves and draws it (a ready, fast library, not our own pan and zoom): each plan is a
  // pyramid of tiles (lib/mapgl.ts), the level the size on screen needs fading in over the coarser one, and the room
  // numbers are its labels, at a size one can read at any zoom, as many as fit without touching, halls and bigger rooms
  // first, fading in and out (zoomed out, the map is never empty). Opened on a room, the whole floor shows
  // first, then it flies in. The main plans are black on white: the dark look inverts them (the
  // colours keep their hue). The whole screen is the map's: no capsule of ours over it (overlay.bare; Telegram's own
  // Back and menu stay). The magnifier at the top
  // turns the whole top row into a search box (one row, not a big box), which finds a room by its number or a hall by its name (roomOf), goes to its floor and glides to it.
  // The sun/moon at the top right turns the map light or dark, picked right on the map,
  // the map only and for this look: the app keeps its own theme, and the map opens in it again next time (a
  // glance at the light map, and the app stays dark). The panel carries the theme as a class (tokens.css).
  import { onMount, tick, untrack } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import { theme, reveal, paintFor, type Theme } from '../../lib/state/theme.svelte';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t, i18n, placeOf } from '../../lib/i18n/index.svelte';
  import { haptic, inTelegram } from '../../lib/tg';
  import { campusPoint, roomOf, floorOf, nearRooms, spotOf } from '../../lib/map';
  import { campusPlace } from '../../lib/campusPlace';
  import { FRAMES, HAS, widthAt, overview, roomAt, labelsOf, labelData, type Ver } from '../../lib/mapgl';
  import { Map as GLMap, type MapMouseEvent, type StyleSpecification, type GeoJSONSource } from 'maplibre-gl';
  import { inkOf, planSource as planSourceOf, planLayer as planLayerOf, wordLayers, pinData as pinDataOf, pinLayer, styleSync } from './mapLayers';
  import 'maplibre-gl/dist/maplibre-gl.css';
  import uniqRooms from '../../assets/map/uniq-rooms.json';
  import { UNITS, toPlan, fromPlan } from './planUnits';
  import { glass, jelly } from '../../ui/glass';
  import { floorSwipe, railGestures, liftFloor } from './floorSwipe';
  import { camera, MAX, spring } from './mapCamera';
  import { stageGestures } from './mapGestures';
  import MapPad, { placeGroups, exitTiles } from './MapPad.svelte';
  import RouteUI, { type RouteView } from './RouteUI.svelte';
  import MapMarks from './MapMarks.svelte';
  import RoomCard from './RoomCard.svelte';
  import MapTopRow from './MapTopRow.svelte';
  import MapDock from './MapDock.svelte';
  import { floorName, doorNamed, checkFind as checkFindIn, roomTitle } from './mapFind';
  import { flawsOn, sendFlaw, type Flaw } from './mapFlaws';
  import { api } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { takeMapIris, fadeIn, irisIn, fadeOut, irisOut } from './mapIris';
  import type { RoomWeek } from '../../lib/rooms';
  import { freeTints, roomLine as roomLineOf } from './freeRooms';
  import { nowTs } from '../../lib/time';

  let { overlay, place, exit = false }: { overlay: Overlay; place?: string; exit?: boolean } = $props();
  const ROOMS = uniqRooms as unknown as Record<string, number[][]>[]; // by floor: room → where its number is printed
  const campus = untrack(() => campusPlace(place));
  const opening = campus && campusPoint(campus, ROOMS);
  let room = $state(untrack(() => opening ? opening.room || null : roomOf(place)));
  let cur = $state(untrack(() => opening?.f ?? floorOf(place) ?? 1)); // the floor it opens on; the switcher takes over from there
  const roomFloor = $derived(floorOf(room)); // 0: the basement's 1-99
  const onRoomFloor = $derived(!!room && cur === roomFloor);
  const title = $derived(cur === 0 ? t('map.basement') : t('map.title', { n: cur }));
  let own = $state<Theme | null>(null); // the map's theme while it is open; null: the app's
  const look = $derived(own ?? theme.current);
  // which map (a list at the top left): ours, the newest and the default (owner, Nov 20), Uni-Q's, the 2023 plan.
  // Opened on a room or a place: Uni-Q's (its rooms are ringed there, the basement is only there)
  const VERS: Ver[] = ['kbtu', 'main', 'old'];
  let ver = $state<Ver>(untrack(() => (place || exit ? 'main' : 'kbtu')));
  let menu = $state(false);
  let rt = $state<RouteView>({ graph: null, route: null, step: 0 });
  let routing = $state(false);
  let openingRoute = $state(false);
  let routeUI = $state<ReturnType<typeof RouteUI>>();
  let leaving = $state(untrack(() => exit)); // opened by the "help me get out" link: everyone gets that one
  async function openRoute() {
    if (openingRoute || routing) return;
    haptic.tap();
    if (ver !== 'main') setVer('main');
    if (!rt.graph) {
      openingRoute = true;
      await loadGraph();
      openingRoute = false;
    }
    if (overlay.closing) return;
    if (!rt.graph) { say(t('route.noGraph'), 'pleading_face_3d'); return; }
    routing = true;
  }
  async function loadGraph() {
    if (!rt.graph) rt.graph = await api.mapGraph().catch(() => null);
  }
  /** show a step: its floor, framed */
  async function go(f: number, pts: { u: number; v: number }[]) {
    if (f !== cur) { halt(); cur = f; touched++; }
    framed = pts.map((p) => [p.u, p.v]);
    await tick(); // the step's card, not the tall one it replaces (the first step was framed far off)
    reframe();
  }
  // the step on screen: framed again whenever the stage changes size (the keyboard going away after "Lead me out" grows
  // it: else the way sits small at the top) until a finger moves the map
  let framed: number[][] | null = null, reframeT = 0;
  function reframe() { if (!framed || !(rt.route || rt.pick)) return; glided = false; clearTimeout(glideT); frame(framed); }
  const routeFloors = $derived(new Set(rt.route?.legs.map((l) => l.f) ?? []));
  const AR = $derived(FRAMES[ver].ar); // the plan's height to its width
  let panel: HTMLDivElement;
  let stage: HTMLDivElement;
  let gl: HTMLDivElement;
  let first: HTMLDivElement;
  let plan: HTMLDivElement;
  let gone = false;

  // the camera (mapCamera.ts): MapLibre's, the plan's scale 1 when it is as wide as the stage
  let map: GLMap;
  let ready = $state(false);
  const fr = $derived(FRAMES[ver]);
  let side: HTMLDivElement; // the top row: the plan rests below where it starts
  const { W, H, scale, cam, uvAt, within, follow, head, homeK, middle, out, halt, reset, easeFit, grab, rest, free, fitOf } = camera({
    map: () => map, fr: () => fr, ver: () => ver, panel: () => panel, stage: () => stage, side: () => side, plan: () => plan, first: () => first, fingers: () => fingers(),
  });

  // ---- what MapLibre draws: the floor's tiles, the 2023 plan's original over its redraw when asked, the labels ----
  // (the builders are mapLayers.ts; these read the map's version, frame and look now)
  const ink = () => inkOf(ver, look === 'dark');
  const planSource = () => planSourceOf(fr, ver, look === 'dark', cur);
  const planLayer = () => planLayerOf(ink());
  let orig = $state(false); // the 2023 plan as it was given, over our redraw
  // the room looked for is the first to get its place among the labels: its ring is never round nothing
  const words = () => labelData(fr, orig && ver === 'old' ? [] : labelsOf(ver, cur, look === 'dark', (k) => t(`kmap.${k}` as 'kmap.canteen'), room ?? ''));
  const wordsNow = () => `${ver}|${cur}|${look}|${i18n.lang}|${orig}|${room}`;
  const pinData = () => pinDataOf(fr, [...flawsHere, ...(draft && draft.f === cur && draft.ver === ver ? [draft] : [])]);
  $effect(() => { const d = pinData(); if (ready) untrack(() => (map.getSource('pins') as GeoJSONSource).setData(d)); });
  // the map is given what changed since it was last given it (mapLayers.ts styleSync)
  const layers = styleSync(() => map, () => gone);
  $effect(() => {
    if (!ready) return;
    const want = { ver, cur, dark: look === 'dark', fr, wk: wordsNow(), sc: ver === 'old' && orig ? cur : 0, words };
    untrack(() => { layers.sync(want); follow(); });
  });
  // ---- fingers: MapLibre's, and ours on top (mapGestures.ts): a hold in place, the floor swipe while zoomed out; the
  // taps (tap below) ----
  const { down, move, up, fingers, takeHeld, cancel: cancelHold } = stageGestures({
    stage: () => stage, map: () => map, swipe: () => swipe, out,
    touch: (primary) => { menu = false; clearTimeout(glideT); touched++; framed = null; grab(primary); }, // a finger first: the glide gives way
    busy: () => !!(rt.route || rt.pick), hold: flaw, swiped: () => (lastTap = 0),
  });
  let lastTap = 0, tapAt = { x: 0, y: 0 };
  // a long press in place: "something's wrong here" (the map's flaws marked in the app, not by screenshots),
  // a line of text, the spot to the admin's list with its floor and the plan's units
  // where it was marked (the spot was saved, but nothing showed where): a pin at the pressed point while the note
  // is written, a check on it once saved, and my own open ones on the floor as small pins (mapFlaws.ts); a tap on one
  // shows its words
  let mine = $state<Flaw[]>([]);
  let draft = $state<{ ver: Ver; f: number; u: number; v: number } | null>(null);
  let okId = $state(0), seen = $state(0), okT = 0;
  const canFlaw = () => !!session.me?.student && session.board; // where the policy's section 12 is in force (BOARD), for everyone it covers
  $effect(() => { if (canFlaw()) api.mapFlawsMine().then((l) => (mine = l), () => {}); });
  // "free now" by the timetable (lib/rooms): fetched as the map opens, nothing of it shows until it comes or if the
  // server has no timetable (404); the rooms the main map numbers, tinted where their number is printed
  let week = $state<Record<string, RoomWeek> | null>(null), freeOn = $state(false), clock = $state(nowTs());
  api.mapRooms().then((r) => (week = r.rooms), () => {});
  const freeHere = $derived(!week || !freeOn || ver !== 'main' ? [] : freeTints(ROOMS[cur], week, clock));
  const roomLine = $derived(roomLineOf(room, week, clock));
  function toggleFree() { haptic.select(); freeOn = !freeOn; clock = nowTs(); if (freeOn) say(t('map.freeHint'), 'sparkles_3d'); }
  const flawsHere = $derived(flawsOn(mine, cur, ver));
  function flaw(at: { x: number; y: number }): boolean {
    const [u, v] = uvAt(at.x, at.y);
    if (gone || u < 0 || u > 1 || v < 0 || v > 1 || !canFlaw()) return false; // a hold that fired as the map closed
    haptic.soft(); lastTap = 0; seen = 0;
    const [px, py] = toPlan(ver, u, v), f = cur, vr = ver;
    draft = { ver: vr, f, u, v };
    // zoomed in, a spot low on the screen comes up above the sheet the note is written in
    if (!out() && at.y > H() * 0.4) map.panBy([0, at.y - H() * 0.3], { duration: 420 });
    void sendFlaw({ ver: vr, floor: f, u, v, px, py }).then((m) => {
      if (!m || gone) return; // cancelled, failed, or sent as the map closed: nothing of it to mark
      mine = [...mine, m];
      okId = m.id; clearTimeout(okT); okT = window.setTimeout(() => (okId = 0), 1400);
    }).finally(() => (draft = null));
    return true;
  }
  /** a tap (MapLibre's click: a finger that didn't move): my own pin shows what I wrote there, a tinted room opens its
   *  card, a second tap within 300 ms of the first and near it zooms in, or back out to the whole floor */
  function tap(e: MapMouseEvent) {
    if (takeHeld()) return; // the let-go of a hold
    const el = e.originalEvent.target as Element, p = e.point, now = performance.now();
    if (rt.pick) { // a route's end being picked on the map: what is under the finger (a finger's reach, 24 px at this zoom); a second tap still zooms
      const [u, v] = uvAt(p.x, p.y);
      if (u >= 0 && u <= 1 && v >= 0 && v <= 1) routeUI?.mapTap(cur, u, v, 24 / widthAt(fr, map.getZoom()));
    } else {
      const pin = Number(el.closest<HTMLElement>('[data-flaw]')?.dataset.flaw ?? 0), tinted = el.closest<HTMLElement>('[data-room]')?.dataset.room ?? '';
      if (pin || seen) { if (pin) haptic.tap(); seen = pin && pin !== seen ? pin : 0; }
      if (pin) return;
      // a tap on a tinted room: its card, with when it is free (no glide: it is on screen already)
      if (tinted) { haptic.tap(); at = null; room = tinted; glided = true; lastTap = 0; return; }
    }
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
  // only the tiles change (one's place isn't lost with each floor)
  // ---- floors: a tap on the rail, a drag along it, or a sideways
  // swipe on the map while it's zoomed out. The model is the route card's floor row: the plan changes floor in
  // place, the same frame (no sliding pictures), and the knob springs over with the jelly squash. The knob
  // follows the finger while it drags (on the map: a page turn, the finger to the left goes a floor up); the floor
  // changes on the let-go.
  let knob = $state<HTMLSpanElement>();
  let kp = $state(0), dragging = $state(false);
  const idxOf = (n: number) => railFloors.indexOf(n);
  // the knob goes wherever the floor comes from (a tap, a search, a route step, the old plan's narrower rail)
  $effect(() => { const i = idxOf(cur); if (!untrack(() => dragging)) { kp = i; jelly(untrack(() => knob)); } });
  // the change itself: a lift's depth, the floor left sinking away or rising (floorSwipe.ts liftFloor)
  let ghost = $state<string | null>(null), ghostEl = $state<HTMLImageElement>();
  async function goTo(n: number) {
    if (n === cur) return;
    haptic.select(); halt();
    const up = Math.sign(idxOf(n) - idxOf(cur));
    ghost = overview(ver, look === 'dark', cur); // the floor being left, as its overview
    cur = n; touched++;
    await tick();
    if (!ghostEl) return;
    const src = ghost;
    liftFloor(first, ghostEl, map.getCanvas(), up, W() / 2, H() / 2, () => { if (ghost === src) ghost = null; });
  }
  // the floors next to this one decoded ahead (each one's overview: its coarsest tile), so the new one is there the
  // moment the floor changes (a swipe goes one floor; a far one on the rail decodes from the cache under the
  // cross-fade). Only the neighbours: all six were ~60 MB of decoded pixels kept for the whole visit (the glass went grey)
  $effect(() => {
    const i = railFloors.indexOf(cur), dark = ver === 'kbtu' && look === 'dark';
    const held = railFloors.slice(Math.max(0, i - 1), i + 2).map((f) => { const im = new Image(); im.src = overview(ver, dark, f); void im.decode().catch(() => {}); return im; });
    return () => { held.length = 0; };
  });
  function pick(n: number) { void goTo(n); }
  // the gestures themselves: floorSwipe.ts (the rail's listeners too: railGestures)
  const swipe = floorSwipe({
    floors: () => railFloors, cur: () => cur, knobWidth: () => knob?.offsetWidth || 42, stageWidth: W,
    kp: () => kp, setKp: (p) => (kp = p), setDragging: (on) => (dragging = on), goTo: (n) => void goTo(n), settle: () => jelly(knob),
  });
  const { swipeable, swiped: railSwiped } = railGestures(swipe, () => !!rt.route);
  /** another map: the same part of the building stays on screen at the same size (it zoomed out) */
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
  // the map's controls (mockup design/mock/map.html): the search bar and the exit at the bottom, the floors as
  // a lift panel on the right with the look button above it; every input is our keypad (MapPad), no system keyboard
  let pad = $state(false);
  // a found place without a number (canteen, Independence Hall); the schedule can open the map on one
  let at = $state<{ f: number; u: number; v: number; label: string } | null>(untrack(() => {
    if (opening && !room && place) return { f: opening.f, u: opening.u, v: opening.v, label: place };
    const sp = place && !room ? spotOf(place) : null;
    return sp?.f != null ? { f: sp.f, u: sp.u!, v: sp.v!, label: t(`route.spot.${sp.k}` as 'route.spot.canteen') } : null;
  }));
  function openPad() {
    haptic.tap(); pad = true;
    void loadGraph();
  }
  const checkFind = (text: string) => checkFindIn(text, rt.graph, ROOMS);
  /** the keypad's answer: to its floor, ringed, glided to (the room's own effect below), the card under it */
  function found(text: string) {
    haptic.tap(); pad = false; clearTimeout(glideT);
    const dn = doorNamed(rt.graph, text), sp = dn ? { f: dn.f, u: dn.u, v: dn.v } : spotOf(text);
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
  const dest = $derived(room ?? (at ? placeOf(at.label) : null));
  const cardTitle = $derived(at ? dest ?? '' : room ? roomTitle(room) : '');
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
      // just opened: the whole floor for a blink (so one sees where it came from; less than a tenth of
      // a second, no waiting for tiles); the landing's tiles come while it moves, over the coarser ones
      const t0 = ++touched;
      await new Promise((done) => setTimeout(done, Math.max(0, shownAt + 90 - performance.now())));
      await new Promise((done) => requestAnimationFrame(done));
      if (gone || touched !== t0) return; // a finger, a floor or the other version came first
      map.easeTo({ ...to, duration: 800, easing: spring }); // the spring: an easy ease felt too slow at 0.95 s and 0.62 s, too fast at 0.52 s
    });
  }
  // where the room's number stands on this map (Uni-Q's: read off the plan; the drawn ones: their own labels); 251a is
  // another room than 251. A named place is a point of Uni-Q's plan
  const spots = $derived(onRoomFloor ? roomAt(ver, cur, room!) : ver === 'main' && at && at.f === cur ? [[at.u, at.v]] : []);
  // not numbered on the plan: its nearest numbers show roughly where it is (nearRooms)
  const near = $derived(ver !== 'main' || !onRoomFloor || spots.length ? [] : nearRooms(ROOMS[cur], room!, AR).map(([, at]) => at));
  /** glide to show all of `pts` above the card (mapCamera.ts fitOf) */
  function frame(pts: number[][]) { const f = fitOf(pts); glideTo(f.u, f.v, f.zoom, true); }
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
    if (!iris) { fadeIn(panel, overlay); return; }
    ({ under, underEl } = irisIn(iris, panel, stage, overlay, () => gone));
  }
  let under: Animation | null = null, underEl: HTMLElement | null = null;
  const iris = takeMapIris(); // the button it opened from (mapIris.ts), null: it fades
  untrack(() => { if (iris) overlay.holdBack = true; }); // until a moment into the circle (appear); set before the first frame

  onMount(() => {
    const dark = look === 'dark';
    layers.seed({ ver, cur, dark, wk: wordsNow() });
    map = new GLMap({
      container: gl, ...middle(), attributionControl: false, renderWorldCopies: false, fadeDuration: 250,
      dragRotate: false, pitchWithRotate: false, touchPitch: false, keyboard: false, boxZoom: false, doubleClickZoom: false,
      pixelRatio: Math.min(3, devicePixelRatio || 1), transformConstrain: within,
      style: { version: 8, sources: { plan: planSource(), words: { type: 'geojson', data: words() }, pins: { type: 'geojson', data: pinData() } }, layers: [planLayer(), ...wordLayers(fr, ver), pinLayer] } as StyleSpecification,
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
    if (leaving) void openRoute(); else void loadGraph();
    const clockT = setInterval(() => (clock = nowTs()), 60_000); // "free now" moves on with the hour
    return () => {
      gone = true; cancelHold(); clearTimeout(reframeT); clearTimeout(okT); under?.cancel(); // closed without leave(): the page under unscaled
      clearInterval(clockT); delete d.map; underEl?.style.removeProperty('visibility'); ro.disconnect(); clearTimeout(glideT); layers.stop(); undoChrome(); map.remove(); if (own) paintFor(theme.current); };
  });

  function leave() {
    if (gone) return;
    gone = true;
    cancelHold(); // a finger still down: no note's sheet opens over the closing map
    if (!appeared) { removeOverlay(overlay.id); return; } // closed before it showed
    const a = iris ? irisOut(iris, panel, stage, under, underEl, () => { undoChrome(); undoChrome = () => {}; }) : fadeOut(panel);
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
      <!-- what stands on the plan: the room found, the way, the tints, my flaws' marks -->
      <MapMarks {rt} {cur} {ver} ar={AR} {routing} {spots} {near} {card} {cardTitle} {freeHere} {flawsHere} {okId} {seen} {draft} />
    </div>
  </div>
  <!-- the top row: the floors, the map's look at its end (a lift panel on the right covered the plan) -->
  <div class="side" bind:this={side}>
    <!-- the maps, the floors, the look -->
    <MapTopRow bind:menu bind:knob onWay={!!rt.route} {ver} vers={VERS} onver={setVer} floors={railFloors} {routeFloors} {cur} {kp} {dragging}
      {swipeable} swiped={railSwiped} onpick={pick} {look} onflip={flip} />
  </div>
  <!-- "free now": under the maps button, on the main map only (its rooms' numbers are where the tint goes) -->
  {#if week && ver === 'main'}
    <button class="freeb glass glass-pill" class:on={freeOn} class:away={!!rt.route} use:glass onclick={toggleFree} aria-pressed={freeOn}>
      <i aria-hidden="true"></i>{t('map.freeNow')}</button>
  {/if}
  <!-- the 2023 plan as it was given, over our redraw of it, to compare -->
  {#if ver === 'old'}
    <button class="freeb glass glass-pill" class:on={orig} use:glass onclick={() => { haptic.select(); orig = !orig; }} aria-pressed={orig}>
      <i aria-hidden="true"></i>{t('map.orig')}</button>
  {/if}
  <!-- the credit under the map; the bottom row: the way out, the search, the map's own button -->
  <MapDock away={pad || card || routing} busy={openingRoute} note={ver === 'main' ? t('map.noteMain') : ver === 'kbtu' ? t('map.noteKbtu') : t('map.note')}
    onexit={() => { leaving = true; void openRoute(); }} onfind={openPad} onclose={() => close(overlay.id)} />
  {#if card}
    <RoomCard title={cardTitle} floor={floorName(at ? at.f : (roomFloor ?? 0))} line={roomLine} busy={openingRoute}
      onfind={openPad} onclose={clearFound} onroute={() => { leaving = false; void openRoute(); }} />
  {/if}
  {#if pad}<MapPad title={t('pad.findTitle')} go={t('pad.find')} point="b" placeTab={t('pad.entranceOrPlace')} groups={[{ title: t('pad.entrances'), tiles: exitTiles(rt.graph) }, ...placeGroups()]} check={checkFind} onsubmit={found} onclose={() => (pad = false)} />{/if}
  {#if routing}
    <RouteUI bind:this={routeUI} {rt} {cur} {pick} ar={AR} rooms={ROOMS} to={dest} {go} out={leaving} onclose={() => { routing = false; leaving = false; rt.route = null; }} />
  {/if}
</div>

<style>
  :global(.map-halo) {
    position: fixed; z-index: 9999; translate: -50% -50%; border-radius: 50%; pointer-events: none;
    /* clear, not heavy (thinner gets lost, 3.5 px is too much); the glow is stepped rings with no blur,
       a blurred shadow repainted the whole growing circle every frame and the opening stuttered */
    box-shadow: 0 0 0 2.5px rgba(255, 255, 255, 0.95), 0 0 0 5px rgba(150, 180, 255, 0.5), 0 0 0 9px rgba(130, 165, 255, 0.24),
      0 0 0 14px rgba(120, 160, 255, 0.1), inset 0 0 0 4px rgba(150, 180, 255, 0.3), inset 0 0 0 9px rgba(130, 165, 255, 0.12);
  }
  /* the glow the map button takes as it catches the closing circle: a soft light, faded in and out (opacity only) */
  :global(.map-glow) { position: fixed; z-index: 9998; translate: -50% -50%; border-radius: 50%; pointer-events: none;
    background: radial-gradient(circle, rgba(170, 195, 255, 0.55), rgba(120, 160, 255, 0.22) 45%, transparent 70%); }
  .panel { position: absolute; inset: 0; z-index: var(--z-sheet); background: var(--bg); overflow: hidden; }
  /* on the way the floors are the step card's last row (one panel, not two) */
  /* the paper all round: white, or inverted with the plan in the dark look (Uni-Q's and the 2023 plan); ours has its ground */
  .panel.main { background: #fff; }
  .panel.main.theme-dark { background: #0d0d0d; }
  .panel.kbtu { background: #DCE0EA; }
  .panel.kbtu.theme-dark { background: #0A0B10; }
  .x { position: absolute; z-index: 2; left: 12px; top: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2)); width: 38px; height: 38px;
    border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--surface-solid); color: var(--text); }
  .stage { position: absolute; inset: 0; overflow: hidden; touch-action: none; }
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
  /* right edge: the look button, the floors as a lift panel, "whole floor" */
  .side { position: absolute; z-index: 2; left: 12px; right: 12px; top: calc(max(48px, var(--top)) + 10px); display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .freeb { position: absolute; z-index: 1; left: 12px; top: calc(max(48px, var(--top)) + 66px); height: 36px; padding: 0 14px 0 12px; border-radius: var(--r-full);
    display: flex; align-items: center; gap: 8px; font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text); transition: transform 0.45s var(--ease-bounce), opacity 0.3s; }
  .freeb i { width: 10px; height: 10px; border-radius: 50%; box-shadow: inset 0 0 0 2px var(--success); transition: background 0.2s; }
  .freeb.on i { background: var(--success); }
  .freeb:active { transform: scale(0.94); transition-duration: 80ms; }
  .freeb.away { opacity: 0; pointer-events: none; }
</style>
