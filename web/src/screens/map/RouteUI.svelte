<script lang="ts" module>
  import type { Graph, Leg, MapNode, Pt, Route } from '../../lib/route';
  /** What the map draws for routes (CampusMap owns it): the graph, the chosen route and its step */
  export type RouteView = { graph: Graph | null; route: Route | null; step: number; ends?: [string, string]; pick?: Pick };
  /** an end being picked on the map: A or B, and what the last tap (or the typed room) found there */
  export type Pick = { end: 'a' | 'b'; at: Pt | null };
</script>

<script lang="ts">
  // Indoor routes on the main map: "How to get there" (from a room or an entrance to a
  // room: fastest by stairs, by lift, another staircase), "How do I get out?" (the exits open now, nearest first), the
  // way step by step, floor by floor. (The graph's editor went with its save route: the graph is edited in the repo.)
  import { untrack } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import Check from '@lucide/svelte/icons/check';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Zap from '@lucide/svelte/icons/zap';
  import ArrowUpDown from '@lucide/svelte/icons/arrow-up-down';
  import Shuffle from '@lucide/svelte/icons/shuffle';
  import DoorOpen from '@lucide/svelte/icons/door-open';
  import Pencil from '@lucide/svelte/icons/pencil';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { say } from '../../lib/state/ui.svelte';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import { roomOf, spotOf, adminZone, locate, tapAt } from '../../lib/map';
  import { attach, routes, openAt, showsOpen, examOnly, liftRush, RUSH_WAIT, type Mode } from '../../lib/route';
  import { glass, refract, jelly } from '../../ui/glass';
  import MapPad, { placeGroups, exitTiles, doorHint, adminNote, type PadCheck } from './MapPad.svelte';

  let { rt, cur, ar, rooms, to = null, out = false, go, pick, onclose }: {
    rt: RouteView; cur: number; ar: number; rooms: Record<string, number[][]>[]; to?: string | null; out?: boolean;
    go: (f: number, pts: { u: number; v: number }[]) => void; pick: (f: number) => void; onclose: () => void;
  } = $props();

  // ---- finding the way: where to comes from the room card, where from from the keypad (MapPad), then the ways; either
  // end can be typed again (its row in the ways) or tapped on the map (the keypad's map button: a room, an entrance, a
  // named place, or just a point) ----
  type End = 'a' | 'b';
  type P = Pt & { room: string; spot?: string; near?: string };
  let from = $state(''), dest = $state(untrack(() => to ?? '')), leaving = $state(untrack(() => out)); // leaving: "Help me get out"
  /** a point tapped on the map with nothing named there: that end is the point itself */
  let pins = $state<Record<End, Pt | null>>({ a: null, b: null });
  /** what is being set now: an end on the keypad or on the map; null: both are, the ways show */
  let edit = $state<{ end: End; by: 'pad' | 'map' } | null>({ end: 'a', by: 'pad' });
  /** on the map: what the last tap found (a name, or the point alone) */
  let cand = $state<{ text: string; pin: Pt | null } | null>(null);
  const spotName = (k: string) => t(`route.spot.${k}` as 'route.spot.canteen');
  /** an entrance by its name on the graph: a start too (A16: people come in from Tole bi, Kazybek bi, Panfilov) */
  const exitNamed = (text: string) => rt.graph?.n.find((n) => n.k === 'x' && n.name === text) ?? null;
  const exits = $derived(exitTiles(rt.graph));
  /** a picked entrance that won't open now: said by its name, the way still goes */
  const shut = (text: string) => { const n = exitNamed(text); return !n ? (adminZone(roomOf(text) ?? spotOf(text)?.room) ? t('route.admin') : '') : n.e ? t('pad.evac') : showsOpen(n, new Date()) ? '' : t(examOnly(n, new Date()) ? 'pad.exam' : 'pad.closed'); };
  /** a text as a point on its floor (lib/map locate): where its number is printed, else its door, else its nearest
   *  numbered neighbour, "somewhere here" (435 isn't on the plan, lead to where it most likely is) */
  function place(text: string): P | null {
    const p = locate(text, rooms, rt.graph?.n ?? [], ar);
    return p?.spot ? { ...p, room: spotName(p.spot) } : p;
  }
  const textOf = (e: End) => (e === 'a' ? from : dest);
  /** an end as a point: the one tapped, or where its text is */
  const endAt = (e: End): P | null => { const pin = pins[e]; return pin ? { ...pin, room: '' } : place(textOf(e)); };
  /** an end as the ways and the header name it */
  const label = (e: End) => { const pin = pins[e]; return pin ? t('route.pin', { floor: floorName(pin.f) }) : roomOf(textOf(e)) ?? textOf(e); };
  function optionsFor(p: P | null, out: boolean): { route: Route; exit?: MapNode }[] {
    const g = rt.graph;
    if (!g || !p) return [];
    const a = { at: attach(g, p, ar, p.room || undefined), pt: p as Pt };
    if (out) { // the nearest exit open now, one answer; the backup (the night post) whenever none other is open,
      // its own hours or not (Saturday 20-22 had no door at all and the button went dead)
      const now = new Date(), main = g.n.filter((x) => x.k === 'x' && !x.b && !x.e && openAt(x, now));
      const best = (main.length ? main : g.n.filter((x) => x.k === 'x' && x.b)).map((x) => ({ route: routes(g, ar, a, { at: [[x.id, 0]] })[0], exit: x }))
        .filter((o) => o.route).sort((p, q) => p.route.secs - q.route.secs)[0];
      return best ? [best] : [];
    }
    const b = endAt('b');
    return b ? routes(g, ar, a, { at: attach(g, b, ar, b.room || undefined), pt: b }).map((route) => ({ route })) : [];
  }
  const options = $derived(edit ? [] : optionsFor(endAt('a'), false));
  const rush = $derived(!edit && liftRush(new Date())); // the break between classes: the lifts are packed; read when the ways show
  const secs = (r: Route) => r.secs + (r.mode === 'lift' && rush ? RUSH_WAIT : 0);
  /** the keypad's line under the number: where that is, or the exit it leads to */
  function check(text: string): PadCheck {
    const p = text.trim() ? place(text) : null;
    if (!p) return text.length >= 3 || /[^\d\u0430-\u0433]/.test(text) ? { ok: false, tone: 'no', hint: leaving ? t('route.helpUnknown') : t('pad.noRoom') }
      : { ok: false, hint: leaving ? t('pad.outHint') : t('pad.roomHint') };
    if (leaving) {
      const o = optionsFor(place(text), true)[0];
      return o?.exit ? { ok: true, tone: 'ok', hint: `${o.exit.name} \u00b7 ${t('route.openTill', { time: hours(o.exit) }).replace(/^./, (c) => c.toLowerCase())} \u00b7 ${t('route.min', { n: mins(o.route.secs) })}` }
        : { ok: false, tone: 'no', hint: t('route.noExit') };
    }
    return { ok: true, tone: 'ok', hint: exitNamed(text) ? doorHint(exitNamed(text)!, floorName(p.f)) : p.near ? t('pad.near', { room: p.near }) : floorName(p.f) + adminNote(p.room) };
  }
  const mins = (s: number) => Math.max(1, Math.round(s / 60));
  const ICON: Record<Mode, typeof Zap> = { fast: Zap, lift: ArrowUpDown, alt: Shuffle };
  let chosen = $state<{ route: Route; exit?: MapNode } | null>(null);
  function start(o: { route: Route; exit?: MapNode }) {
    haptic.tap();
    chosen = o; rt.route = o.route; rt.ends = [label('a'), o.exit?.name ?? label('b')]; show(0);
  }
  let drop = $state<HTMLSpanElement>();
  $effect(() => { void cur; jelly(drop); }); // the floors' drop squashes as it slides, as the tab bar's does
  function show(i: number) { rt.step = i; const leg = rt.route!.legs[i]; go(leg.f, leg.pts); }
  function stop() { haptic.tap(); chosen = null; rt.route = null; rt.ends = undefined; onclose(); }
  /** the step card's X: back to the ways, A kept (looked at the fast one, wants the lift); the exit has one way */
  function toWays() { if (leaving) return stop(); haptic.tap(); chosen = null; rt.route = null; rt.ends = undefined; }
  const hours = (x: MapNode): string => { const d = new Date(), h = x.h?.[d.getDay() === 0 ? 2 : d.getDay() === 6 ? 1 : 0]; return h ? h.split('-')[1] : ''; };
  function floorName(n: number) { return n ? t('route.floor', { n }) : t('route.basement'); }
  /** a step in words: walk past the named points to the stairs or lift and go up or down, or arrive */
  function words(i: number): string {
    const route = rt.route!, leg = route.legs[i], last = i === route.legs.length - 1;
    const past = leg.pts.slice(1, -1).map((p) => p.node?.name === '\u0434\u0432\u043e\u0440' ? t('route.yard') : p.node?.name).filter((x, j, all): x is string => !!x && all.indexOf(x) === j && !p_isEnd(x) && x !== from); // not "via Tole bi" to someone coming in there
    const via = past.length ? ' ' + t('route.past', { names: past.join(', ') }) : '';
    if (!last) {
      const lift = leg.up?.k === 'l', up = leg.to! > leg.f;
      if (leg.up?.s === 0) return t('route.toYard') + via; // a level door, no stairs
      return t(lift ? (up ? 'route.liftUp' : 'route.liftDown') : up ? 'route.stairsUp' : 'route.stairsDown', { floor: floorName(leg.to!), near: nearRoom(leg) }).replace(/^./, (c) => c.toUpperCase()) + via; // kk: no room, a small letter first
    }
    const p = chosen?.exit ? null : endAt('b');
    return (chosen?.exit ? t('route.toExit', { name: chosen.exit.name! }) : pins.b ? t('route.toPin') : p?.near ? t('route.toNear', { room: p.near, near: p.room })
      : roomOf(dest) ? t('route.toRoom', { room: roomOf(dest)! }) : t('route.toPlace', { name: spotOf(dest) ? dest : p?.room ?? dest })) + via;
  }
  /** which stairs: " by" the room whose door is nearest to them, or nothing, "the stairs by 384" (a friend's note; a floor has several) */
  function nearRoom(leg: Leg): string {
    const s = leg.up ?? leg.pts[leg.pts.length - 1], by = (n: MapNode) => Math.hypot(n.u - s.u, (n.v - s.v) * ar);
    const ok = (r: string) => /^\d/.test(r) && r !== roomOf(from); // not "the stairs by 351" to someone standing at 351
    // only a door right by them: a far one names the stairs on the other side ("the stairs by 728" sent left)
    const doors = rt.graph!.n.filter((n) => n.f === leg.f && n.r?.some(ok) && by(n) < 0.1).sort((x, y) => by(x) - by(y));
    const r = doors[0]?.r!.find(ok);
    return r ? t('route.by', { room: r }) : '';
  }
  const p_isEnd = (name: string) => name === chosen?.exit?.name;

  // ---- an end on the map ----
  /** the keypad's map button: the typed place shown on the map (the timetable's "Aud. 305" typed in), or, nothing
   *  found, the map to tap on */
  function see(text: string) {
    haptic.tap();
    const e = edit!.end, p = text.trim() ? place(text) : null;
    edit = { end: e, by: 'map' };
    choose(p ? { text, pin: null } : null, p);
    if (p) go(p.f, [p]);
  }
  function choose(c: typeof cand, p: Pt | null) { cand = c; rt.pick = { end: edit!.end, at: p && { f: p.f, u: p.u, v: p.v } }; }
  /** a tap on the map while an end is picked there (CampusMap's tap): what is under the finger, within reach (a
   *  fraction of the plan's width), or the point itself. false: not picking, the map's own tap goes on */
  export function mapTap(f: number, u: number, v: number, reach: number): boolean {
    if (edit?.by !== 'map') return false;
    haptic.select();
    const hit = tapAt({ f, u, v }, rooms, rt.graph?.n ?? [], ar, reach), text = hit?.exit ?? (hit?.spot ? spotName(hit.spot) : hit?.room);
    const p = text ? place(text) : null;
    choose(text && p ? { text, pin: null } : { text: '', pin: { f, u, v } }, p ?? { f, u, v });
    return true;
  }
  /** the end set: the ways (both ends known) */
  function set(e: End, text: string, pin: Pt | null = null) {
    if (e === 'a') from = text; else dest = text;
    pins[e] = pin; cand = null; rt.pick = undefined; edit = null;
  }
  /** back from the keypad: to the ways when there are any to go back to, else out of the routes */
  function back() { cand = null; rt.pick = undefined; if (edit?.by === 'map') edit = { end: edit.end, by: 'pad' }; else if (from || pins.a) edit = null; else onclose(); }
  const candName = $derived(cand ? (cand.pin ? t('route.pin', { floor: floorName(cand.pin.f) }) : roomOf(cand.text) ?? cand.text) : '');
  const candHint = $derived.by(() => {
    if (!cand) return t('route.tapHint');
    if (cand.pin) return t('route.pinHint');
    const p = place(cand.text);
    return p ? (exitNamed(cand.text) ? doorHint(exitNamed(cand.text)!, floorName(p.f)) : p.near ? t('pad.near', { room: p.near }) : floorName(p.f) + adminNote(p.room)) : '';
  });

</script>

{#if chosen && rt.route}
  {@const n = rt.route.legs.length}
  <!-- the step on the way: glass over the plan, a bar per step; the floors are the rail's -->
  <div class="card step glass glass-sheet" data-cover use:glass={{ bloom: true }} use:refract>
    <div class="top"><span>{t('route.step', { i: rt.step + 1, n })} · {floorName(rt.route.legs[rt.step].f)} · {t('route.min', { n: mins(secs(rt.route)) })}</span>
      <button onclick={toWays} aria-label={t('common.close')}><X size={18} /></button></div>
    <div class="bars" aria-hidden="true">{#each rt.route.legs as _, i (i)}<i class:on={i <= rt.step}></i>{/each}</div>
    <div class="nav">{#key rt.step}<p class="txt">{words(rt.step)}</p>{/key}
      {#if n > 1}<button disabled={rt.step === 0} onclick={() => { haptic.tap(); show(rt.step - 1); }} aria-label={t('route.back')}><ChevronLeft size={22} /></button>{/if}
      {#if rt.step < n - 1}<button class="p" onclick={() => { haptic.tap(); show(rt.step + 1); }} aria-label={t('route.next')}><ChevronRight size={22} /></button>
      {:else}<button class="p ok" onclick={() => { haptic.ok(); say(t('pad.arrived'), 'partying_face_3d'); stop(); }} aria-label={t('pad.arrived')}><Check size={22} /></button>{/if}
    </div>
    <!-- on the way the floors are the card's last row, the rail is gone (it hid the way) -->
    <div class="fls" role="tablist" aria-label={t('map.floors')}>
      <span class="drop" bind:this={drop} style:left="calc(3px + (100% - 6px) * {cur} / 6)" aria-hidden="true"></span>
      {#each [0, 1, 2, 3, 4, 5] as f (f)}<button role="tab" aria-selected={cur === f} class:on={cur === f} class:r={rt.route.legs.some((l) => l.f === f)} onclick={() => pick(f)}>{f || t('map.bShort')}</button>{/each}
    </div>
  </div>
{:else if leaving}
  <MapPad title={t('pad.whereTitle')} go={t('route.lead')} point="a" placeTab={t('pad.place')} groups={placeGroups()} {check}
          onsubmit={(v) => { from = v; const o = optionsFor(place(v), true)[0]; if (o) start(o); }} {onclose} />
{:else if edit?.by === 'map'}
  {@const e = edit.end}
  <!-- an end on the map: tap a room, an entrance, a place or any point; the map stays free to move above the card -->
  <div class="card pick glass glass-sheet pt-{e}" data-cover use:glass={{ bloom: true }} use:refract>
    <div class="top"><span class="dot {e}">{e === 'a' ? t('pad.a') : t('pad.b')}</span>
      <span class="grow"><b class="ellipsis">{cand ? candName : t(e === 'a' ? 'route.tapFrom' : 'route.tapTo')}</b><small class="ellipsis">{candHint}</small></span>
      <button onclick={back} aria-label={t('common.close')}><X size={18} /></button></div>
    <button class="set" disabled={!cand} onclick={() => { haptic.tap(); set(e, cand!.text, cand!.pin); }}>{t(e === 'a' ? 'route.setFrom' : 'route.setTo')}</button>
  </div>
{:else if edit}
  {@const e = edit.end}
  {#key e}
  <MapPad title={t(e === 'a' ? 'pad.fromTitle' : 'pad.findTitle')} go={t('pad.showWays')} point={e} placeTab={t('pad.entranceOrPlace')} start={pins[e] ? '' : textOf(e)}
          groups={[{ title: t('pad.entrances'), tiles: exits }, ...placeGroups()]} {check} {see}
          onsubmit={(v) => { haptic.tap(); set(e, v); }} onclose={back} />
  {/key}
{:else}
  <div class="scrim" onclick={onclose} aria-hidden="true"></div>
  <div class="card ways" data-cover>
    <span class="grab" aria-hidden="true"></span>
    <div class="top"><b>{t('route.title')}</b>
      <button onclick={onclose} aria-label={t('common.close')}><X size={18} /></button></div>
    <!-- either end: tap to change it (the keypad, and the map from there) -->
    {#each ['a', 'b'] as const as e (e)}
      <button class="end" onclick={() => { haptic.tap(); edit = { end: e, by: 'pad' }; }}><span class="dot {e}">{e === 'a' ? t('pad.a') : t('pad.b')}</span><b class="ellipsis">{label(e)}</b>{#if !pins[e] && shut(textOf(e))}<small class="shut">{shut(textOf(e))}</small>{/if}{#if pins[e]}<MapPin size={14} />{:else}<Pencil size={14} />{/if}</button>
    {/each}
    <div class="opts">
      {#each options as o, i (i)}
        {@const Icon = ICON[o.route.mode]}
        <button class="opt" class:sel={i === 0} style:animation-delay="{i * 50}ms" onclick={() => start(o)}>
          <span class="ic"><Icon size={18} /></span>
          <span class="grow"><b>{o.route.mode === 'fast' && options.some((x) => secs(x.route) < secs(o.route)) ? t('route.m.stairs') : t(`route.m.${o.route.mode}`)}</b>
            {#if o.route.mode === 'lift' && rush}<small class="rush">{t('route.rush')}</small>
            {:else}<small>{o.route.legs.length > 1 ? o.route.legs.map((l) => floorName(l.f)).join(' → ') : t('route.sameFloor')}</small>{/if}</span>
          <span class="min">{mins(secs(o.route))} <small>{t('route.minShort')}</small></span>
        </button>
      {:else}
        <p class="none">{t('route.noWay')}</p>
      {/each}
    </div>
  </div>
{/if}

<style>
  .card { position: absolute; z-index: 4; left: 10px; right: 10px; bottom: calc(var(--safe-bottom) + 14px); padding: 12px 14px 14px; border-radius: 22px; color: var(--text); }
  .top { display: flex; justify-content: space-between; align-items: center; gap: 8px; font: 600 13px/1.3 var(--font-text); color: var(--text-3); margin-bottom: 4px; }
  .top b { font: 800 24px/1.15 var(--font-display); color: var(--text); letter-spacing: -0.01em; }
  .top button { width: 32px; height: 32px; display: grid; place-items: center; color: var(--text-2); }
  /* the ways: the keypad's panel, short */
  .scrim { position: absolute; inset: 0; z-index: 5; background: rgba(2, 3, 8, 0.45); animation: fade 0.4s ease; }
  @keyframes fade { from { opacity: 0; } }
  .ways { z-index: 6; left: 0; right: 0; bottom: 0; padding: 8px 16px calc(var(--safe-bottom) + 16px); border-radius: 36px 36px 0 0; background: var(--surface-solid);
    box-shadow: 0 -20px 60px -20px rgba(0, 0, 0, 0.8), inset 0 1px 0 rgba(255, 255, 255, 0.08); animation: rise 0.6s var(--ease-spring); }
  @keyframes rise { from { transform: translate3d(0, 105%, 0); } }
  .grab { display: block; width: 38px; height: 5px; border-radius: 3px; background: var(--line-2); margin: 0 auto 8px; }
  .ways .top { margin-bottom: 10px; }
  .ways .top button:last-child { width: 36px; height: 36px; border-radius: 50%; background: var(--surface-2); }
  .end { display: flex; align-items: center; gap: 10px; width: 100%; padding: 4px 2px; font: 600 15px/1.3 var(--font-text); color: var(--text); text-align: left; }
  .end :global(svg) { color: var(--text-3); }
  .end .shut { font-size: 13px; color: var(--danger-text); }
  .dot { width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; flex: none; color: #fff; font: 800 13px/1 var(--font-display); }
  .dot.a { background: #2fc277; }
  .dot.b { background: var(--accent); }
  .opts { display: flex; flex-direction: column; gap: 8px; margin-top: 12px; }
  .opt { display: flex; align-items: center; gap: 12px; padding: 12px; border-radius: 18px; background: var(--surface); text-align: left; box-shadow: inset 0 0 0 1.5px transparent;
    animation: optIn 0.5s var(--ease-spring) backwards; }
  @keyframes optIn { from { opacity: 0; transform: translateY(14px); } }
  .opt.sel { box-shadow: inset 0 0 0 1.5px var(--accent); background: var(--accent-soft); }
  .ic { width: 38px; height: 38px; border-radius: 12px; display: grid; place-items: center; background: var(--surface-2); flex: none; }
  .opt.sel .ic { background: var(--accent); color: #fff; }
  .grow { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .grow b { font: 650 16px/1.2 var(--font-text); }
  .grow small.rush { color: var(--warning-text); font-weight: 650; }
  .grow small, .min small { font: 500 13px/1.2 var(--font-text); color: var(--text-2); }
  .min { font: 800 22px/1 var(--font-display); white-space: nowrap; }
  .none { font: 500 14px/1.3 var(--font-text); color: var(--text-2); padding: 4px 2px; }
  /* the step card as the tab bar's glass; off the floors row, a bar per step */
  .step { left: 10px; right: 10px; bottom: calc(var(--safe-bottom) + 14px); padding: 12px 12px 12px 16px; border-radius: 28px; animation: rise 0.6s var(--ease-spring);
    -webkit-backdrop-filter: blur(20px) saturate(170%) brightness(1.05); backdrop-filter: var(--refract, blur(20px) saturate(170%) brightness(1.05));
    background: rgba(18, 22, 36, 0.38); box-shadow: 0 16px 40px -12px rgba(0, 0, 0, 0.6), 0 0 28px -8px rgba(90, 130, 255, 0.45); }
  .step::after { background: linear-gradient(180deg, rgba(255, 255, 255, 0.75), rgba(255, 255, 255, 0.16) 40%, rgba(255, 255, 255, 0.3)); }
  .step .top { margin: -2px -4px 0 0; }
  .bars { display: flex; gap: 4px; margin: 6px 4px 10px 0; }
  .bars i { flex: 1; height: 4px; border-radius: 2px; background: rgba(255, 255, 255, 0.18); transition: background 0.3s; }
  .bars i.on { background: var(--accent-text); }
  .txt { flex: 1; min-width: 0; font: 650 16px/1.3 var(--font-text); margin: 0; animation: txtIn 0.45s var(--ease-spring); }
  @keyframes txtIn { from { opacity: 0; transform: translateY(8px); filter: blur(4px); } }
  .nav { display: flex; align-items: center; gap: 10px; }
  .nav button { flex: none; width: 48px; height: 48px; display: grid; place-items: center; border-radius: 50%; color: var(--text);
    background: rgba(255, 255, 255, 0.1); box-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.35), inset 0 0 0 0.5px rgba(255, 255, 255, 0.12); }
  .nav button.p { color: #fff; background: radial-gradient(120% 90% at 30% 0%, #7f9dff, var(--accent) 55%, #2448d8);
    box-shadow: 0 6px 18px -4px rgba(59, 107, 255, 0.7), inset 0 1px 0.5px rgba(255, 255, 255, 0.7), inset 0 -2px 4px rgba(0, 0, 40, 0.25); }
  .nav button.p.ok { color: #04140b; background: radial-gradient(120% 90% at 30% 0%, #8ff0bd, #2fc277 55%, #1e9d5c); box-shadow: 0 6px 18px -4px rgba(47, 194, 119, 0.7), inset 0 1px 0.5px rgba(255, 255, 255, 0.7); }
  .nav button:disabled { opacity: 0.3; }
  .fls { position: relative; display: flex; margin: 10px 0 0 -4px; padding: 3px; border-radius: 999px;
    background: rgba(255, 255, 255, 0.06); box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.35), inset 0 -0.5px 0 rgba(255, 255, 255, 0.18); }
  .drop { position: absolute; top: 3px; bottom: 3px; width: calc((100% - 6px) / 6); border-radius: 999px; transition: left 380ms var(--ease-spring);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.95), rgba(225, 232, 255, 0.82));
    box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.45), inset 0 1px 0.5px #fff, inset 0 -2px 4px rgba(90, 120, 255, 0.25); }
  .fls button { position: relative; flex: 1; height: 38px; border-radius: 999px; display: grid; place-items: center; font: 700 16px/1 var(--font-display); color: var(--text-2); transition: color 0.2s ease; }
  .fls button.on { color: #0b1433; }
  .fls button.r::after { content: ''; position: absolute; bottom: 4px; width: 5px; height: 5px; border-radius: 50%; background: var(--accent); }
  :global(.theme-light) .fls { background: rgba(11, 20, 51, 0.06); box-shadow: inset 0 1px 2px rgba(11, 20, 51, 0.15); }
  :global(.theme-light) .drop { background: #0b1433; }
  :global(.theme-light) .fls button.on { color: #fff; }
  :global(.theme-light) .step { background: rgba(255, 255, 255, 0.5); box-shadow: 0 14px 34px -12px rgba(24, 36, 90, 0.4), 0 0 0 0.5px rgba(11, 20, 51, 0.14); }
  :global(.theme-light) .bars i { background: rgba(11, 20, 51, 0.12); }
  :global(.theme-light) .bars i.on { background: var(--accent); }
  :global(.theme-light) .nav button:not(.p) { background: rgba(11, 20, 51, 0.07); }
  /* an end on the map: the step card's glass and its point's colour; one row and the button, low, so the map stays free */
  .pick { padding: 12px 12px 12px 14px; border-radius: var(--r-xl); animation: rise 0.6s var(--ease-spring);
    -webkit-backdrop-filter: blur(20px) saturate(170%) brightness(1.05); backdrop-filter: var(--refract, blur(20px) saturate(170%) brightness(1.05));
    background: rgba(18, 22, 36, 0.38); box-shadow: 0 16px 40px -12px rgba(0, 0, 0, 0.6), 0 0 28px -8px rgba(90, 130, 255, 0.45); }
  .pick .top { margin: 0 -4px 10px 0; gap: 10px; }
  .pick .dot { width: 30px; height: 30px; font-size: var(--fs-body); }
  .pick .grow b { font: 700 var(--fs-card)/1.2 var(--font-text); color: var(--text); }
  .pick .grow small { color: var(--text-2); }
  .set { display: grid; place-items: center; width: 100%; height: 50px; border-radius: var(--r-full); font: 700 var(--fs-body)/1 var(--font-text); color: var(--on-accent); background: var(--accent); transition: opacity 0.25s, filter 0.25s; }
  .pt-a .set { background: var(--success); }
  .set:disabled { opacity: 0.35; filter: saturate(0.4); }
  .end b { min-width: 0; }
  :global(.theme-light) .pick { background: rgba(255, 255, 255, 0.5); box-shadow: 0 14px 34px -12px rgba(24, 36, 90, 0.4), 0 0 0 0.5px rgba(11, 20, 51, 0.14); }
  @media (prefers-reduced-motion: reduce) { .ways, .step, .pick, .opt, .txt { animation: none; } }
</style>
