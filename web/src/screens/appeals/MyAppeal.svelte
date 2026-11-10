<script lang="ts">
  // One of my appeals: its status, by when the answer is due (overdue stays overdue), my words, SG's answer, Delete.
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import { api, type Id } from '../../lib/api';
  import { data } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { count } from '../../lib/stats';
  import { dayMonth } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';
  import { statusOf, lineOf } from './Appeals.svelte';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();
  const a = $derived(data.appeals?.find((x) => x.id === id));
  $effect(() => { if (data.appeals && !a) { say(t('apl.gone'), 'pleading_face_3d'); close(overlay.id, false); } });

  async function drop() {
    if (!a) return;
    if (!(await sheets.ask({ title: t('apl.deleteQ'), text: t('apl.deleteText'), ok: t('apl.delete'), cancel: t('common.cancel'), danger: true }))) return;
    const was = data.appeals ?? [];
    data.appeals = was.filter((x) => x.id !== id);
    close(overlay.id, false); haptic.ok(); say(t('apl.deleted'), 'raising_hands_3d_default'); count('apl.del');
    try { await api.dropAppeal(id); } catch { data.appeals = was; haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

<Sheet {overlay} title={t('apl.mine')} icon={Megaphone} tall>
  {#if a}
    <div class="page">
      <div class="hd">
        <Tag tone={a.overdue && a.status !== 'closed' ? 'danger' : a.status === 'closed' ? 'success' : 'accent'}>{statusOf(a)}</Tag>
        <p class="fs-sub faint">{lineOf(a)}{a.anon ? ' · ' + t('apl.anon') : ''}{a.status !== 'closed' ? ' · ' + t('apl.due', { date: dayMonth(a.due) }) : ''}</p>
      </div>
      <p class="body selectable">{a.text}</p>
      {#if a.answer}
        <Group caption={t('apl.answer')}><p class="body selectable ans">{a.answer}</p></Group>
      {/if}
      <Group><Row title={t('apl.delete')} tone="destructive" onclick={drop} /></Group>
    </div>
  {/if}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-4); }
  .hd { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-2); padding: 0 var(--s-1); }
  .body { margin: 0; padding: 0 var(--s-1); white-space: pre-wrap; overflow-wrap: anywhere; font: 450 var(--fs-row)/1.4 var(--font-text); }
  .ans { padding: var(--s-3) var(--s-4); }
</style>
