<script lang="ts">
  import ChartNoAxesColumn from '@lucide/svelte/icons/chart-no-axes-column';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import { SvelteMap } from 'svelte/reactivity';
  import { ApiErr, type ResearchQuestion, type ResearchSurvey } from '../../lib/api';
  import { answerResearch, data } from '../../lib/state/data.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { count } from '../../lib/stats';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Group from '../../ui/Group.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Row from '../../ui/Row.svelte';

  let { overlay, survey }: { overlay: Overlay; survey: ResearchSurvey } = $props();
  const CONSENT = '2026-11-24'; // server research.ANSWER_CONSENT
  const OTHER = '__other__';
  const current = $derived(data.research?.find((r) => r.slug === survey.slug) ?? survey);
  const answers = new SvelteMap<string, string | string[]>();
  let anonymous = $state(false), busy = $state(false);
  let attempted = $state(false), sent = $state(false);
  const questions = $derived(survey.spec.sections.flatMap((s) => s.questions));
  function selected(q: ResearchQuestion, option: string): boolean {
    const value = answers.get(q.id);
    return Array.isArray(value) ? value.includes(option) : value === option;
  }
  function has(q: ResearchQuestion): boolean {
    const value = answers.get(q.id), values = Array.isArray(value) ? value : [value ?? ''];
    return values.some((v) => q.other && v === OTHER ? !!textValue(q.id + '~').trim() : !!v.trim());
  }
  function pick(q: ResearchQuestion, option: string) {
    haptic.tap();
    if (q.type === 'multi') {
      const value = answers.get(q.id), values = Array.isArray(value) ? value : [];
      answers.set(q.id, values.includes(option) ? values.filter((v) => v !== option) : [...values, option]);
    } else if (selected(q, option)) answers.delete(q.id);
    else answers.set(q.id, option);
  }
  function textValue(key: string): string { const value = answers.get(key); return typeof value === 'string' ? value : ''; }
  async function send() {
    if (busy || current.answered) return;
    attempted = true;
    if (questions.some((q) => q.required && !has(q)) || !questions.some(has)) {
      haptic.error(); say(t('research.checkAnswers'), 'warning_3d'); return;
    }
    busy = true; haptic.tap();
    try {
      await answerResearch(current, Object.fromEntries(answers), anonymous, CONSENT);
      sent = true; answers.clear(); haptic.ok(); count('do.research');
    } catch (e) {
      haptic.error();
      const code = e instanceof ApiErr ? e.code : null;
      say(t(code === 'closed' ? 'research.closed' : code === 'need_student' ? 'research.studentOnly' : 'common.error'), 'warning_3d');
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={ChartNoAxesColumn} title={survey.title} heading={survey.title} full>
  {#if current.answered || sent}
    <div class="done" role="status">
      <CircleCheck size={48} strokeWidth={1.5} />
      <h2 class="t-h2">{t(busy ? 'research.sending' : 'research.answered')}</h2>
      {#if !busy && survey.spec.thanks}<p class="t-body">{survey.spec.thanks}</p>{/if}
    </div>
  {:else}
    <div class="survey">
      {#if survey.spec.intro}<p class="intro t-body">{survey.spec.intro}</p>{/if}
      <Group>
        <Row title={t('research.anonymous')} accessory="switch" checked={anonymous} onchange={(on) => { anonymous = on; haptic.tap(); }} />
      </Group>
      {#each survey.spec.sections as section, sectionIndex (sectionIndex)}
        <section class="section">
          {#if section.title}<h2 class="t-h3">{section.title}</h2>{/if}
          {#each section.questions as q (q.id)}
            <div class="question">
              {#if q.type === 'text' || q.type === 'long'}
                <Field label={q.label + (q.required ? ' *' : '')}
                  bind:value={() => textValue(q.id), (value) => { answers.set(q.id, value); }}
                  multiline={q.type === 'long'} maxlength={q.type === 'long' ? 4000 : 200}
                  error={attempted && q.required && !has(q) ? t('research.required') : undefined} />
              {:else}
                {#if q.type === 'scale'}
                  <p class="label t-foot">{q.label}{q.required ? ' *' : ''}</p>
                  <div class="scale" role="group" aria-label={q.label}>
                    {#each ['1', '2', '3', '4', '5'] as option (option)}
                      <Chip full selected={selected(q, option)} onclick={() => pick(q, option)}>{option}</Chip>
                    {/each}
                  </div>
                {:else}
                  <Group caption={q.label + (q.required ? ' *' : '')}>
                    {#each [...(q.options ?? []), ...(q.other ? [OTHER] : [])] as option (option)}
                      <Row title={option === OTHER ? t('research.other') : option} dense accessory="check"
                        checked={selected(q, option)} onclick={() => pick(q, option)} />
                    {/each}
                  </Group>
                {/if}
                {#if q.type === 'multi'}<p class="hint t-foot">{t('research.many')}</p>{/if}
                {#if q.type === 'scale' && (q.low || q.high)}
                  <div class="ends t-foot"><span>{q.low ? `1 · ${q.low}` : ''}</span><span>{q.high ? `5 · ${q.high}` : ''}</span></div>
                {/if}
                {#if q.other && selected(q, OTHER)}
                  <Field label={t('research.otherAnswer')} bind:value={() => textValue(q.id + '~'), (value) => { answers.set(q.id + '~', value); }} maxlength={200} />
                {/if}
                {#if attempted && q.required && !has(q)}<p class="error t-foot">{t('research.required')}</p>{/if}
              {/if}
              {#if q.hint}<p class="hint t-foot">{q.hint}</p>{/if}
            </div>
          {/each}
        </section>
      {/each}
    </div>
  {/if}
  {#snippet footer()}
    {#if !current.answered && !sent}
      <p class="consent t-foot">{t(anonymous ? 'research.anonymousConsent' : 'research.signedConsent')}</p>
      <Button kind="primary" size="l" full loading={busy} onclick={send}>{t('research.submit')}</Button>
    {/if}
  {/snippet}
</Sheet>

<style>
  .survey, .section { display: flex; flex-direction: column; gap: var(--s-5); }
  .question { display: flex; flex-direction: column; gap: var(--s-2); }
  .section h2, .intro, .hint, .error { margin: 0; }
  .intro, .done p { white-space: pre-wrap; overflow-wrap: anywhere; }
  .hint, .ends { color: var(--text-2); }
  .consent { margin: 0 0 var(--s-2); color: var(--text-2); }
  .error { color: var(--danger-text); }
  .label { margin: 0; color: var(--text-2); }
  .scale { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: var(--s-2); padding-block: var(--s-1); }
  .ends { display: flex; justify-content: space-between; gap: var(--s-3); }
  .ends span { flex: 1; min-width: 0; overflow-wrap: anywhere; }
  .ends span + span { text-align: end; }
  .done { padding: var(--s-6) 0; text-align: center; color: var(--accent-text); }
  .done p { color: var(--text-2); }
</style>
