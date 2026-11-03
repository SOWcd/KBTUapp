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
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
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
  <div class="week">
    {#each days as d (d.wd)}
      <Group caption={dayName(d.wd)}>
        {#each d.list as c, i (i)}
          {@const lk = lessonKind(c.kind)}
          <Row dense title={subjectOf(c)} subtitle={[lk ? t(`list.kind.${lk}Long`) : c.kind, c.room, c.teacher].filter(Boolean).join(' · ')}>
            {#snippet lead()}<span class="tm num"><b>{c.begins}</b><small>{c.ends}</small></span>{/snippet}
          </Row>
        {/each}
      </Group>
    {:else}
      <EmptyState icon={CalendarDays} text={t('sched.none')} />
    {/each}
    <Group footnote={days.length && langs.length ? t('sched.langs', { langs: langs.map((l) => LANG_FULL[l]).join(', ') }) : undefined}>
      {#if days.length && langs.length < LANGS.length}<Row tone="action" title={t('sched.addLang')} onclick={() => open(ScheduleHowTo, { addLang: true })} />{/if}
      <Row tone="action" title={t('sched.update')} onclick={() => sheets.schedHowTo()} />
    </Group>
    {#if days.length}<Group><Row tone="destructive" title={t('sched.del')} onclick={drop} /></Group>{/if}
  </div>
</Sheet>

<style>
  .week { display: flex; flex-direction: column; gap: var(--gap-group); }
  .tm { width: 46px; display: flex; flex-direction: column; gap: 2px; }
  .tm b { font: 700 var(--fs-body)/1.2 var(--font-text); }
  .tm small { font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
</style>
