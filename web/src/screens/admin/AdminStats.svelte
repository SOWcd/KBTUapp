<script lang="ts" module>
  let counted = false; // the big number counts up once a session, the first time it shows
</script>

<script lang="ts">
  // Admin → the numbers card (admins; review Nov 3 §A.2): who opened the app today, big, against the same weekday last
  // week; new today and this week small; the last seven days as bars, today green. Held with the inbox (data store), so it
  // never pops in late. A tap pushes the stats page (the 30 days, a day's people, the AI translator).
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { data } from '../../lib/state/data.svelte';
  import { open } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { calm } from '../../ui/fold';
  import Skeleton from '../../ui/Skeleton.svelte';
  import StatsPane from './StatsPane.svelte';
  import { almatyDay, week } from './stats';

  const st = $derived(data.adminStats);
  const today = almatyDay();
  const bars = $derived(st ? week(st, today) : []);
  const peak = $derived(Math.max(1, ...bars.map((b) => b.n ?? 0)));
  const now = $derived(st?.today ?? 0);
  // whole days only (today is still counting): the last 7 full days against the 7 before them
  const sum = (from: number) => (st?.days ?? []).filter((d) => d.day >= from && d.day < from + 7).reduce((n, d) => n + d.active, 0);
  const last7 = $derived(sum(today - 7)), prev7 = $derived(sum(today - 14));
  const delta = $derived(prev7 ? Math.round(((last7 - prev7) / prev7) * 100) : null);

  let shown = $state(counted ? -1 : 0); // -1: the real number
  $effect(() => {
    if (!st || counted) return;
    counted = true;
    if (calm()) { shown = -1; return; }
    const n = st.today ?? 0, t0 = performance.now();
    let raf = 0;
    const step = (ts: number) => { const k = Math.min(1, (ts - t0) / 500); shown = k < 1 ? Math.round(n * (1 - (1 - k) ** 3)) : -1; if (k < 1) raf = requestAnimationFrame(step); };
    raf = requestAnimationFrame(step);
    return () => cancelAnimationFrame(raf);
  });
</script>

<button class="card" onclick={() => { haptic.tap(); open(StatsPane, {}); }} aria-label={t('adm.stats')}>
  <span class="top"><span class="t-cap">{t('common.today')}</span><ChevronRight size={18} /></span>
  {#if st}
    <span class="mid">
      <span class="big"><b class="num">{shown < 0 ? now : shown}</b>
        {#if delta != null}<i class="num" class:up={delta > 0} class:down={delta < 0}>{delta > 0 ? '▲' : delta < 0 ? '▼' : ''} {Math.abs(delta)}% {t('st.week')}</i>{/if}</span>
      <span class="bars" aria-hidden="true">
        {#each bars as b, i (b.day)}<span class:now={b.day === today} style:height="{b.n == null ? 6 : Math.max(8, (b.n / peak) * 100)}%" style:animation-delay="{i * 30}ms"></span>{/each}
      </span>
    </span>
    <span class="foot num"><em class:new={st.newToday > 0}>+{tn('st.dayNew', st.newToday)}</em></span>
  {:else}
    <Skeleton kind="lines" n={2} />
  {/if}
</button>

<style>
  .card { display: flex; flex-direction: column; gap: var(--s-2); width: 100%; padding: var(--s-4); border-radius: var(--r-group); text-align: left; color: var(--text);
    background: radial-gradient(90% 70% at 15% 0%, var(--accent-soft), transparent 70%), var(--surface); box-shadow: var(--shadow-card);
    transition: transform 450ms var(--ease-bounce); }
  .card:active { transform: scale(0.98); transition-duration: 80ms; }
  .top { display: flex; align-items: center; justify-content: space-between; color: var(--text-3); }
  .mid { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--s-3); }
  .big { display: flex; flex-direction: column; gap: 2px; min-width: 0; }
  .big b { font: 750 var(--fs-title)/1 var(--font-display); letter-spacing: -0.03em; }
  .big i { font: 600 var(--fs-sub)/1.2 var(--font-text); font-style: normal; color: var(--text-3); white-space: nowrap; }
  .big i.up { color: var(--success-text); }
  .big i.down { color: var(--danger-text); }
  .bars { flex: none; display: flex; align-items: flex-end; gap: 4px; width: 84px; height: 40px; }
  .bars span { flex: 1; border-radius: var(--r-full); background: var(--accent); opacity: 0.55; transform-origin: bottom; animation: grow 520ms var(--ease-spring) backwards; }
  .bars span.now { background: var(--success); opacity: 1; }
  @keyframes grow { from { transform: scaleY(0); } }
  :global(html.lowfx) .bars span { animation: none; }
  .foot { font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .foot em { font-style: normal; }
  .foot em.new { color: var(--success-text); font-weight: 650; }
</style>
