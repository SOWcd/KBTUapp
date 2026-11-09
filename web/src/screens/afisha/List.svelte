<script lang="ts">
  // Afisha, one screen, in Luma's manner (owner, Nov 2: mock A with B's covers on top). The date and Today with a quiet
  // pill (the assistant, "In a row"), the news circles; "Your events" (only when I go somewhere): big covers swiped sideways, the next one peeking
  // in (the events I'm going to this week, their Ticket and Route on the cover); then "Events" over its grey count, the
  // featured post, and the days ("Tomorrow / Tuesday"): rows with a square cover, the club, a bold title, time and place
  // with thin icons, classes as slim rows in time order between them, the one on now live in place (the capsule above
  // says it too), hairlines inset to the text. No date strip
  // (owner, Oct 24: people scroll); the headers don't stick (a slab mid-screen over the rows).
  import Clock from '@lucide/svelte/icons/clock';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import MapIcon from '@lucide/svelte/icons/map';
  import Play from '@lucide/svelte/icons/play';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import Bookmark from '@lucide/svelte/icons/bookmark';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import { onMount } from 'svelte';
  import type { ClassItem, EventCard } from '../../lib/api';
  import { data, skipped, classKey, skipClass, prefetchEvent } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { ui } from '../../lib/state/ui.svelte';
  import { t, tn, money, placeOf, subjectOf, friendsLine } from '../../lib/i18n/index.svelte';
  import { lessonKind } from '../../lib/i18n/subjects';
  import { dayNo, nowTs, parts, weekday, dayMonth, OFFSET, soon, time, dateInput, multiDay, daySpan } from '../../lib/time';
  import { classesOn, classesLeft } from '../../lib/classes';
  import { noClasses } from '../../lib/academic';
  import { floorOf, atDorm, DORM_2GIS, atBldg2, bldg2Room, BLDG2_2GIS } from '../../lib/map';
  import { openLink } from '../../lib/tg';
  import { tagName } from '../../lib/posts';
  import { nameOf, shortOf } from '../../lib/short';
  import { inner } from '../../lib/perms';
  import Poster from '../../ui/Poster.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Tag from '../../ui/Tag.svelte';
  import CastingBlock from '../../ui/CastingBlock.svelte';
  import TwoGisMark from '../../ui/TwoGisMark.svelte';
  import EventRow from '../../ui/EventRow.svelte';
  import { fitTitle, largeTitle } from '../../ui/title';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Card from '../../ui/Card.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import StoryRow from './StoryRow.svelte';
  import PullSearch from '../../ui/PullSearch.svelte';
  import { hit as orgHit } from '../../lib/clubs';
  import { hit, namesOf } from '../../lib/search';
  import GalleryCard from './GalleryCard.svelte';

  let openPost = $state(false);

  // the clock: a minute is enough for "21 min left"; moves on at midnight (the app can stay open overnight)
  let now = $state(nowTs());
  onMount(() => { const id = setInterval(() => (now = nowTs()), 30_000); return () => clearInterval(id); });
  const today = $derived(dayNo(now));
  const dayTs = (d: number) => d * 86400 - OFFSET; // start of local day d as a UTC timestamp
  const endOf = (e: EventCard) => e.endsAt ?? e.startsAt + 3 * 3600;

  const featured = $derived(data.posts.find((p) => p.featured));
  const shown = $derived(data.events.filter((e) => e.status !== 'cancelled'));

  type Item = { key: string; at: number } & ({ c: ClassItem; end: number } | { e: EventCard });
  const classesOf = (d: number): Item[] => classesOn(data.schedule, d).map((x) => ({ key: classKey(d, x.c), at: x.b, end: x.e, c: x.c }));
  // an event of several days that began earlier and still runs sits on today (a casting, 2-12 Nov). Its ids as one string:
  // the days below follow the date and this, not the 30 s clock (every tick rebuilt all the days and re-rendered every row)
  const running = $derived(data.events.filter((e) => dayNo(e.startsAt) < today && endOf(e) > now).map((e) => e.id).join());
  const days = $derived.by(() => {
    const by = new Map<number, Item[]>(), on = new Set(running.split(',').map(Number));
    for (const e of data.events) { const d = Math.max(dayNo(e.startsAt), on.has(e.id) ? today : -1); if (d < today) continue; if (!by.has(d)) by.set(d, []); by.get(d)!.push({ key: 'e' + e.id, at: e.startsAt, e }); }
    // the coming week's class days too (the owner missed his Wednesday), later only event days; today's classes stay
    // here too: their rows are where "I won't go" is tapped (and taken back)
    const week = Array.from({ length: 7 }, (_, i) => today + i).filter((d) => d === today || data.schedule.some((c) => c.weekday === (parts(dayTs(d) + 12 * 3600).wd || 7)));
    const wanted = [...new Set([...week, ...by.keys()])].sort((a, b) => a - b);
    // a class before an event that starts at the same minute: you leave the class for it
    return wanted.map((d) => ({ d, items: [...classesOf(d), ...(by.get(d) ?? [])].sort((a, b) => a.at - b.at || ('c' in a ? -1 : 1)) }));
  });
  // the first screenfuls come with the tab, the rest a few days per idle moment: a term's worth of events (200 rows,
  // 5k nodes) was one 2 s task at 4x CPU before the Afisha showed. Off-screen days skip layout and paint (.day)
  // the Gallery's card: under the day of the nearest event, at the latest under the second day (never a hunt)
  const galleryAt = $derived(days[Math.min(Math.max(days.findIndex((x) => x.items.some((i) => 'e' in i)), 0), 1)]?.d);
  const STEP = 8;
  let upto = $state(2 * STEP);
  const shownDays = $derived.by(() => {
    let i = 0;
    for (let n = 0; i < days.length && n < upto; i++) n += days[i].items.length;
    return i >= days.length ? days : days.slice(0, Math.max(1, i));
  });
  $effect(() => {
    if (shownDays.length >= days.length) return;
    if (!('requestIdleCallback' in window)) { const id = setTimeout(() => (upto += STEP), 50); return () => clearTimeout(id); }
    const id = requestIdleCallback(() => (upto += STEP), { timeout: 1000 });
    return () => cancelIdleCallback(id);
  });
  const weekCount = $derived(shown.filter((e) => endOf(e) > now && dayNo(e.startsAt) < today + 7).length);
  // a day off by the academic calendar on a class day: say why the classes are gone
  const offToday = $derived(noClasses(dateInput(now)) && data.schedule.some((c) => c.weekday === (parts(now).wd || 7)));

  // "Your events": only the events I'm going to this week (owner, Nov 2: a class card there showed the class twice)
  const going = $derived(shown.filter((e) => e.my?.status === 'going' && endOf(e) > now && e.startsAt - now < 7 * 86400).sort((a, b) => a.startsAt - b.startsAt));
  // the class on now comes alive in its own row (what's left, a thin progress line); the next one within the hour says
  // how soon. Read once for all rows: the row only compares its key.
  const left = $derived(classesLeft(data.schedule, now).filter((x) => !skipped.has(classKey(today, x.c))));
  const live = $derived(left[0] && left[0].b <= now ? { key: classKey(today, left[0].c), ...left[0] } : null);
  const next = $derived.by(() => { const x = left.find((y) => y.b > now); return x && x.b - now <= 3600 ? { key: classKey(today, x.c), ...x } : null; });

  // no timetable: the one card that asks for it (after the first load: a returning student never sees it flash)
  const askSched = $derived(data.eventsReady && !!session.me?.student && !data.schedule.length);

  const past = $derived(data.past); // "Past": mine that ended, newest first (the server's order)
  let allPast = $state(false);

  // the pull-down search: the events held, upcoming and mine that ended, by title, place or club
  let q = $state('');
  const searching = $derived(!!q.trim());
  const found = $derived(searching ? [...shown, ...past.filter((p) => !shown.some((e) => e.id === p.id))].filter((e) => hit(q, namesOf(e, 'title', 'place')) || orgHit(e.org, q)) : []);

  function head(d: number): [string, string] {
    const w = weekday(dayTs(d) + 12 * 3600);
    if (d === today) return [t('common.today'), w];
    if (d === today + 1) return [t('common.tomorrow'), w];
    return [w.charAt(0).toUpperCase() + w.slice(1), dayMonth(dayTs(d) + 12 * 3600)];
  }
</script>

{#snippet clRow(it: Extract<Item, { c: ClassItem }>)}
            {@const hours = Math.round((it.end - it.at) / 3600)}
                  {@const k = lessonKind(it.c.kind)}
                  <!-- a class: a slim row, its times where the covers are; a tap: "I won't go" (the capsule leaves it out), or back -->
                  {@const isLive = it.key === live?.key}
                  <div class="row cl" class:past={it.end < now} class:skip={skipped.has(it.key)} class:live={isLive} role="button" tabindex="0"
                       onclick={(ev) => { if (!(ev.target as HTMLElement).closest('.cl-r')) void skipClass(it.key, it.c); }} onkeydown={(ev) => ev.key === 'Enter' && skipClass(it.key, it.c)}>
                    <span class="cl-t num"><b>{it.c.begins}</b>{it.c.ends}</span>
                    <!-- the timetable's own name, the same as the capsule's (owner, Nov 2: the short "PE" here, in full there) -->
                    <span class="cl-s"><b class="ellipsis">{subjectOf(it.c)}</b>
                      <small class="ellipsis">{#if isLive && live}<span class="soon num">{t('list.nowLeft', { n: Math.max(1, Math.ceil((live.e - now) / 60)) })}</span>
                        {:else if it.key === next?.key && next}<span class="soon num">{t('cap.inMin', { n: Math.ceil((next.b - now) / 60) })}</span>
                        {:else if k}<i class="cl-k {k}">{t(`list.kind.${k}Long`)}</i>{:else if it.c.kind}{it.c.kind}{/if}{#if hours > 1}<span class="num">&nbsp;· ×{hours}</span>{/if}{#if skipped.has(it.key)}&nbsp;· {t('skip.tag')}{/if}</small></span>
                    {#if isLive && live}<i class="prog" style="width:calc((100% - 90px) * {Math.min(1, (now - live.b) / Math.max(60, live.e - live.b))})"></i>{/if}
                    {#if floorOf(it.c.room) != null}<span class="cl-r on"><Button kind="tinted" size="s" onclick={() => sheets.map(it.c.room!)}>{#snippet icon()}<MapIcon size={14} />{/snippet}{it.c.room}</Button></span>
                    {:else if atBldg2(it.c.room)}<span class="cl-r on" title={it.c.room}><Button kind="tinted" size="s" onclick={() => openLink(BLDG2_2GIS)}>{#snippet icon()}<TwoGisMark size={14} />{/snippet}{[bldg2Room(it.c.room!), t('list.bldg2')].filter(Boolean).join(' · ')}</Button></span>
                    {:else if atDorm(it.c.room)}<span class="cl-r on" title={it.c.room}><Button kind="tinted" size="s" onclick={() => openLink(DORM_2GIS)}>{#snippet icon()}<TwoGisMark size={14} />{/snippet}{t('list.dorm')}</Button></span>
                    {:else if it.c.room}<span class="cl-r ellipsis">{it.c.room}</span>{/if}
                  </div>
{/snippet}

{#snippet status(e: EventCard)}
  {@const st = e.my?.status}
  {@const cancelled = e.status === 'cancelled'}
  {@const over = !cancelled && endOf(e) <= now}
  {@const live = !cancelled && !over && e.startsAt <= now}
  {@const full = e.seats != null && e.taken >= e.seats && st !== 'going' && st !== 'hold'}
  {#if e.toCheck && !cancelled}<Tag tone="warning">{t('studio.chipCheck', { n: e.toCheck })}</Tag>{/if}
  {#if cancelled}<Tag tone="danger">{t('event.cancelled')}</Tag>
  {:else if e.status === 'draft'}<Tag>{t('studio.draft')}</Tag>
  {:else if over}{#if e.my?.checkedInAt}<Tag tone="success">{t('event.attended')}</Tag>{/if}
  {:else if live}<Tag tone="success">{t(e.lateSignup && st !== 'going' ? 'event.liveOpen' : 'event.live')}</Tag>{#if st === 'going'}<Tag tone="accent">{t('event.youGo')}</Tag>{/if}<!-- a casting of ten days runs and I'm in it -->
  {:else if st === 'going'}<Tag tone="accent">{t('event.youGo')}</Tag>
  {:else if st === 'hold'}<Tag tone="warning">{t('event.pay', { price: money(e.price ?? 0) })}</Tag>
  {:else if st === 'waitlist'}<Tag tone="neutral">{t('event.notifyOn')}</Tag>
  {:else if full}<Tag tone="neutral">{t('event.full')}</Tag>
  {:else if e.guestHost}<Tag tone="neutral">{t('event.partner')}</Tag>
  {:else if e.visibility === 'members'}<Tag tone="accent">{t('event.teamOnly')}</Tag>
  {:else if e.firstYear}<Tag tone="warning">{t('event.firstYear')}</Tag>{/if}
  {#if e.friends.length && !cancelled}
    <span class="fr"><span class="av">{#each e.friends.slice(0, 3) as f (f.id)}<Avatar person={f} size={18} tappable={false} />{/each}</span>
      <span class="ellipsis">{friendsLine(e.friends.map((f) => f.name), over)}</span></span>
  {/if}
{/snippet}

<div class="page scroll stagger">
  <PullSearch bind:value={q} placeholder={t('list.search')} />
  <header class="hd">
    <span><p class="kick">{weekday(dayTs(today) + 12 * 3600)}, {dayMonth(dayTs(today) + 12 * 3600)}</p>
      <h1 class="ttl" use:fitTitle use:largeTitle={'afisha'}>{t('common.today')}</h1></span>
    <!-- the assistant (with the forum's switch) and the Feed full screen -->
    {#if session.board || shown.length}
      <span class="tools">
        {#if session.board}<IconButton icon={Sparkles} label={t('as.ask')} onclick={() => sheets.assistant()} />{/if}
        {#if shown.length}<IconButton icon={Play} label={t('list.inRow')} onclick={() => sheets.feed()} />{/if}
      </span>
    {/if}
  </header>
  {#if searching}
    <div class="past">
      {#each found as e (e.id)}<EventRow {e} showDate dateLine={dayMonth(e.startsAt)} />
      {:else}<EmptyState inline text={t('clubs.nothing')} />{/each}
    </div>
  {:else}
  <StoryRow />
  {#if offToday}<p class="off t-foot">{t('list.dayOff')}</p>{/if}

  {#if going.length}
    <h2 class="sec">{t('list.yours')}</h2>
    <div class="heroes" class:one={going.length === 1}>
      {#each going as e (e.id)}
        <!-- an event I'm going to: its cover, how soon, the way there and the ticket -->
        <section class="hero" style="--c:{e.color ?? e.tint}">
          <button class="hit" onpointerdown={() => prefetchEvent(e.id)} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
          <Poster item={e} big radius={0} />
          <div class="shade"></div>
          <div class="hero-tx">
            <span class="when num">{soon(e.startsAt, now)} · {multiDay(e.startsAt, e.endsAt) ? daySpan(e.startsAt, e.endsAt) : time(e.startsAt)}</span>
            <b class="clamp-2">{e.title}</b>
            <span class="where ellipsis">{placeOf(e.place)} · {shortOf(e.org)}{#if e.coHost} × {shortOf(e.coHost)}{/if}</span>
            <!-- over the cover: the glass buttons -->
            <span class="acts">
              <Button kind="glass" onclick={() => sheets.ticket(e.id)}>{#snippet icon()}<QrCode size={17} />{/snippet}{t('event.ticket')}</Button>
              {#if floorOf(e.place) != null}<Button kind="glass" onclick={() => sheets.map(e.place)}>{#snippet icon()}<MapPin size={17} />{/snippet}{t('route.open')}</Button>{/if}
            </span>
          </div>
        </section>
      {/each}
    </div>
  {/if}
  {#if askSched}
    <!-- no timetable yet: one card at the top, under my events (owner, Nov 8: an empty "Your events" over this card in
         today's list read as two empty states); no plans at all: no section, the events below are the way on -->
    <div class="ask"><Button kind="primary" size="l" full onclick={() => sheets.schedHowTo()}>{#snippet icon()}<CalendarPlus size={20} />{/snippet}{t('sched.cardTitle')}</Button><p class="fs-sub">{t('sched.cardSub')}</p></div>
  {/if}

  <h2 class="sec two">{t('list.title')}{#if weekCount}<span class="num">{tn('list.week', weekCount)}</span>{/if}</h2>

  {#if featured}
    <div class="pin"><Card onclick={() => (openPost = !openPost)}>
      <span class="pin-top">{#if !featured.casting}<Tag tone="warning">{tagName(featured.tag) ?? t('common.more')}</Tag>{/if}<span class="ellipsis">{nameOf(featured.org)}</span></span>
      {#if featured.casting}<CastingBlock casting={featured.casting} />{/if}
      <b>{featured.title}</b>
      <span class="pin-b" class:clamp-2={!openPost}>{featured.body}</span>
    </Card></div>
  {/if}

  {#each shownDays as day (day.d)}
    <!-- without a timetable an empty day isn't shown: not a "free day" we can't know (the card above asks for it) -->
    {#if day.items.length || data.schedule.length}
      {@const [a, b] = head(day.d)}
      <div class="day">
      <h3 class="dh">{a}<span>&nbsp;/ {b}</span></h3>
      <!-- classes and events in one line of time (owner, Nov 7: no folded "N classes" block); a class first at a tie -->
      <div class="list">
        {#each day.items as it (it.key)}
          {#if 'c' in it}{@render clRow(it)}
          {:else}
            {@const e = it.e}
            <!-- an event: Luma's row; a club's own event shows its team mark by the club -->
            <div class="row" class:cancelled={e.status === 'cancelled'}>
              <button class="hit" onpointerdown={() => prefetchEvent(e.id)} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
              <Poster item={e} size={76} radius={16} dim={e.status === 'cancelled'} />
              <span class="tx">
                <span class="org">{#if e.coHost}<span class="pair"><OrgLogo org={e.org} size={16} /><OrgLogo org={e.coHost} size={16} /></span><span class="ellipsis">{nameOf(e.org)} × {nameOf(e.coHost)}</span>{:else}<OrgLogo org={e.org} size={16} /><span class="ellipsis">{nameOf(e.org)}</span>{/if}{#if inner(e)}<UsersRound size={13} strokeWidth={2.2} />{/if}{#if e.saved && e.status !== 'cancelled'}<Bookmark class="sv" size={13} strokeWidth={2.4} fill="currentColor" aria-label={t('event.saved')} />{/if}</span>
                <b class="clamp-2 title">{e.title}</b>
                <span class="meta num">
                  <span><Clock size={14} strokeWidth={1.75} />{multiDay(e.startsAt, e.endsAt) ? daySpan(e.startsAt, e.endsAt) : time(e.startsAt)}</span>
                  <span class="ellipsis"><MapPin size={14} strokeWidth={1.75} />{placeOf(e.place)}</span>
                  {#if e.price}<span>{money(e.price)}</span>{/if}
                </span>
                <span class="sub">{@render status(e)}</span>
              </span>
            </div>
          {/if}
        {/each}
      </div>
      {#if !day.items.length}<p class="free t-foot">{t('list.freeDay')}</p>{/if}
      </div>
    {/if}
    {#if day.d === galleryAt}<GalleryCard />{/if}
  {/each}

  {#if past.length}
    <!-- where I've been: the events I was signed up for or came to, newest first (their albums, my rating) -->
    <h2 class="sec">{t('list.past')}</h2>
    <div class="past">
      {#each allPast ? past : past.slice(0, 5) as e (e.id)}<EventRow {e} showDate dateLine={dayMonth(e.startsAt)} />{/each}
      {#if past.length > 5 && !allPast}<span class="lnk"><Button kind="plain" size="s" onclick={() => (allPast = true)}>{t('common.more')}</Button></span>{/if}
    </div>
  {/if}

  {#if data.eventsReady && shown.length < 6}
    <!-- the first weeks of the pilot: a short list should read as "more is coming", not as an empty app -->
    <EmptyState icon={Sparkles} title={t('list.moreSoon')} text={t('list.moreSoonText')} action={{ label: t('list.toClubs'), onclick: () => { ui.tab = 'club'; } }} />
  {/if}
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; }
  .hd { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 16px; }
  .kick { font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); margin-bottom: 2px; }
  .kick::first-letter { text-transform: uppercase; }
  .ttl { font: 800 var(--fs-title)/1.05 var(--font-display); letter-spacing: -0.035em; }
  .tools { flex: none; display: flex; gap: var(--s-2); }
  .off { margin: 12px 4px 0; color: var(--text-2); }
  .past { display: flex; flex-direction: column; gap: 8px; }
  .lnk { align-self: center; }

  /* Luma's section titles: bold, the second line grey at the same size */
  .sec { margin: 26px 0 12px; font: 800 var(--fs-t1)/1.1 var(--font-display); letter-spacing: -0.03em; }
  .sec.two { display: flex; flex-direction: column; margin-top: 34px; }
  .sec.two span { color: var(--text-3); font-weight: 700; }
  /* a day: skipped while off screen (its size remembered once seen); a paint box, so it spans the gutters too (a row's
     press and shadow are never clipped) and takes the heading's top margin itself (inside, it would no longer collapse
     with the one above) */
  .day { margin: 22px calc(-1 * var(--gutter)) 0; padding: 0 var(--gutter); content-visibility: auto; contain-intrinsic-size: auto 360px; }
  .day > .dh { margin-top: 0; }
  .dh { margin: 22px 0 6px; font: 700 var(--fs-row)/1.2 var(--font-display); letter-spacing: -0.02em; }
  .dh span { color: var(--text-3); font-weight: 600; }
  .dh span::first-letter { text-transform: none; }
  .hit { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }

  /* "Your events": covers side by side, the next one peeks in; room below for the covers' glow (the scroller clipped
     it into a hard band) */
  .heroes { display: flex; gap: 10px; overflow-x: auto; scroll-snap-type: x mandatory; margin: 0 calc(-1 * var(--gutter)) -28px; padding: 0 var(--gutter) 28px; scroll-padding: 0 var(--gutter); scrollbar-width: none; }
  .heroes::-webkit-scrollbar { display: none; }
  .hero { position: relative; flex: none; width: calc(100% - 28px); height: 210px; scroll-snap-align: start; overflow: hidden; border-radius: var(--r-xl);
    box-shadow: inset 0 0 0 1px var(--line), 0 18px 36px -24px var(--c, transparent); transition: transform var(--t-fast) var(--ease); }
  .hero:has(> .hit:active) { transform: scale(0.985); }
  .heroes.one .hero { width: 100%; }
  .hero :global(.poster) { position: absolute; inset: 0; }
  /* an emoji cover: its mark in the top corner, clear of the title and the buttons (centred, it sat on "tomorrow · 18:30") */
  .hero :global(.poster .emoji) { position: absolute; top: 16px; right: 16px; width: 64px; height: 64px; filter: drop-shadow(0 10px 14px rgba(0, 0, 0, 0.35)); }
  .shade { position: absolute; inset: 35% 0 0; background: linear-gradient(transparent, rgba(0, 0, 0, 0.64)); pointer-events: none; }
  .hero-tx { position: absolute; left: 0; right: 0; bottom: 0; display: flex; flex-direction: column; gap: 3px; padding: 16px; color: var(--on-accent); pointer-events: none; }
  .when { font: 600 var(--fs-sub)/1.2 var(--font-text); opacity: 0.85; }
  .hero-tx b { font: 800 var(--fs-sec)/1.15 var(--font-display); letter-spacing: -0.025em; }
  .where { font: 500 var(--fs-sub)/1.3 var(--font-text); opacity: 0.75; }
  .acts { position: relative; z-index: 2; display: flex; gap: 8px; margin-top: 12px; pointer-events: auto; }


  /* the featured post: its own card, the body folded to two lines */
  .pin { margin-bottom: 4px; }
  .pin :global(.card) { display: flex; flex-direction: column; gap: 6px; }
  .pin-top { display: flex; align-items: center; gap: 8px; min-width: 0; font: 500 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .pin b { font: 700 var(--fs-card)/1.25 var(--font-text); }
  .pin-b { font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text-2); }

  /* the rows of a day: a hairline between them, inset to the text (Luma) */
  .list { display: flex; flex-direction: column; }
  .row { position: relative; display: flex; align-items: center; gap: 14px; padding: 12px 0; }
  .row + .row::before { content: ''; position: absolute; top: 0; left: 90px; right: 0; height: 0.5px; background: var(--separator); }
  .row :global(.poster) { box-shadow: inset 0 0 0 1px var(--line); transition: transform var(--t-fast) var(--ease); }
  .row:has(> .hit:active) :global(.poster) { transform: scale(0.96); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; pointer-events: none; }
  .tx :global(button), .tx :global(a) { pointer-events: auto; }
  .org { display: flex; align-items: center; gap: 6px; min-width: 0; font: 500 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .org :global(.logo) { box-shadow: 0 0 0 1px var(--line); }
  /* a co-hosted event: both marks, the second over the first's edge (as ui/OrgTag) */
  .pair { display: flex; flex: none; }
  .pair :global(.logo + .logo) { margin-left: -5px; box-shadow: 0 0 0 1.5px var(--bg); }
  .org :global(svg) { flex: none; color: var(--accent-text); }
  .org :global(.sv) { color: var(--warning-text); } /* saved: the themed amber */
  .title { font: 700 var(--fs-card)/1.22 var(--font-text); letter-spacing: -0.01em; }
  .cancelled .title { text-decoration: line-through; color: var(--text-2); }
  .meta { display: flex; flex-wrap: wrap; gap: 2px 12px; min-width: 0; font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .meta span { display: inline-flex; align-items: center; gap: 5px; min-width: 0; }
  .meta :global(svg) { flex: none; color: var(--text-3); }
  .sub { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .sub:empty { display: none; }
  .fr { display: flex; align-items: center; gap: 6px; min-width: 0; font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .av { flex: none; display: flex; }
  .av :global(.av + .av) { margin-left: -5px; }
  .av :global(.av) { box-shadow: 0 0 0 1.5px var(--bg); }

  /* a class: its times in the covers' column, the room at the row's end */
  .cl { min-height: 56px; padding: 8px 0; cursor: pointer; }
  .cl.past, .cl.skip { opacity: 0.5; }
  .cl.skip .cl-s b { text-decoration: line-through; }
  /* the class on now: its times in the accent, what's left, a thin line of how far it's gone under the text */
  .cl.live .cl-t b { color: var(--accent-text); }
  .soon { font-weight: 600; color: var(--accent-text); }
  .prog { position: absolute; left: 90px; bottom: 0; height: 2px; border-radius: var(--r-full); background: var(--grad-accent); }
  .cl-t { flex: none; width: 76px; display: flex; flex-direction: column; align-items: center; gap: 3px; font: 500 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }
  .cl-t b { font: 600 var(--fs-body)/1 var(--font-text); color: var(--text); }
  .cl-s { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .cl-s b { font: 600 var(--fs-body)/1.25 var(--font-text); }
  .cl-s small { font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .cl-k { font-style: normal; }
  .cl-k.lecture { color: var(--accent-text); }
  .cl-k.practice { color: var(--success-text); }
  .cl-k.lab { color: var(--warning-text); }
  .cl-r { flex: none; max-width: 42%; font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  /* a room in the main building opens the map on its floor; the dorm and the second building open 2GIS */
  .cl-r.on { display: flex; justify-content: flex-end; }
  .cl-r.on :global(.btn) { max-width: 100%; }
  .free { padding: 6px 0 0 90px; }

  .ask { margin-top: 20px; }
  .ask p { margin: 8px 0 0; text-align: center; color: var(--text-3); }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
