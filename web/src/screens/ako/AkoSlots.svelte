<script lang="ts">
  // The interview time: days as a horizontal choice, times as a grid of big buttons. A tap selects at once and rolls
  // back with a message if the server refuses. compact: no title and lead (the status page's "Change time").
  import CalendarClock from '@lucide/svelte/icons/calendar-clock';
  import { ako } from '../../lib/api/ako';
  import type { AkoView } from '../../lib/api/types';
  import { aw, type AkoKey } from '../../lib/i18n/ako';
  import { dayNo, parts, time, weekday, weekdayShort, dayMonth } from '../../lib/time';
  import { errOf, errKey } from './AkoDocs.svelte';

  type Slot = AkoView['slots'][number];
  let { view, token, onchange, compact = false }: { view: AkoView; token: string; onchange: (v: AkoView) => void; compact?: boolean } = $props();

  let day = $state<number | null>(null);
  let pending = $state<Slot['id'] | null>(null);
  let err = $state<AkoKey | ''>('');

  // the free times plus my own (the server lists only free ones)
  const all = $derived.by(() => {
    const m = new Map<Slot['id'], Slot>();
    for (const s of view.slots) m.set(s.id, s);
    if (view.slot) m.set(view.slot.id, view.slot);
    return [...m.values()].sort((a, b) => a.at - b.at);
  });
  const days = $derived.by(() => {
    const out: { no: number; at: number; list: Slot[] }[] = [];
    for (const s of all) {
      const no = dayNo(s.at), last = out[out.length - 1];
      if (last?.no === no) last.list.push(s); else out.push({ no, at: s.at, list: [s] });
    }
    return out;
  });
  const cur = $derived(days.find((d) => d.no === (day ?? (view.slot ? dayNo(view.slot.at) : -1))) ?? days[0]);
  const chosen = $derived(pending ?? view.slot?.id ?? null);
  const picked = $derived(all.find((s) => s.id === chosen) ?? null);
  const minutes = $derived(view.slot?.minutes ?? view.slots[0]?.minutes ?? 30);
  const decided = $derived(view.status === 'accepted' || view.status === 'declined');


  async function book(s: Slot) {
    if (pending != null || s.id === view.slot?.id) return;
    pending = s.id; err = '';
    try { onchange(await ako.book(token, s.id)); }
    catch (e) {
      // the server: 'full' (ako_slot_taken) someone just took it; 'closed' (ako_slot_late, ako_decided) too late or decided
      const { code, msg } = errOf(e);
      if (code === 'full') {
        err = 'ako.err.full';
        try { onchange(await ako.view(token)); } catch { /* the old list stays */ }
      } else if (code === 'closed') err = decided || msg === 'ako_decided' ? 'ako.err.closed' : 'ako.err.late';
      else err = errKey(e);
    } finally { pending = null; }
  }
</script>

<div class="slots" class:compact>
  {#if !compact}
    <h1 class="a-h1">{aw('ako.slotTitle')}</h1>
    <p class="a-lead">{aw('ako.slotLead', { min: minutes })}</p>
  {/if}

  {#if view.rebook && !view.slot}
    <p class="a-note warn gap" role="status">{view.rebook === '-' ? aw('ako.rebookPlain') : aw('ako.rebook', { why: view.rebook })}</p>
  {/if}

  {#if !days.length}
    <section class="a-card none gap">
      <span class="ico"><CalendarClock size={26} /></span>
      <p class="a-sub">{aw('ako.noSlots')}</p>
    </section>
  {:else}
    <div class="days" role="group" aria-label={aw('ako.slotTitle')}>
      {#each days as d (d.no)}
        <button type="button" class="day" class:on={cur?.no === d.no} aria-pressed={cur?.no === d.no} aria-label={`${weekday(d.at)}, ${dayMonth(d.at)}`}
          onclick={() => (day = d.no)}>
          <span class="wd">{weekdayShort(d.at)}</span>
          <b>{parts(d.at).d}</b>
          <i class="mk" class:has={picked != null && dayNo(picked.at) === d.no}></i>
        </button>
      {/each}
    </div>

    {#if cur}
      <p class="dh"><b>{weekday(cur.at)}, {dayMonth(cur.at)}</b><span class="a-sub">{aw('ako.almaty')}</span></p>
      {#key cur.no}
        <div class="grid" role="radiogroup" aria-label={`${weekday(cur.at)}, ${dayMonth(cur.at)}`}>
          {#each cur.list as s (s.id)}
            <button type="button" class="t" class:on={chosen === s.id} class:wait={pending === s.id} role="radio" aria-checked={chosen === s.id}
              onclick={() => book(s)}>{time(s.at)}</button>
          {/each}
        </div>
      {/key}
    {/if}

    {#if err}<p class="a-note bad gap" role="alert">{aw(err)}</p>{/if}

    <!-- the picked time is confirmed in the wizard's sticky bar (Ako.svelte); on the status page, by the interview card -->
  {/if}
</div>

<style>
  .gap { margin-top: var(--s-5); }
  .compact > .gap:first-child { margin-top: 0; }

  .none { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-3); }
  .ico { display: grid; place-items: center; width: 52px; height: 52px; border-radius: var(--r-full); background: var(--fill); color: var(--text-2); }

  .days { display: flex; gap: var(--s-2); margin: var(--s-6) calc(-1 * var(--s-5)) 0; padding: var(--s-1) var(--s-5); overflow-x: auto;
    scroll-snap-type: x proximity; scroll-padding: 0 var(--s-5); scrollbar-width: none; -webkit-overflow-scrolling: touch; }
  .days::-webkit-scrollbar { display: none; }
  .compact .days { margin-top: 0; }
  .day { flex: none; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 2px; min-width: 68px; height: 84px;
    border-radius: var(--r-m); background: var(--surface); box-shadow: var(--card-rim); color: var(--text); scroll-snap-align: start;
    -webkit-tap-highlight-color: transparent; transition: transform var(--t-base) var(--ease-bounce); }
  .day:active { transform: scale(0.95); }
  .day .wd { font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); text-transform: capitalize; }
  .day b { font: 700 var(--fs-sec)/1.1 var(--font-display); letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
  .day.on { background: var(--text); color: var(--bg); box-shadow: none; }
  .day.on .wd { color: inherit; opacity: 0.7; }
  .mk { width: 6px; height: 6px; border-radius: var(--r-full); background: transparent; }
  .mk.has { background: var(--accent); }

  .dh { display: flex; flex-wrap: wrap; align-items: baseline; justify-content: space-between; gap: 0 var(--s-3); margin: var(--s-6) 0 var(--s-3); }
  .dh b { font: 600 var(--fs-row)/1.3 var(--font-text); }
  .dh b::first-letter { text-transform: uppercase; }

  .grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: var(--s-2); animation: rise var(--t-base) var(--ease) both; }
  @keyframes rise { from { opacity: 0; transform: translateY(6px); } }
  .t { display: flex; align-items: center; justify-content: center; min-height: 60px; padding: 0; text-align: center; border-radius: var(--r-m); background: var(--surface); box-shadow: var(--card-rim); color: var(--text);
    font: 600 var(--fs-t3)/1 var(--font-display); letter-spacing: -0.01em; font-variant-numeric: tabular-nums;
    -webkit-tap-highlight-color: transparent; transition: transform var(--t-base) var(--ease-bounce); }
  .t:active { transform: scale(0.95); }
  .t.on { display: flex; justify-content: center; background: var(--accent); color: var(--on-accent); box-shadow: none; animation: pop var(--t-base) var(--ease-bounce); }
  .t.wait { animation: pop var(--t-base) var(--ease-bounce), wait 0.9s ease-in-out var(--t-base) infinite alternate; }
  @keyframes pop { from { transform: scale(0.92); } }
  @keyframes wait { to { opacity: 0.6; } }


  @media (prefers-reduced-motion: reduce) {
    .grid, .t.on, .t.wait { animation: none; }
    .day, .t { transition: none; }
  }
</style>
