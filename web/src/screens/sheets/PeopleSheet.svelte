<script lang="ts">
  // Everyone in a club or school (President and Vice on the club sheet, one button for the rest): names
  // and roles, highest first; a tap opens the person's card. A club may hide the list (ClubEditSheet): then a line.
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
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

<Sheet {overlay} {title}>
  {#if shut}
    <p class="t-foot none">{t('club.listHidden')}</p>
  {:else if list}
    <div class="list">
      {#each list as m (m.person.id)}
        <button class="row" onclick={() => sheets.person(m.person.id)}>
          <Avatar person={m.person} size={40} tappable={false} />
          <b class="ellipsis">{m.person.name}</b>
          {#if m.role !== 'member' || m.title}<span class="t-foot">{roleName(m.role, titleOf(m))}</span>{/if}
        </button>
      {/each}
    </div>
  {/if}
</Sheet>

<style>
  .none { padding: 12px 2px; }
  .list { display: flex; flex-direction: column; border-radius: var(--r-l); background: var(--surface); overflow: hidden; }
  .row { display: flex; align-items: center; gap: 12px; min-height: 58px; padding: 9px 14px; text-align: left; }
  .row + .row { box-shadow: inset 0 1px 0 var(--line); }
  .row:active { background: var(--surface-2); }
  .row b { flex: 1; min-width: 0; font: 600 15px/1.25 var(--font-text); color: var(--text); }
  .row span { flex: none; }
</style>
