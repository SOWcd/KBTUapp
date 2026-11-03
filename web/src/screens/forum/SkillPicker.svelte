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
  import Chip from '../../ui/Chip.svelte';

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
    if (busy) return; // engine: Chip has no `disabled`; the tap is ignored while one is being made
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
  {#each chosen as s (s.id)}<Chip selected icon={X} onclick={() => (chosen = chosen.filter((c) => c.id !== s.id))}>{s.name}</Chip>{/each}
  {#if !chosen.length}<span class="hint">{t('fo.noSkills')}</span>{/if}
</div>
<SearchField bind:value={q} placeholder={t('fo.skillFind')} />
{#if near}
  <p class="hint top">{t('fo.didYouMean')}</p>
  <div class="chips">{#each near as s (s.id)}<Chip selected={false} onclick={() => pick(s)}>{s.name}</Chip>{/each}
    <Chip selected={false} icon={Plus} onclick={() => create(true)}>{t('fo.createAnyway', { name: q.trim() })}</Chip></div>
{:else}
  <div class="chips">
    {#each free as s (s.id)}<Chip selected={false} onclick={() => pick(s)}>{s.name}{#if s.people}<i class="n num">{s.people}</i>{/if}</Chip>{/each}
    {#if q.trim() && !exact}<Chip selected={false} icon={Plus} onclick={() => create()}>{t('fo.create', { name: q.trim() })}</Chip>{/if}
  </div>
{/if}

<style>
  .chips { display: flex; flex-wrap: wrap; gap: var(--s-2); margin: var(--s-2) 0; padding: 4px 0; }
  .n { font-style: normal; font-weight: 450; color: var(--text-3); }
  .hint { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); align-self: center; }
  .hint.top { display: block; margin-top: var(--s-3); }
</style>
