<script lang="ts">
  // My whole week of classes (PLAN 26: the class card on Home, tapped; the bot's "check them in the app"): a day a
  // block, each class its times, kind, room and teacher, as the portal had them. A new one from the portal replaces it;
  // the last row deletes it. Its languages under the week: the portal's page sent again in another one adds its names
  // (Oct 30; only what the student sends, no translation).
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import type { ClassItem } from '../../lib/api';
  import { close, open, type Overlay } from '../../lib/state/ui.svelte';
  import { data, dropSchedule } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, subjectOf, LANGS, LANG_FULL } from '../../lib/i18n/index.svelte';
  import { lessonKind } from '../../lib/i18n/subjects';
  import { weekday } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import ScheduleHowTo from './ScheduleHowTo.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  // a weekday's name in the app's language: 2024-01-01 was a Monday (noon UTC, the same day in Almaty)
  const dayName = (wd: number) => { const w = weekday(Date.UTC(2024, 0, wd, 12) / 1000); return w.charAt(0).toUpperCase() + w.slice(1); };
  // the week it had stays put while the sheet slides away after "Delete" (the store is empty at once, for the others)
  let shown: ClassItem[] = [];
  const days = $derived.by(() => {
    if (!overlay.closing) shown = data.schedule;
    return [1, 2, 3, 4, 5, 6, 7].map((wd) => ({ wd, list: shown.filter((c) => c.weekday === wd) })).filter((d) => d.list.length);
  });
  // the languages it has names in: those at least half its classes have (as the bot counts them, logic.sched_langs)
  const langs = $derived.by(() => { const all = days.flatMap((d) => d.list); return LANGS.filter((l) => 2 * all.filter((c) => c.names?.[l]).length >= all.length); });
  async function drop() {
    if (!(await sheets.ask({ title: t('sched.delAsk'), text: t('sched.delText'), ok: t('cm.delete'), cancel: t('common.cancel'), danger: true }))) return;
    close(overlay.id);
    void dropSchedule();
  }
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
  {#if days.length}
    <div class="langs">{#if langs.length}<span class="t-foot">{t('sched.langs', { langs: langs.map((l) => LANG_FULL[l]).join(', ') })}</span>{/if}
      {#if langs.length < LANGS.length}<button class="add" onclick={() => open(ScheduleHowTo, { addLang: true })}>{t('sched.addLang')}</button>{/if}</div>
  {/if}
  <button class="upd" onclick={() => sheets.schedHowTo()}>{t('sched.update')}</button>
  {#if days.length}<button class="upd red" onclick={drop}>{t('sched.del')}</button>{/if}
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
  /* a quiet line: the languages in grey, the action at its end */
  .langs { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 44px; margin: 8px 4px -8px; }
  .add { flex: none; min-height: 44px; margin-left: auto; color: var(--accent-text); font: 620 var(--fs-sub)/1.2 var(--font-text); }
  .upd { display: block; width: 100%; height: 44px; margin-top: 16px; border-radius: var(--r-m); background: var(--surface-2); color: var(--accent-text); font: 620 14.5px/1 var(--font-text); text-align: center; }
  .upd.red { margin-top: 8px; color: var(--danger-text); }
</style>
