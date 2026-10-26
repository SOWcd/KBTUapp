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

  let { changed }: { changed: () => void } = $props();
  let mod = $state<ForumMod | null>(null);
  let q = $state(''), found = $state<Skill[]>([]), open = $state<Skill | null>(null), name = $state(''), into = $state(''), targets = $state<Skill[]>([]);
  const load = () => api.forumMod().then((m) => (mod = m)).catch(() => (mod = null));
  load();
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
  {#if mod.held.length}
    <h3 class="t-cap cap">{t('fo.mod.waiting')}</h3>
    {#each mod.held as a (a.id)}
      <article class="ask surface">
        <div class="ah"><span class="why">{t(`fo.mod.why.${a.why}`)}</span><span class="t-foot" class:late={a.dueAt <= nowTs()}>{due(a)}</span></div>
        <b class="at">{a.title}</b>
        {#if a.body}<p class="ab">{a.body}</p>{/if}
        <span class="t-foot">{a.author.name}{a.skills.length ? ` · ${a.skills.map((s) => s.name).join(', ')}` : ''}</span>
        <div class="acts">
          {#if a.status === 'held'}<button class="go" onclick={() => decide(a, true)}>{t('fo.mod.release')}</button>{/if}
          <button class="no" onclick={() => decide(a, false)}>{t('fo.mod.hide')}</button>
        </div>
      </article>
    {/each}
  {/if}

  <h3 class="t-cap cap">{t('fo.mod.catalog')}</h3>
  <SearchField bind:value={q} placeholder={t('fo.mod.catalogPh')} />
  <div class="list surface">
    {#each shown as s (s.id)}
      <button class="row" onclick={() => pick(s)}>
        <b class="ellipsis">{s.name}</b><span class="t-foot">{s.public ? '' : `${t('fo.mod.new')} · `}{t('fo.mod.people', { n: s.people ?? 0 })}</span>
      </button>
      {#if open?.id === s.id}
        <div class="edit">
          <div class="acts">
            <input class="field" bind:value={name} maxlength="24" aria-label={t('fo.mod.rename')} />
            <button class="go" disabled={!name.trim() || name.trim() === s.name} onclick={() => change(s, { name })}>{t('fo.mod.rename')}</button>
          </div>
          <input class="field" bind:value={into} placeholder={t('fo.mod.mergePh')} />
          {#if targets.length}<div class="sk">{#each targets as x (x.id)}<button class="chip" onclick={() => change(s, { into: x.id })}>→ {x.name}</button>{/each}</div>{/if}
          <div class="acts">
            {#if !s.public}<button class="go" onclick={() => change(s, { approve: true })}>{t('fo.mod.approve')}</button>{/if}
            <button class="no" onclick={() => change(s, { delete: true })}>{t('fo.mod.delete')}</button>
          </div>
        </div>
      {/if}
    {:else}
      <p class="t-foot empty">{t(q.trim() ? 'fo.mod.noneFound' : 'fo.mod.noneNew')}</p>
    {/each}
  </div>
{/if}

<style>
  .cap { margin: 22px 4px 10px; }
  .ask { display: flex; flex-direction: column; gap: 8px; padding: 14px; border-radius: var(--r-l); margin-bottom: 10px; }
  .ah { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
  .why { font: 700 11px/1 var(--font-text); letter-spacing: 0.06em; text-transform: uppercase; color: var(--warning-text, var(--text-2)); }
  .late { color: var(--danger, var(--text)); font-weight: 650; }
  .at { font: 680 16px/1.25 var(--font-text); }
  .ab { font: 450 14px/1.4 var(--font-text); color: var(--text-2); white-space: pre-line; }
  .acts { display: flex; gap: 8px; align-items: center; }
  .go, .no { flex: none; height: 32px; padding: 0 12px; border-radius: var(--r-full); font: 650 13px/1 var(--font-text); }
  .go { background: var(--accent-soft); color: var(--accent-text); }
  .go:disabled { background: var(--surface-2); color: var(--text-3); }
  .no { background: var(--surface-2); color: var(--text-2); }
  .list { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; margin-top: 10px; }
  .row { display: flex; align-items: baseline; justify-content: space-between; gap: 10px; padding: 12px 14px; text-align: left; }
  .row + .row, .edit + .row { border-top: 1px solid var(--line); }
  .row b { font: 620 15px/1.25 var(--font-text); min-width: 0; }
  .edit { display: flex; flex-direction: column; gap: 8px; padding: 0 14px 12px; }
  .field { min-width: 0; height: 36px; padding: 0 12px; border-radius: var(--r-m, 10px); background: var(--surface-2); color: var(--text); font: 500 14px/1 var(--font-text); }
  .acts .field { flex: 1; }
  .sk { display: flex; flex-wrap: wrap; gap: 6px; }
  .chip { display: inline-flex; align-items: center; height: 28px; padding: 0 10px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 600 13px/1 var(--font-text); }
  .empty { padding: 12px 14px; }
</style>
