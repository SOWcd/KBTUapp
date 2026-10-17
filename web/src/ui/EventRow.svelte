<script lang="ts">
  // Event card #1 (of three): the list row used in List, club pages and tickets.
  import type { EventCard } from '../lib/api';
  import { t, tn, money, friendsLine, placeOf } from '../lib/i18n/index.svelte';
  import { time, nowTs } from '../lib/time';
  import { sheets } from '../lib/state/sheets';
  import { prefetchEvent } from '../lib/state/data.svelte';
  import Poster from './Poster.svelte';
  import Chip from './Chip.svelte';
  import Avatar from './Avatar.svelte';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import { inner } from '../lib/perms';

  let { e, showDate = false, dateLine = '', onopen }: { e: EventCard; showDate?: boolean; dateLine?: string; onopen?: () => void } = $props();

  const st = $derived(e.my?.status);
  const full = $derived(e.seats != null && e.taken >= e.seats && st !== 'going' && st !== 'hold');
  const cancelled = $derived(e.status === 'cancelled');
  const live = $derived(!cancelled && e.startsAt <= nowTs() && (e.endsAt ?? e.startsAt + 3 * 3600) > nowTs());
  const over = $derived(!cancelled && (e.endsAt ?? e.startsAt + 3 * 3600) <= nowTs());
</script>

<!-- a club's own event looks like one: an outline instead of a card, the team mark by its time (owner, Oct 6) -->
<button class="row press" class:cancelled class:inner={inner(e)} onpointerdown={() => { if (!onopen) prefetchEvent(e.id); }} onclick={(ev) => (onopen ? onopen() : sheets.event(e.id, ev.currentTarget.querySelector('.poster')))}>
  <Poster item={e} size={68} radius={16} dim={cancelled} />
  <span class="txt">
    <span class="t-title clamp-2 title">{e.title}</span>
    <span class="t-foot meta">{#if inner(e)}<UsersRound size={13} strokeWidth={2.4} />{/if}{showDate ? dateLine + ' · ' : ''}{time(e.startsAt)} · {placeOf(e.place)}{e.price ? ' · ' + money(e.price) : ''}</span>
    <span class="foot">
      {#if e.toCheck && !cancelled}<Chip tone="warning">{t('studio.chipCheck', { n: e.toCheck })}</Chip>{/if}
      {#if cancelled}<Chip tone="danger">{t('event.cancelled')}</Chip>
      {:else if e.status === 'draft'}<Chip>{t('studio.draft')}</Chip>
      {:else if over}{#if e.my?.checkedInAt}<Chip tone="success">{t('event.attended')}</Chip>{/if}
      {:else if live}<Chip tone="success">{t('event.live')}</Chip>
      {:else if st === 'going'}<Chip tone="accent">{t('event.youGo')}</Chip>
      {:else if st === 'hold'}<Chip tone="warning">{t('event.pay', { price: money(e.price ?? 0) })}</Chip>
      {:else if st === 'waitlist'}<Chip tone="neutral">{t('event.notifyOn')}</Chip>
      {:else if full}<Chip tone="neutral">{t('event.full')}</Chip>
      {:else if e.visibility === 'members'}<Chip tone="accent">{t('event.teamOnly')}</Chip>
      {:else if e.firstYear}<Chip tone="warning">{t('event.firstYear')}</Chip>{/if}
      {#if e.friends.length && !cancelled}
        <span class="fr">
          <span class="stack">{#each e.friends.slice(0, 3) as f (f.id)}<Avatar person={f} size={20} tappable={false} />{/each}</span>
          <span class="t-foot ellipsis">{friendsLine(e.friends.map((f) => f.name), over)}</span>
        </span>
      {:else if !cancelled && !over}
        <span class="t-foot faint">{tn('event.going', e.taken)}</span>
      {/if}
    </span>
  </span>
</button>

<style>
  .row { display: flex; gap: 12px; align-items: center; width: 100%; padding: 10px; border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-card); text-align: left; }
  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .title { color: var(--text); }
  .cancelled .title { text-decoration: line-through; color: var(--text-2); }
  .meta { color: var(--text-2); }
  .inner { background: transparent; box-shadow: inset 0 0 0 1.5px var(--line-2); }
  .meta :global(svg) { display: inline; vertical-align: -2px; margin-right: 5px; color: var(--accent-text); }
  .foot { display: flex; align-items: center; gap: 8px; margin-top: 3px; min-height: 22px; min-width: 0; }
  .fr { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .stack { display: flex; }
  .stack :global(.av + .av) { margin-left: -6px; }
  .stack :global(.av) { box-shadow: 0 0 0 2px var(--surface); }
</style>
