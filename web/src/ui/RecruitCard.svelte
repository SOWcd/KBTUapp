<script lang="ts">
  // A recruitment round as a card in the Clubs tab's strip: the club's cover with its big mark and name, the deadline
  // (warning colour in the last 3 days), how many are in it and one button. The card opens the club; the button, the
  // round's own application.
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
  import Emoji from './Emoji.svelte';
  import GovMark from './GovMark.svelte';
  import IconButton from './IconButton.svelte';
  import OfficialMark from './OfficialMark.svelte';
  import { COVERS } from './OrgLogo.svelte';

  let { org: o, round }: { org: Org; round: NonNullable<Org['round']> } = $props();
</script>

<div class="rc surface">
  <button class="open" onclick={() => sheets.club(o.id)} aria-label={o.name}></button>
  <span class="cv" style:background={COVERS[o.cover % COVERS.length]}>
    <span class="mark">{#if o.logo}<img src={o.logo} alt="" width="96" height="96" draggable="false" />{:else}<Emoji name={o.emoji} size={112} />{/if}</span>
    <b><span class="clamp-2">{nameOf(o)}</span>{#if o.official && o.kind === 'club'}<OfficialMark size={15} />{/if}{#if o.gov}<GovMark size={14} />{/if}</b>
  </span>
  <span class="bt">
    <span class="due"><em class={{ soon: daysLeft(round.closesAt) <= 3 }}>{roundDue(round.closesAt)}</em><small class="ellipsis">{tn('club.members', o.members)}</small></span>
    <span class="act">
      {#if session.me?.student && !o.myRole}<Button kind={round.applied ? 'neutral' : 'primary'} size="s" onclick={() => sheets.roundApply(o.id, 'join')}>{t(round.applied ? 'clubs.applied' : 'join.apply')}</Button>
      {:else}<IconButton icon={o.subscribed ? BellCheck : Bell} size="s" on={o.subscribed} onclick={() => toggleSub(o.id)} label={t(o.subscribed ? 'clubs.subscribed' : 'clubs.subscribe')} />{/if}
    </span>
  </span>
</div>

<style>
  .rc { position: relative; flex: none; width: 262px; display: flex; flex-direction: column; overflow: hidden; scroll-snap-align: start; }
  .open { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }
  .cv { position: relative; display: block; height: 92px; overflow: hidden; color: var(--on-accent); }
  .mark { position: absolute; right: -6px; top: -10px; rotate: -9deg; display: flex; filter: drop-shadow(0 12px 16px rgba(0, 0, 0, 0.28)); }
  .mark img { border-radius: var(--r-l); object-fit: cover; }
  b { position: absolute; left: 14px; right: 108px; bottom: 11px; display: flex; align-items: flex-end; gap: 4px; font: 700 var(--fs-card)/1.15 var(--font-display); letter-spacing: -0.015em; text-shadow: 0 1px 10px rgba(0, 0, 0, 0.28); }
  b :global(.om) { color: var(--on-accent); }
  b :global(.om .tick) { stroke: var(--accent); }
  .bt { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); padding: 11px 12px 12px 14px; }
  .due { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  em { font: 600 var(--fs-sub)/1.2 var(--font-text); font-style: normal; color: var(--text-2); }
  em.soon { color: var(--warning-text); }
  small { font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .act { position: relative; z-index: 2; flex: none; display: flex; }
  .act :global(.btn) { padding-inline: 12px; font-size: var(--fs-sub); } /* the deadline keeps its one line beside it */
</style>
