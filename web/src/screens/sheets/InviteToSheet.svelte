<script lang="ts">
  // "Bring a friend" from a friend's card (SPEC §4.7, §4.12): the events I'm going to, and "Invite" next to each — the bot
  // brings them our card, once per event. Nothing upcoming yet: the way to Events.
  import Mail from '@lucide/svelte/icons/mail';
  import { api, ApiErr, type Id } from '../../lib/api';
  import { say, close, ui, type Overlay, overlays } from '../../lib/state/ui.svelte';
  import { data } from '../../lib/state/data.svelte';
  import { t, placeOf } from '../../lib/i18n/index.svelte';
  import { relDay, time, nowTs } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import Button from '../../ui/Button.svelte';
  import Poster from '../../ui/Poster.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import CalendarHeart from '@lucide/svelte/icons/calendar-heart';

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
    } catch (e) { haptic.error(); say(e instanceof ApiErr && e.code === 'rate_limited' ? t('inv.tooMany') : t('common.error'), 'warning_3d'); }
    finally { busy = null; }
  }
  // the Afisha in sight: every sheet down (the person's and the Friends sheet were left over it)
  function toEvents() { overlays.forEach((o) => close(o.id, true)); ui.tab = 'afisha'; } // as by a hand: a sheet with unsent text asks first
</script>

<Sheet {overlay} icon={TelegramMark} title={t('inv.toTitle', { name })}>
  <h2 class="fs-sec hd">{t('inv.toTitle', { name })}</h2>
  {#if mine.length}
    <p class="fs-sub dim sub">{t('inv.toSub')}</p>
    <Group>
      {#each mine as e (e.id)}
        {@const when = `${relDay(e.startsAt)}, ${time(e.startsAt)} · ${placeOf(e.place)}`}
        {#if sent[e.id]}
          <Row dense title={e.title} subtitle={when} value={sent[e.id] === 'going' ? t('inv.going') : t('inv.invited')}>{#snippet lead()}<Poster item={e} size={44} radius={10} />{/snippet}</Row>
        {:else}
          <Row dense title={e.title} subtitle={when}>
            {#snippet lead()}<Poster item={e} size={44} radius={10} />{/snippet}
            {#snippet trailing()}<Button kind="tinted" size="s" loading={busy === e.id} onclick={() => invite(e.id)}>{#snippet icon()}<Mail size={15} />{/snippet}{t('inv.invite')}</Button>{/snippet}
          </Row>
        {/if}
      {/each}
    </Group>
  {:else}
    <EmptyState icon={CalendarHeart} title={t('inv.toEmpty')} action={{ label: t('inv.toEvents'), onclick: toEvents }} />
  {/if}
</Sheet>

<style>
  .hd { margin: var(--s-1) var(--s-1); }
  .sub { margin: 0 var(--s-1) var(--s-3); }
</style>
