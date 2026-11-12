<script lang="ts">
  // A captain's invite link (startapp=et_<token>, server evteams.invite): the team's name, its captain and how many,
  // one tap to join. Not signed up yet: the tap signs up and joins at once (the event's own questions and phone first,
  // as any sign-up); waiting for a seat: said, nothing changes (lib/teams.ts inviteStep).
  import { onMount } from 'svelte';
  import { api, ApiErr, type TeamInvite } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { cardFor, errorText, toggleGoing } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { inviteStep } from '../../lib/teams';
  import Sheet from '../../ui/Sheet.svelte';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay, token }: { overlay: Overlay; token: string } = $props();
  let inv = $state<TeamInvite | null>(null);
  let dead = $state(false);
  let busy = $state(false);
  onMount(() => { api.teamInvite(token).then((x) => (inv = x)).catch(() => (dead = true)); });

  async function join() {
    if (!inv || busy) return;
    const eid = inv.event;
    busy = true; haptic.tap();
    try {
      const step = inviteStep((await cardFor(eid))?.my?.status);
      if (step === 'noSeat') { haptic.soft(); say(t('tm.noSeat'), 'pleading_face_3d'); return; }
      if (step === 'join') {
        await api.teamJoin(eid, token);
        haptic.ok(); say(t('tm.joined'), 'party_popper_3d');
      } else toggleGoing(eid, undefined, { join: token }); // says what came of it itself
      close(overlay.id); sheets.event(eid);
    } catch (e) { haptic.error(); say(e instanceof ApiErr ? errorText(e) : t('common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={UsersRound} title={t('tm.inviteTitle')}>
  {#if dead}
    <EmptyState icon={UsersRound} title={t('tm.dead')} />
  {:else if inv}
    <div class="page">
      <div class="hd">
        <h2 class="fs-sec">{inv.team.name}</h2>
        <p class="fs-sub dim">{inv.title}</p>
      </div>
      <Group>
        {#if inv.team.captain}
          {@const cap = inv.team.captain}
          <Row dense title={cap.name} subtitle={t('tm.captain')} value={t('tm.of', { n: inv.team.count, max: inv.max })}>
            {#snippet lead()}<Avatar person={cap} size={32} />{/snippet}
          </Row>
        {/if}
      </Group>
    </div>
  {/if}
  {#snippet footer()}
    {#if inv && !dead}
      {#if inv.mine}<Button kind="neutral" size="l" full disabled>{t('tm.inThis')}</Button>
      {:else if inv.locked}<Button kind="neutral" size="l" full disabled>{t('tm.locked')}</Button>
      {:else if !inv.room}<Button kind="neutral" size="l" full disabled>{t('tm.full')}</Button>
      {:else}<Button kind="primary" size="l" full loading={busy} onclick={join}>{t('tm.join')}</Button>{/if}
    {/if}
  {/snippet}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-5); }
  .hd { display: flex; flex-direction: column; gap: var(--s-1); padding: 0 var(--s-1); }
</style>
