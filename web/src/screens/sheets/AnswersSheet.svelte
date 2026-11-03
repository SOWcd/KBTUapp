<script lang="ts">
  // An event's own questions at sign-up (Oct 30, an organizer's ask: "a few more fields the buyer fills in"): asked in
  // the "I'm going" tap, sent with it. Text or a choice; the required ones must be answered. Closed without
  // answering: no sign-up. The organizers see the answers (Attendees, the CSV); they go 30 days after the event.
  import { onDestroy, untrack } from 'svelte';
  import type { Question } from '../../lib/api';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import MessageCircleQuestion from '@lucide/svelte/icons/message-circle-question';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Chip from '../../ui/Chip.svelte';

  let { overlay, title, questions, done }: { overlay: Overlay; title: string; questions: Question[]; done: (a: { q: string; a: string }[] | null) => void } = $props();
  let answers = $state<string[]>(untrack(() => questions.map(() => ''))); // the sheet asks one fixed list
  let tried = $state(false);
  let sent = false;
  const missing = (i: number) => questions[i].required && !answers[i].trim();
  const ready = $derived(questions.every((_, i) => !missing(i)));
  function go() {
    tried = true;
    if (!ready) { haptic.error(); return; }
    sent = true; done(answers.map((a, i) => ({ q: questions[i].label, a: a.trim() }))); close(overlay.id); // each with its question: an edit meanwhile is caught
  }
  onDestroy(() => { if (!sent) done(null); }); // closed some other way: not signed up
</script>

<Sheet {overlay} icon={MessageCircleQuestion} title={title}>
  <div class="page">
    <div class="hd">
      <h2 class="fs-sec">{t('qs.title')}</h2>
      <p class="fs-sub dim">{t('qs.sub')}</p>
    </div>
    {#each questions as q, i (i)}
      {@const bad = tried && missing(i)}
      {#if q.kind === 'choice'}
        <div class="q" class:bad role="group" aria-label={q.label}>
          <span class="lb">{q.label}{#if q.required}<i> *</i>{/if}</span>
          <div class="opts">
            {#each q.options ?? [] as o (o)}
              <Chip selected={answers[i] === o} onclick={() => { answers[i] = answers[i] === o ? '' : o; haptic.select(); }}>{o}</Chip>
            {/each}
          </div>
          {#if bad}<p class="err">{t('ed.need')}</p>{/if}
        </div>
      {:else}
        <Field label={q.label + (q.required ? ' *' : '')} bind:value={answers[i]} maxlength={200} error={bad ? t('ed.need') : undefined}
          enterkeyhint={i === questions.length - 1 ? 'done' : 'next'} />
      {/if}
    {/each}
  </div>
  {#snippet footer()}
    <Button kind="primary" size="l" full onclick={go}>{t('event.go')}</Button>
  {/snippet}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-5); }
  .hd { display: flex; flex-direction: column; gap: var(--s-1); padding: 0 var(--s-1); }
  /* a choice question: Field's label and error line around a row of chips */
  .q { display: flex; flex-direction: column; gap: 6px; }
  .lb, .err { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .lb i { color: var(--danger-text); font-style: normal; }
  .err { color: var(--danger-text); }
  .opts { display: flex; flex-wrap: wrap; gap: var(--s-2); padding: var(--s-1) 0; }
</style>
