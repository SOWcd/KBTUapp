<script lang="ts">
  // Tab 2 for students who aren't in a club yet: clubs taking applications (§4.5), and the way to start one.
  // A card opens the club; the button applies at once, and a second tap offers to withdraw.
  import BadgeCheck from '@lucide/svelte/icons/badge-check';
  import { data, toggleJoin } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Button from '../../ui/Button.svelte';
  import CreateClubCard from '../../ui/CreateClubCard.svelte';
  import { dayMonth } from '../../lib/time';

  // a recruitment round first (soonest deadline first), then clubs taking one-tap applications; KBTU's schools after
  // the clubs under their own heading (owner, Oct 20: joinable, but not up front)
  const open = $derived(data.orgs.filter((o) => (o.round || o.recruiting) && !o.myRole)
    .sort((a, b) => (a.round ? a.round.closesAt : Infinity) - (b.round ? b.round.closesAt : Infinity)));
  const groups = $derived([open.filter((o) => o.kind !== 'school'), open.filter((o) => o.kind === 'school')]);
</script>

<div class="page scroll">
  <header class="hd"><h1 class="t-h1">{t('join.title')}</h1><p class="t-foot">{t('join.sub')}</p></header>
  <div class="list">
    {#each groups as group, gi (gi)}
    {#if gi && group.length}<h2 class="grp t-h3">{t('clubs.schools')}</h2>{/if}
    {#each group as o (o.id)}
      <article class="club surface">
        <button class="open" onclick={() => sheets.club(o.id)} aria-label={o.name}></button>
        <div class="top">
          <OrgLogo org={o} size={48} />
          <span class="nm"><b class="t-title">{o.name}</b>{#if o.official}<span class="ok"><BadgeCheck size={16} /></span>{/if}</span>
        </div>
        <p class="t-body dim">{o.description}</p>
        <div class="bot">
          <span class="t-foot">{o.round ? t('cast.recruiting', { when: dayMonth(o.round.closesAt) }) : tn('club.members', o.members)}</span>
          {#if o.round}
            <Button kind={o.round.applied ? 'neutral' : 'primary'} size="m" onclick={() => sheets.roundApply(o.id, 'join')}>{o.round.applied ? t('cast.applied') : t('join.apply')}</Button>
          {:else if o.myRequest === 'rejected'}
            <Button kind="neutral" size="m" disabled>{t('join.notNow')}</Button>
          {:else}
            <Button kind={o.myRequest ? 'neutral' : 'primary'} size="m" onclick={() => toggleJoin(o.id)}>{o.myRequest ? t('join.sent') : t('join.apply')}</Button>
          {/if}
        </div>
      </article>
    {/each}
    {/each}
    <CreateClubCard />
  </div>
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; }
  .hd { margin-bottom: 16px; }
  .hd p { margin-top: 4px; }
  .list { display: flex; flex-direction: column; gap: 10px; }
  .grp { margin: 10px 2px 0; }
  .club { position: relative; display: flex; flex-direction: column; gap: 10px; padding: 14px; }
  .open { position: absolute; inset: 0; border-radius: inherit; }
  .top { display: flex; align-items: center; gap: 12px; }
  .nm { display: flex; align-items: center; gap: 5px; }
  .ok { display: inline-flex; color: var(--accent-text); }
  .bot { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .bot :global(.btn) { position: relative; z-index: 1; }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
