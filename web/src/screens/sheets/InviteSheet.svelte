<script lang="ts">
  // "Bring a friend" (SPEC §4.7): my friends and where they stand with this event. "Invite" has the bot bring them our
  // card ("<name> invites you to <title>" + a button), once per friend; if they sign up, the credit is mine. No friends
  // yet: the way to add some.
  import Mail from '@lucide/svelte/icons/mail';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import { api, ApiErr, type FriendInvite, type Id } from '../../lib/api';
  import { say, close, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay, id, title }: { overlay: Overlay; id: Id; title: string } = $props();
  let list = $state<FriendInvite[] | null>(null);
  let busy = $state<Id | null>(null);
  $effect(() => { api.eventInvites(id).then((l) => (list = l)).catch(() => { list = []; say(t('common.error'), 'warning_3d'); }); });

  async function invite(f: FriendInvite) {
    busy = f.person.id;
    try { list = await api.inviteFriend(id, f.person.id); haptic.ok(); say(t('inv.sent', { name: f.person.name }), 'love_letter_3d'); }
    catch (e) {
      haptic.error();
      say(e instanceof ApiErr && e.code === 'rate_limited' ? t('inv.tooMany') : e instanceof ApiErr && e.code === 'closed' ? t('inv.closed') : t('common.error'), 'warning_3d');
    } finally { busy = null; }
  }
  function addFriends() { close(overlay.id); sheets.addFriend(); }
</script>

<Sheet {overlay} icon={TelegramMark} title={t('inv.title')}>
  <p class="fs-sub dim sub">{t('inv.sub', { title, award: t('ach.soul.name') })}</p>
  {#if list === null}
    <Skeleton kind="rows" n={3} />
  {:else if !list.length}
    <EmptyState icon={UserPlus} title={t('inv.empty')} action={{ label: t('inv.addFriends'), onclick: addFriends }} />
  {:else}
    <Group>
      {#each list as f (f.person.id)}
        {#if f.state === 'going' || f.state === 'invited'}
          <Row dense title={f.person.name} value={f.state === 'going' ? t('inv.going') : t('inv.invited')}>{#snippet lead()}<Avatar person={f.person} size={36} />{/snippet}</Row>
        {:else}
          <Row dense title={f.person.name}>
            {#snippet lead()}<Avatar person={f.person} size={36} />{/snippet}
            {#snippet trailing()}<Button kind="tinted" size="s" loading={busy === f.person.id} onclick={() => invite(f)}>{#snippet icon()}<Mail size={15} />{/snippet}{t('inv.invite')}</Button>{/snippet}
          </Row>
        {/if}
      {/each}
      <Row tone="add" title={t('inv.addFriends')} onclick={addFriends} />
    </Group>
  {/if}
</Sheet>

<style>
  .sub { margin: 0 var(--s-1) var(--s-4); text-wrap: pretty; }
</style>
