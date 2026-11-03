<script lang="ts">
  // Admin → Team (pushed from the right; review Nov 3): the app's team with their roles, the banned under it with
  // the reason; a row opens the person (role, awards, ban). Anyone else is found from Admin's search.
  import { api, type Staff, type StaffRow } from '../../lib/api';
  import { open, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Pane from '../../ui/Pane.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import PersonPane from './PersonPane.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let staff = $state<Staff | null>(null);
  $effect(() => { api.staff().then((s) => (staff = s)).catch(() => say(t('common.error'), 'warning_3d')); });
  const person = (row: StaffRow) => { haptic.tap(); open(PersonPane, { row, onchange: (s: Staff) => (staff = s) }); };
</script>

{#snippet rowOf(p: StaffRow, sub: string | undefined, value: string | undefined)}
  <Row dense title={p.person.name} subtitle={sub} {value} accessory="chevron" onclick={() => person(p)}>
    {#snippet lead()}<Avatar person={p.person} size={36} tappable={false} />{/snippet}
  </Row>
{/snippet}

<Pane {overlay} title={t('adm.team')}>
  {#if staff}
    <div class="page stagger">
      <Group caption={t('staff.now')}>
        {#each staff.team as p (p.person.id)}{@render rowOf(p, p.username ? '@' + p.username : undefined, p.owner ? t('staff.owner') : t(`staff.role.${p.role}`))}{/each}
      </Group>
      {#if staff.banned.length}
        <Group caption={t('staff.bannedList')}>
          {#each staff.banned as p (p.person.id)}{@render rowOf(p, p.banReason ?? (p.username ? '@' + p.username : undefined), undefined)}{/each}
        </Group>
      {/if}
    </div>
  {:else}<Skeleton n={4} />{/if}
</Pane>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-6); }
</style>
