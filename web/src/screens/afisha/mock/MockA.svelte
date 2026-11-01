<script lang="ts">
  // Afisha mock A, "Luma list" (stage 1, a throwaway): the page reads like Luma's home. Big two-line section titles, day
  // headers "Tomorrow / Tuesday", rows with a square cover, the club, a bold title, time and place with thin icons;
  // hairlines inset to the text between rows of one day. My events first, each row ending in its countdown and a
  // ticket button. The assistant and "In a row" share one quiet pill top right.
  import Clock from '@lucide/svelte/icons/clock';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import Play from '@lucide/svelte/icons/play';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import CalendarCheck from '@lucide/svelte/icons/calendar-check';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { onMount } from 'svelte';
  import type { EventCard } from '../../../lib/api';
  import { data, prefetchEvent } from '../../../lib/state/data.svelte';
  import { session } from '../../../lib/state/session.svelte';
  import { sheets } from '../../../lib/state/sheets';
  import { t, tn, money, placeOf } from '../../../lib/i18n/index.svelte';
  import { dayMonth, dayNo, nowTs, soon, time, weekday } from '../../../lib/time';
  import { nameOf } from '../../../lib/short';
  import Poster from '../../../ui/Poster.svelte';
  import OrgLogo from '../../../ui/OrgLogo.svelte';
  import Avatar from '../../../ui/Avatar.svelte';
  import { fitTitle, largeTitle } from '../../../ui/title';
  import StoryRow from '../StoryRow.svelte';
  import { byDay, dayHead, dayTs, mine } from './days';

  let now = $state(nowTs());
  onMount(() => { const id = setInterval(() => (now = nowTs()), 30_000); return () => clearInterval(id); });
  const today = $derived(dayNo(now));
  const days = $derived(byDay(data.events, now));
  const going = $derived(mine(data.events, now));
  const week = $derived(days.filter((x) => x.d < today + 7).reduce((n, x) => n + x.events.length, 0));
  const askSched = $derived(!!session.me?.student && !data.schedule.length);
</script>

{#snippet row(e: EventCard, end?: 'ticket')}
  <div class="row">
    <button class="hit" onpointerdown={() => prefetchEvent(e.id)} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
    <Poster item={e} size={76} radius={16} />
    <span class="tx">
      <span class="org"><OrgLogo org={e.org} size={16} /><span class="ellipsis">{nameOf(e.org)}</span></span>
      <b class="clamp-2">{e.title}</b>
      <span class="meta num">
        <span><Clock size={14} strokeWidth={1.75} />{end ? soon(e.startsAt, now) : time(e.startsAt)}</span>
        <span class="ellipsis"><MapPin size={14} strokeWidth={1.75} />{placeOf(e.place)}</span>
      </span>
      {#if !end && (e.friends.length || e.price)}
        <span class="sub">
          {#if e.friends.length}<span class="av">{#each e.friends.slice(0, 3) as f (f.id)}<Avatar person={f} size={18} tappable={false} />{/each}</span>{/if}
          {#if e.price}<span class="num">{money(e.price)}</span>{/if}
        </span>
      {/if}
    </span>
    {#if end}<button class="tk" onclick={() => sheets.ticket(e.id)} aria-label={t('event.ticket')}><QrCode size={18} strokeWidth={2} /></button>{/if}
  </div>
{/snippet}

<div class="page scroll">
  <header class="hd">
    <span><p class="kick">{weekday(dayTs(today) + 12 * 3600)}, {dayMonth(dayTs(today) + 12 * 3600)}</p>
      <h1 class="ttl" use:fitTitle use:largeTitle={'afisha'}>{t('common.today')}</h1></span>
    <!-- Luma's "+ / bell" pill: two quiet icons, not a loud gradient button -->
    <span class="pill">
      {#if session.board}<button onclick={() => sheets.assistant()} aria-label={t('as.ask')}><Sparkles size={19} strokeWidth={1.9} /></button>{/if}
      <button onclick={() => sheets.feed()} aria-label={t('list.inRow')}><Play size={17} strokeWidth={2} fill="currentColor" /></button>
    </span>
  </header>
  <StoryRow />

  <h2 class="sec">{t('list.yours')}</h2>
  {#if going.length}
    <div class="list">{#each going as e (e.id)}{@render row(e, 'ticket')}{/each}</div>
  {:else}
    <div class="empty"><span class="ic"><CalendarCheck size={26} strokeWidth={1.75} /></span><p>{t('list.yoursNone')}</p></div>
  {/if}

  <h2 class="sec two">{t('list.title')}<span class="num">{tn('list.week', week)}</span></h2>
  {#if askSched}
    <button class="tile" onclick={() => sheets.schedHowTo()}>
      <span class="ic sm"><CalendarPlus size={20} strokeWidth={1.75} /></span>
      <span class="tt"><b>{t('sched.cardTitle')}</b><small>{t('sched.cardSub')}</small></span>
      <ChevronRight size={18} />
    </button>
  {/if}
  {#each days as day (day.d)}
    {@const [a, b] = dayHead(day.d, today)}
    <h3 class="dh">{a}{#if b}<span>&nbsp;/ {b}</span>{/if}</h3>
    <div class="list">{#each day.events as e (e.id)}{@render row(e)}{/each}</div>
  {/each}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; }
  .hd { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
  .kick { font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); margin-bottom: 2px; }
  .kick::first-letter { text-transform: uppercase; }
  .ttl { font: 800 var(--fs-title)/1.05 var(--font-display); letter-spacing: -0.035em; }
  .pill { flex: none; display: flex; height: var(--ctl-m); padding: 0 4px; border-radius: var(--r-full); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); }
  .pill button { width: 42px; display: grid; place-items: center; color: var(--text); transition: transform var(--t-fast) var(--ease); }
  .pill button:active { transform: scale(0.88); }

  /* Luma's section titles: bold, the second line grey at the same size */
  .sec { margin: 26px 0 12px; font: 780 var(--fs-t1)/1.1 var(--font-display); letter-spacing: -0.03em; }
  .sec.two { display: flex; flex-direction: column; margin-top: 34px; }
  .sec.two span { color: var(--text-3); font-weight: 720; }
  .dh { margin: 22px 0 6px; font: 720 var(--fs-row)/1.2 var(--font-display); letter-spacing: -0.02em; }
  .dh span { color: var(--text-3); font-weight: 600; }

  .list { display: flex; flex-direction: column; }
  .row { position: relative; display: flex; align-items: center; gap: 14px; padding: 12px 0; }
  /* a hairline between rows of one day, inset to the text (Luma) */
  .row + .row::before { content: ''; position: absolute; top: 0; left: 90px; right: 0; height: 0.5px; background: var(--separator); }
  .hit { position: absolute; inset: 0; border-radius: var(--r-m); }
  .hit:active ~ :global(.poster) { transform: scale(0.97); }
  .row :global(.poster) { box-shadow: inset 0 0 0 1px var(--line); transition: transform var(--t-fast) var(--ease); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; pointer-events: none; }
  .org { display: flex; align-items: center; gap: 6px; min-width: 0; font: 560 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .org :global(.logo) { box-shadow: 0 0 0 1px var(--line); }
  .tx b { font: 700 var(--fs-card)/1.22 var(--font-text); letter-spacing: -0.01em; }
  .meta { display: flex; flex-wrap: wrap; gap: 2px 12px; min-width: 0; font: 520 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .meta span { display: inline-flex; align-items: center; gap: 5px; min-width: 0; }
  .meta :global(svg) { flex: none; color: var(--text-3); }
  .sub { display: flex; align-items: center; gap: 8px; margin-top: 2px; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }
  .av { display: flex; }
  .av :global(.av + .av) { margin-left: -5px; }
  .av :global(.av) { box-shadow: 0 0 0 1.5px var(--bg); }
  /* my event's row ends in its control: the ticket, round, aligned */
  .tk { position: relative; flex: none; width: var(--ctl-s); height: var(--ctl-s); display: grid; place-items: center; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); }
  .tk:active { transform: scale(0.9); }

  /* Luma's empty state: a soft tile with an icon, one sentence */
  .empty { display: flex; align-items: center; gap: 16px; }
  .ic { flex: none; display: grid; place-items: center; width: 76px; height: 76px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text-3); }
  .ic.sm { width: 44px; height: 44px; border-radius: var(--r-s); }
  .empty p { font: 540 var(--fs-body)/1.35 var(--font-text); color: var(--text-2); text-wrap: pretty; }
  .tile { display: flex; align-items: center; gap: 14px; width: 100%; padding: 12px 14px; border-radius: var(--r-l); background: var(--surface); text-align: left; color: var(--text-3); }
  .tile .tt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tile b { font: 650 var(--fs-body)/1.25 var(--font-text); color: var(--text); }
  .tile small { font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
