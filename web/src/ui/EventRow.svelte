<script lang="ts">
  // Event card #1 (of three): the list row used in List, club pages and tickets. A saved event has a small bookmark in
  // its corner (Oct 30: Profile's "Coming up" is gone, the saved ones are found on the list).
  import type { EventCard } from '../lib/api';
  import { t, tn, money, friendsLine, placeOf } from '../lib/i18n/index.svelte';
  import { time, nowTs } from '../lib/time';
  import { sheets } from '../lib/state/sheets';
  import { prefetchEvent } from '../lib/state/data.svelte';
  import Poster from './Poster.svelte';
  import Tag from './Tag.svelte';
  import Avatar from './Avatar.svelte';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import Bookmark from '@lucide/svelte/icons/bookmark';
  import { inner } from '../lib/perms';

  let { e, showDate = false, dateLine = '', onopen }: { e: EventCard; showDate?: boolean; dateLine?: string; onopen?: () => void } = $props();

  const st = $derived(e.my?.status);
  const full = $derived(e.seats != null && e.taken >= e.seats && st !== 'going' && st !== 'hold');
  const cancelled = $derived(e.status === 'cancelled');
  const live = $derived(!cancelled && e.startsAt <= nowTs() && (e.endsAt ?? e.startsAt + 3 * 3600) > nowTs());
  const over = $derived(!cancelled && (e.endsAt ?? e.startsAt + 3 * 3600) <= nowTs());
</script>

<!-- a club's own event looks like one: an outline instead of a card, the team mark by its time -->
<button class="row press" class:cancelled class:inner={inner(e)} onpointerdown={() => { if (!onopen) prefetchEvent(e.id); }} onclick={(ev) => (onopen ? onopen() : sheets.event(e.id, ev.currentTarget.querySelector('.poster')))}>
  <Poster item={e} size={68} radius={16} dim={cancelled} />
  {#if e.saved && !cancelled}<span class="saved" title={t('event.saved')}><Bookmark size={14} strokeWidth={2.4} fill="currentColor" /></span>{/if}
  <span class="txt" class:pr={e.saved && !cancelled}>
    <span class="t-title clamp-2 title">{e.title}</span>
    <span class="t-foot meta">{#if inner(e)}<UsersRound size={13} strokeWidth={2.4} />{/if}{showDate ? dateLine + ' · ' : ''}{time(e.startsAt)} · {placeOf(e.place)}{e.price ? ' · ' + money(e.price) : ''}</span>
    <span class="foot">
      {#if e.toCheck && !cancelled}<Tag tone="warning">{t('studio.chipCheck', { n: e.toCheck })}</Tag>{/if}
      {#if cancelled}<Tag tone="danger">{t('event.cancelled')}</Tag>
      {:else if e.status === 'draft'}<Tag>{t('studio.draft')}</Tag>
      {:else if over}{#if e.my?.checkedInAt}<Tag tone="success">{t('event.attended')}</Tag>{/if}
      {:else if live}<Tag tone="success">{t('event.live')}</Tag>
      {:else if st === 'going'}<Tag tone="accent">{t('event.youGo')}</Tag>
      {:else if st === 'hold'}<Tag tone="warning">{t('event.pay', { price: money(e.price ?? 0) })}</Tag>
      {:else if st === 'waitlist'}<Tag tone="neutral">{t('event.notifyOn')}</Tag>
      {:else if full}<Tag tone="neutral">{t('event.full')}</Tag>
      {:else if e.guestHost}<Tag tone="neutral">{t('event.partner')}</Tag>
      {:else if e.visibility === 'members'}<Tag tone="accent">{t('event.teamOnly')}</Tag>
      {:else if e.firstYear}<Tag tone="warning">{t('event.firstYear')}</Tag>{/if}
      {#if e.friends.length && !cancelled}
        <span class="fr">
          <span class="stack">{#each e.friends.slice(0, 3) as f (f.id)}<Avatar person={f} size={20} tappable={false} />{/each}</span>
          <span class="t-foot ellipsis">{friendsLine(e.friends.map((f) => f.name), over)}</span>
        </span>
      {:else if !cancelled && !over && !e.guestHost}
        <span class="t-foot faint">{tn('event.going', e.taken)}</span>
      {/if}
    </span>
  </span>
</button>

<style>
  .row { position: relative; display: flex; gap: 12px; align-items: center; width: 100%; padding: 10px; border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-card); text-align: left; }
  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .txt.pr .title { padding-right: 16px; }
  .saved { position: absolute; top: 10px; right: 10px; display: flex; color: var(--warning-text); } /* the themed amber: plain gold faded on a light row */
  .title { color: var(--text); }
  .cancelled .title { text-decoration: line-through; color: var(--text-2); }
  .meta { color: var(--text-2); }
  .inner { background: transparent; box-shadow: inset 0 0 0 1.5px var(--line-2); }
  .meta :global(svg) { display: inline; vertical-align: -2px; margin-right: 5px; color: var(--accent-text); }
  .foot { display: flex; align-items: center; gap: 8px; margin-top: 3px; min-height: 22px; min-width: 0; }
  .fr { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .stack { display: flex; }
  .stack :global(.av + .av) { margin-left: -6px; }
  .stack :global(.av) { box-shadow: 0 0 0 2px var(--surface-solid); }
</style>
