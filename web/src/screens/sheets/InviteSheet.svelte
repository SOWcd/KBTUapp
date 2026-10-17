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
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';

  let { overlay, id, title }: { overlay: Overlay; id: Id; title: string } = $props();
  let list = $state<FriendInvite[] | null>(null);
  let busy = $state<Id | null>(null);
  $effect(() => { api.eventInvites(id).then((l) => (list = l)).catch(() => { list = []; say(t('common.error'), 'pleading_face_3d'); }); });

  async function invite(f: FriendInvite) {
    busy = f.person.id;
    try { list = await api.inviteFriend(id, f.person.id); haptic.ok(); say(t('inv.sent', { name: f.person.name }), 'love_letter_3d'); }
    catch (e) {
      haptic.error();
      say(e instanceof ApiErr && e.code === 'rate_limited' ? t('inv.tooMany') : e instanceof ApiErr && e.code === 'closed' ? t('inv.closed') : t('common.error'), 'pleading_face_3d');
    } finally { busy = null; }
  }
  function addFriends() { close(overlay.id); sheets.addFriend(); }
</script>

<Sheet {overlay} title={t('inv.title')}>
  <h2 class="t-h2 hd">{t('inv.title')}</h2>
  <p class="t-foot sub">{t('inv.sub', { title, award: t('ach.soul.name') })}</p>
  {#if list === null}
    <div class="wait" aria-hidden="true"><span></span><span></span><span></span></div>
  {:else if !list.length}
    <div class="empty">
      <p class="t-body">{t('inv.empty')}</p>
      <Button kind="primary" size="m" onclick={addFriends}>{#snippet icon()}<UserPlus size={18} />{/snippet}{t('inv.addFriends')}</Button>
    </div>
  {:else}
    <div class="list">
      {#each list as f (f.person.id)}
        <div class="fr">
          <Avatar person={f.person} size={44} />
          <b class="ellipsis">{f.person.name}</b>
          {#if f.state === 'going'}<span class="st ok">{t('inv.going')}</span>
          {:else if f.state === 'invited'}<span class="st">{t('inv.invited')}</span>
          {:else}<Button kind="primary" size="s" loading={busy === f.person.id} onclick={() => invite(f)}>{#snippet icon()}<Mail size={15} />{/snippet}{t('inv.invite')}</Button>{/if}
        </div>
      {/each}
    </div>
    <button class="more" onclick={addFriends}><UserPlus size={16} />{t('inv.addFriends')}</button>
  {/if}
</Sheet>

<style>
  .hd { margin: 4px 0 4px; }
  .sub { margin-bottom: 14px; text-wrap: pretty; }
  .list { display: flex; flex-direction: column; gap: 2px; }
  .fr { display: flex; align-items: center; gap: 12px; min-height: 60px; padding: 8px 4px; }
  .fr b { flex: 1; min-width: 0; font: 640 15.5px/1.25 var(--font-text); }
  .st { flex: none; font: 620 13.5px/1 var(--font-text); color: var(--text-2); }
  .st.ok { color: var(--success-text); }
  .empty { display: flex; flex-direction: column; align-items: center; gap: 14px; padding: 18px 8px 8px; text-align: center; color: var(--text-2); }
  .more { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; height: 44px; margin-top: 10px; border-radius: var(--r-m);
    background: var(--surface-2); color: var(--text-2); font: 620 14px/1 var(--font-text); }
  .more:active { transform: scale(0.98); }
  .wait { display: flex; flex-direction: column; gap: 10px; }
  .wait span { height: 52px; border-radius: var(--r-m); background: var(--surface-2); animation: pulse 1.1s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.5; } }
</style>
