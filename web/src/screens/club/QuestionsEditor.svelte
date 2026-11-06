<script lang="ts" module>
  import type { RoundQuestion } from '../../lib/api';
  /** A question left half-written: no text, or a choice with fewer than two options. */
  export const unfinished = (qs: RoundQuestion[]) => qs.some((q) => !q.text.trim() || ((q.kind === 'one' || q.kind === 'many') && (q.options ?? []).filter((o) => o.trim()).length < 2));
  /** As the server takes them. */
  export const toSave = (qs: RoundQuestion[]) => qs.map((q) => ({ kind: q.kind, text: q.text.trim(), options: q.kind === 'one' || q.kind === 'many' ? (q.options ?? []).map((o) => o.trim()).filter(Boolean) : null,
    required: q.required, tagId: q.tagId ?? null }));
</script>

<script lang="ts">
  // A club's own questions (up to six, from templates or written): a recruitment round's (RoundSetup) and the
  // always-open applications' (JoinQuestions). Locked (someone applied to the round): as they are, to read.
  // deps: the round's departments, so a question may be one department's alone (none: for everyone).
  import Plus from '@lucide/svelte/icons/plus';
  import type { Id, RoundKind } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import type { MenuItem } from '../../ui/menu';

  let { qs = $bindable(), locked = false, deps = [], tagName = () => '', error = false }:
    { qs: RoundQuestion[]; locked?: boolean; deps?: Id[]; tagName?: (id: Id) => string; error?: boolean } = $props();

  const KINDS: RoundKind[] = ['short', 'long', 'one', 'many', 'link'];
  const TEMPLATES: (RoundQuestion & { key: string })[] = [
    { key: 'hours', kind: 'one', text: t('cast.tplHours'), options: ['1-4', '5-8', '9-12', '13+'], required: true },
    { key: 'why', kind: 'long', text: t('cast.tplWhy'), required: true },
    { key: 'about', kind: 'long', text: t('cast.tplAbout'), required: false },
    { key: 'portfolio', kind: 'link', text: t('cast.tplPortfolio'), required: false },
    { key: 'exp', kind: 'long', text: t('cast.tplExp'), required: false },
    { key: 'insta', kind: 'short', text: t('cast.tplInsta'), required: false },
  ];
  const used = (txt: string) => qs.some((q) => q.text === txt);
  function addQ(q: RoundQuestion) { if (qs.length < 6) qs = [...qs, { ...q, options: q.options ? [...q.options] : null, tagId: null }]; }
  const kindMenu = (q: RoundQuestion): MenuItem[] => KINDS.map((k) => ({ label: t(`cast.kind.${k}`), checked: q.kind === k, onselect: () => { q.kind = k; } }));
  const forMenu = (q: RoundQuestion): MenuItem[] => [{ label: t('cast.forAll'), checked: q.tagId == null, onselect: () => { q.tagId = null; } },
    ...deps.map((d) => ({ label: t('cast.onlyFor', { name: tagName(d) }), checked: q.tagId === d, onselect: () => { q.tagId = d; } }))];
</script>

{#if locked}
  <!-- someone applied: the questions as they are, to read -->
  {#if qs.length}
    <Group>
      {#each qs as q, i (i)}
        <Row dense title={q.text} subtitle={[t(`cast.kind.${q.kind}`), q.required ? t('cast.required') : '', q.tagId ? t('cast.onlyFor', { name: tagName(q.tagId) }) : ''].filter(Boolean).join(' · ')} />
      {/each}
    </Group>
  {/if}
{:else}
  {#each qs as q, i (i)}
    <div class="q">
      <Field label={t('cast.qText')} bind:value={q.text} maxlength={200} />
      {#if q.kind === 'one' || q.kind === 'many'}
        <Field label={t('cast.options')} multiline rows={3} bind:value={() => (q.options ?? []).join('\n'), (v) => (q.options = v.split('\n'))} />
      {/if}
      <Group>
        <Row title={t('cast.qKind')} value={t(`cast.kind.${q.kind}`)} menu={kindMenu(q)} />
        <Row title={t('cast.required')} accessory="switch" checked={q.required} onchange={(on) => (q.required = on)} />
        {#if deps.length > 1}<Row title={t('cast.qFor')} value={q.tagId ? tagName(q.tagId) : t('cast.forAll')} menu={forMenu(q)} />{/if}
        <Row tone="destructive" title={t('memo.drop')} onclick={() => (qs = qs.filter((_, j) => j !== i))} />
      </Group>
    </div>
  {/each}
{/if}
{#if error}<p class="err">{t('cast.needQs')}</p>{/if}
{#if !locked && qs.length < 6}
  <div class="wrap tpls">
    {#each TEMPLATES.filter((x) => !used(x.text)) as x (x.key)}<Button kind="tinted" size="s" onclick={() => addQ(x)}>{#snippet icon()}<Plus size={14} />{/snippet}{x.text}</Button>{/each}
    <Button kind="tinted" size="s" onclick={() => addQ({ kind: 'short', text: '', required: true })}>{#snippet icon()}<Plus size={14} />{/snippet}{t('cast.ownQ')}</Button>
  </div>
{/if}

<style>
  .err { margin: 0 var(--s-4); font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--danger-text); }
  .wrap { display: flex; flex-wrap: wrap; gap: var(--s-2); padding-block: var(--s-1); }
  .tpls > :global(.btn) { max-width: 100%; }
  .q { display: flex; flex-direction: column; gap: var(--s-2); }
  .q + .q { padding-top: var(--s-3); border-top: 0.5px solid var(--separator); }
</style>
