<script lang="ts">
  // Studio → the Ascent (owner, Nov 17: no ladder panel on Studio's home): the ladder and the ask for the ✓ on a page of
  // their own. path: as Studio holds it, so the page opens full; the ask answers here at once, Studio reads it again.
  import { untrack } from 'svelte';
  import { api, ApiErr, type Id, type OfficialPath } from '../../lib/api';
  import { studioChanged } from '../../lib/state/data.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { nowTs } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Pane from '../../ui/Pane.svelte';
  import Ascent from './Ascent.svelte';

  let { overlay, org, path: first, presVice }: { overlay: Overlay; org: Id; path: OfficialPath; presVice: boolean } = $props();
  let path = $state(untrack(() => first));
  async function ask() {
    const was = path;
    haptic.tap();
    path = { ...path, request: { id: 0, status: 'pending', reason: null, createdAt: nowTs(), decidedAt: null, againAt: null } }; // at once
    try { path = (await api.askOfficial(org)) ?? was; haptic.ok(); say(t('op.sent'), 'party_popper_3d'); studioChanged(); }
    catch (e) { path = was; haptic.error(); say(e instanceof ApiErr && e.message === 'president_elsewhere' ? t('op.presElsewhere') : t('common.error'), 'warning_3d'); }
  }
</script>

<Pane {overlay} title={t('op.title')}>
  <div class="page"><Ascent {path} {presVice} onask={ask} /></div>
</Pane>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-6); }
  .page :global(.asc > .cap) { display: none; } /* the page's title says it */
</style>
