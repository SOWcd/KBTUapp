<script lang="ts">
  // A recruitment round as a card in the Clubs tab's strip: the club, how many are in it, the deadline (warning colour in
  // the last 3 days) and one button. The card opens the club; the button, the round's own application.
  import Bell from '@lucide/svelte/icons/bell';
  import BellCheck from '@lucide/svelte/icons/bell-check';
  import type { Org } from '../lib/api';
  import { t, tn } from '../lib/i18n/index.svelte';
  import { daysLeft, roundDue } from '../lib/clubs';
  import { toggleSub } from '../lib/state/data.svelte';
  import { session } from '../lib/state/session.svelte';
  import { sheets } from '../lib/state/sheets';
  import { nameOf } from '../lib/short';
  import Button from './Button.svelte';
  import GovMark from './GovMark.svelte';
  import IconButton from './IconButton.svelte';
  import OfficialMark from './OfficialMark.svelte';
  import OrgLogo from './OrgLogo.svelte';

  let { org: o, round }: { org: Org; round: NonNullable<Org['round']> } = $props();
</script>

<div class="rc surface">
  <button class="open" onclick={() => sheets.club(o.id)} aria-label={o.name}></button>
  <span class="top">
    <OrgLogo org={o} size={48} />
    <span class="who">
      <span class="nm"><b class="clamp-2">{nameOf(o)}</b>{#if o.official && o.kind === 'club'}<OfficialMark size={15} />{/if}{#if o.gov}<GovMark size={14} />{/if}</span>
      <small class="ellipsis">{tn('club.members', o.members)}</small>
    </span>
  </span>
  <span class="due">
    <em class={{ soon: daysLeft(round.closesAt) <= 3 }}>{roundDue(round.closesAt)}</em>
    <span class="act">
      {#if session.me?.student && !o.myRole}<Button kind={round.applied ? 'neutral' : 'primary'} size="s" onclick={() => sheets.roundApply(o.id, 'join')}>{t(round.applied ? 'clubs.applied' : 'join.apply')}</Button>
      {:else}<IconButton icon={o.subscribed ? BellCheck : Bell} size="s" on={o.subscribed} onclick={() => toggleSub(o.id)} label={t(o.subscribed ? 'clubs.subscribed' : 'clubs.subscribe')} />{/if}
    </span>
  </span>
</div>

<style>
  .rc { position: relative; flex: none; width: 250px; display: flex; flex-direction: column; padding: 14px; scroll-snap-align: start; }
  .open { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }
  .top { display: flex; align-items: center; gap: 12px; min-width: 0; }
  .who { min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .nm { display: flex; align-items: center; gap: 4px; min-width: 0; }
  .nm b { font: 600 var(--fs-body)/1.2 var(--font-text); }
  .who small { font: 500 var(--fs-sub)/1.25 var(--font-text); color: var(--text-3); }
  .due { flex: 1; display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); margin-top: 14px; padding-top: 12px; box-shadow: inset 0 0.5px 0 var(--line-2); }
  em { min-width: 0; font: 600 var(--fs-sub)/1.2 var(--font-text); font-style: normal; color: var(--text-2); }
  em.soon { color: var(--warning-text); }
  .act { position: relative; z-index: 2; flex: none; display: flex; }
  .act :global(.btn) { padding-inline: 12px; font-size: var(--fs-sub); } /* the deadline keeps its one line beside it */
</style>
