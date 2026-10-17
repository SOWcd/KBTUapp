<script lang="ts">
  // "Bring a friend" from a friend's card (SPEC §4.7, §4.12): the events I'm going to, and "Invite" next to each — the bot
  // brings them our card, once per event. Nothing upcoming yet: the way to Events.
  import Mail from '@lucide/svelte/icons/mail';
  import { api, ApiErr, type Id } from '../../lib/api';
  import { say, close, ui, type Overlay } from '../../lib/state/ui.svelte';
  import { data } from '../../lib/state/data.svelte';
  import { t, placeOf } from '../../lib/i18n/index.svelte';
  import { relDay, time, nowTs } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Poster from '../../ui/Poster.svelte';

  let { overlay, id, name }: { overlay: Overlay; id: Id; name: string } = $props();
  const mine = $derived(data.events.filter((e) => e.status === 'published' && e.startsAt > nowTs() && (e.visibility ?? 'public') === 'public'
    && ['going', 'hold', 'waitlist'].includes(e.my?.status ?? '')).slice(0, 12));
  let sent = $state<Record<number, 'invited' | 'going'>>({});
  let busy = $state<number | null>(null);

  async function invite(eid: number) {
    busy = eid;
    try {
      const l = await api.inviteFriend(eid, id);
      const st = l.find((x) => x.person.id === id)?.state;
      sent = { ...sent, [eid]: st === 'going' ? 'going' : 'invited' };
      haptic.ok(); say(t('inv.sent', { name }), 'love_letter_3d');
    } catch (e) { haptic.error(); say(e instanceof ApiErr && e.code === 'rate_limited' ? t('inv.tooMany') : t('common.error'), 'pleading_face_3d'); }
    finally { busy = null; }
  }
  function toEvents() { close(overlay.id); ui.tab = 'afisha'; ui.page.afisha = 1; }
</script>

<Sheet {overlay} title={t('inv.toTitle', { name })}>
  <h2 class="t-h2 hd">{t('inv.toTitle', { name })}</h2>
  {#if mine.length}
    <p class="t-foot sub">{t('inv.toSub')}</p>
    <div class="list">
      {#each mine as e (e.id)}
        <div class="row">
          <Poster item={e} size={52} radius={14} />
          <span class="tx"><b class="clamp-2">{e.title}</b><i>{relDay(e.startsAt)}, {time(e.startsAt)} · {placeOf(e.place)}</i></span>
          {#if sent[e.id] === 'going'}<span class="st ok">{t('inv.going')}</span>
          {:else if sent[e.id] === 'invited'}<span class="st">{t('inv.invited')}</span>
          {:else}<Button kind="primary" size="s" loading={busy === e.id} onclick={() => invite(e.id)}>{#snippet icon()}<Mail size={15} />{/snippet}{t('inv.invite')}</Button>{/if}
        </div>
      {/each}
    </div>
  {:else}
    <div class="empty"><p class="t-body">{t('inv.toEmpty')}</p><Button kind="primary" size="m" onclick={toEvents}>{t('inv.toEvents')}</Button></div>
  {/if}
</Sheet>

<style>
  .hd { margin: 4px 0 4px; }
  .sub { margin-bottom: 12px; }
  .list { display: flex; flex-direction: column; gap: 4px; }
  .row { display: flex; align-items: center; gap: 12px; padding: 8px 2px; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .tx b { font: 650 14.5px/1.25 var(--font-text); }
  .tx i { font: 500 12.5px/1.25 var(--font-text); font-style: normal; color: var(--text-2); }
  .st { flex: none; font: 620 13.5px/1 var(--font-text); color: var(--text-2); }
  .st.ok { color: var(--success-text); }
  .empty { display: flex; flex-direction: column; align-items: center; gap: 14px; padding: 18px 8px 8px; text-align: center; color: var(--text-2); }
</style>
