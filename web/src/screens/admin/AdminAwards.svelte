<script lang="ts">
  // Admin → Awards (pushed from the right; owner, Nov 3: "one Initiation 2026 medal as three buttons is dumb"): one row
  // per award with its real medal and how many hold it; a row opens the award's page (its variant, Scan, Link, the
  // links, who has it). A person's awards are given from the person (Admin's search → a person).
  import { api } from '../../lib/api';
  import { MANUAL, manualMedal, manualTitle } from '../../lib/awards';
  import { session } from '../../lib/state/session.svelte';
  import { open, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Pane from '../../ui/Pane.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Medal from '../../ui/Medal.svelte';
  import AwardPane from './AwardPane.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const list = $derived(MANUAL.filter((a) => !a.creator || !!session.me?.founder));
  let counts = $state<Record<string, number>>({});
  const load = () => api.awardCounts().then((c) => (counts = c)).catch(() => {});
  void load();
</script>

<Pane {overlay} title={t('aw.title')}>
  <div class="stagger">
    <Group>
      {#each list as a (a.code)}
        <Row title={manualTitle(a)} value={counts[a.code] != null ? String(counts[a.code]) : undefined} accessory="chevron"
          onclick={() => { haptic.tap(); open(AwardPane, { award: a, onchange: load }); }}>
          {#snippet lead()}<Medal a={manualMedal(a.code, a.emoji)} size={32} />{/snippet}
        </Row>
      {/each}
    </Group>
  </div>
</Pane>
