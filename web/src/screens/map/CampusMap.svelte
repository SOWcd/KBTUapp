<script lang="ts">
  // The campus map (CONTEXT): a floor of the main building full screen, pinch to zoom and drag to look around, a
  // double tap zooms in or out, the floors 0–5 at the bottom under the thumb. Two versions, switched at the top left
  // (owner, Oct 6): the main one, UNI-Q's plans (credited under the map), and the old one, our vector redraw with red
  // walls (floors 1-5 from the 2023 plans, which nobody updates, so it says so). Opens on a room's floor ("Aud. 305"
  // → 3), rings the room's number and glides in to it (owner, Oct 5: "show where the room is"); a room the plan
  // doesn't number frames its nearest numbers on the floor, "somewhere here, look yourself", or just says it couldn't
  // find it (the old plan won't have it either: owner, Oct 6).
  // While fingers move the plan is only scaled as a picture (smooth); once they let go it is laid out at the new size,
  // so the browser draws it sharp again: the old map's vectors, or the main map's tiles of the level that size needs,
  // only those on screen, over the floor's overview while they come. An animated zoom in (the glide to a room, a double
  // tap) is laid out at the size it lands at before it moves (prepare), so it is sharp all the way. Opened on a room, the
  // whole floor shows first and the landing is prepared and decoded while one looks at it, then it flies in (owner,
  // Oct 12: "show the whole map first, then zoom", "why is it blurry first, then sharp"). The main plans are black on white: the dark look inverts them (the
  // colours keep their hue). The capsule says "Map · floor 3", or "Room 305 · floor 3" (SPEC §8.2). The magnifier at the top
  // turns the whole top row into a search box (owner, Oct 12: one row, not a big box), which finds a room by its number or a hall by its name (roomOf), goes to its floor and glides to it (owner, Oct 12).
  // The sun/moon at the top right turns the map light or dark (owner, Oct 5: "let the student pick right on the map"),
  // the map only and for this look: the app keeps its own theme, and the map opens in it again next time (owner: "I
  // turn white on, look at it, and that's it; the app stays dark"). The panel carries the theme as a class (tokens.css).
  import { flushSync, onMount, tick, untrack } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import Search from '@lucide/svelte/icons/search';
  import Sun from '@lucide/svelte/icons/sun';
  import Moon from '@lucide/svelte/icons/moon';
  import { theme, reveal, paintFor, type Theme } from '../../lib/state/theme.svelte';
  import MapIcon from '@lucide/svelte/icons/map';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, inTelegram } from '../../lib/tg';
  import { FLOORS, TILES, SPOTS, loadFloor, roomOf, floorOf, normRoom, nearRooms, spotOf } from '../../lib/map';
  import uniq from '../../assets/map/uniq-tiles.json';
  import uniqRooms from '../../assets/map/uniq-rooms.json';
  import { glass } from '../../ui/glass';
  import RouteIcon from '@lucide/svelte/icons/route';
  import MapPad, { placeTiles, type PadCheck } from './MapPad.svelte';
  import DoorOpen from '@lucide/svelte/icons/door-open';
  import RouteUI, { type RouteView } from './RouteUI.svelte';
  import { api } from '../../lib/api';

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
  let ver = $state<'main' | 'old'>('main');
  let rt = $state<RouteView>({ graph: null, route: null, step: 0, edit: false, sel: null, moving: false });
  let routing = $state(false), ui = $state<RouteUI>();
  let leaving = $state(untrack(() => exit)); // opened by the "help me get out" link: everyone gets that one (owner, Oct 15)
  async function openRoute(edit = false) {
    haptic.tap();
    if (ver !== 'main') setVer('main');
    if (!rt.graph) rt.graph = await api.mapGraph().catch(() => null);
    if (!rt.graph) { say(t('route.noGraph'), 'pleading_face_3d'); return; }
    if (edit) rt.edit = true; else routing = true;
  }
  if (untrack(() => exit)) void openRoute();
  /** show a step: its floor, framed */
  async function go(f: number, pts: { u: number; v: number }[]) {
    if (f !== cur) { halt(); cur = f; tiles = []; touched++; pickTiles(); }
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
  const edgesHere = $derived.by(() => {
    if (!rt.edit || !rt.graph) return [];
    const by = new Map(rt.graph.n.map((n) => [n.id, n]));
    return rt.graph.e.map(([a, b]) => [by.get(a), by.get(b)]).filter(([a, b]) => a && b && a.f === cur && b.f === cur) as [NonNullable<RouteView['graph']>['n'][0], NonNullable<RouteView['graph']>['n'][0]][];
  });
  const line = (pts: { u: number; v: number }[]) => pts.map((p) => `${p.u * 1000},${p.v * 1000 * AR}`).join(' ');
  const AR = $derived(ver === 'main' ? uniq.h / uniq.w : 1); // the plan's height to its width
  let svg = $state('');
  // another room: a clean plan, without the last one's rings
  $effect(() => { const n = cur; void room; svg = ''; if (ver === 'old') loadFloor(n).then((m) => { if (n === cur) svg = m; }, () => {}); });

  let panel: HTMLDivElement;
  let stage: HTMLDivElement;
  let plan: HTMLDivElement;
  let gone = false;

  // the plan's transform: translate (x, y) then scale s, origin top-left; written straight to the style per frame. It is
  // laid out at scale `base` (drawn sharp there); between base and s it is a CSS scale until the fingers let go.
  let s = 1, x = 0, y = 0, base = 1, settleT = 0;
  const MAX = 8;
  const paint = (ease = '') => { plan.style.transition = ease; plan.style.transform = `translate3d(${x}px,${y}px,0) scale(${s / base})`; };
  /** lay the plan out at the scale it is shown at, in the same place on screen, so the browser draws it sharp */
  function settle() {
    clearTimeout(settleT);
    if (base !== s) { base = s; plan.style.width = `${s * 100}%`; paint(); }
    pickTiles();
  }
  const settleSoon = (ms: number) => { clearTimeout(settleT); settleT = window.setTimeout(settle, ms); };
  /** keep the plan on screen, with half a screen of room past each edge: a corner, or a route under the card, can be
   *  dragged to the middle (owner, Oct 15) */
  function clamped(s: number, x: number, y: number): [number, number] {
    const W = stage.clientWidth, H = stage.clientHeight, pw = W * s, ph = pw * AR; // as wide as the stage at s = 1
    return [Math.min(Math.max(0, W - pw) + W / 2, Math.max(Math.min(0, W - pw) - W / 2, x)),
      Math.min(Math.max(0, H - ph) + H / 2, Math.max(Math.min(0, H - ph) - H / 2, y))];
  }
  const clamp = () => { [x, y] = clamped(s, x, y); };
  function reset() { halt(); s = 1; x = 0; y = Math.max(0, (stage.clientHeight - stage.clientWidth * AR) / 2); base = 1; plan.style.width = ''; tiles = []; clamp(); paint(); }

  // the main map's tiles on screen at scale s and offset (x, y), from the level that size needs; none while the overview will do
  type Tile = { key: string; src: string; l: number; t: number; w: number; h: number };
  let tiles = $state<Tile[]>([]);
  const pickTiles = () => { if (ver === 'main') tiles = tilesAt(s, x, y); };
  function tilesAt(s: number, x: number, y: number): Tile[] {
    const W = stage.clientWidth, H = stage.clientHeight, pw = W * s, ph = pw * AR, T = uniq.tile;
    const need = (pw * Math.min(3, devicePixelRatio || 1)) / 1.4; // device px across the plan; a level may stretch 1.4 times
    if (need <= uniq.w / 4) return [];
    const levels = uniq.floors[cur], i = levels.findIndex((l) => l.w >= need), k = i < 0 ? levels.length - 1 : i, lv = levels[k];
    const cols = Math.ceil(lv.w / T), rows = Math.ceil(lv.h / T);
    const c0 = Math.max(0, Math.floor(((-x / pw) * lv.w) / T)), c1 = Math.min(cols - 1, Math.floor((((W - x) / pw) * lv.w) / T));
    const r0 = Math.max(0, Math.floor(((-y / ph) * lv.h) / T)), r1 = Math.min(rows - 1, Math.floor((((H - y) / ph) * lv.h) / T));
    const next: Tile[] = [];
    for (let r = r0; r <= r1; r++) for (let c = c0; c <= c1; c++) {
      if (lv.has[r * cols + c] !== '1') continue; // blank paper: the overview has it
      const name = `${cur}/${k + 1}/${c}_${r}`; // each tile reaches a pixel into its right and bottom neighbours
      next.push({ key: name, src: `${TILES}f${name}.webp`, l: (c * T * 100) / lv.w, t: (r * T * 100) / lv.h,
        w: ((Math.min(lv.w, c * T + T + 1) - c * T) * 100) / lv.w, h: ((Math.min(lv.h, r * T + T + 1) - r * T) * 100) / lv.h });
    }
    return next;
  }
  /** scale s·k around the point (cx, cy) of the stage, kept on screen: [scale, x, y] */
  function around(k: number, cx: number, cy: number): [number, number, number] {
    const ns = Math.min(MAX, Math.max(1, s * k)), [nx, ny] = clamped(ns, cx - ((cx - x) * ns) / s, cy - ((cy - y) * ns) / s);
    return [ns, nx, ny];
  }
  function zoomAt(k: number, cx: number, cy: number) { [s, x, y] = around(k, cx, cy); paint(); }
  /** The landing, before the move: the tiles it lands on go into the plan, and going in, the plan is laid out at the size
   *  it lands at and shown where it is now (scaled down). WebKit draws a layer at its laid-out size and only stretches
   *  that picture for a transform (GraphicsLayerCA::updateRootRelativeScale), so a small plan scaled up is blurry until
   *  it settles (owner, Oct 7 and Oct 12), while a big one scaled down stays sharp all the way. Going out, the big plan
   *  just shrinks. A 3.2x glide on a phone is about 50 MB of tiles for a moment (WebKit caps a layer at 156). */
  function prepare(ns: number, nx: number, ny: number): Tile[] {
    const next = ver === 'main' ? tilesAt(ns, nx, ny) : [];
    if (next.length) flushSync(() => { tiles = [...tiles.filter((a) => !next.some((b) => b.key === a.key)), ...next]; });
    if (ns > base) { base = ns; plan.style.width = `${ns * 100}%`; paint(); void plan.offsetWidth; }
    return next;
  }
  let anim: Animation | null = null;
  function zoomTo(ns: number, nx: number, ny: number, ms: number) {
    halt();
    prepare(ns, nx, ny);
    // the scale in even steps to the eye (geometric, not linear: a linear one rushed at the start) around the one point of
    // the plan that stays put on screen, so nothing swerves; a pan alone moves straight. Timed by a critically
    // damped spring baked into the frames: off at once, settles without a crawl (owner, Oct 12: an easy ease was "very
    // slow", the spring "was good"; Oct 9: an ease-out one crawled at the end)
    const s0 = s, x0 = x, y0 = y, n = 32, frames: Keyframe[] = [];
    const fx = ns !== s0 ? (x0 - nx) / (ns - s0) : 0, fy = ns !== s0 ? (y0 - ny) / (ns - s0) : 0;
    for (let i = 0; i <= n; i++) {
      const p = i / n, k = i === n ? 1 : 1 - (1 + 10 * p) * Math.exp(-10 * p), sk = s0 * (ns / s0) ** k;
      const xk = ns !== s0 ? x0 + fx * (s0 - sk) : x0 + (nx - x0) * k, yk = ns !== s0 ? y0 + fy * (s0 - sk) : y0 + (ny - y0) * k;
      frames.push({ transform: `translate3d(${xk}px,${yk}px,0) scale(${sk / base})` });
    }
    s = ns; x = nx; y = ny;
    paint();
    anim = plan.animate(frames, { duration: ms, easing: 'linear' });
    anim.onfinish = () => { anim = null; settle(); };
  }
  /** a running zoom stops where it is on screen (a finger, a floor, the other version came) */
  function halt() {
    if (!anim) return;
    const m = new DOMMatrix(getComputedStyle(plan).transform);
    anim.cancel(); anim = null;
    s = m.a * base; x = m.e; y = m.f;
    paint();
  }

  // ---- fingers: one drags, two pinch around their middle; a quick second tap zooms in or out ----
  const pts = new Map<number, { x: number; y: number }>();
  let from: { d: number; cx: number; cy: number } | null = null;
  let lastTap = 0;
  const local = (e: PointerEvent) => { const r = stage.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  function mid() {
    const [a, b] = [...pts.values()];
    return b ? { d: Math.hypot(a.x - b.x, a.y - b.y), cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2 } : { d: 0, cx: a.x, cy: a.y };
  }
  let press: { x: number; y: number; t: number } | null = null; // the editor's tap: a finger down and up in place
  function down(e: PointerEvent) {
    clearTimeout(settleT); clearTimeout(glideT); touched++; halt(); framed = null; // a finger first: the glide gives way
    press = pts.size ? null : { ...local(e), t: performance.now() };
    stage.setPointerCapture(e.pointerId);
    pts.set(e.pointerId, local(e));
    from = mid();
    if (pts.size === 1 && !rt.edit) {
      const now = performance.now();
      if (now - lastTap < 300) { haptic.tap(); zoomTo(...around(s > 1.5 ? 1 / s : 2.5, from.cx, from.cy), 380); lastTap = 0; }
      else lastTap = now;
    }
  }
  function move(e: PointerEvent) {
    if (!pts.has(e.pointerId) || !from) return;
    pts.set(e.pointerId, local(e));
    const m = mid();
    x += m.cx - from.cx; y += m.cy - from.cy;
    if (pts.size > 1 && from.d) zoomAt(m.d / from.d, m.cx, m.cy);
    else { clamp(); paint(); }
    from = m;
  }
  function up(e: PointerEvent) {
    const p = pts.has(e.pointerId) ? local(e) : null;
    pts.delete(e.pointerId); from = pts.size ? mid() : null; if (!pts.size) settleSoon(120);
    // zoomed out, the plan let go anywhere goes back to the middle; zoomed in, it stays where it was left (owner, Oct 15)
    const hy = Math.max(0, (stage.clientHeight - stage.clientWidth * AR) / 2);
    const dragged = !press || !p || Math.hypot(p.x - press.x, p.y - press.y) >= 8; // a tap (a double tap's first) isn't a let-go
    if (!pts.size && !rt.edit && dragged && s < 1.3 && Math.hypot(x, y - hy) > 4) zoomTo(1, 0, hy, 380);
    if (rt.edit && press && p && !pts.size && Math.hypot(p.x - press.x, p.y - press.y) < 8 && performance.now() - press.t < 400) {
      const W = stage.clientWidth * s, u = (p.x - x) / W, v = (p.y - y) / (W * AR);
      const hit = rt.graph?.n.filter((n) => n.f === cur).map((n) => ({ n, d: Math.hypot(x + n.u * W - p.x, y + n.v * W * AR - p.y) }))
        .sort((a, b) => a.d - b.d)[0];
      if (u >= 0 && u <= 1 && v >= 0 && v <= 1) ui?.tap(u, v, hit && hit.d < 22 ? hit.n.id : null);
    }
    press = null;
  }
  function wheel(e: WheelEvent) { e.preventDefault(); halt(); const p = { x: e.clientX - stage.getBoundingClientRect().left, y: e.clientY - stage.getBoundingClientRect().top }; zoomAt(Math.exp(-e.deltaY * 0.002), p.x, p.y); settleSoon(200); }

  /** the circle grows from the switch, as the app's does; Telegram's bars follow once it has covered the screen */
  function flip(from: Element) {
    haptic.select();
    const next = look === 'dark' ? 'light' : 'dark';
    reveal(() => (own = next), () => { if (!gone) paintFor(next); }, from);
  }

  // another floor keeps the view: the floors share one frame, so the same part of the building stays on screen and
  // only the tiles change (owner, Oct 6: "switching floors resets the map's size")
  function pick(n: number) { if (n === cur) return; haptic.select(); halt(); cur = n; tiles = []; touched++; pickTiles(); }
  function setVer(v: 'main' | 'old') { if (v === ver) return; haptic.select(); ver = v; if (v === 'old' && !cur) cur = 1; glided = false; clearTimeout(glideT); touched++; reset(); }

  // the room: its number ringed wherever the plan has it, and once, a beat after the floor shows, a glide in to it
  let glided = false, glideT = 0, touched = 0;
  // the map's controls (owner, Oct 24, mockup design/mock/map.html): the search bar and the exit at the bottom, the floors as
  // a lift panel on the right with the look button above it; every input is our keypad (MapPad), no system keyboard
  let pad = $state(false), menu = $state(false);
  let at = $state<{ f: number; u: number; v: number; label: string } | null>(null); // a found place without a number (canteen)
  const floorName = (n: number) => (n ? t('route.floor', { n }) : t('route.basement'));
  function checkFind(text: string): PadCheck {
    const sp = spotOf(text);
    if (sp) return { ok: true, tone: 'ok', hint: floorName(sp.f ?? floorOf(sp.room) ?? 0) };
    const r = roomOf(text), f = floorOf(r);
    if (!r || f == null) return text.length >= 3 || /[^\d\u0430-\u0433]/.test(text) ? { ok: false, tone: 'no', hint: t('pad.noRoom') } : { ok: false, hint: t('pad.roomHint') };
    return ROOMS[f]?.[r] ? { ok: true, tone: 'ok', hint: floorName(f) } : { ok: true, hint: t('pad.near', { room: r }) };
  }
  /** the keypad's answer: to its floor, ringed, glided to (the room's own effect below), the card under it */
  function found(text: string) {
    haptic.tap(); pad = false; clearTimeout(glideT);
    const sp = spotOf(text);
    if (sp && sp.f != null) {
      room = null; at = { f: sp.f, u: sp.u!, v: sp.v!, label: text }; glided = false;
      if (ver === 'old') { ver = 'main'; reset(); }
      if (sp.f !== cur) { halt(); cur = sp.f; tiles = []; touched++; pickTiles(); }
      glideTo(sp.u!, sp.v!, 3.2, true);
      return;
    }
    const r = roomOf(text);
    if (!r) return;
    at = null; glided = r === room; // the same room again: stay
    room = r;
    const f = floorOf(r)!;
    if (!f && ver === 'old') { ver = 'main'; reset(); } // the basement is on the main map only
    if (f !== cur) { halt(); cur = f; tiles = []; touched++; pickTiles(); }
  }
  const dest = $derived(room ?? at?.label ?? null);
  const cardTitle = $derived(at ? at.label : room ? (SPOTS.find((x) => x.room === room) ? t(`route.spot.${SPOTS.find((x) => x.room === room)!.k}` as 'route.spot.canteen') : t('map.roomTitle', { room })) : '');
  const card = $derived(!pad && !routing && !rt.edit && !!dest);
  function clearFound() { haptic.tap(); room = null; at = null; glided = false; clearTimeout(glideT); fit(); }
  /** the whole floor again, gliding */
  function fit() { halt(); framed = null; zoomTo(1, 0, Math.max(0, (stage.clientHeight - stage.clientWidth * AR) / 2), 420); }
  const railFloors = $derived([5, 4, 3, 2, 1, 0].filter((n) => ver === 'main' || FLOORS[n]));
  /** the glide, to a point of the plan as fractions of its width and height, at least at `zoom` */
  function glideTo(u: number, v: number, zoom = 3.2, fit = false) {
    if (glided) return;
    glided = true;
    glideT = window.setTimeout(async () => { // after onMount: the stage has its size
      if (gone) return;
      const W = stage.clientWidth, ns = fit ? zoom : Math.max(s, zoom), { top, bottom } = fit ? free() : { top: 0, bottom: 0 };
      const [nx, ny] = clamped(ns, W / 2 - u * W * ns, (top + stage.clientHeight - bottom) / 2 - v * W * AR * ns);
      // just opened: the whole floor for a blink (owner, Oct 12: "you can't see where it came from"; "less than a tenth of
      // a second", no waiting for tiles), the landing laid out big meanwhile (prepare: sharp all the way); its tiles come
      // while it moves
      const t0 = ++touched;
      prepare(ns, nx, ny);
      await new Promise((done) => setTimeout(done, Math.max(0, shownAt + 90 - performance.now())));
      await new Promise((done) => requestAnimationFrame(done));
      if (gone || touched !== t0) return; // a finger, a floor or the other version came first
      zoomTo(ns, nx, ny, 800); // the spring: an easy ease (0.95 s, then 0.62 s) was "very slow", 0.52 s "too fast" (owner, Oct 12)
    });
  }
  // the main map: where the number is printed (uniq-rooms.json, read off the plan); 251a is another room than 251
  const spots = $derived(ver !== 'main' ? [] : onRoomFloor ? (ROOMS[cur][room!] ?? []) : at && at.f === cur ? [[at.u, at.v]] : []);
  // not numbered on the plan: its nearest numbers show roughly where it is (nearRooms)
  const near = $derived(ver !== 'main' || !onRoomFloor || spots.length ? [] : nearRooms(ROOMS[cur], room!, AR).map(([, at]) => at));
  /** the stage's part nothing covers: above the bottom card or sheet (data-cover); measured, so the card's height and
   *  the safe areas count. One place for every framing */
  function free() {
    // offsets, not rects: a card still rising (a transform) would measure short
    const H = panel.clientHeight; let bottom = 0;
    panel.querySelectorAll<HTMLElement>('[data-cover]').forEach((el) => { bottom = Math.max(bottom, H - el.offsetTop); });
    return { top: 8, bottom: bottom ? bottom + 12 : 0 };
  }
  /** glide to show all of `pts`, between the buttons at the top and `inset` px at the bottom (a route's card): the whole
   *  step, never closer than it fits (owner, Oct 15: the way didn't fit and he had to find himself) */
  function frame(pts: number[][]) {
    const { top, bottom } = free(), us = pts.map((p) => p[0]), vs = pts.map((p) => p[1]), W = stage.clientWidth, H = stage.clientHeight - top - bottom;
    const bw = Math.max(...us) - Math.min(...us) + 0.08, bh = (Math.max(...vs) - Math.min(...vs)) * AR + 0.08;
    glideTo((Math.min(...us) + Math.max(...us)) / 2, (Math.min(...vs) + Math.max(...vs)) / 2, Math.min(3.2, Math.max(1, Math.min(1 / bw, H / (bh * W)))), true);
  }
  $effect(() => {
    if (ver !== 'main' || !onRoomFloor) return;
    if (spots.length) glideTo(spots[0][0], spots[0][1], 3.2, true); // framed above the room's card
    else if (glided) return;
    else if (near.length) { say(t('map.lookHere', { room: room! }), 'pleading_face_3d'); frame(near); }
    else { glided = true; say(t('map.notFound', { room: room! }), 'pleading_face_3d'); } // the old plan won't have it either
  });
  // the old map: the number is real text in the SVG
  $effect(() => {
    if (ver !== 'old' || !svg || !onRoomFloor) return;
    const el = plan.querySelector('svg');
    if (!el) return;
    const hits = [...el.querySelectorAll<SVGTextElement>('.t-room text')].filter((x) => normRoom(x.textContent ?? '') === room);
    if (!hits.length) { if (!glided) { glided = true; say(t('map.noRoom', { room: room! }), 'pleading_face_3d'); } return; }
    const rings = hits.map((h) => {
      const b = h.getBBox(), c = document.createElementNS('http://www.w3.org/2000/svg', 'circle');
      c.setAttribute('cx', String(b.x + b.width / 2)); c.setAttribute('cy', String(b.y + b.height / 2));
      c.setAttribute('r', String(Math.max(b.width, b.height) / 2 + 9));
      c.setAttribute('class', 'hl');
      if (h.getAttribute('transform')) c.setAttribute('transform', h.getAttribute('transform')!); // a label set sideways
      el.insertBefore(c, el.querySelector('g.t'));
      h.classList.add('hl-t');
      return c;
    });
    // the ring's centre in the plan's own pixels (getCTM: not thrown off by the panel's opening scale), at scale 1
    const m = rings[0].getCTM();
    if (!m) return;
    const c = new DOMPoint(+rings[0].getAttribute('cx')!, +rings[0].getAttribute('cy')!).matrixTransform(m), W = stage.clientWidth * base;
    glideTo(c.x / W, c.y / W);
  });

  // the panel shows at once, or with its glide when it opens on a room (glideTo; a nearly transparent panel still gets painted)
  let appeared = false, shownAt = 0, undoChrome = () => {};
  function appear() {
    if (appeared || gone) return;
    appeared = true; shownAt = performance.now();
    panel.animate([{ opacity: 0, transform: 'scale(0.97)' }, { opacity: 1, transform: 'none' }], { duration: 260, easing: 'cubic-bezier(.2,.9,.25,1)' });
    undoChrome = hideChrome();
  }

  onMount(() => {
    reset();
    appear();
    const ro = new ResizeObserver(() => { clamp(); paint(); clearTimeout(reframeT); reframeT = window.setTimeout(reframe, 200); });
    const d = document.documentElement.dataset;
    d.map = ''; // a toast floats above the floors (Toast.svelte)
    ro.observe(stage);
    stage.addEventListener('wheel', wheel, { passive: false });
    return () => { delete d.map; ro.disconnect(); stage.removeEventListener('wheel', wheel); clearTimeout(settleT); clearTimeout(glideT); undoChrome(); if (own) paintFor(theme.current); };
  });

  function leave() {
    if (gone) return;
    gone = true;
    if (!appeared) { removeOverlay(overlay.id); return; } // closed before it showed
    const a = panel.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });
</script>

<div class="panel theme-{look}" class:main={ver === 'main'} bind:this={panel}>
  {#if !inTelegram}<button class="x" onclick={() => close(overlay.id)} aria-label={t('common.close')}><X size={22} /></button>{/if}
  <div class="stage" bind:this={stage} role="img" aria-label={title} data-noswipe
       onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up}>
    <div class="plan" bind:this={plan} style:aspect-ratio={ver === 'main' ? `${uniq.w} / ${uniq.h}` : '1'}>
      {#if ver === 'main'}
        <div class="sheet">
          {#key cur}<img class="ov" src="{TILES}f{cur}/o.webp" alt="" draggable="false" />{/key}
          {#each tiles as tl (tl.key)}
            <img src={tl.src} alt="" draggable="false" decoding="async" style:left="{tl.l}%" style:top="{tl.t}%" style:width="{tl.w}%" style:height="{tl.h}%" />
          {/each}
        </div>
        {#each spots as [u, v], i (i)}<span class="spot" style:left="{u * 100}%" style:top="{v * 100}%"></span>
          {#if i === 0 && card}<span class="pin flag" style:left="{u * 100}%" style:top="{v * 100}%">{cardTitle}</span>{/if}{/each}
        {#each near as [u, v], i (i)}<span class="spot near" style:left="{u * 100}%" style:top="{v * 100}%"></span>{/each}
        {#if legsHere.length || edgesHere.length}
          <svg class="way" viewBox="0 0 1000 {1000 * AR}" preserveAspectRatio="none" aria-hidden="true">
            {#each edgesHere as [a, b] (a.id + '-' + b.id)}<line x1={a.u * 1000} y1={a.v * 1000 * AR} x2={b.u * 1000} y2={b.v * 1000 * AR} class="edge" />{/each}
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
        {#if rt.edit && rt.graph}
          {#each rt.graph.n.filter((n) => n.f === cur) as n (n.id)}
            <span class="node k{n.k ?? ''}" class:sel={n.id === rt.sel} class:b={n.b} style:left="{n.u * 100}%" style:top="{n.v * 100}%">{n.k === 's' ? 'S' : n.k === 'l' ? 'L' : ''}</span>
          {/each}
        {/if}
      {:else}
        {@html svg}
      {/if}
    </div>
  </div>
  <!-- right edge: the map's look (the menu), the floors as a lift panel ("whole floor" dropped: owner, Oct 24, no use) -->
  <div class="side">
    <button class="rb glass glass-pill" class:on={menu} use:glass onclick={() => { haptic.tap(); menu = !menu; }} aria-label={t('map.look')} aria-expanded={menu}>
      {#if look === 'dark'}<Moon size={20} />{:else}<Sun size={20} />{/if}</button>
    <!-- on the way only the look button stays: the floors move into the step card (owner, Oct 24) -->
    <div class="rail glass glass-pill" class:away={!!rt.route} inert={!!rt.route} use:glass role="tablist" aria-label={t('map.floors')}>
      <span class="knob" style:top="{4 + railFloors.indexOf(cur) * 42}px" aria-hidden="true"></span>
      {#each railFloors as n (n)}<button role="tab" aria-selected={cur === n} class:on={cur === n} class:r={routeFloors.has(n)} onclick={() => pick(n)}
        aria-label={floorName(n)}>{n || t('map.bShort')}</button>{/each}
    </div>
  </div>
  <div class="menu" class:on={menu} inert={!menu}>
    <div class="vseg" class:r={look === 'light'}><span class="knob" aria-hidden="true"></span>
      <button class:on={look === 'dark'} onclick={(e) => { if (look !== 'dark') flip(e.currentTarget); }}>{t('map.dark')}</button>
      <button class:on={look === 'light'} onclick={(e) => { if (look !== 'light') flip(e.currentTarget); }}>{t('map.light')}</button></div>
    <button class="mrow" onclick={() => setVer(ver === 'old' ? 'main' : 'old')} role="switch" aria-checked={ver === 'old'}>
      <span>{t('map.oldPlan')}<small>{ver === 'old' ? t('map.note') : t('map.oldSub')}</small></span><i class="sw" class:on={ver === 'old'}></i></button>
    <p class="credit">{t('map.noteMain')}</p>
  </div>
  {#if menu}<div class="shade" onpointerdown={() => (menu = false)} aria-hidden="true"></div>{/if}
  <!-- the bottom, under the thumb: find a room or place, or get out -->
  <div class="dock" class:away={pad || card || routing || rt.edit} inert={pad || card || routing || rt.edit}>
    <button class="bar glass glass-pill" use:glass onclick={() => { haptic.tap(); menu = false; pad = true; }}><Search size={20} />{t('map.find')}</button>
    <button class="exit glass glass-pill" use:glass onclick={() => { menu = false; leaving = true; void openRoute(); }} aria-label={t('route.out')}><DoorOpen size={24} /></button>
  </div>
  {#if card}
    <div class="rcard" data-cover>
      <span class="grab" aria-hidden="true"></span>
      <div class="rhead"><div><h2><span class="ptb" aria-hidden="true">{t('pad.b')}</span>{cardTitle}</h2><p>{floorName(at ? at.f : (roomFloor ?? 0))}</p></div>
        <button class="xb" onclick={clearFound} aria-label={t('common.close')}><X size={18} /></button></div>
      <div class="btns"><button class="go" onclick={() => { leaving = false; void openRoute(); }}><RouteIcon size={20} />{t('map.routeHere')}</button>
        <button class="ghost" onclick={() => { haptic.tap(); pad = true; }}><Search size={18} />{t('map.other')}</button></div>
    </div>
  {/if}
  {#if pad}<MapPad title={t('pad.findTitle')} go={t('pad.find')} point="b" placeTab={t('pad.place')} groups={[{ tiles: placeTiles() }]} check={checkFind} onsubmit={found} onclose={() => (pad = false)} />{/if}
  {#if routing || rt.edit}
    <RouteUI bind:this={ui} {rt} {cur} {pick} ar={AR} rooms={ROOMS} to={dest} {go} out={leaving} onclose={() => { routing = false; leaving = false; rt.route = null; }} />
  {/if}
</div>

<style>
  .panel { position: absolute; inset: 0; z-index: var(--z-sheet); background: var(--bg); overflow: hidden; }
  /* on the way the floors are the step card's last row (owner, Oct 15: one panel, not two) */
  /* the main map's paper all round, white, or inverted with the plan in the dark look */
  .panel.main { background: #fff; }
  .panel.main.theme-dark { background: #0d0d0d; }
  .x { position: absolute; z-index: 2; left: 12px; top: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2)); width: 38px; height: 38px;
    border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--surface-solid); color: var(--text); }
  .stage { position: absolute; inset: max(48px, var(--top)) 0 0; overflow: hidden; touch-action: none; cursor: grab; }
  .plan { position: absolute; left: 0; top: 0; width: 100%; aspect-ratio: 1; transform-origin: 0 0; will-change: transform;
    user-select: none; -webkit-user-select: none; -webkit-touch-callout: none;
    --m-wall: #d70b19; --m-col: #b9d3bd; --m-col-line: #3a4a3d; --m-ink: #1c1c1e; --m-soft: #a1a1a6; --m-part: #a3192b; --m-dot: #c7c7cc; }
  .theme-dark .plan { --m-wall: #e5484d; --m-col: #3d5444; --m-col-line: #8fb59a; --m-ink: #e5e5ea; --m-soft: #6e6e73; --m-part: #d4525f; --m-dot: #48484a; }
  /* the SVG carries light-theme colours of its own (so it reads on its own); the theme's win here */
  .plan :global(svg) { display: block; width: 100%; height: 100%; }
  .plan :global(.w) { fill: var(--m-wall); }
  .plan :global(.c) { fill: var(--m-col); stroke: var(--m-col-line); }
  .plan :global(.lk) { stroke: var(--m-ink); }
  .plan :global(.k) { fill: var(--m-ink); }
  .plan :global(.lg) { stroke: var(--m-soft); }
  .plan :global(.lr) { stroke: var(--m-part); }
  .plan :global(.o) { fill: var(--m-dot); stroke: var(--m-ink); }
  .plan :global(.t) { fill: var(--text); font-family: var(--font-text); }
  .plan :global(.hl) { fill: var(--accent); fill-opacity: 0.16; stroke: var(--accent); stroke-width: 2.6; animation: ring 1.6s ease-in-out infinite; }
  .plan :global(.hl-t) { fill: var(--accent-text); font-weight: 800; }
  :global(html.lowfx) .plan :global(.hl) { animation: none; } /* power saving: the old plan's ring repainted the SVG every frame */
  @keyframes ring { 50% { stroke-opacity: 0.3; fill-opacity: 0.08; } }
  .sheet { position: absolute; inset: 0; }
  .sheet img { position: absolute; display: block; pointer-events: none; -webkit-user-drag: none; }
  .sheet .ov { inset: 0; width: 100%; height: 100%; }
    .theme-dark .sheet { filter: invert(0.95) hue-rotate(180deg); }
  /* the room found: a ring that breathes out, its name in a blue flag above (mockup, Oct 24) */
  .spot { position: absolute; width: 3.4%; aspect-ratio: 1; border-radius: 50%; transform: translate(-50%, -50%); pointer-events: none;
    border: 3px solid var(--accent-text); background: rgba(59, 107, 255, 0.14); box-shadow: 0 0 22px rgba(59, 107, 255, 0.6); }
  .spot::before, .spot::after { content: ''; position: absolute; inset: -3px; border-radius: 50%; border: 3px solid var(--accent-text); animation: ripple 2s var(--ease-spring) infinite; }
  .spot::after { animation-delay: 1s; }
  @keyframes ripple { from { transform: scale(1); opacity: 0.9; } to { transform: scale(2.2); opacity: 0; } }
  .spot.near { border-style: dashed; border-color: var(--text-3); background: none; box-shadow: none; } /* a neighbour, for bearings */
  .spot.near::before, .spot.near::after { display: none; }
  /* the way: a soft glow under the step on screen, the line, white dots running along it (owner, Oct 24: "chic") */
  .way { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; overflow: visible; }
  .way polyline { fill: none; stroke: var(--accent); stroke-opacity: 0.35; stroke-width: 5; stroke-linecap: round; stroke-linejoin: round; vector-effect: non-scaling-stroke; }
  .way polyline.now { stroke: #6e92ff; stroke-opacity: 1; stroke-width: 7; }
  .way polyline.glow { stroke: var(--accent); stroke-opacity: 0.22; stroke-width: 20; }
  .way polyline.run { stroke: #fff; stroke-opacity: 1; stroke-width: 2.6; stroke-dasharray: 1 13; animation: run 0.9s linear infinite; }
  @keyframes run { to { stroke-dashoffset: -14; } }
  .way .edge { stroke: var(--accent); stroke-opacity: 0.7; stroke-width: 2.5; vector-effect: non-scaling-stroke; }
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
  :global(html.lowfx) .way polyline.run, :global(html.lowfx) .spot::before, :global(html.lowfx) .spot::after, :global(html.lowfx) .pin.end::before { animation: none; }
  @media (prefers-reduced-motion: reduce) { .way polyline.run, .spot::before, .spot::after, .pin.end::before, .pin.flag { animation: none; } }
  .node { position: absolute; width: 12px; height: 12px; transform: translate(-50%, -50%); border-radius: 50%; pointer-events: none;
    background: var(--bg); border: 2.5px solid var(--accent-text); display: grid; place-items: center; font: 800 9px/1 var(--font-text); color: #fff; }
  .node.ks, .node.kl { width: 16px; height: 16px; border-radius: 5px; background: var(--accent-2); border: 0; }
  .node.kx { width: 16px; height: 16px; background: #34c77b; border: 0; }
  .node.b { border-style: dashed; opacity: 0.7; }
  .node.sel { outline: 3px solid var(--text); outline-offset: 2px; }

  /* right edge: the look button, the floors as a lift panel, "whole floor" (owner, Oct 24 mockup) */
  .side { position: absolute; z-index: 2; right: 12px; top: calc(max(48px, var(--top)) + 10px); display: flex; flex-direction: column; align-items: center; gap: 10px; }
  .rb { position: relative; width: 46px; height: 46px; border-radius: 50%; display: grid; place-items: center; color: var(--text); transition: transform 0.45s var(--ease-bounce), opacity 0.3s; }
  .rb:active { transform: scale(0.92); transition-duration: 80ms; }
  .rail { position: relative; display: flex; flex-direction: column; padding: 4px; border-radius: 26px; transition: opacity 0.3s, transform 0.5s var(--ease-spring); }
  .rail.away { opacity: 0; transform: translateX(40px); pointer-events: none; }
  .rail .knob { position: absolute; left: 4px; right: 4px; height: 42px; border-radius: 21px; transition: top 0.5s var(--ease-spring);
    background: linear-gradient(180deg, #fff, #e1e7ff); box-shadow: inset 0 -2px 5px rgba(80, 100, 200, 0.22), inset 0 1px 0 #fff, 0 6px 16px -6px rgba(140, 170, 255, 0.7); }
  .rail button { position: relative; width: 42px; height: 42px; border-radius: 21px; display: grid; place-items: center; font: 750 16px/1 var(--font-display); color: var(--text-2); transition: color 0.25s; }
  .rail button.on { color: #0a0f24; }
  .rail button.r::after { content: ''; position: absolute; right: 3px; top: 50%; width: 6px; height: 6px; margin-top: -3px; border-radius: 50%; background: #6e92ff; box-shadow: 0 0 8px #6e92ff; }
  .menu { position: absolute; z-index: 4; right: 66px; top: calc(max(48px, var(--top)) + 10px); width: 236px; padding: 8px; border-radius: 22px; color: #f5f7ff;
    -webkit-backdrop-filter: blur(28px) saturate(170%); backdrop-filter: blur(28px) saturate(170%); background: linear-gradient(180deg, rgba(40, 46, 80, 0.86), rgba(16, 19, 38, 0.94));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.25), 0 20px 50px -10px rgba(0, 0, 0, 0.7);
    transform-origin: 100% 0; transform: scale(0.6); opacity: 0; pointer-events: none; transition: transform 0.45s var(--ease-spring), opacity 0.2s; }
  .menu.on { transform: none; opacity: 1; pointer-events: auto; }
  /* the light look: a light menu (owner, Oct 24: it was the dark one) */
  .theme-light .menu { color: #0b1433; background: linear-gradient(180deg, rgba(255, 255, 255, 0.92), rgba(240, 243, 252, 0.96)); box-shadow: inset 0 1px 0 #fff, 0 0 0 0.5px rgba(11, 20, 51, 0.12), 0 20px 50px -14px rgba(24, 36, 90, 0.35); }
  .theme-light .vseg { background: rgba(11, 20, 51, 0.06); }
  .theme-light .vseg .knob { background: #0b1433; box-shadow: 0 6px 16px -6px rgba(11, 20, 51, 0.5); }
  .theme-light .vseg button { color: rgba(11, 20, 51, 0.6); }
  .theme-light .vseg button.on { color: #fff; }
  .theme-light .mrow small, .theme-light .credit { color: rgba(11, 20, 51, 0.5); }
  .theme-light .credit { border-top-color: rgba(11, 20, 51, 0.08); }
  .theme-light .sw { background: rgba(11, 20, 51, 0.12); }
  .shade { position: absolute; inset: 0; z-index: 3; }
  .vseg { position: relative; display: flex; padding: 3px; border-radius: 15px; background: rgba(255, 255, 255, 0.07); }
  .vseg .knob { position: absolute; top: 3px; bottom: 3px; left: 3px; width: calc(50% - 3px); border-radius: 12px; transition: transform 0.5s var(--ease-spring);
    background: linear-gradient(180deg, #fff, #e1e7ff); box-shadow: inset 0 1px 0 #fff, 0 6px 16px -6px rgba(140, 170, 255, 0.7); }
  .vseg.r .knob { transform: translateX(100%); }
  .vseg button { position: relative; flex: 1; height: 36px; font: 650 14px/1 var(--font-text); color: rgba(236, 240, 255, 0.7); transition: color 0.25s; }
  .vseg button.on { color: #0a0f24; }
  .mrow { display: flex; width: 100%; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 8px 8px; text-align: left; font: 600 14px/1.25 var(--font-text); color: inherit; }
  .mrow small { display: block; color: rgba(236, 240, 255, 0.5); font: 500 12px/1.3 var(--font-text); }
  .sw { position: relative; flex: none; width: 46px; height: 28px; border-radius: 14px; background: rgba(255, 255, 255, 0.14); transition: background 0.3s; }
  .sw::after { content: ''; position: absolute; left: 2px; top: 2px; width: 24px; height: 24px; border-radius: 50%; background: #fff; transition: transform 0.45s var(--ease-bounce); box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35); }
  .sw.on { background: #3fd68a; }
  .sw.on::after { transform: translateX(18px); }
  .credit { margin: 4px 0 0; padding: 10px 8px 4px; border-top: 1px solid rgba(255, 255, 255, 0.08); color: rgba(236, 240, 255, 0.5); font: 500 12px/1.3 var(--font-text); }
  /* the bottom: the search bar and the exit */
  .dock { position: absolute; z-index: 2; left: 12px; right: 12px; bottom: calc(var(--safe-bottom) + 16px); display: flex; gap: 10px; transition: transform 0.55s var(--ease-spring), opacity 0.25s; }
  .dock.away { transform: translateY(130%); opacity: 0; pointer-events: none; }
  .bar { position: relative; flex: 1; min-width: 0; height: 58px; border-radius: 29px; display: flex; align-items: center; gap: 12px; padding: 0 20px; font: 600 17px/1 var(--font-text); color: var(--text-2); }
  .bar :global(svg) { color: var(--text); flex: none; }
  .exit { position: relative; width: 58px; height: 58px; border-radius: 50%; display: grid; place-items: center; color: var(--success); flex: none; }
  .bar, .exit { transition: transform 0.45s var(--ease-bounce); }
  .bar:active, .exit:active { transform: scale(0.95); transition-duration: 80ms; }
  /* the room found: a short panel with the way to it */
  .rcard { position: absolute; z-index: 4; left: 0; right: 0; bottom: 0; padding: 8px 16px calc(var(--safe-bottom) + 16px); border-radius: 36px 36px 0 0; background: var(--surface-solid); color: var(--text);
    box-shadow: 0 -20px 60px -20px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.08); animation: rise 0.6s var(--ease-spring); }
  @keyframes rise { from { transform: translate3d(0, 105%, 0); } }
  .grab { display: block; width: 38px; height: 5px; border-radius: 3px; background: var(--line-2); margin: 0 auto 10px; }
  .rhead { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; }
  .ptb { width: 28px; height: 28px; border-radius: 50%; display: inline-grid; place-items: center; margin-right: 10px; vertical-align: 2px; background: var(--accent); color: #fff;
    font: 800 15px/1 var(--font-display); box-shadow: 0 0 0 4px rgba(59, 107, 255, 0.25); }
  .rhead h2 { margin: 0; font: 800 24px/1.15 var(--font-display); letter-spacing: -0.01em; }
  .rhead p { margin: 3px 0 0; color: var(--text-2); font: 550 15px/1.3 var(--font-text); }
  .xb { width: 36px; height: 36px; border-radius: 50%; background: var(--surface-2); display: grid; place-items: center; color: var(--text-2); flex: none; }
  .btns { display: flex; gap: 10px; margin-top: 14px; }
  .go { flex: 1; height: 56px; border-radius: 28px; display: flex; align-items: center; justify-content: center; gap: 8px; font: 750 17px/1 var(--font-text); color: #fff;
    background: linear-gradient(180deg, #5c85ff, #3b6bff 55%, #3457e0); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 10px 24px -8px rgba(59, 107, 255, 0.8); }
  .ghost { flex: none; height: 56px; padding: 0 20px; border-radius: 28px; background: var(--surface-2); display: flex; align-items: center; gap: 8px; font: 700 16px/1 var(--font-text); color: var(--text); }
  @media (prefers-reduced-motion: reduce) { .rcard { animation: none; } }
</style>
