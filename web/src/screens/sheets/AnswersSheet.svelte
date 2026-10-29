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
  import Button from '../../ui/Button.svelte';

  let { overlay, title, questions, done }: { overlay: Overlay; title: string; questions: Question[]; done: (a: string[] | null) => void } = $props();
  let answers = $state<string[]>(untrack(() => questions.map(() => ''))); // the sheet asks one fixed list
  let tried = $state(false);
  let sent = false;
  const missing = (i: number) => questions[i].required && !answers[i].trim();
  const ready = $derived(questions.every((_, i) => !missing(i)));
  function go() {
    tried = true;
    if (!ready) { haptic.error(); return; }
    sent = true; done(answers.map((a) => a.trim())); close(overlay.id);
  }
  onDestroy(() => { if (!sent) done(null); }); // closed some other way: not signed up
</script>

<Sheet {overlay} title={title}>
  <h2 class="t-h2 hd">{t('qs.title')}</h2>
  <p class="t-foot sub">{t('qs.sub')}</p>
  {#each questions as q, i (i)}
    <div class="q" class:bad={tried && missing(i)}>
      <span class="t-cap lb">{q.label}{#if q.required}<i> *</i>{/if}</span>
      {#if q.kind === 'choice'}
        <div class="opts">
          {#each q.options ?? [] as o (o)}
            <button class:on={answers[i] === o} aria-pressed={answers[i] === o} onclick={() => { answers[i] = answers[i] === o ? '' : o; haptic.select(); }}>{o}</button>
          {/each}
        </div>
      {:else}
        <input bind:value={answers[i]} maxlength="200" enterkeyhint={i === questions.length - 1 ? 'done' : 'next'} />
      {/if}
    </div>
  {/each}
  {#snippet footer()}
    <Button kind="primary" size="l" full onclick={go}>{t('event.go')}</Button>
  {/snippet}
</Sheet>

<style>
  .hd { margin: 4px 0 2px; }
  .sub { margin-bottom: 14px; }
  .q { display: flex; flex-direction: column; gap: 8px; margin-bottom: 16px; }
  .lb { margin-left: 2px; }
  .lb i { color: var(--danger-text); font-style: normal; }
  .q input { height: 46px; padding: 0 14px; border-radius: 14px; background: var(--surface-2); color: var(--text); font: 450 16px/1 var(--font-text);
    box-shadow: inset 0 0 0 1.5px transparent; transition: box-shadow var(--t-base) var(--ease); }
  .q.bad input, .q.bad .opts { box-shadow: inset 0 0 0 1.5px var(--danger); border-radius: 14px; }
  .opts { display: flex; flex-wrap: wrap; gap: 8px; }
  .opts button { height: 38px; padding: 0 16px; border-radius: var(--r-full); background: var(--surface-2); color: var(--text-2); font: 620 14.5px/1 var(--font-text);
    transition: background-color var(--t-base) var(--ease), color var(--t-base) var(--ease), transform var(--t-fast) var(--ease); }
  .opts button:active { transform: scale(0.95); }
  .opts button.on { background: var(--accent); color: #fff; }
</style>
