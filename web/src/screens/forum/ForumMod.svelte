<script lang="ts">
  // The forum's moderators: requests waiting for a word (held by the AI, or reported enough without its agreement),
  // each due a day on, to let go live or hide; and the skills catalog: new names to approve, any name to rename, merge
  // into another, or delete. Empty and silent for everyone else (the server says no).
  import { api, ApiErr, type ForumMod, type ModAsk, type Skill } from '../../lib/api';
  import { say } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { nowTs, duration } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import SearchField from '../../ui/SearchField.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Section from '../../ui/Section.svelte';
  import Field from '../../ui/Field.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Button from '../../ui/Button.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { changed, round = 0 }: { changed: () => void; round?: number } = $props();
  let mod = $state<ForumMod | null>(null);
  let q = $state(''), found = $state<Skill[]>([]), open = $state<Skill | null>(null), name = $state(''), into = $state(''), targets = $state<Skill[]>([]);
  const load = () => api.forumMod().then((m) => (mod = m)).catch(() => (mod = null));
  $effect(() => { void round; load(); });
  const search = (s: string, then: (l: Skill[]) => void) => { if (s.trim()) api.skills(s.trim()).then(then).catch(() => then([])); else then([]); };
  $effect(() => search(q, (l) => (found = l)));
  $effect(() => search(into, (l) => (targets = l.filter((x) => x.id !== open?.id))));

  const fail = (e: unknown) => { haptic.error(); say(t(e instanceof ApiErr && e.code === 'conflict' ? 'fo.mod.taken' : 'common.error'), 'pleading_face_3d'); };
  const due = (a: ModAsk) => a.dueAt > nowTs() ? t('fo.mod.dueIn', { left: duration(a.dueAt - nowTs()) }) : t('fo.mod.overdue');
  async function decide(a: ModAsk, live: boolean) {
    try { await (live ? api.releaseAsk(a.id) : api.hideAsk(a.id)); haptic.ok(); load(); changed(); } catch (e) { fail(e); }
  }
  function pick(s: Skill) { open = open?.id === s.id ? null : s; name = s.name; into = ''; }
  async function change(s: Skill, c: Parameters<typeof api.skillMod>[1]) {
    try { await api.skillMod(s.id, c); haptic.ok(); open = null; load(); search(q, (l) => (found = l)); changed(); } catch (e) { fail(e); }
  }
  const shown = $derived(q.trim() ? found : mod?.skills ?? []);
</script>

{#if mod}
  <div class="col">
    {#if mod.held.length}
      <!-- a request: the words, whose, why and when it's due, the two answers (AdminForum's post rows) -->
      <Group caption={t('fo.mod.waiting')}>
        {#each mod.held as a (a.id)}
          <div class="mrow">
            <div class="ah"><span class="why">{t(`fo.mod.why.${a.why}`)}</span><span class="mm" class:late={a.dueAt <= nowTs()}>{due(a)}</span></div>
            <b class="at">{a.title}</b>
            {#if a.body}<p class="ab">{a.body}</p>{/if}
            <span class="mm">{a.author.name}{a.skills.length ? ` · ${a.skills.map((s) => s.name).join(', ')}` : ''}</span>
            <span class="mb">
              {#if a.status === 'held'}<Button kind="tinted" size="s" onclick={() => decide(a, true)}>{t('fo.mod.release')}</Button>{/if}
              <Button kind="gray" size="s" onclick={() => decide(a, false)}>{t('fo.mod.hide')}</Button>
            </span>
          </div>
        {/each}
      </Group>
    {/if}

    <Section title={t('fo.mod.catalog')}>
      <SearchField bind:value={q} placeholder={t('fo.mod.catalogPh')} />
      <Group>
        {#each shown as s (s.id)}
          <Row dense title={s.name} value={`${s.public ? '' : `${t('fo.mod.new')} · `}${t('fo.mod.people', { n: s.people ?? 0 })}`}
            accessory="disclosure" open={open?.id === s.id} onclick={() => pick(s)} />
          {#if open?.id === s.id}
            <div class="edit">
              <Field label={t('fo.mod.rename')} bind:value={name} maxlength={24} />
              <Button kind="tinted" size="s" disabled={!name.trim() || name.trim() === s.name} onclick={() => change(s, { name })}>{t('fo.mod.rename')}</Button>
              <Field label={t('fo.mod.mergePh')} bind:value={into} />
              {#if targets.length}<div class="sk">{#each targets as x (x.id)}<Chip selected={false} onclick={() => change(s, { into: x.id })}>→ {x.name}</Chip>{/each}</div>{/if}
              <span class="mb">
                {#if !s.public}<Button kind="tinted" size="s" onclick={() => change(s, { approve: true })}>{t('fo.mod.approve')}</Button>{/if}
                <Button kind="destructive" size="s" onclick={() => change(s, { delete: true })}>{t('fo.mod.delete')}</Button>
              </span>
            </div>
          {/if}
        {:else}
          <EmptyState inline text={t(q.trim() ? 'fo.mod.noneFound' : 'fo.mod.noneNew')} />
        {/each}
      </Group>
    </Section>
  </div>
{/if}

<style>
  .col { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--gap-group); }
  .mrow { position: relative; display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-3) var(--s-4); }
  .mrow + .mrow::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .ah { display: flex; justify-content: space-between; align-items: center; gap: var(--s-2); }
  .why { font: 600 var(--fs-cap)/1.2 var(--font-text); color: var(--warning-text); }
  .mm { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .late { color: var(--danger-text); font-weight: 600; }
  .at { font: 600 var(--fs-body)/1.3 var(--font-text); }
  .ab { font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text-2); white-space: pre-line; }
  .mb { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  /* a skill opened in place: rename, merge into another, approve or delete, under its row */
  .edit { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-2); padding: 0 var(--s-4) var(--s-4); }
  .edit > :global(.fld) { align-self: stretch; }
  .sk { display: flex; flex-wrap: wrap; gap: var(--s-2); padding: 4px 0; }
</style>
