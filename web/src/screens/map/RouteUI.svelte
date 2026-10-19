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
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Zap from '@lucide/svelte/icons/zap';
  import Accessibility from '@lucide/svelte/icons/accessibility';
  import Shuffle from '@lucide/svelte/icons/shuffle';
  import DoorOpen from '@lucide/svelte/icons/door-open';
  import Delete from '@lucide/svelte/icons/delete';
  import Undo from '@lucide/svelte/icons/undo-2';
  import Move from '@lucide/svelte/icons/move';
  import Trash from '@lucide/svelte/icons/trash';
  import Pencil from '@lucide/svelte/icons/pencil';
  import { api } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { say } from '../../lib/state/ui.svelte';
  import { roomOf, floorOf, nearRooms, spotOf, SPOTS } from '../../lib/map';
  import { attach, routes, openAt, type Mode, type Pt } from '../../lib/route';
  import { glass, refract, jelly } from '../../ui/glass';

  let { rt, cur, ar, rooms, to = null, out = false, go, pick, onclose, onedit }: {
    rt: RouteView; cur: number; ar: number; rooms: Record<string, number[][]>[]; to?: string | null; out?: boolean;
    go: (f: number, pts: { u: number; v: number }[]) => void; pick: (f: number) => void; onclose: () => void; onedit?: () => void;
  } = $props();

  // ---- finding the way ----
  let from = $state(''), dest = $state(untrack(() => to ?? '')), leaving = $state(untrack(() => out)); // leaving: "Help me get out"
  // a hint: any room of the building, not always 305 (owner, Oct 15)
  const all = untrack(() => rooms.flatMap((r) => Object.keys(r)).filter((r) => /^\d{3}$/.test(r))), hint = all[Math.floor(Math.random() * all.length)] ?? '305';
  // our own keypad (owner, Oct 19: the keyboard must be there at once; iOS shows the system one only after a tap) and
  // the places without a number beside it: a button puts the place's name in, a digit after it starts a number again
  const spotName = (k: string) => t(`route.spot.${k}` as 'route.spot.canteen');
  function key(k: string) {
    const typed = spotOf(from) ? '' : from;
    from = k === 'del' ? typed.slice(0, -1) : typed.length < 4 ? typed + k : typed;
  }
  /** a room as a point on its floor: where its number is printed, else its door (r), else its nearest numbered
   *  neighbour, "somewhere here" (owner, Oct 15: 435 isn't on the plan, lead to where it most likely is) */
  function place(text: string): (Pt & { room: string; near?: string }) | null {
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
  const options = $derived.by<{ route: Route; exit?: MapNode }[]>(() => {
    const g = rt.graph, p = place(from);
    if (!g || !p) return [];
    const a = { at: attach(g, p, ar, p.room), pt: p as Pt };
    if (leaving) { // the nearest exit open now, one answer (owner, Oct 15); a backup one (the night post) only when none other is open
      const now = new Date(), open = g.n.filter((x) => x.k === 'x' && openAt(x, now)), main = open.filter((x) => !x.b);
      const best = (main.length ? main : open).map((x) => ({ route: routes(g, ar, a, { at: [[x.id, 0]] })[0], exit: x }))
        .filter((o) => o.route).sort((p, q) => p.route.secs - q.route.secs)[0];
      return best ? [best] : [];
    }
    const b = place(dest);
    return b ? routes(g, ar, a, { at: attach(g, b, ar, b.room), pt: b }).map((route) => ({ route })) : [];
  });
  const mins = (s: number) => Math.max(1, Math.round(s / 60));
  const ICON: Record<Mode, typeof Zap> = { fast: Zap, lift: Accessibility, alt: Shuffle };
  let chosen = $state<{ route: Route; exit?: MapNode } | null>(null);
  function start(o: { route: Route; exit?: MapNode }) {
    haptic.tap(); (document.activeElement as HTMLElement | null)?.blur(); // the keyboard goes, the floors come back
    chosen = o; rt.route = o.route; rt.ends = [roomOf(from) ?? from, o.exit?.name ?? roomOf(dest) ?? dest]; show(0);
  }
  let drop = $state<HTMLSpanElement>();
  $effect(() => { void cur; jelly(drop); }); // the floors' drop squashes as it slides, as the tab bar's does
  function show(i: number) { rt.step = i; const leg = rt.route!.legs[i]; go(leg.f, leg.pts); }
  function stop() { haptic.tap(); chosen = null; rt.route = null; rt.ends = undefined; }
  const hours = (x: MapNode) => { const d = new Date(), h = x.h?.[d.getDay() === 0 ? 2 : d.getDay() === 6 ? 1 : 0]; return h ? h.split('-')[1] : ''; };
  const floorName = (n: number) => (n ? t('route.floor', { n }) : t('route.basement'));
  /** a step in words: walk past the named points to the stairs or lift and go up or down, or arrive */
  function words(i: number): string {
    const route = rt.route!, leg = route.legs[i], last = i === route.legs.length - 1;
    const past = leg.pts.slice(1, -1).map((p) => p.node?.name).filter((x, j, all): x is string => !!x && all.indexOf(x) === j && !p_isEnd(x));
    const via = past.length ? ' ' + t('route.past', { names: past.join(', ') }) : '';
    if (!last) {
      const lift = leg.up?.k === 'l', up = leg.to! > leg.f;
      return t(lift ? (up ? 'route.liftUp' : 'route.liftDown') : up ? 'route.stairsUp' : 'route.stairsDown', { floor: floorName(leg.to!), near: nearRoom(leg) }) + via;
    }
    const p = chosen?.exit ? null : place(dest);
    return (chosen?.exit ? t('route.toExit', { name: chosen.exit.name! }) : p?.near ? t('route.toNear', { room: p.near, near: p.room })
      : roomOf(dest) ? t('route.toRoom', { room: roomOf(dest)! }) : t('route.toPlace', { name: p?.room ?? dest })) + via;
  }
  /** which stairs: the room whose door is nearest to them, "the stairs by 384" (a friend's note, Oct 16: a floor has several) */
  function nearRoom(leg: Leg): string {
    const s = leg.up ?? leg.pts[leg.pts.length - 1], by = (n: MapNode) => Math.hypot(n.u - s.u, (n.v - s.v) * ar);
    const ok = (r: string) => /^\d/.test(r) && r !== roomOf(from); // not "the stairs by 351" to someone standing at 351
    const doors = rt.graph!.n.filter((n) => n.f === leg.f && n.r?.some(ok)).sort((x, y) => by(x) - by(y));
    return doors[0]?.r!.find(ok) ?? '';
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
  <div class="card step glass glass-sheet" use:glass={{ bloom: true }} use:refract>
    <div class="top"><span>{t('route.step', { i: rt.step + 1, n })} · {floorName(rt.route.legs[rt.step].f)} · {t('route.min', { n: mins(rt.route.secs) })}</span>
      <button onclick={stop} aria-label={t('common.close')}><X size={18} /></button></div>
    <!-- one row: the step, back and next beside it (owner, Oct 15: the card hid the way) -->
    <div class="nav"><p class="txt">{words(rt.step)}</p>
      {#if n > 1}<button disabled={rt.step === 0} onclick={() => { haptic.tap(); show(rt.step - 1); }} aria-label={t('route.back')}><ChevronLeft size={22} /></button>
      <button class="p" disabled={rt.step === n - 1} onclick={() => { haptic.tap(); show(rt.step + 1); }} aria-label={t('route.next')}><ChevronRight size={22} /></button>{/if}
    </div>
    <div class="fls" role="tablist" aria-label={t('map.floors')}>
      <span class="drop" bind:this={drop} style:left="calc(3px + (100% - 6px) * {cur} / 6)" aria-hidden="true"></span>
      {#each [0, 1, 2, 3, 4, 5] as f (f)}<button role="tab" aria-selected={cur === f} class:on={cur === f} class:r={rt.route.legs.some((l) => l.f === f)} onclick={() => pick(f)}>{f}</button>{/each}
    </div>
  </div>
{:else if leaving}
  <!-- "Help me get out" (owner, Oct 15): one big question, one answer, then the way -->
  <form class="card help glass glass-sheet" use:glass onsubmit={(e) => { e.preventDefault(); if (options[0]) start(options[0]); else haptic.error(); }}>
    <div class="top"><span></span><button type="button" onclick={onclose} aria-label={t('common.close')}><X size={18} /></button></div>
    <h2>{t('route.helpTitle')}</h2>
    <p class="ask">{t('route.helpAsk')}</p>
    <div class="big" class:wait={!from} class:word={!!spotOf(from)} role="status" aria-label={t('route.helpAsk')}>{from || hint}</div>
    <div class="spots">{#each SPOTS as s (s.k)}<button type="button" class:on={spotOf(from) === s} onclick={() => (from = spotName(s.k))}>{spotName(s.k)}</button>{/each}</div>
    <div class="pad">{#each ['1', '2', '3', '4', '5', '6', '7', '8', '9', 'a', '0', 'del'] as k (k)}
      <button type="button" onclick={() => key(k)} aria-label={k === 'del' ? t('route.erase') : k}>{#if k === 'del'}<Delete size={22} />{:else}{k}{/if}</button>{/each}</div>
    {#if options[0]?.exit}
      {@const o = options[0]}
      <p class="ans"><DoorOpen size={16} />{o.exit!.name} · {t('route.openTill', { time: hours(o.exit!) })} · {t('route.min', { n: mins(o.route.secs) })}</p>
      <button class="go">{t('route.lead')}</button>
    {:else if from.trim()}
      <p class="ans none">{place(from) ? t('route.noExit') : t('route.helpUnknown')}</p>
    {/if}
  </form>
{:else}
  <div class="card glass glass-sheet" use:glass>
    <div class="top"><b>{t('route.title')}</b>
      {#if onedit}<button class="ed" onclick={() => { haptic.tap(); onedit(); }}><Pencil size={15} />{t('route.edit')}</button>{/if}
      <button onclick={onclose} aria-label={t('common.close')}><X size={18} /></button></div>
    <label class="ft"><span class="dot"></span><input bind:value={from} placeholder={t('route.from')} enterkeyhint="next" autocomplete="off" /></label>
    <label class="ft"><span class="dot end"></span><input bind:value={dest} placeholder={t('route.to')} enterkeyhint="go" autocomplete="off" /></label>
    <div class="opts">
      {#each options as o, i (i)}
        {@const Icon = ICON[o.route.mode]}
        <button class="opt" class:sel={i === 0} onclick={() => start(o)}>
          <span class="ic"><Icon size={18} /></span>
          <span class="grow"><b>{t(`route.m.${o.route.mode}`)}</b>
            <small>{o.route.legs.length > 1 ? o.route.legs.map((l) => floorName(l.f)).join(' → ') : t('route.sameFloor')}</small></span>
          <span class="min">{mins(o.route.secs)} <small>{t('route.minShort')}</small></span>
        </button>
      {:else}
        {#if from && dest}<p class="none">{t('route.noWay')}</p>{/if}
      {/each}
    </div>
    <button class="link" onclick={() => { haptic.tap(); leaving = true; }}><DoorOpen size={15} />{t('route.out')}</button>
  </div>
{/if}

<style>
  .card { position: absolute; z-index: 4; left: 10px; right: 10px; bottom: calc(var(--safe-bottom) + 76px); padding: 12px 14px 14px; border-radius: 22px; color: var(--text); }
  .top { display: flex; justify-content: space-between; align-items: center; gap: 8px; font: 600 13px/1.3 var(--font-text); color: var(--text-3); margin-bottom: 4px; }
  .step { padding: 8px 10px 10px 14px; }
  .step .top { margin: -2px -4px 2px 0; }
  .top b { font: 700 18px/1.2 var(--font-display); color: var(--text); }
  .top .ed { width: auto; margin-left: auto; gap: 5px; display: flex; font: 600 13px/1 var(--font-text); color: var(--accent-text); }
  .top button { width: 32px; height: 32px; display: grid; place-items: center; color: var(--text-2); }
  .ft { display: flex; align-items: center; gap: 10px; background: var(--surface); border-radius: 14px; padding: 0 12px; height: 44px; margin-top: 6px; }
  .ft input { flex: 1; min-width: 0; height: 100%; border: 0; background: none; outline: none; color: var(--text); font: 600 16px/1 var(--font-text); }
  .ft input::placeholder { color: var(--text-3); font-weight: 500; }
  .dot { width: 12px; height: 12px; border-radius: 50%; border: 3px solid var(--accent); flex: none; }
  .dot.end { background: var(--accent); }
  .opts { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
  .opt { display: flex; align-items: center; gap: 12px; padding: 10px 12px; border-radius: 16px; background: var(--surface); text-align: left; border: 1.5px solid transparent; }
  .opt.sel { border-color: var(--accent); background: var(--accent-soft); }
  .ic { width: 34px; height: 34px; border-radius: 11px; display: grid; place-items: center; background: var(--surface); flex: none; }
  .opt.sel .ic { background: var(--accent); color: #fff; }
  .grow { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .grow b { font: 650 15px/1.2 var(--font-text); }
  .grow small, .min small { font: 500 12px/1.2 var(--font-text); color: var(--text-2); }
  .min { font: 700 19px/1 var(--font-display); white-space: nowrap; }
  .none { font: 500 13px/1.3 var(--font-text); color: var(--text-2); padding: 4px 2px; }
  .link { display: flex; align-items: center; justify-content: center; gap: 6px; width: 100%; margin-top: 10px; height: 34px; font: 650 14px/1 var(--font-text); color: var(--accent-text); }
  .help h2 { font: 800 28px/1.15 var(--font-display); margin: 0 0 6px; }
  .help .ask { font: 550 16px/1.3 var(--font-text); color: var(--text-2); margin: 0 0 14px; }
  .help .big { display: grid; place-items: center; width: 100%; height: 64px; border-radius: 18px; background: var(--surface); color: var(--text);
    font: 800 38px/1 var(--font-display); letter-spacing: 0.04em; overflow: hidden; white-space: nowrap; }
  .help .big.wait { color: var(--text-3); opacity: 0.7; }
  .help .big.word { font-size: 24px; letter-spacing: 0; }
  .spots { display: flex; gap: 6px; overflow-x: auto; margin: 10px -14px 0; padding: 0 14px; scrollbar-width: none; }
  .spots::-webkit-scrollbar { display: none; }
  .spots button { flex: none; height: 34px; padding: 0 12px; border-radius: 17px; background: var(--surface); font: 620 14px/1 var(--font-text); color: var(--text); }
  .spots button.on { background: var(--accent); color: #fff; }
  .pad { display: grid; grid-template-columns: repeat(3, 1fr); gap: 6px; margin-top: 10px; }
  .pad button { height: 48px; border-radius: 14px; background: var(--surface); display: grid; place-items: center; font: 700 22px/1 var(--font-display); color: var(--text); }
  .pad button:active { background: var(--surface-2); transform: scale(0.96); }
  .help .big.wait { animation: ask 1.6s ease-in-out infinite; }
  @keyframes ask { 0%, 100% { box-shadow: 0 0 0 0 rgba(59, 107, 255, 0), inset 0 0 0 1.5px rgba(59, 107, 255, 0.35); }
    50% { box-shadow: 0 0 0 6px rgba(59, 107, 255, 0.18), inset 0 0 0 1.5px rgba(59, 107, 255, 0.9); } }
  @media (prefers-reduced-motion: reduce) { .help .big.wait { animation: none; } }
  .help .ans { display: flex; align-items: center; justify-content: center; gap: 6px; margin: 12px 0 0; font: 600 14px/1.3 var(--font-text); color: var(--text-2); text-align: center; }
  .help .go { display: grid; place-items: center; width: 100%; height: 54px; margin-top: 12px; border-radius: 16px; background: #34c77b; color: #fff; font: 750 18px/1 var(--font-text); }
  .txt { flex: 1; min-width: 0; font: 650 16px/1.3 var(--font-text); margin: 0; }
  .nav { display: flex; align-items: center; gap: 8px; }
  /* the step card as the tab bar's glass (owner, Oct 15: "more liquid glass"): a clear body that refracts, an edge
     all the way round with the colour fringes, a soft blue glow; the floors in a glass groove with a sliding drop */
  .step { -webkit-backdrop-filter: blur(20px) saturate(170%) brightness(1.05); backdrop-filter: var(--refract, blur(20px) saturate(170%) brightness(1.05));
    background: rgba(18, 22, 36, 0.38); border-radius: 26px; box-shadow: 0 16px 40px -12px rgba(0, 0, 0, 0.6), 0 0 28px -8px rgba(90, 130, 255, 0.45); }
  .step::after { background: linear-gradient(180deg, rgba(255, 255, 255, 0.75), rgba(255, 255, 255, 0.16) 40%, rgba(255, 255, 255, 0.3)),
      linear-gradient(90deg, rgba(255, 120, 200, 0.45), transparent 22%, transparent 78%, rgba(90, 190, 255, 0.5)); }
  .fls { position: relative; display: flex; margin: 10px -2px 0 -6px; padding: 3px; border-radius: 999px;
    background: rgba(255, 255, 255, 0.06); box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.35), inset 0 -0.5px 0 rgba(255, 255, 255, 0.18); }
  .drop { position: absolute; top: 3px; bottom: 3px; width: calc((100% - 6px) / 6); border-radius: 999px; transition: left 380ms var(--ease-spring);
    background: linear-gradient(180deg, rgba(255, 255, 255, 0.95), rgba(225, 232, 255, 0.82));
    box-shadow: 0 4px 12px -2px rgba(0, 0, 0, 0.45), inset 0 1px 0.5px #fff, inset 0 -2px 4px rgba(90, 120, 255, 0.25); }
  .fls button { position: relative; flex: 1; height: 38px; border-radius: 999px; display: grid; place-items: center; font: 700 16px/1 var(--font-display); color: var(--text-2); transition: color 0.2s ease; }
  .fls button.on { color: #0b1433; }
  .fls button.r::after { content: ''; position: absolute; bottom: 4px; width: 5px; height: 5px; border-radius: 50%; background: var(--accent); }
  .nav button { flex: none; width: 44px; height: 44px; display: grid; place-items: center; border-radius: 50%; color: var(--text);
    background: rgba(255, 255, 255, 0.08); box-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.35), inset 0 0 0 0.5px rgba(255, 255, 255, 0.12); }
  .nav button.p { color: #fff; background: radial-gradient(120% 90% at 30% 0%, #7f9dff, var(--accent) 55%, #2448d8);
    box-shadow: 0 6px 18px -4px rgba(59, 107, 255, 0.7), inset 0 1px 0.5px rgba(255, 255, 255, 0.7), inset 0 -2px 4px rgba(0, 0, 40, 0.25); }
  .nav button:disabled { opacity: 0.35; }
  :global(.theme-light) .step { background: rgba(255, 255, 255, 0.5); box-shadow: 0 14px 34px -12px rgba(24, 36, 90, 0.4), 0 0 0 0.5px rgba(11, 20, 51, 0.14); }
  :global(.theme-light) .fls { background: rgba(11, 20, 51, 0.06); box-shadow: inset 0 1px 2px rgba(11, 20, 51, 0.15); }
  :global(.theme-light) .nav button:not(.p) { background: rgba(11, 20, 51, 0.06); }
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
