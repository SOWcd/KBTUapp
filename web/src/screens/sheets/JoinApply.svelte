<script lang="ts">
  // Applying to a club that takes applications any time, when it has questions of its own (toggleJoin opens this;
  // without questions Apply is one tap). The answers go with the application to the club's inbox (JoinInbox).
  // ponytail: no draft kept on the phone (RoundApply keeps one); add it if long answers get lost to Telegram closing.
  import ClipboardPen from '@lucide/svelte/icons/clipboard-pen';
  import { api, ApiErr, type Id } from '../../lib/api';
  import { data, phrase } from '../../lib/state/data.svelte';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Answers, { missing, type Answer } from './Answers.svelte';

  let { overlay, org }: { overlay: Overlay; org: Id } = $props();

  const o = $derived(data.orgs.find((x) => x.id === org));
  const qs = $derived(o?.joinQuestions ?? []);
  let answers = $state<Record<string, Answer>>({});
  let tried = $state(false), busy = $state(false);

  async function send() {
    tried = true;
    if (!o || qs.some((q) => missing(q, answers))) { haptic.error(); return; }
    busy = true;
    try {
      Object.assign(o, await api.apply(org, Object.fromEntries(qs.map((q) => [String(q.id), answers[q.id] ?? '']))));
      data.kept++;
      haptic.ok(); burst();
      say(phrase('say.applied'), 'raising_hands_3d_default');
      close(overlay.id);
    } catch (x) {
      haptic.error();
      const code = x instanceof ApiErr ? x.code : '';
      if (code === 'closed' && o) o.recruiting = false;
      say(code === 'closed' ? t('join.closed') : code === 'bad_input' ? t('jr.qsChanged') : t('common.error'), 'warning_3d');
      if (code === 'bad_input') api.org(org).then((x) => o && Object.assign(o, { joinQuestions: x.joinQuestions })).catch(() => {});
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={ClipboardPen} tall title={o?.name ?? t('join.apply')}>
  <div class="body">
    <p class="t-foot">{t('cast.shares')}</p>
    <Answers questions={qs} bind:answers {tried} />
  </div>
  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} onclick={send}>{t('cast.send')}</Button>
  {/snippet}
</Sheet>

<style>
  .body { display: flex; flex-direction: column; gap: var(--gap-group); }
  .body > p { margin: 0 var(--s-4); }
</style>
