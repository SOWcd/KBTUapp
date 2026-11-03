<script lang="ts">
  // Admin → the numbers card (owner, Nov 3: just these three): everyone in the app, the KBTU-confirmed students among
  // them, and who joined today. Held with the inbox (data store), so it never pops in late. A tap pushes the stats page.
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { data } from '../../lib/state/data.svelte';
  import { open } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Skeleton from '../../ui/Skeleton.svelte';
  import StatsPane from './StatsPane.svelte';

  const st = $derived(data.adminStats);
</script>

<button class="card" onclick={() => { haptic.tap(); open(StatsPane, {}); }} aria-label={t('adm.stats')}>
  {#if st}
    <span class="n"><b class="num">{st.users}</b><i>{t('st.users')}</i></span>
    <span class="n"><b class="num">{st.students}</b><i>{t('st.students')}</i></span>
    <span class="n"><b class="num" class:new={st.newToday > 0}>+{st.newToday}</b><i>{t('st.newToday')}</i></span>
    <ChevronRight size={18} />
  {:else}
    <Skeleton kind="lines" n={2} />
  {/if}
</button>

<style>
  .card { display: flex; align-items: center; gap: var(--s-3); width: 100%; padding: var(--s-4); border-radius: var(--r-group); text-align: left; color: var(--text-3);
    background: var(--surface); box-shadow: var(--shadow-card); transition: transform 450ms var(--ease-bounce); }
  .card:active { transform: scale(0.98); transition-duration: 80ms; }
  .n { flex: 1; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .n b { font: 750 var(--fs-t1)/1 var(--font-display); letter-spacing: -0.03em; color: var(--text); }
  .n b.new { color: var(--success-text); }
  .n i { font: 500 var(--fs-sub)/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
</style>
