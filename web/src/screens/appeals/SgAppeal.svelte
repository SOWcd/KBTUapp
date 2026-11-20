<script lang="ts">
  // One appeal in SG's queue: opening it is logged (server appeals.detail). The author: a named one's short name, an
  // anonymous one's never. The status and the answer; closing needs an answer (the server says so too). The author gets
  // a template message from the bot on the first answer, never the words. desk 'help': a question at the help desk, the same way.
  import { onMount, untrack } from 'svelte';
  import Inbox from '@lucide/svelte/icons/inbox';
  import { api, ApiErr, type Appeal, type AppealStatus, type Id } from '../../lib/api';
  import { data } from '../../lib/state/data.svelte';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { dayMonth } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import Tag from '../../ui/Tag.svelte';
  import { statusOf, lineOf, type Desk } from './Appeals.svelte';

  let { overlay, id, desk = 'sg' }: { overlay: Overlay; id: Id; desk?: Desk } = $props();
  const sg = untrack(() => desk === 'sg');
  // the queue's row at once (its first line only, no answer); the server's whole (the logged look) replaces it
  const was = untrack(() => (sg ? data.sg : data.helpq)?.items.find((x) => x.id === id));
  let a = $state<Appeal | undefined>(was), full = $state(false);
  let status = $state<AppealStatus>(was?.status ?? 'new'), answer = $state(''), busy = $state(false);
  onMount(() => {
    (sg ? api.sgAppeal(id) : api.helpAppeal(id)).then((x) => { a = x; status = x.status; answer = x.answer ?? ''; full = true; }).catch((e) => {
      if (e instanceof ApiErr && e.code !== 'unavailable') { say(t(sg ? 'apl.gone' : 'ask.gone'), 'pleading_face_3d'); close(overlay.id, false); }
    });
  });
  const changed = $derived(!!a && full && (status !== a.status || answer.trim() !== (a.answer ?? '')));
  const blocked = $derived(status === 'closed' && !answer.trim());

  async function save() {
    if (!a || !changed || blocked || busy) return;
    busy = true;
    try {
      const x = await (sg ? api.sgAct : api.helpAct)(id, { status, answer: answer.trim() });
      a = x; haptic.ok(); say(t('apl.saved'), 'raising_hands_3d_default');
      if (sg && data.sg) data.sg = { ...data.sg, items: data.sg.items.map((y) => (y.id === id ? { ...x, text: y.text } : y)) };
      if (!sg && data.helpq) data.helpq = { ...data.helpq, items: data.helpq.items.map((y) => (y.id === id ? { ...x, text: y.text } : y)) };
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); } finally { busy = false; }
  }
</script>

<Sheet {overlay} title={t(sg ? 'apl.sgRow' : 'ask.queue')} icon={Inbox} full>
  {#if a}
    <div class="page">
      <div class="hd">
        <Tag tone={a.overdue && a.status !== 'closed' ? 'danger' : a.status === 'closed' ? 'success' : 'accent'}>{statusOf(a)}</Tag>
        <p class="fs-sub faint">{a.anon ? t('apl.anonAuthor') : a.author ?? ''} · {lineOf(a)}{a.status !== 'closed' ? ' · ' + t('apl.due', { date: dayMonth(a.due) }) : ''}</p>
      </div>
      <p class="body selectable">{a.text}</p>
      {#if full}
        <Segmented bind:value={status} label={t('apl.status')} items={(['new', 'work', 'closed'] as AppealStatus[]).map((v) => ({ value: v, label: t(`apl.st.${v}`) }))} />
        <Field label={t(sg ? 'apl.answer' : 'ask.answer')} placeholder={t('apl.answerPh')} bind:value={answer} multiline rows={4} maxlength={4000}
          error={blocked ? t('apl.needAnswer') : undefined} />
      {/if}
    </div>
  {/if}
  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} disabled={!changed || blocked} onclick={save}>{t('common.save')}</Button>
  {/snippet}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-4); }
  .hd { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-2); padding: 0 var(--s-1); }
  .body { margin: 0; padding: 0 var(--s-1); white-space: pre-wrap; overflow-wrap: anywhere; font: 450 var(--fs-row)/1.4 var(--font-text); }
</style>
