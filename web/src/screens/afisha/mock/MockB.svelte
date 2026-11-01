<script lang="ts">
  // Afisha mock B, "Poster cards" (stage 1, a throwaway): every event is its own rounded card led by its cover (Luma's
  // event page, Apple's Events). My next events on top as big covers you swipe, the next one peeking at the edge;
  // their Ticket and Route float on the cover as liquid glass (the shared engine). The card's foot ends in the
  // price or "Free", aligned.
  import Clock from '@lucide/svelte/icons/clock';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import Play from '@lucide/svelte/icons/play';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import CalendarCheck from '@lucide/svelte/icons/calendar-check';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { onMount } from 'svelte';
  import { data, prefetchEvent } from '../../../lib/state/data.svelte';
  import { session } from '../../../lib/state/session.svelte';
  import { sheets } from '../../../lib/state/sheets';
  import { t, tn, money, placeOf } from '../../../lib/i18n/index.svelte';
  import { dayMonth, dayNo, nowTs, soon, time, weekday } from '../../../lib/time';
  import { nameOf } from '../../../lib/short';
  import { floorOf } from '../../../lib/map';
  import Poster from '../../../ui/Poster.svelte';
  import OrgLogo from '../../../ui/OrgLogo.svelte';
  import Avatar from '../../../ui/Avatar.svelte';
  import { glass } from '../../../ui/glass';
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

<div class="page scroll">
  <header class="hd">
    <span><p class="kick">{weekday(dayTs(today) + 12 * 3600)}, {dayMonth(dayTs(today) + 12 * 3600)}</p>
      <h1 class="ttl" use:fitTitle use:largeTitle={'afisha'}>{t('common.today')}</h1></span>
    <span class="pill">
      {#if session.board}<button onclick={() => sheets.assistant()} aria-label={t('as.ask')}><Sparkles size={19} strokeWidth={1.9} /></button>{/if}
      <button onclick={() => sheets.feed()} aria-label={t('list.inRow')}><Play size={17} strokeWidth={2} fill="currentColor" /></button>
    </span>
  </header>
  <StoryRow />

  <h2 class="sec">{t('list.yours')}</h2>
  {#if going.length}
    <div class="heroes" class:one={going.length === 1}>
      {#each going as e (e.id)}
        <section class="hero" style="--c:{e.color ?? e.tint}">
          <button class="hit" onpointerdown={() => prefetchEvent(e.id)} onclick={() => sheets.event(e.id)} aria-label={e.title}></button>
          <Poster item={e} big radius={0} />
          <div class="shade"></div>
          <div class="hero-tx">
            <span class="when num">{soon(e.startsAt, now)} · {time(e.startsAt)}</span>
            <b class="clamp-2">{e.title}</b>
            <span class="where ellipsis">{placeOf(e.place)} · {nameOf(e.org)}</span>
            <!-- over the cover: the engine's glass, the way iOS puts controls on artwork -->
            <span class="acts">
              <button class="glass glass-pill" use:glass={{ bloom: true }} onclick={() => sheets.ticket(e.id)}><QrCode size={17} />{t('event.ticket')}</button>
              {#if floorOf(e.place) != null}<button class="glass glass-pill" use:glass={{ bloom: true }} onclick={() => sheets.map(e.place)}><MapPin size={17} />{t('route.open')}</button>{/if}
            </span>
          </div>
        </section>
      {/each}
    </div>
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
    {#each day.events as e (e.id)}
      <article class="card">
        <button class="hit" onpointerdown={() => prefetchEvent(e.id)} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
        <div class="cover"><Poster item={e} big radius={0} /></div>
        <div class="body">
          <span class="org"><OrgLogo org={e.org} size={16} /><span class="ellipsis">{nameOf(e.org)}</span></span>
          <b class="clamp-2">{e.title}</b>
          <span class="meta num"><span><Clock size={14} strokeWidth={1.75} />{time(e.startsAt)}</span><span class="ellipsis"><MapPin size={14} strokeWidth={1.75} />{placeOf(e.place)}</span></span>
          <span class="foot">
            <span class="fr">
              {#if e.friends.length}<span class="av">{#each e.friends.slice(0, 3) as f (f.id)}<Avatar person={f} size={20} tappable={false} />{/each}</span>{/if}
              {#if e.my?.status === 'going'}<span>{t('event.youGo')}</span>{:else if e.taken}<span class="num">{tn('event.going', e.taken)}</span>{/if}
            </span>
            <span class="price num">{e.price ? money(e.price) : t('event.free')}</span>
          </span>
        </div>
      </article>
    {/each}
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

  .sec { margin: 26px 0 12px; font: 780 var(--fs-t1)/1.1 var(--font-display); letter-spacing: -0.03em; }
  .sec.two { display: flex; flex-direction: column; margin-top: 34px; }
  .sec.two span { color: var(--text-3); font-weight: 720; }
  .dh { margin: 22px 0 10px; font: 720 var(--fs-row)/1.2 var(--font-display); letter-spacing: -0.02em; }
  .dh span { color: var(--text-3); font-weight: 600; }
  .hit { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }

  /* my events: big covers side by side, the next one peeks in */
  .heroes { display: flex; gap: 10px; overflow-x: auto; scroll-snap-type: x mandatory; margin: 0 calc(-1 * var(--gutter)); padding: 0 var(--gutter); scroll-padding: 0 var(--gutter); scrollbar-width: none; }
  .heroes::-webkit-scrollbar { display: none; }
  .hero { position: relative; flex: none; width: calc(100% - 28px); aspect-ratio: 4 / 3.6; scroll-snap-align: start; overflow: hidden; border-radius: var(--r-xl);
    box-shadow: inset 0 0 0 1px var(--line), 0 18px 36px -24px var(--c); }
  .heroes.one .hero { width: 100%; }
  .hero :global(.poster) { position: absolute; inset: 0; }
  .hero :global(.poster .emoji) { width: 104px; height: 104px; margin-bottom: 42%; filter: drop-shadow(0 16px 18px rgba(0, 0, 0, 0.4)); }
  .shade { position: absolute; inset: 40% 0 0; background: linear-gradient(transparent, rgba(0, 0, 0, 0.62)); pointer-events: none; }
  .hero-tx { position: absolute; left: 0; right: 0; bottom: 0; display: flex; flex-direction: column; gap: 3px; padding: 16px; color: var(--on-accent); pointer-events: none; }
  .when { font: 650 var(--fs-sub)/1.2 var(--font-text); opacity: 0.85; }
  .hero-tx b { font: 780 var(--fs-sec)/1.15 var(--font-display); letter-spacing: -0.025em; }
  .where { font: 520 var(--fs-sub)/1.3 var(--font-text); opacity: 0.75; }
  .acts { position: relative; z-index: 2; display: flex; gap: 8px; margin-top: 12px; pointer-events: auto; }
  .acts button { position: relative; display: inline-flex; align-items: center; gap: 6px; height: var(--btn-m); padding: 0 16px; border-radius: var(--r-full);
    color: var(--on-accent); font: 650 var(--fs-body)/1 var(--font-text); }
  .acts button > :global(svg) { position: relative; }
  .acts button:active { transform: scale(0.95); }

  /* an event: its own card, the cover on top, the foot ending in the price */
  .card { position: relative; display: flex; flex-direction: column; margin-bottom: 12px; overflow: hidden; border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-card); }
  .card:has(.hit:active) { transform: scale(0.985); }
  .card { transition: transform var(--t-fast) var(--ease); }
  .cover { position: relative; height: 112px; }
  .cover :global(.poster .emoji) { width: 72px; height: 72px; filter: drop-shadow(0 10px 12px rgba(0, 0, 0, 0.3)); }
  .cover :global(.poster) { position: absolute; inset: 0; }
  .body { display: flex; flex-direction: column; gap: 4px; padding: 12px 14px 14px; }
  .org { display: flex; align-items: center; gap: 6px; min-width: 0; font: 560 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .body b { font: 720 var(--fs-card)/1.22 var(--font-text); letter-spacing: -0.01em; }
  .meta { display: flex; flex-wrap: wrap; gap: 2px 12px; font: 520 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .meta span { display: inline-flex; align-items: center; gap: 5px; min-width: 0; }
  .meta :global(svg) { flex: none; color: var(--text-3); }
  .foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-top: 8px; padding-top: 10px; border-top: 0.5px solid var(--separator); }
  .fr { display: flex; align-items: center; gap: 8px; min-width: 0; font: 560 var(--fs-sub)/1 var(--font-text); color: var(--text-3); }
  .av { display: flex; }
  .av :global(.av + .av) { margin-left: -6px; }
  .av :global(.av) { box-shadow: 0 0 0 1.5px var(--surface-solid); }
  .price { flex: none; font: 680 var(--fs-body)/1 var(--font-text); }

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
