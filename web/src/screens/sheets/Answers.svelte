<script lang="ts" module>
  import type { RoundQuestion } from '../../lib/api';
  export type Answer = string | string[];
  /** A required question without an answer yet. */
  export const missing = (q: RoundQuestion & { id: number }, answers: Record<string, Answer>) =>
    q.required && !(Array.isArray(answers[q.id]) ? (answers[q.id] as string[]).length : String(answers[q.id] ?? '').trim());
</script>

<script lang="ts">
  // A student's answers to a club's own questions: a recruitment round's (RoundApply) and the always-open
  // applications' (JoinApply). Choices are chips; the rest fields, as long as the server takes them.
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Field from '../../ui/Field.svelte';
  import Chip from '../../ui/Chip.svelte';

  let { questions, answers = $bindable(), tried = false }:
    { questions: (RoundQuestion & { id: number })[]; answers: Record<string, Answer>; tried?: boolean } = $props();

  function toggleMany(qid: number, opt: string) {
    const cur = (answers[qid] as string[] | undefined) ?? [];
    answers[qid] = cur.includes(opt) ? cur.filter((x) => x !== opt) : [...cur, opt];
  }
</script>

{#each questions as q (q.id)}
  {@const label = q.text + (q.required ? '' : ' · ' + t('cast.optional'))}
  {@const error = tried && missing(q, answers) ? t('ed.need') : undefined}
  {#if q.kind === 'one' || q.kind === 'many'}
    <div class="q">
      <span class="lab">{label}</span>
      <div class="opts">
        {#each q.options ?? [] as o (o)}
          {@const on = q.kind === 'one' ? answers[q.id] === o : ((answers[q.id] as string[] | undefined) ?? []).includes(o)}
          <Chip selected={on} onclick={() => { haptic.select(); if (q.kind === 'one') answers[q.id] = o; else toggleMany(q.id, o); }}>{o}</Chip>
        {/each}
      </div>
      {#if error}<p class="err">{error}</p>{/if}
    </div>
  {:else}
    <Field {label} {error} multiline={q.kind === 'long'} rows={4} maxlength={q.kind === 'long' ? 2000 : q.kind === 'link' ? 300 : 200}
      type={q.kind === 'link' ? 'url' : 'text'} inputmode={q.kind === 'link' ? 'url' : 'text'} placeholder={q.kind === 'link' ? 'https://' : ''}
      bind:value={() => String(answers[q.id] ?? ''), (v) => (answers[q.id] = v)} />
  {/if}
{/each}

<style>
  .q { display: flex; flex-direction: column; gap: 6px; }
  .lab { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); } /* ui/Field's label */
  .opts { display: flex; flex-wrap: wrap; gap: var(--s-2); padding-block: var(--s-1); }
  /* engine: ui/Chip could wrap a long label (a question's options are sentences sometimes) */
  .opts :global(.fc) { max-width: 100%; height: auto; min-height: var(--ctl-s); padding-block: var(--s-2); white-space: normal; line-height: 1.25; text-align: left; }
  .err { margin-top: 6px; padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--danger-text); }
</style>
