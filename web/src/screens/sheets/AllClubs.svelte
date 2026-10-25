<script lang="ts">
  // Every club, from the Clubs tab's "All clubs · N" (owner, Oct 25: 44 tiles were chaos): compact rows, a search, the
  // biggest first (members, then followers), empty clubs last; the Student Government first. Schools have their own row.
  import Search from '@lucide/svelte/icons/search';
  import X from '@lucide/svelte/icons/x';
  import type { Org } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { data } from '../../lib/state/data.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { byWeight, hit } from '../../lib/clubs';
  import Sheet from '../../ui/Sheet.svelte';
  import ClubRow from '../../ui/ClubRow.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let q = $state('');
  const all = $derived(data.orgs.filter((o) => o.kind !== 'school').sort(byWeight));
  const list = $derived(q.trim() ? all.filter((o) => hit(o, q)) : all);
  const sub = (o: Org) => [o.members ? tn('club.members', o.members) : '', o.subscribers ? tn('clubs.subscribers', o.subscribers) : ''].filter(Boolean).join(' · ');
</script>

<Sheet {overlay} tall title={t('clubs.allTitle')}>
  <h2 class="t-h2 hd">{t('clubs.allTitle')}<span>{all.length}</span></h2>
  <label class="search">
    <Search size={18} />
    <input bind:value={q} placeholder={t('clubs.search')} type="search" enterkeyhint="search" autocomplete="off" />
    {#if q}<button onclick={() => (q = '')} aria-label={t('common.close')}><X size={16} /></button>{/if}
  </label>
  <p class="t-foot note">{t('clubs.allNote')}</p>
  <div class="list surface">
    {#each list as o (o.id)}<ClubRow org={o} sub={sub(o)} />{:else}<p class="t-foot empty">{t('clubs.nothing')}</p>{/each}
  </div>
</Sheet>

<style>
  .hd { display: flex; align-items: baseline; gap: 8px; margin: 4px 0 12px; }
  .hd span { font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-3); }
  .search { display: flex; align-items: center; gap: 8px; height: 44px; padding: 0 12px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text-3); }
  .search input { flex: 1; min-width: 0; font: 500 var(--fs-body)/1 var(--font-text); color: var(--text); }
  .search input::placeholder { color: var(--text-3); }
  .search input::-webkit-search-cancel-button { display: none; }
  .search button { display: flex; color: var(--text-3); padding: 4px; }
  .note { margin: 10px 4px 10px; }
  .list { display: flex; flex-direction: column; border-radius: var(--r-l); overflow: hidden; }
  .empty { padding: 20px 14px; }
</style>
