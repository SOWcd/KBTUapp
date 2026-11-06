<script lang="ts">
  // The always-open applications' own questions (Vice+; club presidents, Nov 6): the same editor as a round's. Sent
  // applications keep the questions' text with their answers, so these may change any time.
  import { untrack } from 'svelte';
  import ClipboardPen from '@lucide/svelte/icons/clipboard-pen';
  import { api, type Id, type RoundQuestion } from '../../lib/api';
  import { data } from '../../lib/state/data.svelte';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import QuestionsEditor, { toSave, unfinished } from './QuestionsEditor.svelte';

  let { overlay, org }: { overlay: Overlay; org: Id } = $props();

  const o = $derived(data.orgs.find((x) => x.id === org));
  let qs = $state<RoundQuestion[]>(untrack(() => (o?.joinQuestions ?? []).map((q) => ({ ...q, options: q.options ? [...q.options] : null }))));
  let tried = $state(false), busy = $state(false);

  async function save() {
    tried = true;
    if (unfinished(qs)) { haptic.error(); return; }
    busy = true;
    try {
      const x = await api.updateOrg(org, { joinQuestions: toSave(qs) });
      if (o) o.joinQuestions = x.joinQuestions;
      haptic.ok(); say(t('cast.updated'), 'sparkles_3d'); close(overlay.id);
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={ClipboardPen} full title={t('cast.questions')}>
  <div class="stack">
    <p class="hint">{t('jr.qsHint')}</p>
    <QuestionsEditor bind:qs error={tried && unfinished(qs)} />
  </div>
  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} onclick={save}>{t('common.save')}</Button>
  {/snippet}
</Sheet>

<style>
  .stack { display: flex; flex-direction: column; gap: var(--s-3); }
  .hint { margin: 0 var(--s-4); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
</style>
