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
  import { FLOORS, TILES, loadFloor, roomOf, floorOf, normRoom, nearRooms } from '../../lib/map';
  import uniq from '../../assets/map/uniq-tiles.json';
  import uniqRooms from '../../assets/map/uniq-rooms.json';
  import { glass } from '../../ui/glass';
  import RouteIcon from '@lucide/svelte/icons/route';
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
  let routing = $state(false), ui = $state<RouteUI>(), typing = $state(false);
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
  // no floors bar on the way (the step card has them) or on "Help me get out" (no use for them there)
  const bare = $derived(!!rt.route || (routing && leaving));
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
  let q = $state(''), searching = $state(false), box = $state<HTMLInputElement>();
  /** the row becomes the box; focused in the tap itself, so iOS brings the keyboard up */
  function openSearch() { haptic.tap(); flushSync(() => (searching = true)); box?.focus(); } // no longer inert: focusable in the tap itself, so iOS brings the keyboard up
  function shutSearch() { searching = false; box?.blur(); }
  function find(e: SubmitEvent) {
    e.preventDefault();
    const r = roomOf(q);
    if (!r) { box?.blur(); haptic.error(); say(t('map.noMatch'), 'pleading_face_3d'); return; }
    haptic.tap();
    shutSearch();
    clearTimeout(glideT); glided = r === room; // the same room again: stay
    room = r;
    const f = floorOf(r)!;
    if (!f && ver === 'old') { ver = 'main'; reset(); } // the basement is on the main map only
    if (f !== cur) { halt(); cur = f; tiles = []; touched++; pickTiles(); }
  }
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
  const spots = $derived(ver === 'main' && onRoomFloor ? (ROOMS[cur][room!] ?? []) : []);
  // not numbered on the plan: its nearest numbers show roughly where it is (nearRooms)
  const near = $derived(ver !== 'main' || !onRoomFloor || spots.length ? [] : nearRooms(ROOMS[cur], room!, AR).map(([, at]) => at));
  /** the stage's part nothing covers: below the buttons' row, above the bottom card; measured, so the keyboard, the
   *  card's height and the safe areas all count. One place for every route framing */
  function free() {
    const st = stage.getBoundingClientRect(), lens = panel.querySelector('.lens')?.getBoundingClientRect(), card = panel.querySelector('.card')?.getBoundingClientRect();
    return { top: lens ? Math.max(0, lens.bottom - st.top) + 8 : 0, bottom: card ? Math.max(0, st.bottom - card.top) + 12 : 0 };
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
    if (spots.length) glideTo(spots[0][0], spots[0][1]);
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

<!-- typing (a room for the way out, the route's rooms): the floors hide under the keyboard (owner, Oct 15) -->
<div class="panel theme-{look}" class:main={ver === 'main'} class:typing class:onway={bare} bind:this={panel}
     onfocusin={(e) => (typing = e.target instanceof HTMLInputElement)} onfocusout={() => (typing = false)}>
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
        {#each spots as [u, v], i (i)}<span class="spot" style:left="{u * 100}%" style:top="{v * 100}%"></span>{/each}
        {#each near as [u, v], i (i)}<span class="spot near" style:left="{u * 100}%" style:top="{v * 100}%"></span>{/each}
        {#if legsHere.length || edgesHere.length}
          <svg class="way" viewBox="0 0 1000 {1000 * AR}" preserveAspectRatio="none" aria-hidden="true">
            {#each edgesHere as [a, b] (a.id + '-' + b.id)}<line x1={a.u * 1000} y1={a.v * 1000 * AR} x2={b.u * 1000} y2={b.v * 1000 * AR} class="edge" />{/each}
            {#each legsHere as l (l.i)}<polyline points={line(l.pts)} class:now={l.i === rt.step} />{/each}
          </svg>
        {/if}
        {#each legsHere as l (l.i)}
          {@const a = l.pts[0]}
          {@const b = l.pts[l.pts.length - 1]}
          {#if l.i === 0}
            <!-- where you are: the room's number in a blue badge over the printed one, the line from under it, "You are
                 here" above (owner, Oct 15: the label hid the number, then a ring in plan units looked wrong) -->
            <span class="pin me" style:left="{a.u * 100}%" style:top="{a.v * 100}%">{rt.ends?.[0] ?? ''}</span>
            <span class="pin tag me-tag" style:left="{a.u * 100}%" style:top="{a.v * 100}%">{t('route.here')}</span>
          {:else}<span class="pin start" class:now={l.i === rt.step} style:left="{a.u * 100}%" style:top="{a.v * 100}%"></span>{/if}
          {#if l.to != null}<span class="pin badge" style:left="{b.u * 100}%" style:top="{b.v * 100}%">{l.to > l.f ? '↑' : '↓'}{l.to}</span>
          {:else}<span class="pin end" style:left="{b.u * 100}%" style:top="{b.v * 100}%"></span>
            {#if rt.ends}<span class="pin tag end-tag" style:left="{b.u * 100}%" style:top="{b.v * 100}%">{rt.ends[1]}</span>{/if}{/if}
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
  <!-- the magnifier grows into the box across the row while the row's buttons fade; closing runs it back -->
  <form class="find glass glass-pill" class:open={searching} use:glass role="search" onsubmit={find} inert={!searching}>
    <Search size={18} />
    <input type="search" bind:this={box} bind:value={q} placeholder={t('map.search')} enterkeyhint="search" autocomplete="off" spellcheck="false"
           aria-label={t('map.search')} onblur={() => { if (!q.trim()) searching = false; }} />
    <button type="button" class="shut" onclick={() => { haptic.tap(); shutSearch(); }} aria-label={t('common.close')}><X size={18} /></button>
  </form>
  <div class="row" class:away={searching} inert={searching}>
  <button class="lens glass glass-pill" use:glass onclick={openSearch} aria-label={t('map.search')}><Search size={20} /></button>
  <!-- "Help me get out" for everyone, in the app too, not only by the link (owner, Oct 15); the admin's map is anyone's (Oct 16) -->
  <button class="rb glass glass-pill" use:glass onclick={() => { leaving = true; void openRoute(); }} aria-label={t('route.out')}><DoorOpen size={20} /></button>
  <button class="th glass glass-pill" use:glass onclick={(e) => flip(e.currentTarget)}
          aria-label={t('map.theme')}>{#if look === 'dark'}<Sun size={20} />{:else}<Moon size={20} />{/if}</button>
  <div class="ver glass glass-pill" use:glass role="tablist" aria-label={t('map.version')}>
    <button role="tab" aria-selected={ver === 'main'} class:on={ver === 'main'} onclick={() => setVer('main')}>{t('map.verMain')}</button>
    <button role="tab" aria-selected={ver === 'old'} class:on={ver === 'old'} onclick={() => setVer('old')}>{t('map.verOld')}</button>
  </div>
  </div>
  <!-- from one room to another for everyone, in sight (owner, Oct 19: "routes matter a lot", it had no button left) -->
  <button class="goto glass glass-pill" class:away={searching || routing || rt.edit} inert={searching || routing || rt.edit} use:glass
          onclick={() => { leaving = false; void openRoute(); }}><RouteIcon size={18} />{t('route.title')}</button>
  <p class="note" class:away={searching || routing || rt.edit}>{ver === 'main' ? t('map.noteMain') : t('map.note')}</p>
  {#if routing || rt.edit}
    <RouteUI bind:this={ui} {rt} {cur} ar={AR} rooms={ROOMS} to={room} {go} {pick} out={leaving} onclose={() => { routing = false; leaving = false; rt.route = null; }} />
  {/if}
  <div class="floors glass glass-pill" class:away={searching || typing || bare} inert={searching || typing || bare} use:glass role="tablist" aria-label={t('map.floors')}>
    {#each FLOORS as old, n (n)}
      {#if ver === 'main' || old}<button role="tab" aria-selected={cur === n} class:on={cur === n} class:r={routeFloors.has(n)} onclick={() => pick(n)}>{n}</button>{/if}
    {/each}
  </div>
</div>

<style>
  .panel { position: absolute; inset: 0; z-index: var(--z-sheet); background: var(--bg); overflow: hidden; }
  /* the floors are gone while typing: the card takes their place, right above the keyboard (owner, Oct 15) */
  .panel.typing :global(.card), .panel.onway :global(.card) { bottom: calc(var(--safe-bottom) + 10px); }
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
  .spot { position: absolute; width: 3.4%; aspect-ratio: 1; border-radius: 50%; transform: translate(-50%, -50%); pointer-events: none;
    border: 2.5px solid var(--accent); background: rgba(59, 107, 255, 0.14); animation: spot 1.6s ease-in-out infinite; }
  @keyframes spot { 50% { opacity: 0.45; } }
  .way { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; overflow: visible; }
  .way polyline { fill: none; stroke: var(--accent); stroke-opacity: 0.35; stroke-width: 5; stroke-linecap: round; stroke-linejoin: round; vector-effect: non-scaling-stroke; }
  .way polyline.now { stroke-opacity: 1; stroke-width: 6; }
  .way .edge { stroke: var(--accent); stroke-opacity: 0.7; stroke-width: 2.5; vector-effect: non-scaling-stroke; }
  .pin { position: absolute; transform: translate(-50%, -50%); pointer-events: none; }
  .pin.start { width: 14px; height: 14px; border-radius: 50%; background: var(--bg); border: 3px solid var(--accent); opacity: 0.5; }
  .pin.start.now { opacity: 1; }
  .pin.end { width: 16px; height: 16px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 4px rgba(59, 107, 255, 0.25); }
  .pin.me { min-width: 30px; height: 30px; padding: 0 8px; border-radius: 15px; display: grid; place-items: center; background: var(--accent); color: #fff;
    font: 750 14px/1 var(--font-display); border: 2px solid #fff; box-shadow: 0 0 0 5px rgba(59, 107, 255, 0.28), 0 4px 12px rgba(0, 0, 0, 0.4); }
  .pin.tag.me-tag { transform: translate(-50%, calc(-100% - 26px)); } /* over the badge and its 5px ring; .pin.tag below used to win and sat it on the number (owner, Oct 17) */
  .pin.tag { transform: translate(-50%, calc(-100% - 8px)); padding: 4px 8px; border-radius: 9px; background: var(--text); color: var(--bg); font: 700 12px/1 var(--font-text); white-space: nowrap; }
  .pin.end-tag { transform: translate(-50%, calc(-100% - 14px)); background: var(--accent); color: #fff; }
  .pin.badge { transform: translate(-50%, -130%); padding: 3px 7px; border-radius: 9px; background: var(--accent); color: #fff; font: 700 12px/1 var(--font-text); }
  .node { position: absolute; width: 12px; height: 12px; transform: translate(-50%, -50%); border-radius: 50%; pointer-events: none;
    background: var(--bg); border: 2.5px solid var(--accent-text); display: grid; place-items: center; font: 800 9px/1 var(--font-text); color: #fff; }
  .node.ks, .node.kl { width: 16px; height: 16px; border-radius: 5px; background: var(--accent-2); border: 0; }
  .node.kx { width: 16px; height: 16px; background: #34c77b; border: 0; }
  .node.b { border-style: dashed; opacity: 0.7; }
  .node.sel { outline: 3px solid var(--text); outline-offset: 2px; }
  .spot.near { border-style: dashed; border-color: var(--text-3); background: none; animation: none; } /* a neighbour, for bearings */

  /* always the whole row, clipped: closed, the clip is the magnifier exactly (44 px, 64 px from the right); opening grows
     the clip, so nothing is laid out again per frame (owner, Oct 15: moving left/right made the opening jerky) */
  .find { position: absolute; z-index: 3; left: 12px; right: 12px; top: calc(max(48px, var(--top)) + 10px); height: 44px; display: flex;
    align-items: center; gap: 8px; padding: 0 13px; border-radius: var(--r-full); color: var(--text); overflow: hidden; opacity: 0; pointer-events: none;
    clip-path: inset(0 52px 0 calc(100% - 96px) round 22px);
    transition: clip-path 0.42s var(--ease-spring), opacity 0.16s ease 0.1s; }
  .find.open { opacity: 1; pointer-events: auto; clip-path: inset(0 0 0 0 round 22px); transition: clip-path 0.46s var(--ease-spring), opacity 0.12s ease; }
  .find :global(svg) { flex: none; }
  .find input, .find .shut { opacity: 0; transition: opacity 0.14s ease; }
  .find.open input, .find.open .shut { opacity: 1; transition: opacity 0.24s ease 0.14s; }
  .row { transition: opacity 0.2s ease; }
  .row.away { opacity: 0; }
  .shut { flex: none; width: 32px; height: 32px; margin-right: -8px; display: flex; align-items: center; justify-content: center; color: var(--text-2); }
  .floors, .note, .goto { transition: opacity 0.2s ease, translate 0.3s var(--ease-spring); }
  .floors.away, .note.away, .goto.away { opacity: 0; translate: 0 24px; pointer-events: none; }
  .find input { flex: 1; min-width: 0; height: 100%; border: 0; background: none; outline: none; color: var(--text);
    font: 600 16px/1 var(--font-text); -webkit-appearance: none; appearance: none; }
  .find input::placeholder { color: var(--text-3); }
  .find input::-webkit-search-cancel-button { -webkit-appearance: none; }
  .lens { position: absolute; z-index: 2; right: 64px; top: calc(max(48px, var(--top)) + 10px); width: 44px; height: 44px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; color: var(--text); transition: transform var(--t-fast) var(--ease); }
  .lens:active { transform: scale(0.92); }
  .rb { position: absolute; z-index: 2; right: 116px; top: calc(max(48px, var(--top)) + 10px); width: 44px; height: 44px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; color: var(--text); }
  .floors button.r::after { content: ''; position: absolute; bottom: 4px; width: 5px; height: 5px; border-radius: 50%; background: var(--accent); }
  .th { position: absolute; z-index: 2; right: 12px; top: calc(max(48px, var(--top)) + 10px); width: 44px; height: 44px; border-radius: 50%;
    display: flex; align-items: center; justify-content: center; color: var(--text); transition: transform var(--t-fast) var(--ease); }
  .th:active { transform: scale(0.92); }
  .ver { position: absolute; z-index: 2; left: 12px; top: calc(max(48px, var(--top)) + 10px); display: flex; gap: 2px; padding: 4px; border-radius: var(--r-full); }
  .ver button { height: 36px; padding: 0 14px; border-radius: var(--r-full); font: 650 14px/1 var(--font-text); color: var(--text-2);
    transition: background-color var(--t-fast), color var(--t-fast), transform var(--t-fast) var(--ease); }
  .ver button.on { background: var(--text); color: var(--bg); }
  .ver button:active { transform: scale(0.94); }
  .goto { position: absolute; z-index: 2; left: 50%; bottom: calc(var(--safe-bottom) + 100px); transform: translateX(-50%); height: 44px; padding: 0 18px;
    border-radius: var(--r-full); display: flex; align-items: center; gap: 8px; font: 650 15px/1 var(--font-text); color: var(--text); white-space: nowrap; }
  .note { position: absolute; left: 0; right: 0; bottom: calc(var(--safe-bottom) + 76px); text-align: center; pointer-events: none;
    font: 550 12px/1.3 var(--font-text); color: var(--text-3); }
  .floors { position: absolute; left: 50%; bottom: calc(var(--safe-bottom) + 16px); transform: translateX(-50%); display: flex; gap: 4px; padding: 4px;
    border-radius: var(--r-full); }
  .floors button { position: relative; width: 48px; height: 44px; display: flex; align-items: center; justify-content: center; border-radius: var(--r-full); font: 700 16px/1 var(--font-display); color: var(--text-2);
    transition: background-color var(--t-fast), color var(--t-fast), transform var(--t-fast) var(--ease); }
  .floors button.on { background: var(--text); color: var(--bg); }
  .floors button:active { transform: scale(0.92); }
</style>
