<script lang="ts">
  import { untrack } from 'svelte';
  // Admin → "An event for a club" (owner, Nov 11): clubs ask the creator to post their events. Pick the club; the usual
  // editor opens for it as staff (EventEditor staff): the draft is the club's, its organizers run it in Studio, the
  // owner's log says the admin made it, and no role is given.
  // studio: the creator's "A club's Studio" (owner, Nov 15): the club's whole Studio as its President (lib/state/creator).
  import { byWeight, hit } from '../../lib/clubs';
  import { data } from '../../lib/state/data.svelte';
  import { openAsCreator } from '../../lib/state/creator.svelte';
  import { api, type OrgRef } from '../../lib/api';
  import { sheets } from '../../lib/state/sheets';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Pane from '../../ui/Pane.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay, studio = false }: { overlay: Overlay; studio?: boolean } = $props();
  let q = $state('');
  const s = $derived(q.trim().toLowerCase());
  const clubs = $derived(data.orgs.filter((o) => !s || hit(o, s) || o.slug.includes(s)).sort(byWeight));
  // the registry leaves out offices (DMP) and hidden clubs: the creator's Studio opens them too (owner, Nov 16: DMP's
  // panel wasn't found here), so Admin's own list adds what the registry lacks, after the clubs already in sight
  let rest = $state<OrgRef[]>([]);
  if (untrack(() => studio)) api.adminOrgs().then((l) => (rest = l)).catch(() => {});
  const more = $derived(rest.filter((o) => !data.orgs.some((d) => d.id === o.id) && (!s || hit(o, s) || o.slug.includes(s))));
  const found = $derived<OrgRef[]>([...clubs, ...more]);
  const pick = (o: OrgRef) => {
    haptic.tap(); close(overlay.id);
    if (studio) { openAsCreator(o); sheets.studio(o.id, true); } else sheets.editor(o.id, undefined, true);
  };
</script>

<Pane {overlay} title={t(studio ? 'adm.studioFor' : 'adm.eventFor')}>
  <div class="page">
    <SearchField bind:value={q} placeholder={t('adm.find')} />
    {#if found.length}
      <Group>
        {#each found as o (o.id)}
          <Row dense title={o.name} accessory="chevron" onclick={() => pick(o)}>
            {#snippet lead()}<OrgLogo org={o} size={36} />{/snippet}
          </Row>
        {/each}
      </Group>
    {:else}<EmptyState inline text={t('adm.nothingFound')} />{/if}
  </div>
</Pane>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-5); }
</style>
