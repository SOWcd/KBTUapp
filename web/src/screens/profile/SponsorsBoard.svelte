<script lang="ts">
  // The Sponsors honour board (Profile's row, the donate page's row): only people who agreed to be named (sp1), each with
  // their medal; the total only for those who also agreed to show it (sa1). The server orders it: tier, then the shown
  // totals, so a place never hints at an amount nobody agreed to show. Loaded with the app (loadSupport).
  import { data } from '../../lib/state/data.svelte';
  import { t, money } from '../../lib/i18n/index.svelte';
  import { sponsorMedal, tierLabel } from '../../lib/awards';
  import Medal from '../../ui/Medal.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
</script>

<Group footnote={t('sp.listHint')}>
  {#if data.sponsors?.length}
    {#each data.sponsors as p, i (i)}
      <Row title={p.name} subtitle={`${t('ach.sponsor.name')} · ${tierLabel(p.tier, 3)}`} value={p.amount ? money(p.amount) : undefined}>
        {#snippet lead()}<Medal a={sponsorMedal(p.tier)} size={36} />{/snippet}
      </Row>
    {/each}
  {:else if data.sponsors}<Row title={t('sp.empty')} />{/if}
</Group>
