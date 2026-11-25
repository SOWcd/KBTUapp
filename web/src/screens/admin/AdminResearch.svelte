<script lang="ts">
  import ChartNoAxesColumn from '@lucide/svelte/icons/chart-no-axes-column';
  import { api, type ResearchRequest } from '../../lib/api';
  import { staffOnly } from '../../lib/state/staffGate.svelte';
  import { staffStill } from '../../lib/state/staffAccess.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { data, loadResearchRequests, researchDecision } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  staffOnly(() => overlay, 'staff');
  const owner = $derived(session.me?.role === 'admin' && !!session.me?.founder);
  let busy = $state<number[]>([]);
  async function approve(r: ResearchRequest) {
    if (!owner || busy.includes(r.id)) return;
    const before = r.approved, still = staffStill('staff');
    researchDecision(true);
    busy = [...busy, r.id]; r.approved = !before; haptic.tap();
    try { await api.approveResearch(r.id, !before); }
    catch { if (still()) r.approved = before; haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = busy.filter((id) => id !== r.id); researchDecision(false); }
  }
</script>

<Sheet {overlay} icon={ChartNoAxesColumn} title={t('research.requests')} heading={t('research.requests')} full>
  <div class="requests">
    {#if owner}<p class="t-foot">{t('research.manual')}</p>{/if}
    {#if data.researchRequestsFailed}
      <p class="t-foot">{t('common.error')}</p><Button kind="gray" onclick={() => { void loadResearchRequests(); }}>{t('common.retry')}</Button>
    {:else if !data.researchRequests}
      <p class="t-foot" role="status">{t('research.loading')}</p>
    {:else if !data.researchRequests.length}
      <p class="t-body">{t('research.noRequests')}</p>
    {/if}
    {#each data.researchRequests ?? [] as r (r.id)}
      <article class="request surface">
        <h3 class="t-h3">{r.title}</h3>
        <button class="who t-foot" onclick={() => { haptic.tap(); if (r.username) openLink(`https://t.me/${r.username}`); else sheets.person(r.person.id); }}>
          {r.person.realName ?? r.person.name}{r.username ? ` · @${r.username}` : ''} · {ago(r.at)}
        </button>
        <dl>
          <dt>{t('research.goal')}</dt><dd>{r.goal}</dd>
          <dt>{t('research.questions')}</dt><dd>{r.questions}</dd>
          <dt>{t('research.organizer')}</dt><dd>{r.organizer}</dd>
        </dl>
        <div class="decision"><span class="t-foot">{t(r.approved ? 'research.approved' : 'research.pending')}</span>
          {#if owner}<Button kind="gray" size="s" disabled={busy.includes(r.id)} onclick={() => approve(r)}>{t(r.approved ? 'adm.undo' : 'research.approve')}</Button>{/if}
        </div>
      </article>
    {/each}
  </div>
</Sheet>

<style>
  .requests { display: flex; flex-direction: column; gap: var(--s-3); }
  .request { padding: var(--s-4); border-radius: var(--r-l); overflow-wrap: anywhere; }
  .request h3 { margin: 0 0 var(--s-2); }
  .who { text-align: start; color: var(--accent-text); min-height: var(--tap); }
  dl { margin: var(--s-3) 0; }
  dt { margin-top: var(--s-3); color: var(--text-3); font: 450 var(--fs-sub)/1.4 var(--font-text); }
  dd { margin: var(--s-1) 0 0; white-space: pre-wrap; font: 450 var(--fs-body)/1.4 var(--font-text); }
  .decision { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); }
</style>
