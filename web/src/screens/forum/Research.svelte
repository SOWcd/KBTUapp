<script lang="ts">
  import ChartNoAxesColumn from '@lucide/svelte/icons/chart-no-axes-column';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { data, loadResearch } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t, fmtNum } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay }: { overlay: Overlay } = $props();
</script>

<Sheet {overlay} icon={ChartNoAxesColumn} title={t('research.title')} heading={t('research.title')} full>
  <div class="surveys">
    {#each data.research ?? [] as survey (survey.slug)}
      <button class="survey surface" onclick={() => { haptic.tap(); sheets.researchForm(survey); }}>
        <span class="copy"><b>{survey.title}</b><span class="about">{survey.about}</span><small>{t('research.answers', { n: fmtNum(survey.answers) })}{survey.answered ? ` · ${t('research.answered')}` : ''}</small></span>
        <ChevronRight size={18} />
      </button>
    {/each}
    {#if data.researchFailed}
      <p class="t-foot">{t('common.error')}</p>
      <Button kind="gray" onclick={() => { void loadResearch(); }}>{t('common.retry')}</Button>
    {:else if !data.research}
      <p class="t-foot" role="status">{t('research.loading')}</p>
    {:else if !data.research.length}
      <p class="t-body">{t('research.empty')}</p>
    {/if}
  </div>
  {#snippet footer()}
    <Button kind="primary" size="l" full onclick={() => { haptic.tap(); sheets.researchPropose(); }}>{t('research.propose')}</Button>
  {/snippet}
</Sheet>

<style>
  .surveys { display: flex; flex-direction: column; gap: var(--s-3); }
  .survey { display: flex; align-items: center; gap: var(--s-3); padding: var(--s-4); border-radius: var(--r-l); text-align: start; }
  .copy { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--s-1); }
  .copy b { font: 600 var(--fs-row)/1.3 var(--font-text); overflow-wrap: anywhere; }
  .about { color: var(--text-2); font: 450 var(--fs-body)/1.4 var(--font-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .copy small { color: var(--text-3); font: 450 var(--fs-sub)/1.4 var(--font-text); }
</style>
