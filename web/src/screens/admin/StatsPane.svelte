<script lang="ts">
  // Admin → the numbers card → this page (pushed from the right): active in a day, a week, a month; the 30 days as bars
  // (a finger slides along them; a day picked says how many came and who); the AI translator a row away. Counts only,
  // no per-person logs; the chart is the nightly rows.
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import { api, type AdminDay } from '../../lib/api';
  import { data } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t, tn, i18n } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { fold } from '../../ui/fold';
  import Pane from '../../ui/Pane.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import { almatyDay, week } from './stats';

  let { overlay }: { overlay: Overlay } = $props();
  const st = $derived(data.adminStats);
  const today = almatyDay();
  const slots = $derived(st ? week(st, today, 30) : []);
  const peak = $derived(Math.max(1, ...slots.map((d) => d.n ?? 0)));

  // a day tapped on the chart: how many and who came in
  let picked = $state<AdminDay | null>(null), pickedDay = $state<number | null>(null);
  async function pickDay(day: number, toggle = true) {
    if (pickedDay === day && !toggle) return;
    haptic.select();
    if (pickedDay === day) { pickedDay = null; picked = null; return; }
    pickedDay = day; picked = null;
    try { const d = await api.adminDay(day); if (pickedDay === day) picked = d; } catch { say(t('common.error'), 'warning_3d'); }
  }
  // a bar is ~8 px wide: the finger picks by where it is along the chart, and slides from day to day
  let scrub = false;
  function at(e: PointerEvent, toggle: boolean) {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    const i = Math.min(slots.length - 1, Math.max(0, Math.floor(((e.clientX - r.left) / r.width) * slots.length)));
    void pickDay(slots[i].day, toggle);
  }
  const dayName = (day: number) => new Intl.DateTimeFormat(i18n.lang, { weekday: 'short', day: 'numeric', month: 'short', timeZone: 'UTC' }).format(new Date(day * 864e5));
</script>

<Pane {overlay} title={t('adm.stats')}>
  {#if st}
    <div class="page stagger">
      <div class="tiles">
        {#each [['st.day', st.day], ['st.week', st.week], ['st.month', st.month]] as [string, number][] as [k, n] (k)}
          <span class="tile"><b class="num">{n}</b><i>{t(k as 'st.day')}</i></span>
        {/each}
      </div>

      <div class="chartbox">
        <div class="chart" role="group" aria-label={t('st.chart')} onpointerdown={(e) => { scrub = true; at(e, true); }} onpointermove={(e) => scrub && at(e, false)}
          onpointerup={() => (scrub = false)} onpointercancel={() => (scrub = false)}>
          <!-- the buttons are for the keyboard and screen readers (a pointer tap is handled by the chart: e.detail is 0 only for keys) -->
          {#each slots as d, i (d.day)}<button class:none={d.n == null} class:on={pickedDay === d.day} class:now={d.day === today} onclick={(e) => e.detail === 0 && pickDay(d.day)}
            aria-label={`${dayName(d.day)}: ${d.n ?? 0}`}><span style:height="{d.n == null ? 4 : Math.max(6, (d.n / peak) * 100)}%" style:animation-delay="{i * 12}ms"></span></button>{/each}
        </div>
        <div class="foot"><i>{t('st.chart')}</i><i class="num">{t('st.peak', { n: peak })}</i></div>
      </div>

      {#if pickedDay != null}
        <div transition:fold>
          <Group caption={dayName(pickedDay) + (picked ? ' · ' + tn('st.dayCame', picked.active) + (picked.new ? ' · ' + tn('st.dayNew', picked.new) : '') : '')}>
            {#if picked?.people}
              {#each picked.people as p (p.id)}
                <Row dense title={p.name} subtitle={p.username ? '@' + p.username : undefined} disabled={!p.profile && !p.username}
                  accessory={p.profile ? 'chevron' : p.username ? 'external' : 'none'} onclick={() => (p.profile ? sheets.person(p.id) : openLink('https://t.me/' + p.username))}>
                  {#snippet lead()}<Avatar person={{ id: p.id, name: p.name }} size={32} tappable={false} />{/snippet}
                  {#snippet detail()}{#if p.new}<Tag tone="success">{t('st.newOne')}</Tag>{/if}{/snippet}
                </Row>
              {/each}
            {:else if picked}<EmptyState inline text={t('st.dayOld')} />
            {:else}<EmptyState inline text="…" />{/if}
          </Group>
        </div>
      {/if}

      {#if st.ai}
        <Group>
          <Row title={t('ai.title')} value={st.ai.on ? String(st.ai.today) : t('ex.no')} accessory="chevron"
            onclick={() => { haptic.tap(); sheets.adminAi(); }}>{#snippet lead()}<span class="gi"><Sparkles size={22} strokeWidth={1.9} /></span>{/snippet}</Row>
        </Group>
      {/if}
    </div>
  {/if}
</Pane>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-6); }
  .tiles { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--s-2); }
  .tile { display: flex; flex-direction: column; gap: 4px; min-width: 0; padding: 14px; border-radius: var(--r-l); box-shadow: var(--shadow-card);
    background: radial-gradient(90% 70% at 15% 0%, var(--accent-soft), transparent 70%), var(--surface); }
  .tile b { font: 750 var(--fs-t1)/1 var(--font-display); letter-spacing: -0.03em; }
  .tile i { font: 500 var(--fs-sub)/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .chartbox { display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-4); border-radius: var(--r-group); background: var(--surface); box-shadow: var(--shadow-card); }
  .chart { display: flex; align-items: stretch; gap: 3px; height: 120px; touch-action: pan-y; }
  .chart button { flex: 1; min-width: 0; display: flex; align-items: flex-end; padding: 0; }
  .chart span { width: 100%; border-radius: var(--r-full); background: var(--accent); opacity: 0.9; transform-origin: bottom;
    transition: opacity var(--t-base); animation: grow 560ms var(--ease-spring) backwards; }
  @keyframes grow { from { transform: scaleY(0); } }
  :global(html.lowfx) .chart span { animation: none; }
  .chart .none span { background: var(--line); }
  .chart .now span { background: var(--success); opacity: 1; } /* today, still counting */
  .chart:has(.on) button:not(.on) span { opacity: 0.25; }
  .chart .on span { opacity: 1; }
  .foot { display: flex; justify-content: space-between; gap: var(--s-2); }
  .gi { display: inline-flex; width: 26px; justify-content: center; color: var(--text-2); }
  .foot i { font: 500 var(--fs-cap)/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
</style>
