<script lang="ts" module>
  import type { Graph, Leg, MapNode, Route } from '../../lib/route';
  /** What the map draws for routes (CampusMap owns it): the chosen route and its step, or the editor's graph and pick */
  export type RouteView = { graph: Graph | null; route: Route | null; step: number; edit: boolean; sel: number | null; moving: boolean; ends?: [string, string] };
</script>

<script lang="ts">
  // Indoor routes on the main map (PLAN item 22, mockup Oct 15): "How to get there" (from a room or an entrance to a
  // room: fastest by stairs, by lift, another staircase), "How do I get out?" (the exits open now, nearest first), the
  // way step by step, floor by floor. And the owner's editor: tap to drop a point, tap a point to link it to the picked
  // one (again to unlink), a point's kind, floors, name, rooms, hours below; saved a moment after each change.
  import { untrack } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import Check from '@lucide/svelte/icons/check';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Zap from '@lucide/svelte/icons/zap';
  import Accessibility from '@lucide/svelte/icons/accessibility';
  import Shuffle from '@lucide/svelte/icons/shuffle';
  import DoorOpen from '@lucide/svelte/icons/door-open';
  import Undo from '@lucide/svelte/icons/undo-2';
  import Move from '@lucide/svelte/icons/move';
  import Trash from '@lucide/svelte/icons/trash';
  import Pencil from '@lucide/svelte/icons/pencil';
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { say } from '../../lib/state/ui.svelte';
  import { roomOf, floorOf, nearRooms, spotOf, SPOTS } from '../../lib/map';
  import { attach, routes, openAt, liftRush, RUSH_WAIT, type Mode, type Pt } from '../../lib/route';
  import { glass, refract, jelly } from '../../ui/glass';
  import MapPad, { placeTiles, exitTiles, type PadCheck } from './MapPad.svelte';

  let { rt, cur, ar, rooms, to = null, out = false, go, pick, onclose, onedit }: {
    rt: RouteView; cur: number; ar: number; rooms: Record<string, number[][]>[]; to?: string | null; out?: boolean;
    go: (f: number, pts: { u: number; v: number }[]) => void; pick: (f: number) => void; onclose: () => void; onedit?: () => void;
  } = $props();

  // ---- finding the way: where to comes from the room card, where from from the keypad (MapPad), then the ways ----
  let from = $state(''), dest = $state(untrack(() => to ?? '')), leaving = $state(untrack(() => out)); // leaving: "Help me get out"
  let asked = $state(false); // "from" answered: the ways show
  const spotName = (k: string) => t(`route.spot.${k}` as 'route.spot.canteen');
  /** an entrance by its name on the graph: a start too (A16: people come in from Tole bi, Kazybek bi, Panfilov) */
  const exitNamed = (text: string) => rt.graph?.n.find((n) => n.k === 'x' && n.name === text) ?? null;
  const exits = $derived(exitTiles(rt.graph));
  /** a room as a point on its floor: where its number is printed, else its door (r), else its nearest numbered
   *  neighbour, "somewhere here" (owner, Oct 15: 435 isn't on the plan, lead to where it most likely is) */
  function place(text: string): (Pt & { room: string; near?: string }) | null {
    const x = exitNamed(text);
    if (x) return { f: x.f, u: x.u, v: x.v, room: x.name! };
    const s = spotOf(text);
    if (s?.f != null) return { f: s.f, u: s.u!, v: s.v!, room: spotName(s.k) };
    const r = roomOf(text), f = floorOf(r);
    if (!r || f == null) return null;
    const at = rooms[f]?.[r]?.[0], door = rt.graph?.n.find((n) => n.r?.includes(r));
    if (at) return { f, u: at[0], v: at[1], room: r };
    if (door) return { f: door.f, u: door.u, v: door.v, room: r };
    const nb = nearRooms(rooms[f] ?? {}, r, ar)[0];
    return nb ? { f, u: nb[1][0], v: nb[1][1], room: nb[0], near: r } : null;
  }
  function optionsFor(text: string, out: boolean): { route: Route; exit?: MapNode }[] {
    const g = rt.graph, p = place(text);
    if (!g || !p) return [];
    const a = { at: attach(g, p, ar, p.room), pt: p as Pt };
    if (out) { // the nearest exit open now, one answer (owner, Oct 15); a backup one (the night post) only when none other is open
      const now = new Date(), open = g.n.filter((x) => x.k === 'x' && openAt(x, now)), main = open.filter((x) => !x.b);
      const best = (main.length ? main : open).map((x) => ({ route: routes(g, ar, a, { at: [[x.id, 0]] })[0], exit: x }))
        .filter((o) => o.route).sort((p, q) => p.route.secs - q.route.secs)[0];
      return best ? [best] : [];
    }
    const b = place(dest);
    return b ? routes(g, ar, a, { at: attach(g, b, ar, b.room), pt: b }).map((route) => ({ route })) : [];
  }
  const options = $derived(asked ? optionsFor(from, false) : []);
  const rush = liftRush(new Date()); // the break between classes: the lifts are packed (owner, Oct 24)
  /** the keypad's line under the number: where that is, or the exit it leads to */
  function check(text: string): PadCheck {
    const p = text.trim() ? place(text) : null;
    if (!p) return text.length >= 3 || /[^\d\u0430-\u0433]/.test(text) ? { ok: false, tone: 'no', hint: leaving ? t('route.helpUnknown') : t('pad.noRoom') }
      : { ok: false, hint: leaving ? t('pad.outHint') : t('pad.roomHint') };
    if (leaving) {
      const o = optionsFor(text, true)[0];
      return o?.exit ? { ok: true, tone: 'ok', hint: `${o.exit.name} \u00b7 ${t('route.openTill', { time: hours(o.exit) }).replace(/^./, (c) => c.toLowerCase())} \u00b7 ${t('route.min', { n: mins(o.route.secs) })}` }
        : { ok: false, tone: 'no', hint: t('route.noExit') };
    }
    return { ok: true, tone: 'ok', hint: exitNamed(text) ? t('pad.entrance', { floor: floorName(p.f) }) : p.near ? t('pad.near', { room: p.near }) : floorName(p.f) };
  }
  const mins = (s: number) => Math.max(1, Math.round(s / 60));
  const ICON: Record<Mode, typeof Zap> = { fast: Zap, lift: Accessibility, alt: Shuffle };
  let chosen = $state<{ route: Route; exit?: MapNode } | null>(null);
  function start(o: { route: Route; exit?: MapNode }) {
    haptic.tap();
    chosen = o; rt.route = o.route; rt.ends = [roomOf(from) ?? from, o.exit?.name ?? roomOf(dest) ?? dest]; show(0);
  }
  let drop = $state<HTMLSpanElement>();
  $effect(() => { void cur; jelly(drop); }); // the floors' drop squashes as it slides, as the tab bar's does
  function show(i: number) { rt.step = i; const leg = rt.route!.legs[i]; go(leg.f, leg.pts); }
  function stop() { haptic.tap(); chosen = null; rt.route = null; rt.ends = undefined; onclose(); }
  const hours = (x: MapNode): string => { const d = new Date(), h = x.h?.[d.getDay() === 0 ? 2 : d.getDay() === 6 ? 1 : 0]; return h ? h.split('-')[1] : ''; };
  function floorName(n: number) { return n ? t('route.floor', { n }) : t('route.basement'); }
  /** a step in words: walk past the named points to the stairs or lift and go up or down, or arrive */
  function words(i: number): string {
    const route = rt.route!, leg = route.legs[i], last = i === route.legs.length - 1;
    const past = leg.pts.slice(1, -1).map((p) => p.node?.name).filter((x, j, all): x is string => !!x && all.indexOf(x) === j && !p_isEnd(x) && x !== from); // not "via Tole bi" to someone coming in there
    const via = past.length ? ' ' + t('route.past', { names: past.join(', ') }) : '';
    if (!last) {
      const lift = leg.up?.k === 'l', up = leg.to! > leg.f;
      return t(lift ? (up ? 'route.liftUp' : 'route.liftDown') : up ? 'route.stairsUp' : 'route.stairsDown', { floor: floorName(leg.to!), near: nearRoom(leg) }).replace(/^./, (c) => c.toUpperCase()) + via; // kk: no room, a small letter first
    }
    const p = chosen?.exit ? null : place(dest);
    return (chosen?.exit ? t('route.toExit', { name: chosen.exit.name! }) : p?.near ? t('route.toNear', { room: p.near, near: p.room })
      : roomOf(dest) ? t('route.toRoom', { room: roomOf(dest)! }) : t('route.toPlace', { name: p?.room ?? dest })) + via;
  }
  /** which stairs: " by" the room whose door is nearest to them, or nothing, "the stairs by 384" (a friend's note, Oct 16: a floor has several) */
  function nearRoom(leg: Leg): string {
    const s = leg.up ?? leg.pts[leg.pts.length - 1], by = (n: MapNode) => Math.hypot(n.u - s.u, (n.v - s.v) * ar);
    const ok = (r: string) => /^\d/.test(r) && r !== roomOf(from); // not "the stairs by 351" to someone standing at 351
    // only a door right by them: a far one names the stairs on the other side (owner, Oct 24: "the stairs by 728" sent left)
    const doors = rt.graph!.n.filter((n) => n.f === leg.f && n.r?.some(ok) && by(n) < 0.1).sort((x, y) => by(x) - by(y));
    const r = doors[0]?.r!.find(ok);
    return r ? t('route.by', { room: r }) : '';
  }
  const p_isEnd = (name: string) => name === chosen?.exit?.name;

  // ---- the owner's editor ----
  const MAXG = () => Math.max(0, ...(rt.graph?.n ?? []).map((n) => n.g ?? 0));
  const node = $derived(rt.graph?.n.find((n) => n.id === rt.sel) ?? null);
  const floorsOf = $derived(node?.g != null ? new Set(rt.graph!.n.filter((n) => n.k === node.k && n.g === node.g).map((n) => n.f)) : new Set<number>());
  let undo: string[] = [], saving = $state<'' | 'wait' | 'ok' | 'err'>(''), saveT = 0;
  function change(fn: (g: Graph) => void) {
    const g = rt.graph!;
    undo.push(JSON.stringify(g)); if (undo.length > 60) undo.shift();
    fn(g);
    rt.graph = { ...g };
    saving = 'wait'; clearTimeout(saveT); saveT = window.setTimeout(save, 1200);
  }
  async function save() {
    try { const g = await api.saveMapGraph(rt.graph!); rt.graph = { ...rt.graph!, ver: g.ver }; saving = 'ok'; }
    catch (e) { saving = 'err'; say((e as { code?: string }).code === 'conflict' ? t('route.conflict') : t('route.saveFailed'), 'pleading_face_3d'); }
  }
  function back() { const s = undo.pop(); if (!s) return; haptic.tap(); const ver = rt.graph!.ver; rt.graph = { ...JSON.parse(s), ver }; rt.sel = null; saving = 'wait'; clearTimeout(saveT); saveT = window.setTimeout(save, 1200); }
  const nextId = () => Math.max(0, ...rt.graph!.n.map((n) => n.id)) + 1;
  const linked = (g: Graph, a: number, b: number) => g.e.findIndex(([x, y]) => (x === a && y === b) || (x === b && y === a));
  /** CampusMap's tap in edit mode: at (u, v) of the plan on floor `cur`, on point `hit` if one is under the finger */
  export function tap(u: number, v: number, hit: number | null) {
    if (!rt.graph) return;
    haptic.tap();
    if (rt.moving && node) { change(() => { node.u = u; node.v = v; }); rt.moving = false; return; }
    if (hit == null) { // a new point, linked to the picked one on this floor
      const id = nextId(), prev = node && node.f === cur ? node.id : null;
      change((g) => { g.n.push({ id, f: cur, u: +u.toFixed(5), v: +v.toFixed(5) }); if (prev != null) g.e.push([prev, id]); });
      rt.sel = id;
    } else if (rt.sel == null || hit === rt.sel || node?.f !== cur) rt.sel = hit === rt.sel ? null : hit;
    else { const a = rt.sel; change((g) => { const i = linked(g, a, hit); if (i >= 0) g.e.splice(i, 1); else g.e.push([a, hit]); }); rt.sel = hit; }
  }
  function kind(k: MapNode['k']) {
    if (!node || node.k === k) return;
    change(() => { node.k = k; if (k === 's' || k === 'l') node.g ??= MAXG() + 1; else delete node.g; if (k === 'x') node.h ??= ['07:00-22:00', '07:00-22:00', '']; else delete node.h; });
  }
  /** a staircase or lift on one more floor (a point at the same spot, linked to that floor's nearest point) or one less */
  function toggleFloor(f: number) {
    if (!node || node.g == null) return;
    const n0 = node;
    change((g) => {
      const there = g.n.find((n) => n.k === n0.k && n.g === n0.g && n.f === f);
      if (there) { if (there.id === n0.id) return; g.n = g.n.filter((n) => n !== there); g.e = g.e.filter(([a, b]) => a !== there.id && b !== there.id); return; }
      const id = nextId(), near = g.n.filter((n) => n.f === f).sort((a, b) => Math.hypot(a.u - n0.u, a.v - n0.v) - Math.hypot(b.u - n0.u, b.v - n0.v))[0];
      g.n.push({ id, f, u: n0.u, v: n0.v, k: n0.k, g: n0.g });
      if (near) g.e.push([id, near.id]);
    });
  }
  function field(fn: (n: MapNode) => void) { if (node) change(() => fn(node)); }
  function remove() { if (!node) return; const id = node.id; change((g) => { g.n = g.n.filter((n) => n.id !== id); g.e = g.e.filter(([a, b]) => a !== id && b !== id); }); rt.sel = null; }
  const DAYS = ['route.weekdays', 'route.sat', 'route.sun'] as const;
</script>

{#if rt.edit}
  <div class="tools">
    <button class="glass glass-pill" use:glass onclick={back} aria-label={t('route.undo')}><Undo size={18} /></button>
    {#if node}<button class="glass glass-pill" class:on={rt.moving} use:glass onclick={() => { haptic.tap(); rt.moving = !rt.moving; }}><Move size={18} />{t('route.move')}</button>{/if}
    <span class="state">{saving === 'wait' ? t('route.saving') : saving === 'ok' ? t('route.saved') : saving === 'err' ? t('route.notSaved') : t('route.editHint')}</span>
    <button class="glass glass-pill" use:glass onclick={() => { rt.edit = false; rt.sel = null; rt.moving = false; }} aria-label={t('common.close')}><X size={18} /></button>
  </div>
  {#if node}
    <div class="card glass glass-sheet" use:glass>
      <div class="seg">
        {#each [[undefined, 'route.kCorridor'], ['s', 'route.kStairs'], ['l', 'route.kLift'], ['x', 'route.kExit']] as const as [k, label] (label)}
          <button class:on={node.k === k} onclick={() => kind(k)}>{t(label)}</button>
        {/each}
      </div>
      {#if node.k === 's' || node.k === 'l'}
        <p class="lbl">{t('route.floors')}</p>
        <div class="fl">{#each [0, 1, 2, 3, 4, 5] as f (f)}<button class:on={floorsOf.has(f)} onclick={() => toggleFloor(f)}>{f}</button>{/each}</div>
      {/if}
      {#if node.k === 'x'}
        <div class="hours">{#each DAYS as d, i (d)}<label><span class="lbl">{t(d)}</span>
          <input value={node.h?.[i] ?? ''} placeholder="07:00-18:00" inputmode="numeric"
                 onchange={(e) => { const v = e.currentTarget.value.trim(); if (/^(|\d\d:\d\d-\d\d:\d\d)$/.test(v)) field((n) => { n.h = [...(n.h ?? ['', '', ''])]; n.h[i] = v; }); else haptic.error(); }} /></label>{/each}</div>
      {/if}
      <div class="two">
        <label><span class="lbl">{t('route.name')}</span><input value={node.name ?? ''} maxlength="40" onchange={(e) => field((n) => { const v = e.currentTarget.value.trim(); if (v) n.name = v; else delete n.name; })} /></label>
        <label><span class="lbl">{t('route.rooms')}</span><input value={node.r?.join(', ') ?? ''} onchange={(e) => field((n) => { const r = e.currentTarget.value.split(/[\s,]+/).map((x) => roomOf(x)).filter((x): x is string => !!x); if (r.length) n.r = r; else delete n.r; })} /></label>
      </div>
      <div class="row">
        <label class="sw"><input type="checkbox" checked={!!node.b} onchange={(e) => field((n) => { if (e.currentTarget.checked) n.b = true; else delete n.b; })} />{t('route.backup')}</label>
        <button class="del" onclick={remove}><Trash size={16} />{t('route.delete')}</button>
      </div>
    </div>
  {/if}
{:else if chosen && rt.route}
  {@const n = rt.route.legs.length}
  <!-- the step on the way (owner, Oct 24 mockup): glass over the plan, a bar per step; the floors are the rail's -->
  <div class="card step glass glass-sheet" data-cover use:glass={{ bloom: true }} use:refract>
    <div class="top"><span>{t('route.step', { i: rt.step + 1, n })} · {floorName(rt.route.legs[rt.step].f)} · {t('route.min', { n: mins(rt.route.secs) })}</span>
      <button onclick={stop} aria-label={t('common.close')}><X size={18} /></button></div>
    <div class="bars" aria-hidden="true">{#each rt.route.legs as _, i (i)}<i class:on={i <= rt.step}></i>{/each}</div>
    <div class="nav">{#key rt.step}<p class="txt">{words(rt.step)}</p>{/key}
      {#if n > 1}<button disabled={rt.step === 0} onclick={() => { haptic.tap(); show(rt.step - 1); }} aria-label={t('route.back')}><ChevronLeft size={22} /></button>{/if}
      {#if rt.step < n - 1}<button class="p" onclick={() => { haptic.tap(); show(rt.step + 1); }} aria-label={t('route.next')}><ChevronRight size={22} /></button>
      {:else}<button class="p ok" onclick={() => { haptic.ok(); say(t('pad.arrived'), 'partying_face_3d'); stop(); }} aria-label={t('pad.arrived')}><Check size={22} /></button>{/if}
    </div>
    <!-- on the way the floors are the card's last row, the rail is gone (owner, Oct 15 and again Oct 24: it hid the way) -->
    <div class="fls" role="tablist" aria-label={t('map.floors')}>
      <span class="drop" bind:this={drop} style:left="calc(3px + (100% - 6px) * {cur} / 6)" aria-hidden="true"></span>
      {#each [0, 1, 2, 3, 4, 5] as f (f)}<button role="tab" aria-selected={cur === f} class:on={cur === f} class:r={rt.route.legs.some((l) => l.f === f)} onclick={() => pick(f)}>{f || t('map.bShort')}</button>{/each}
    </div>
  </div>
{:else if leaving}
  <MapPad title={t('pad.whereTitle')} go={t('route.lead')} point="a" placeTab={t('pad.place')} groups={[{ tiles: placeTiles() }]} {check}
          onsubmit={(v) => { from = v; const o = optionsFor(v, true)[0]; if (o) start(o); }} {onclose} />
{:else if !asked}
  <MapPad title={t('pad.fromTitle')} go={t('pad.showWays')} point="a" placeTab={t('pad.entranceOrPlace')} start={from}
          groups={[{ title: t('pad.entrances'), tiles: exits }, { title: t('pad.places'), tiles: placeTiles() }]} {check}
          onsubmit={(v) => { haptic.tap(); from = v; asked = true; }} {onclose} />
{:else}
  <div class="scrim" onclick={onclose} aria-hidden="true"></div>
  <div class="card ways" data-cover>
    <span class="grab" aria-hidden="true"></span>
    <div class="top"><b>{t('route.title')}</b>
      {#if onedit}<button class="ed" onclick={() => { haptic.tap(); onedit(); }}><Pencil size={15} />{t('route.edit')}</button>{/if}
      <button onclick={onclose} aria-label={t('common.close')}><X size={18} /></button></div>
    <!-- the start: tap to change it (back to the keypad) -->
    <button class="end" onclick={() => { haptic.tap(); asked = false; }}><span class="dot a">{t('pad.a')}</span><b>{roomOf(from) ?? from}</b><Pencil size={14} /></button>
    <div class="end"><span class="dot b">{t('pad.b')}</span><b>{roomOf(dest) ?? dest}</b></div>
    <div class="opts">
      {#each options as o, i (i)}
        {@const Icon = ICON[o.route.mode]}
        <button class="opt" class:sel={i === 0} style:animation-delay="{i * 50}ms" onclick={() => start(o)}>
          <span class="ic"><Icon size={18} /></span>
          <span class="grow"><b>{o.route.mode === 'fast' && options.some((x) => x.route.secs < o.route.secs) ? t('route.m.stairs') : t(`route.m.${o.route.mode}`)}</b>
            {#if o.route.mode === 'lift' && rush}<small class="rush">{t('route.rush')}</small>
            {:else}<small>{o.route.legs.length > 1 ? o.route.legs.map((l) => floorName(l.f)).join(' → ') : t('route.sameFloor')}</small>{/if}</span>
          <span class="min">{mins(o.route.secs + (o.route.mode === 'lift' && rush ? RUSH_WAIT : 0))} <small>{t('route.minShort')}</small></span>
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
  .top .ed { width: auto; margin-left: auto; gap: 5px; display: flex; font: 600 13px/1 var(--font-text); color: var(--accent-text); }
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
  /* the step card as the tab bar's glass (owner, Oct 15: "more liquid glass"); off the floors row, a bar per step */
  .step { left: 10px; right: 10px; bottom: calc(var(--safe-bottom) + 14px); padding: 12px 12px 12px 16px; border-radius: 28px; animation: rise 0.6s var(--ease-spring);
    -webkit-backdrop-filter: blur(20px) saturate(170%) brightness(1.05); backdrop-filter: var(--refract, blur(20px) saturate(170%) brightness(1.05));
    background: rgba(18, 22, 36, 0.38); box-shadow: 0 16px 40px -12px rgba(0, 0, 0, 0.6), 0 0 28px -8px rgba(90, 130, 255, 0.45); }
  .step::after { background: linear-gradient(180deg, rgba(255, 255, 255, 0.75), rgba(255, 255, 255, 0.16) 40%, rgba(255, 255, 255, 0.3)),
      linear-gradient(90deg, rgba(255, 120, 200, 0.45), transparent 22%, transparent 78%, rgba(90, 190, 255, 0.5)); }
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
  @media (prefers-reduced-motion: reduce) { .ways, .step, .opt, .txt { animation: none; } }
  .tools { position: absolute; z-index: 4; left: 12px; right: 12px; top: calc(max(48px, var(--top)) + 62px); display: flex; align-items: center; gap: 8px; }
  .tools button { height: 40px; min-width: 40px; padding: 0 12px; border-radius: 20px; display: flex; align-items: center; justify-content: center; gap: 6px; font: 600 14px/1 var(--font-text); color: var(--text); }
  .tools button.on { background: var(--accent); color: #fff; }
  .state { flex: 1; text-align: center; font: 550 12px/1.2 var(--font-text); color: var(--text-2); }
  .seg { display: flex; background: var(--surface); border-radius: 12px; padding: 3px; }
  .seg button { flex: 1; padding: 8px 0; border-radius: 9px; font: 600 13px/1 var(--font-text); color: var(--text-2); }
  .seg button.on { background: var(--accent); color: #fff; }
  .lbl { display: block; font: 550 12px/1.3 var(--font-text); color: var(--text-3); margin: 10px 0 4px; }
  .fl { display: flex; gap: 6px; }
  .fl button { flex: 1; height: 34px; border-radius: 10px; background: var(--surface); font: 650 14px/1 var(--font-text); color: var(--text-3); }
  .fl button.on { background: var(--accent-soft); color: var(--accent-text); outline: 1.5px solid var(--accent); }
  .two, .hours { display: flex; gap: 8px; }
  .two label, .hours label { flex: 1; min-width: 0; }
  .two input, .hours input { width: 100%; height: 38px; border: 0; border-radius: 10px; background: var(--surface); color: var(--text); padding: 0 10px; font: 550 15px/1 var(--font-text); outline: none; }
  .row { display: flex; justify-content: space-between; align-items: center; margin-top: 10px; }
  .sw { display: flex; align-items: center; gap: 8px; font: 550 14px/1.2 var(--font-text); }
  .del { display: flex; align-items: center; gap: 6px; font: 600 14px/1 var(--font-text); color: var(--danger, #e5484d); }
</style>
