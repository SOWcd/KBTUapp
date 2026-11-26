<script lang="ts">
  // Applying to a club that takes applications any time, when it has questions of its own (toggleJoin opens this;
  // without questions Apply is one tap). The answers go with the application to the club's inbox (JoinInbox).
  import { onMount, untrack } from 'svelte';
  import ClipboardPen from '@lucide/svelte/icons/clipboard-pen';
  import { api, ApiErr, type Id } from '../../lib/api';
  import { useDraft } from '../../lib/draft';
  import { sheets } from '../../lib/state/sheets';
  import { data, phrase } from '../../lib/state/data.svelte';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { count } from '../../lib/stats';
  import { burst } from '../../ui/burst';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Answers, { missing, type Answer } from './Answers.svelte';

  let { overlay, org }: { overlay: Overlay; org: Id } = $props();

  const o = $derived(data.orgs.find((x) => x.id === org) ?? data.small.find((x) => x.id === org));
  const qs = $derived(o?.joinQuestions ?? []);
  type Draft = { questions: string; answers: Record<string, Answer> };
  const draft = useDraft<Draft>(untrack(() => `kb-join-${org}`));
  const questions = $derived(JSON.stringify(qs));
  const first = untrack(() => draft.read());
  let answers = $state<Record<string, Answer>>({});
  let tried = $state(false), busy = $state(false);
  let checkedDraft = $state(!first);
  onMount(() => {
    if (!first) return;
    let open = true;
    void api.org(org).then((fresh) => {
      if (!open || !o || !fresh.recruiting || fresh.myRole || fresh.myRequest) return;
      o.joinQuestions = fresh.joinQuestions;
      if (first.questions === JSON.stringify(fresh.joinQuestions ?? []) && !hasAnswers) answers = first.answers;
    }).catch(() => {}).finally(() => { if (open) checkedDraft = true; });
    return () => { open = false; };
  });
  const hasAnswers = $derived(qs.some((q) => {
    const a = answers[q.id];
    return Array.isArray(a) ? a.length > 0 : !!a?.trim();
  }));
  $effect(() => { if (checkedDraft) draft.track(hasAnswers ? { questions, answers } : null); });

  async function discard() {
    if (!(await sheets.ask({ title: t('ed.leaveAsk'), text: t('ed.leaveText'), ok: t('ed.leaveGo'), cancel: t('ed.stay'), danger: true }))) return;
    draft.discard();
    close(overlay.id);
  }

  async function send() {
    tried = true;
    if (!o || qs.some((q) => missing(q, answers))) { haptic.error(); return; }
    const sentAt = draft.stamp();
    busy = true;
    try {
      Object.assign(o, await api.apply(org, Object.fromEntries(qs.map((q) => [String(q.id), answers[q.id] ?? '']))));
      draft.discard(sentAt);
      data.kept++;
      count('join.sent');
      haptic.ok(); burst();
      say(phrase('say.applied'), 'raising_hands_3d_default');
      close(overlay.id);
    } catch (x) {
      haptic.error();
      count('join.fail');
      const code = x instanceof ApiErr ? x.code : '';
      if (code === 'closed' && o) o.recruiting = false;
      say(code === 'closed' ? t('join.closed') : code === 'bad_input' ? t('jr.qsChanged') : t('common.error'), 'warning_3d');
      if (code === 'bad_input') api.org(org).then((x) => o && Object.assign(o, { joinQuestions: x.joinQuestions })).catch(() => {});
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={ClipboardPen} tall title={o?.name ?? t('join.apply')} hold={() => overlay.byUser === true && hasAnswers} onhold={discard}>
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
