<script lang="ts">
  // My whole week of classes (PLAN 26: the class card on Home, tapped; the bot's "check them in the app"): a day a
  // block, each class its times, kind, room and teacher, as the portal had them. A new one from the portal replaces it.
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { data } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, subjectOf } from '../../lib/i18n/index.svelte';
  import { lessonKind } from '../../lib/i18n/subjects';
  import { weekday } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  // a weekday's name in the app's language: 2024-01-01 was a Monday (noon UTC, the same day in Almaty)
  const dayName = (wd: number) => { const w = weekday(Date.UTC(2024, 0, wd, 12) / 1000); return w.charAt(0).toUpperCase() + w.slice(1); };
  const days = $derived([1, 2, 3, 4, 5, 6, 7].map((wd) => ({ wd, list: data.schedule.filter((c) => c.weekday === wd) })).filter((d) => d.list.length));
</script>

<Sheet {overlay} tall title={t('sched.weekTitle')} icon={CalendarDays}>
  <h2 class="t-h2 hd">{t('sched.weekTitle')}</h2>
  {#each days as d (d.wd)}
    <h3 class="t-cap cap">{dayName(d.wd)}</h3>
    <div class="list surface">
      {#each d.list as c, i (i)}
        {@const lk = lessonKind(c.kind)}
        <div class="row">
          <span class="tm num"><b>{c.begins}</b><small>{c.ends}</small></span>
          <span class="tx"><b class="clamp-2">{subjectOf(c)}</b>
            <small class="ellipsis">{[lk ? t(`list.kind.${lk}Long`) : c.kind, c.room, c.teacher].filter(Boolean).join(' · ')}</small></span>
        </div>
      {/each}
    </div>
  {:else}
    <p class="t-foot none">{t('sched.none')}</p>
  {/each}
  <button class="upd" onclick={() => sheets.schedHowTo()}>{t('sched.update')}</button>
</Sheet>

<style>
  .hd { margin: 4px 0 4px; }
  .cap { margin: 16px 4px 8px; }
  .list { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .row { display: flex; align-items: flex-start; gap: 14px; padding: 11px 14px; }
  .row + .row { border-top: 1px solid var(--line); }
  .tm { flex: none; width: 46px; display: flex; flex-direction: column; gap: 2px; }
  .tm b { font: 700 15px/1.2 var(--font-text); }
  .tm small { font: 500 12.5px/1.2 var(--font-text); color: var(--text-3); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .tx b { font: 640 15px/1.25 var(--font-text); }
  .tx small { font: 500 12.5px/1.25 var(--font-text); color: var(--text-2); }
  .none { padding: 20px 4px; }
  .upd { display: block; width: 100%; height: 44px; margin-top: 16px; border-radius: var(--r-m); background: var(--surface-2); color: var(--accent-text); font: 620 14.5px/1 var(--font-text); }
</style>
