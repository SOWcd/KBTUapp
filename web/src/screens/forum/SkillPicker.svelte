<script lang="ts">
  // Skills from the one shared catalog (forum.py): the chosen ones as chips, suggestions while typing (the most common
  // first), "create" when nothing matches; a close one is offered before a new one is made ("did you mean").
  import X from '@lucide/svelte/icons/x';
  import Plus from '@lucide/svelte/icons/plus';
  import { api, ApiErr, type Skill } from '../../lib/api';
  import { say } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import SearchField from '../../ui/SearchField.svelte';

  let { chosen = $bindable([]), max }: { chosen?: Skill[]; max: number } = $props();
  let q = $state(''), found = $state<Skill[]>([]), near = $state<Skill[] | null>(null), busy = $state(false);
  let timer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const s = q.trim();
    near = null;
    clearTimeout(timer);
    timer = setTimeout(() => api.skills(s).then((l) => (found = l)).catch(() => {}), s ? 220 : 0);
  });
  const free = $derived(found.filter((s) => !chosen.some((c) => c.id === s.id)));
  const exact = $derived(found.some((s) => s.name === q.trim().toLowerCase()));
  function pick(s: Skill) {
    if (chosen.length >= max) { haptic.error(); say(t('fo.max', { n: max }), 'pleading_face_3d'); return; }
    haptic.tap(); chosen = [...chosen, s]; q = ''; near = null;
  }
  async function create(force = false) {
    busy = true;
    try {
      const r = await api.newSkill(q.trim(), force);
      if (r.skill) pick(r.skill);
      else near = r.didYouMean ?? [];
    } catch (e) { haptic.error(); say(t(e instanceof ApiErr && e.message === 'ai' ? 'fo.skillNo' : 'common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }
</script>

<div class="chips">
  {#each chosen as s (s.id)}<button class="chip on" onclick={() => (chosen = chosen.filter((c) => c.id !== s.id))}>{s.name}<X size={13} /></button>{/each}
  {#if !chosen.length}<span class="t-foot">{t('fo.noSkills')}</span>{/if}
</div>
<SearchField bind:value={q} placeholder={t('fo.skillFind')} />
{#if near}
  <p class="t-foot hint">{t('fo.didYouMean')}</p>
  <div class="chips">{#each near as s (s.id)}<button class="chip" onclick={() => pick(s)}>{s.name}</button>{/each}
    <button class="chip new" disabled={busy} onclick={() => create(true)}><Plus size={13} />{t('fo.createAnyway', { name: q.trim() })}</button></div>
{:else}
  <div class="chips">
    {#each free as s (s.id)}<button class="chip" onclick={() => pick(s)}>{s.name}{#if s.people}<i>{s.people}</i>{/if}</button>{/each}
    {#if q.trim() && !exact}<button class="chip new" disabled={busy} onclick={() => create()}><Plus size={13} />{t('fo.create', { name: q.trim() })}</button>{/if}
  </div>
{/if}

<style>
  .chips { display: flex; flex-wrap: wrap; gap: 6px; margin: 10px 0; }
  .chip { display: inline-flex; align-items: center; gap: 5px; height: 32px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-2); color: var(--text); font: 600 13.5px/1 var(--font-text); }
  .chip i { font-style: normal; color: var(--text-3); font-weight: 500; }
  .chip.on { background: var(--accent-soft); color: var(--accent-text); }
  .chip.new { color: var(--accent-text); box-shadow: inset 0 0 0 1.5px var(--line-2); background: none; }
  .hint { margin: 10px 4px 0; }
</style>
