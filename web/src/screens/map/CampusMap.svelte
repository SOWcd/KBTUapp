<script lang="ts">
  // The campus map (CONTEXT): a floor of the main building full screen, pinch to zoom and drag to look around, a
  // double tap zooms in or out, the floors 0–5 at the bottom under the thumb. Three versions, picked from a list at the top left
  // (owner, Oct 6 and Oct 27; ours, KBTU App's, has floor 1 so far): the main one, UNI-Q's plans (credited under the map), and the old one, our vector redraw with red
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
  import Layers from '@lucide/svelte/icons/layers';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { haptic, inTelegram } from '../../lib/tg';
  import { FLOORS, KBTU_FLOORS, TILES, SPOTS, loadSvg, roomOf, floorOf, normRoom, nearRooms, spotOf } from '../../lib/map';
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
  // which map (owner, Oct 27: a list at the top left): UNI-Q's, ours (floor 1 so far, not the default yet), the 2023 plan
  type Ver = 'main' | 'kbtu' | 'old';
  const VERS: Ver[] = ['kbtu', 'main', 'old']; // ours first in the list (owner, Oct 28); UNI-Q stays the default for now
  let ver = $state<Ver>('main');
  let menu = $state(false);
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
  // our map's words in the UI language: each <text> holds the English and carries data-ru / data-kk
  const shown = $derived(i18n.lang === 'en' ? svg
    : svg.replace(new RegExp(`(<text[^>]*\\sdata-${i18n.lang}="([^"]*)"[^>]*>)[^<]*`, 'g'), (_, open: string, w: string) => open + w));
  // another room: a clean plan, without the last one's rings
  $effect(() => {
    const n = cur, url = ver === 'old' ? FLOORS[n] : ver === 'kbtu' ? KBTU_FLOORS[n]?.[look === 'dark' ? 1 : 0] : null; // ours is drawn light and dark
    void room; svg = '';
    if (url) loadSvg(url).then((m) => { if (n === cur) svg = m; }, () => {});
  });

  let panel: HTMLDivElement;
  let stage: HTMLDivElement;
  let plan: HTMLDivElement;
  let gone = false;

  // the plan's transform: translate (x, y) then scale s, origin top-left; written straight to the style per frame. It is
  // laid out at scale `base` (drawn sharp there); between base and s it is a CSS scale until the fingers let go.
  let s = 1, x = 0, y = 0, base = 1, settleT = 0;
  const MAX = 8;
  const paint = (ease = '') => {
    plan.style.transition = ease; plan.style.transform = `translate3d(${x}px,${y}px,0) scale(${s / base})`;
    const px = stage.clientWidth * s / 1000; // our map's px a unit
    plan.classList.toggle('mid', px >= 0.7); // room numbers and door signs (Oct 28: far off they were specks)
    plan.classList.toggle('near', px >= 1.1); // fine detail: windows, doors, WC fixtures
  };
  /** lay the plan out at the scale it is shown at, in the same place on screen, so the browser draws it sharp */
  function settle() {
    clearTimeout(settleT);
    if (base !== s) { base = s; plan.style.width = `${s * 100}%`; paint(); }
    pickTiles();
  }
  const settleSoon = (ms: number) => { clearTimeout(settleT); settleT = window.setTimeout(settle, ms); };
  /** keep the plan on screen, with half a screen of room past each edge: a corner, or a route under the card, can be
   *  dragged to the middle (owner, Oct 15) */
  function bounds(s: number): [number, number, number, number] {
    const W = stage.clientWidth, H = stage.clientHeight, pw = W * s, ph = pw * AR; // as wide as the stage at s = 1
    return [Math.min(0, W - pw) - W / 2, Math.max(0, W - pw) + W / 2, Math.min(0, H - ph) - H / 2, Math.max(0, H - ph) + H / 2];
  }
  function clamped(s: number, x: number, y: number): [number, number] {
    const [x0, x1, y0, y1] = bounds(s);
    return [Math.min(x1, Math.max(x0, x)), Math.min(y1, Math.max(y0, y))];
  }
  const clamp = () => { [x, y] = clamped(s, x, y); };
  function reset() { halt(); s = 1; x = 0; y = Math.max(0, (stage.clientHeight - stage.clientWidth * AR) / 2); base = 1; plan.style.width = ''; tiles = []; clamp(); paint(); }
  /** the view a floor opens in: on the main map the building (u .12-.85 of UNI-Q's sheet, white margins round it) fills
   *  the width (owner, Oct 24: "why is it so far away"); the old plan has no margins, the whole of it */
  function home(): [number, number, number] {
    const k = ver === 'main' ? 1.3 : 1;
    return [k, ...centered(k)];
  }
  /** where the plan sits zoomed out at scale k: the building in the middle (home's place, at any scale) */
  function centered(k: number): [number, number] {
    const W = stage.clientWidth, H = stage.clientHeight;
    return clamped(k, ver === 'main' ? W / 2 - 0.485 * W * k : 0, (H - W * AR * k) / 2);
  }
  // one finger past where the plan may rest follows it less and less (a rubber band), and the plan springs back on the
  // let-go, its size kept: zoomed out it may rest only in the middle, zoomed in anywhere within bounds() (owner: "the
  // map doesn't listen": it stopped dead at an edge, then flew to the middle and zoomed by itself)
  const out = () => !rt.edit && s < home()[0] * 1.05;
  function rest(): [number, number, number, number] {
    if (!out()) return bounds(s);
    const [cx, cy] = centered(s);
    return [cx, cx, cy, cy];
  }
  const band = (r: number, lo: number, hi: number, size: number) => {
    const o = r < lo ? lo - r : r > hi ? r - hi : 0, k = size * 0.35 * (1 - 1 / (1 + o / size));
    return r < lo ? lo - k : r > hi ? hi + k : r;
  };
  let rx = 0, ry = 0; // one finger's position for the plan without the band
  function goHome() { [s, x, y] = home(); settle(); paint(); }

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
  let lastTap = 0, tapAt = { x: 0, y: 0 };
  const local = (e: PointerEvent) => { const r = stage.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  function mid() {
    const [a, b] = [...pts.values()];
    return b ? { d: Math.hypot(a.x - b.x, a.y - b.y), cx: (a.x + b.x) / 2, cy: (a.y + b.y) / 2 } : { d: 0, cx: a.x, cy: a.y };
  }
  let press: { x: number; y: number; t: number } | null = null; // the editor's tap: a finger down and up in place
  // a long press in place: "something's wrong here" (owner, Oct 29: the map's flaws marked in the app, not by screenshots),
  // a line of text, the spot to the admin's list with its floor and the plan's units
  let holdT: ReturnType<typeof setTimeout> | undefined;
  function flaw(at: { x: number; y: number }) {
    const W = stage.clientWidth * s, u = (at.x - x) / W, v = (at.y - y) / (W * AR);
    if (u < 0 || u > 1 || v < 0 || v > 1 || !session.me?.student || !(session.board || ['admin', 'moderator'].includes(session.me.role))) return; // the team, students with the forum's switch (its policy section)
    haptic.soft(); press = null; lastTap = 0;
    const [px, py] = toPlan(ver, u, v);
    void sheets.askText({ title: t('map.flawTitle'), text: t('map.flawText', { floor: cur }), ok: t('map.flawSend'), cancel: t('common.cancel'), placeholder: t('map.flawPh'), max: 300 })
      .then((body) => body ? api.mapFlaw({ ver, floor: cur, u, v, px, py, body }).then(() => { haptic.ok(); say(t('map.flawThanks'), 'sparkles_3d'); }) : undefined)
      .catch(() => say(t('common.error'), 'pleading_face_3d'));
  }
  function down(e: PointerEvent) {
    menu = false; clearTimeout(settleT); clearTimeout(glideT); touched++; halt(); framed = null; // a finger first: the glide gives way
    press = pts.size ? null : { ...local(e), t: performance.now() };
    clearTimeout(holdT);
    if (press && !rt.edit && !rt.route) { const at = { x: press.x, y: press.y }; holdT = setTimeout(() => flaw(at), 600); }
    stage.setPointerCapture(e.pointerId);
    if (pts.size) swipeEnd(true); // a second finger: a pinch, never a floor
    else if (!rt.route && !rt.edit && s <= home()[0] * 1.05) swipeStart(e.clientX, e.clientY); // zoomed out: a sideways swipe changes the floor
    pts.set(e.pointerId, local(e));
    from = mid();
    rx = x; ry = y;
  }
  function move(e: PointerEvent) {
    if (!pts.has(e.pointerId) || !from) return;
    if (pts.size === 1 && swipeMove(e.clientX, e.clientY)) { press = null; lastTap = 0; clearTimeout(holdT); return; }
    pts.set(e.pointerId, local(e));
    if (press && Math.hypot(local(e).x - press.x, local(e).y - press.y) > 8) clearTimeout(holdT); // it moved: not a hold
    const m = mid();
    if (pts.size > 1 && from.d) { x += m.cx - from.cx; y += m.cy - from.cy; zoomAt(m.d / from.d, m.cx, m.cy); rx = x; ry = y; }
    else {
      rx += m.cx - from.cx; ry += m.cy - from.cy;
      const [x0, x1, y0, y1] = rest();
      x = band(rx, x0, x1, stage.clientWidth); y = band(ry, y0, y1, stage.clientHeight);
      paint();
    }
    from = m;
  }
  function up(e: PointerEvent) {
    clearTimeout(holdT);
    if (sw?.on) { pts.delete(e.pointerId); from = pts.size ? mid() : null; press = null; swipeEnd(); return; }
    sw = null;
    const p = pts.has(e.pointerId) ? local(e) : null;
    pts.delete(e.pointerId); from = pts.size ? mid() : null; if (!pts.size) settleSoon(120);
    // zoomed out, the plan let go anywhere goes back to the middle; zoomed in, it stays where it was left (owner, Oct 15);
    // either way at the size the fingers left it, and only from the rubber band's stretch
    const tap = !!press && !!p && Math.hypot(p.x - press.x, p.y - press.y) < 8 && performance.now() - press.t < 300;
    if (!pts.size && !rt.edit && !tap) {
      const [x0, x1, y0, y1] = rest(), tx = Math.min(x1, Math.max(x0, x)), ty = Math.min(y1, Math.max(y0, y));
      if (Math.hypot(x - tx, y - ty) > 0.5) zoomTo(s, tx, ty, 380);
    }
    // a double tap: two taps, the second let go within 300 ms of the first and near it, zooms in (or back out)
    if (tap && !pts.size && !rt.edit && p) {
      if (lastTap && performance.now() - lastTap < 300 && Math.hypot(p.x - tapAt.x, p.y - tapAt.y) < 40) { haptic.tap(); zoomTo(...around(s > 1.5 ? 1 / s : 2.5, p.x, p.y), 380); lastTap = 0; }
      else { lastTap = performance.now(); tapAt = p; }
    } else if (!tap) lastTap = 0;
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
  // ---- floors (PLAN 97; owner's iPhone videos IMG_6661/6663, Oct 25): a tap on the rail, a drag along it, or a sideways
  // swipe on the map while it's zoomed out. The owner's model is the route card's floor row: the plan changes floor in
  // place, the same frame (no sliding pictures: "disgusting"), and the knob springs over with the jelly squash. The knob
  // follows the finger while it drags (on the map: a page turn, the finger to the left goes a floor up); the floor
  // changes on the let-go.
  let knob = $state<HTMLSpanElement>();
  let kp = $state(0), dragging = $state(false);
  let sw: { x0: number; y0: number; px: number; py: number; dx: number; on: boolean; hist: [number, number][]; rail: boolean; k0: number } | null = null;
  const idxOf = (n: number) => railFloors.indexOf(n);
  // the knob goes wherever the floor comes from (a tap, a search, a route step, the old plan's narrower rail)
  $effect(() => { const i = idxOf(cur); if (!untrack(() => dragging)) { kp = i; jelly(untrack(() => knob)); } });
  // the change itself (owner, Oct 25: "the picture just swaps, give it a push so you feel the floor changed"): a lift's
  // depth. Going up, the floor you leave sinks away under you and the new one comes down from above, settling to size;
  // going down, the other way. Both pictures scale about the middle of the screen; opacity and transform only.
  async function goTo(n: number) {
    if (n === cur) return;
    haptic.select(); halt();
    const up = Math.sign(idxOf(n) - idxOf(cur)), was = ver === 'main' ? plan.querySelector<HTMLImageElement>('.sheet img.ov') : null;
    let ghost: HTMLImageElement | null = null;
    if (was) { ghost = was.cloneNode() as HTMLImageElement; ghost.classList.add('ghost'); was.parentElement!.prepend(ghost); }
    cur = n; tiles = []; touched++; pickTiles();
    if (!ghost) return;
    await tick();
    const k = s / base, o = `${(stage.clientWidth / 2 - x) / k}px ${(stage.clientHeight / 2 - y) / k}px`;
    const fresh = plan.querySelector<HTMLImageElement>('.sheet img.ov:not(.ghost)');
    const ease = { duration: 480, easing: 'cubic-bezier(.3, .75, .25, 1)' };
    ghost.style.transformOrigin = o;
    ghost.animate({ transform: ['scale(1)', `scale(${up > 0 ? 0.9 : 1.1})`], opacity: [1, 0.5, 0] }, ease).finished.catch(() => {}).finally(() => ghost.remove());
    if (fresh) { fresh.style.transformOrigin = o; fresh.animate({ transform: [`scale(${up > 0 ? 1.08 : 0.93})`, 'scale(1)'], opacity: [0, 1] }, ease); }
  }
  // every floor's picture decoded ahead, so the new one is there the moment the floor changes
  const ahead: HTMLImageElement[] = [];
  $effect(() => {
    if (ver !== 'main') return;
    ahead.length = 0;
    for (const f of railFloors) { const im = new Image(); im.src = `${TILES}f${f}/o.webp`; void im.decode().catch(() => {}); ahead.push(im); }
  });
  function pick(n: number) { void goTo(n); }
  function swipeStart(px: number, py: number, rail = false) { sw = { x0: px, y0: py, px: x, py: y, dx: 0, on: false, hist: [], rail, k0: idxOf(cur) }; }
  /** a finger moved: true once it's a floor swipe (the caller then neither pans nor taps) */
  function swipeMove(px: number, py: number): boolean {
    if (!sw) return false;
    const dx = px - sw.x0, dy = py - sw.y0;
    if (!sw.on) {
      if (dx * dx + dy * dy < 144) return false;
      if (Math.abs(dx) <= Math.abs(dy) * 2) { sw = null; return false; } // not clearly sideways (a diagonal pan): the map pans as before
      sw.on = true; dragging = true;
      x = sw.px; y = sw.py; paint(); // the few pixels it panned before the lock go back
    }
    sw.dx = dx;
    const now = performance.now();
    sw.hist.push([now, dx]);
    while (sw.hist.length > 2 && now - sw.hist[0][0] > 90) sw.hist.shift();
    const last = railFloors.length - 1, fb = knob?.offsetWidth || 42;
    // on the rail the knob stays under the finger; on the map a half screen's swipe is one floor, the other way
    let p = sw.rail ? sw.k0 + dx / fb : sw.k0 - Math.max(-1, Math.min(1, dx / (stage.clientWidth / 2)));
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
  // (120, 130), UNI-Q's sheet fitted to it by its room numbers (design/map/tools/clean, median error ~9 units)
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
    haptic.select();
    const W = stage.clientWidth, H = stage.clientHeight, zoomed = !out();
    const P = toPlan(ver, (W / 2 - x) / (W * s), (H / 2 - y) / (W * AR * s)), k = s * UNITS[v] / UNITS[ver];
    ver = v; if ((v === 'old' && !cur) || (v === 'kbtu' && !KBTU_FLOORS[cur])) cur = 1; glided = false; clearTimeout(glideT); touched++; reset();
    if (!zoomed) { goHome(); return; }
    const [u, w] = fromPlan(v, ...P);
    s = Math.min(MAX, Math.max(home()[0], k)); x = W / 2 - u * W * s; y = H / 2 - w * W * AR * s;
    clamp(); settle(); paint();
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
      if (sp.f !== cur) { halt(); cur = sp.f; tiles = []; touched++; pickTiles(); }
      glideTo(sp.u!, sp.v!, 3.2, true);
      return;
    }
    const r = roomOf(text) ?? spotOf(text)?.room ?? null; // a named room: UNI-Q's library is 158
    if (!r) return;
    at = null; glided = r === room; // the same room again: stay
    room = r;
    const f = floorOf(r)!;
    if (ver === 'kbtu' || (!f && ver === 'old')) { ver = 'main'; reset(); } // rooms are ringed on UNI-Q's; the basement is there only
    if (f !== cur) { halt(); cur = f; tiles = []; touched++; pickTiles(); }
  }
  const dest = $derived(room ?? at?.label ?? null);
  const cardTitle = $derived(at ? at.label : room ? (SPOTS.find((x) => x.room === room) ? t(`route.spot.${SPOTS.find((x) => x.room === room)!.k}` as 'route.spot.canteen') : t('map.roomTitle', { room })) : '');
  const card = $derived(!pad && !routing && !rt.edit && !!dest);
  function clearFound() { haptic.tap(); room = null; at = null; glided = false; clearTimeout(glideT); fit(); }
  /** the whole floor again, gliding */
  function fit() { halt(); framed = null; zoomTo(...home(), 420); }
  const railFloors = $derived([0, 1, 2, 3, 4, 5].filter((n) => ver === 'main' || (ver === 'old' ? FLOORS[n] : KBTU_FLOORS[n])));
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
    return { top: 64, bottom: bottom ? bottom + 12 : 0 }; // under the floors row
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
    under = document.querySelector<HTMLElement>('.app > .tab.on')?.animate(
      { transform: ['none', 'scale(0.94)'], opacity: [1, 0.45], transformOrigin: [`${iris.at.x}px ${iris.at.y}px`, `${iris.at.x}px ${iris.at.y}px`] }, { ...o, fill: 'forwards' }) ?? null;
    const h = halo(30, far, o, [1, 1, 1, 0]);
    // the capsule is cut by the circle (owner, Oct 25): inside it already says "Map", outside it's still the old one
    if (iris.cap) split(h, iris.cap, false);
  }
  let under: Animation | null = null;
  // opened from the nav's round button (owner, Oct 25: "one with the bar"): the map grows out of that circle and
  // shrinks back into it; clip-path only, the map under it is painted once
  const reach = ({ x, y }: { x: number; y: number }) => Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
  const iris = (() => {
    const { at, cap } = mapFrom; mapFrom.at = mapFrom.cap = null;
    if (!at || matchMedia('(prefers-reduced-motion: reduce)').matches) return null;
    return Object.assign((r: number) => `circle(${r}px at ${at.x}px ${at.y}px)`, { at, cap });
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
    reset(); goHome();
    if (at) glideTo(at.u, at.v, 3.2, true);
    appear();
    const ro = new ResizeObserver(() => { clamp(); paint(); clearTimeout(reframeT); reframeT = window.setTimeout(reframe, 200); });
    const d = document.documentElement.dataset;
    d.map = ''; // the toast drops under the floor row there (Toast.svelte)
    ro.observe(stage);
    stage.addEventListener('wheel', wheel, { passive: false });
    return () => { delete d.map; ro.disconnect(); stage.removeEventListener('wheel', wheel); clearTimeout(settleT); clearTimeout(glideT); undoChrome(); if (own) paintFor(theme.current); };
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
      const b = document.querySelector<HTMLElement>('.mapb'), dock = b?.parentElement;
      const bt = b?.getBoundingClientRect(), dm = dock && getComputedStyle(dock).transform !== 'none' ? new DOMMatrix(getComputedStyle(dock).transform) : null;
      const c = bt ? { x: bt.left + bt.width / 2 - (dm?.e ?? 0), y: bt.top + bt.height / 2 - (dm?.f ?? 0) } : iris.at;
      const end = bt ? bt.width / 2 : 30, far = reach(c);
      const circle = (r: number) => `circle(${r}px at ${c.x}px ${c.y}px)`;
      const h = halo(far, end, o, [1, 1, 1], c); // held to the end: the ripples take over from it at the button's size
      if (mapCap) split(h, mapCap, true, c);
      undoChrome(); undoChrome = () => {}; // the capsule and the nav come back now, the circle uncovers them
      stage.animate({ transform: ['none', 'scale(1.06)'] }, { ...o, fill: 'forwards' });
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

<div class="panel theme-{look}" class:main={ver === 'main'} bind:this={panel}>
  {#if !inTelegram}<button class="x" onclick={() => close(overlay.id)} aria-label={t('common.close')}><X size={22} /></button>{/if}
  <div class="stage" bind:this={stage} role="img" aria-label={title}
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
        {@html shown}
      {/if}
    </div>
  </div>
  <!-- the top row: the floors, the map's look at its end (owner, Oct 24: a lift panel on the right covered the plan) -->
  <div class="side">
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
  <!-- the credit, and the old plan for who wants it, under the map as before the redo -->
  <p class="note" class:away={pad || card || routing || rt.edit}>{ver === 'main' ? t('map.noteMain') : ver === 'kbtu' ? t('map.noteKbtu') : t('map.note')}</p>
  <!-- the bottom, under the thumb (owner's layout, Oct 26): the way out small on the left, the search, and on the right
       the app's own map button, lit: a tap there closes the map, as the button opened it -->
  <div class="dock" class:away={pad || card || routing || rt.edit} inert={pad || card || routing || rt.edit}>
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
      <button class="go" onclick={() => { leaving = false; void openRoute(); }}><RouteIcon size={20} />{t('map.routeHere')}</button>
    </div>
  {/if}
  {#if pad}<MapPad title={t('pad.findTitle')} go={t('pad.find')} point="b" placeTab={t('pad.entranceOrPlace')} groups={[{ title: t('pad.entrances'), tiles: exitTiles(rt.graph) }, ...placeGroups()]} check={checkFind} onsubmit={found} onclose={() => (pad = false)} />{/if}
  {#if routing || rt.edit}
    <RouteUI bind:this={ui} {rt} {cur} {pick} ar={AR} rooms={ROOMS} to={dest} {go} out={leaving} onclose={() => { routing = false; leaving = false; rt.route = null; }} />
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
  /* the main map's paper all round, white, or inverted with the plan in the dark look */
  .panel.main { background: #fff; }
  .panel.main.theme-dark { background: #0d0d0d; }
  .x { position: absolute; z-index: 2; left: 12px; top: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2)); width: 38px; height: 38px;
    border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--surface-solid); color: var(--text); }
  .stage { position: absolute; inset: max(48px, var(--top)) 0 0; overflow: hidden; touch-action: none; cursor: grab; }
  .rail { touch-action: none; }
  .plan { position: absolute; left: 0; top: 0; width: 100%; aspect-ratio: 1; transform-origin: 0 0; will-change: transform;
    user-select: none; -webkit-user-select: none; -webkit-touch-callout: none;
    --m-wall: #d70b19; --m-col: #b9d3bd; --m-col-line: #3a4a3d; --m-ink: #1c1c1e; --m-soft: #a1a1a6; --m-part: #a3192b; --m-dot: #c7c7cc; }
  .theme-dark .plan { --m-wall: #e5484d; --m-col: #3d5444; --m-col-line: #8fb59a; --m-ink: #e5e5ea; --m-soft: #6e6e73; --m-part: #d4525f; --m-dot: #48484a; }
  /* the SVG carries light-theme colours of its own (so it reads on its own); the theme's win here */
  .plan :global(svg) { display: block; width: 100%; height: 100%; }
  .plan :global(.fine) { opacity: 0; transition: opacity 0.25s; }
  .plan:global(.near) :global(.fine) { opacity: 1; }
  .plan:global(.near) :global(.shade) { display: none; } /* the soft shadow's blur, redrawn over a plan laid out 8x wide, made zooming lag; up close it's off screen anyway */
  .plan :global(.mid) { opacity: 0; transition: opacity 0.25s; }
  .plan:global(.mid) :global(.mid) { opacity: 1; }
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
  /* on each picture, not the sheet: iOS stopped drawing the sheet's filter once the iris animated the panel and the
     stage over it (owner's screenshot, Oct 26: a white plan in the dark look) */
  .theme-dark .sheet img { filter: invert(0.95) hue-rotate(180deg); }
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
  .shut { position: relative; width: 60px; height: 60px; border-radius: 50%; display: grid; place-items: center; flex: none; color: var(--accent); }
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
