<script lang="ts">
  // What stands on the campus map's plan (CampusMap.svelte lays it over MapLibre's canvas and moves it with the
  // camera): the room found and its flag, its numbered neighbours, the "free now" tints, the way and its pins, a
  // route's end being picked, my flaws' marks. Places are fractions of the plan's width and height (u, v).
  import Check from '@lucide/svelte/icons/check';
  import { t } from '../../lib/i18n/index.svelte';
  import type { Ver } from '../../lib/mapgl';
  import type { RouteView } from './RouteUI.svelte';

  let { rt, cur, ver, ar, routing, spots, near, card, cardTitle, freeHere, flawsHere, okId, seen, draft, floorName }: {
    rt: RouteView; cur: number; ver: Ver; ar: number /* the plan's height to its width */; routing: boolean; spots: number[][]; near: number[][]; card: boolean; cardTitle: string;
    freeHere: { r: string; u: number; v: number; free: boolean }[]; flawsHere: { id: number; u: number; v: number; body: string }[];
    okId: number; seen: number; draft: { ver: Ver; f: number; u: number; v: number } | null; floorName: (n: number) => string;
  } = $props();
  const legsHere = $derived(rt.route ? rt.route.legs.map((l, i) => ({ ...l, i })).filter((l) => l.f === cur) : []);
  const line = (pts: { u: number; v: number }[]) => pts.map((p) => `${p.u * 1000},${p.v * 1000 * ar}`).join(' ');
</script>

<!-- a route's end being picked: where the tap (or the typed room) landed, A green, B blue -->
{#if rt.pick?.at && rt.pick.at.f === cur}{#key rt.pick.at}<span class="pin cand {rt.pick.end}" style:left="{rt.pick.at.u * 100}%" style:top="{rt.pick.at.v * 100}%"></span>{/key}{/if}
{#each routing ? [] : spots as [u, v], i (i)}<span class="spot" style:left="{u * 100}%" style:top="{v * 100}%"></span>
  {#if i === 0 && card}<span class="pin flag" style:left="{u * 100}%" style:top="{v * 100}%">{cardTitle}</span>{/if}{/each}
{#each routing ? [] : near as [u, v], i (i)}<span class="spot near" style:left="{u * 100}%" style:top="{v * 100}%"></span>{/each}
{#each freeHere as f (f.r + f.u + f.v)}<span class="room" class:free={f.free} data-room={f.r} style:left="{f.u * 100}%" style:top="{f.v * 100}%"></span>{/each}
{#if legsHere.length}
  <svg class="way" viewBox="0 0 1000 {1000 * ar}" preserveAspectRatio="none" aria-hidden="true">
    <!-- the way: a soft glow, the line, white dots running along the step on screen -->
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
    <!-- where you are: a dot and "You are here" above it -->
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

<style>
  /* the room found: a ring that breathes out, its name in a blue flag above (mockup) */
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
  /* the way: a soft glow under the step on screen, the line, white dots running along it */
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
  .pin.me::after { content: ''; width: 12px; height: 12px; border-radius: 50%; background: #2fc277; } /* A is green, B blue */
  .pin.tag { transform: translate(-50%, calc(-100% - 20px)); padding: 6px 10px; border-radius: 10px; background: #fff; color: #0a0f24; font: 750 12px/1 var(--font-text); white-space: nowrap;
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.35); }
  /* a route's end being picked: a ring in its point's colour (the room's number shows through), dropped in where the finger was */
  .pin.cand { width: 34px; height: 34px; border-radius: 50%; border: 3px solid var(--accent); background: rgba(59, 107, 255, 0.16); box-shadow: 0 4px 14px rgba(0, 0, 0, 0.4); animation: drop 0.45s var(--ease-bounce); }
  .pin.cand.a { border-color: var(--success); background: rgba(47, 191, 113, 0.16); }
  .pin.cand::before { content: ''; position: absolute; inset: -3px; border-radius: 50%; border: 3px solid; border-color: inherit; animation: ripple 2s var(--ease-spring) infinite; }
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
  :global(html.lowfx) .way polyline.run, :global(html.lowfx) .spot::before, :global(html.lowfx) .spot::after, :global(html.lowfx) .pin.end::before, :global(html.lowfx) .pin.cand::before { animation: none; }
  @media (prefers-reduced-motion: reduce) { .way polyline.run, .spot::before, .spot::after, .pin.end::before, .pin.cand, .pin.cand::before, .pin.flag, .pin.mark.draft::after { animation: none; } }

</style>
