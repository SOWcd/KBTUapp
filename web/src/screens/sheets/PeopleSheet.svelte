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

  let { overlay, org, title }: { overlay: Overlay; org: Id; title: string } = $props();
  let list = $state<Member[] | null>(null);
  let shut = $state(false);
  $effect(() => { api.people(org).then((x) => (list = x)).catch(() => (shut = true)); });
</script>

<Sheet {overlay} icon={UsersRound} {title}>
  {#if shut}
    <EmptyState inline text={t('club.listHidden')} />
  {:else if list}
    <Group>
      {#each list as m (m.person.id)}
        <Row dense title={m.person.name} value={m.role !== 'member' || m.title ? roleName(m.role, titleOf(m)) : undefined} accessory="chevron" onclick={() => sheets.person(m.person.id)}>
          {#snippet lead()}<Avatar person={m.person} size={36} tappable={false} />{/snippet}
        </Row>
      {/each}
    </Group>
  {:else}
    <Skeleton n={5} />
  {/if}
</Sheet>
