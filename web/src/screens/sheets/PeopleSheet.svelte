<script lang="ts">
  // Everyone in a club or school (President and Vice on the club sheet, one button for the rest): names
  // and roles, highest first; a tap opens the person's card. A club may hide the list (ClubEditSheet): then a line.
  import Sheet from '../../ui/Sheet.svelte';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import Avatar from '../../ui/Avatar.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import { api, type Id, type Member } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { roleName, titleOf } from '../../lib/perms';
  import { t } from '../../lib/i18n/index.svelte';
  import SortChip from '../../ui/SortChip.svelte';
  import { sorted, byName, usual, type Order } from '../../lib/sort.svelte';
  import { screenful } from '../../lib/screenful.svelte';

  let { overlay, org, title }: { overlay: Overlay; org: Id; title: string } = $props();
  let list = $state<Member[] | null>(null);
  let shut = $state(false);
  const ORDERS: Order<Member>[] = [usual('sort.role'), byName((m) => m.person.name)]; // the server's: highest role first
  const rows = $derived(sorted('club.people', ORDERS, list ?? []));
  const draw = screenful(() => rows.length); // a big club: a screenful with the sheet, the rest after it paints
  $effect(() => { api.people(org).then((x) => (list = x)).catch(() => (shut = true)); });
</script>

<Sheet {overlay} icon={UsersRound} {title}>
  {#if shut}
    <EmptyState inline text={t('club.listHidden')} />
  {:else if list}
    <div class="col">
    {#if rows.length > 1}<SortChip list="club.people" orders={ORDERS} />{/if}
    <Group>
      {#each rows.slice(0, draw.n) as m (m.person.id)}
        <Row dense title={m.person.name} value={m.role !== 'member' || m.title ? roleName(m.role, titleOf(m)) : undefined} accessory="chevron" onclick={() => sheets.person(m.person.id)}>
          {#snippet lead()}<Avatar person={m.person} size={36} tappable={false} />{/snippet}
        </Row>
      {/each}
    </Group>
    </div>
  {:else}
    <Skeleton n={5} />
  {/if}
</Sheet>

<style>
  .col { display: flex; flex-direction: column; gap: var(--s-3); }
</style>
