<script lang="ts">
  // A day is one card, one timeline: events and the optional timetable's classes by start time (owner, Nov 19).
  import Clock from '@lucide/svelte/icons/clock';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import MapIcon from '@lucide/svelte/icons/map';
  import Play from '@lucide/svelte/icons/play';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import Images from '@lucide/svelte/icons/images';
  import Newspaper from '@lucide/svelte/icons/newspaper';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import Bookmark from '@lucide/svelte/icons/bookmark';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import { onMount, tick } from 'svelte';
  import type { ClassItem, EventCard, Post } from '../../lib/api';
  import { data, skipped, classKey, skipClass, prefetchEvent } from '../../lib/state/data.svelte';
  import { session, kriCorner } from '../../lib/state/session.svelte';
  import { sheets, openMapFrom, irisFrom } from '../../lib/state/sheets';
  import { ui, toTickets } from '../../lib/state/ui.svelte';
  import { t, money, placeOf, subjectOf, friendsLine } from '../../lib/i18n/index.svelte';
  import { lessonKind } from '../../lib/i18n/subjects';
  import { dayNo, nowTs, parts, weekday, dayMonth, OFFSET, soon, time, dateInput, multiDay, daySpan } from '../../lib/time';
  import { byStart, classesOn, classesLeft } from '../../lib/classes';
  import { noClasses } from '../../lib/academic';
  import { floorOf, atDorm, DORM_2GIS, atBldg2, bldg2Room, BLDG2_2GIS, awayOf } from '../../lib/map';
  import { openLink, haptic } from '../../lib/tg';
  import { castingOn, tagName } from '../../lib/posts';
  import CastingCard from '../../ui/CastingCard.svelte';
  import { nameOf, shortOf } from '../../lib/short';
  import { inner } from '../../lib/perms';
  import Poster from '../../ui/Poster.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
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
  import StatRow from '../../ui/StatRow.svelte';
  import ActionCard from '../../ui/ActionCard.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import StoryRow from './StoryRow.svelte';
  import PullSearch from '../../ui/PullSearch.svelte';
  import { hit as orgHit } from '../../lib/clubs';
  import { hit, namesOf } from '../../lib/search';
  import GalleryCard from './GalleryCard.svelte';

  const TIMETABLE = 'kbtu.afisha.classes';
  let showClasses = $state((() => { try { return localStorage.getItem(TIMETABLE) !== 'hidden'; } catch { return true; } })());
  function toggleClasses() {
    haptic.tap();
    showClasses = !showClasses;
    try { localStorage.setItem(TIMETABLE, showClasses ? 'shown' : 'hidden'); } catch { /* blocked */ }
  }

  let openPost = $state(false);

  // the clock: a minute is enough for "21 min left"; moves on at midnight (the app can stay open overnight)
  let now = $state(nowTs());
  onMount(() => { const id = setInterval(() => (now = nowTs()), 30_000); return () => clearInterval(id); });
  const today = $derived(dayNo(now));
  const dayTs = (d: number) => d * 86400 - OFFSET; // start of local day d as a UTC timestamp
  const endOf = (e: EventCard) => e.endsAt ?? e.startsAt + 3 * 3600;

  const featured = $derived(data.posts.find((p) => p.featured));
  const shown = $derived(data.events.filter((e) => e.status !== 'cancelled'));

  type Item = { key: string; at: number } & ({ c: ClassItem; end: number } | { e: EventCard } | { p: Post });
  const classesOf = (d: number): Item[] => classesOn(data.schedule, d).map((x) => ({ key: classKey(d, x.c), at: x.b, end: x.e, c: x.c }));
  // an event of several days that began earlier and still runs sits on today (a casting, 2-12 Nov). Its ids as one string:
  // the days below follow the date and this, not the 30 s clock (every tick rebuilt all the days and re-rendered every row)
  const running = $derived(data.events.filter((e) => dayNo(e.startsAt) < today && endOf(e) > now).map((e) => e.id).join());
  const days = $derived.by(() => {
    const by = new Map<number, Item[]>(), on = new Set(running.split(',').map(Number));
    for (const e of data.events) { const d = Math.max(dayNo(e.startsAt), on.has(e.id) ? today : -1); if (d < today) continue; if (!by.has(d)) by.set(d, []); by.get(d)!.push({ key: 'e' + e.id, at: e.startsAt, e }); }
    // an offline casting isn't an event (no sign-up) but it has its hour: on its day, or on today while it runs (owner, Nov 9)
    for (const p of data.castings) { if (!p.casting || !castingOn(p.casting, nowTs())) continue; const d = Math.max(dayNo(p.casting.from), today); if (!by.has(d)) by.set(d, []); by.get(d)!.push({ key: 'p' + p.id, at: p.casting.from, p }); }
    // the coming week's class days too (the owner missed his Wednesday), later only event days; today's classes stay
    // here too: their rows are where "I won't go" is tapped (and taken back)
    const week = !showClasses ? [] : Array.from({ length: 7 }, (_, i) => today + i).filter((d) => d === today || data.schedule.some((c) => c.weekday === (parts(dayTs(d) + 12 * 3600).wd || 7)));
    const wanted = [...new Set([...week, ...by.keys()])].sort((a, b) => a - b);
    // one card, one timeline: classes and events by start time (owner, Nov 19); an event still running from an earlier
    // day starts before today, so it leads
    return wanted.map((d) => ({ d, items: [...(by.get(d) ?? []), ...(showClasses ? classesOf(d) : [])].sort(byStart) }));
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

  // Opal's one hero: my next event, else the nearest coming one (a real cover first: the hero carries the screen's colour)
  const coming = $derived(shown.filter((e) => endOf(e) > now).sort((a, b) => a.startsAt - b.startsAt));
  const hero = $derived(going[0] ?? coming.find((e) => e.cover || e.video?.poster) ?? coming[0]);
  const heroPic = $derived(!!(hero?.cover || hero?.video?.poster));
  const stats = $derived([
    { label: t('list.statWeek'), value: weekCount, key: true },
    ...(going.length ? [{ label: t('list.statGoing'), value: going.length }] : []), // no "0": shown only when I'm going somewhere
    ...(showClasses && data.schedule.length ? [{ label: t('list.statLeft'), value: left.length }] : []),
  ]);

  // no timetable: the one card that asks for it (after the first load: a returning student never sees it flash)
  const askSched = $derived(data.eventsReady && !!session.me?.student && !data.schedule.length);

  const past = $derived(data.past); // "Past": mine that ended, newest first (the server's order)
  let allPast = $state(false), pastOpen = $state(false);

  // the pull-down search: the events held, upcoming and mine that ended, by title, place or club
  let q = $state('');
  const searching = $derived(!!q.trim());
  // KRI's "My tickets": the search goes, my next event's ticket (the hero) comes into view
  onMount(() => {
    toTickets.fn = () => { q = ''; void tick().then(() => document.querySelector('.tab.on .hero')?.scrollIntoView({ block: 'center', behavior: 'smooth' })); };
    return () => { toTickets.fn = null; };
  });
  const found = $derived(searching ? [...shown, ...past.filter((p) => !shown.some((e) => e.id === p.id))].filter((e) => hit(q, namesOf(e, 'title', 'place')) || orgHit(e.org, q)) : []);

  function head(d: number): [string, string] {
    const w = weekday(dayTs(d) + 12 * 3600);
    if (d === today) return [t('common.today'), w];
    if (d === today + 1) return [t('common.tomorrow'), w];
    return [w.charAt(0).toUpperCase() + w.slice(1), dayMonth(dayTs(d) + 12 * 3600)];
  }
</script>

{#snippet clRow(it: Extract<Item, { c: ClassItem }>)}
                  {@const k = lessonKind(it.c.kind)}
                  <!-- a class: a slim row, its start where the covers are; a tap: "I won't go" (the capsule leaves it out), or back -->
                  {@const isLive = it.key === live?.key}
                  <div class="row cl" class:done={it.end < now} class:skip={skipped.has(it.key)} class:live={isLive}>
                    <button class="hit" aria-label={it.c.begins + '–' + it.c.ends + ' · ' + subjectOf(it.c) + ' · ' + t(skipped.has(it.key) ? 'skip.cancel' : 'skip.ok')} aria-pressed={skipped.has(it.key)} onclick={() => void skipClass(it.key, it.c)}></button>
                    <!-- one thin line between the events (the heroes): start over a small dim end in the covers' column (a double
                         class reads 10:00 / 11:50), subject, kind, room -->
                    <span class="cl-t num"><b>{it.c.begins}</b>{it.c.ends}</span>
                    <!-- the timetable's own name, the same as the capsule's (owner, Nov 2: the short "PE" here, in full there) -->
                    <span class="cl-s"><b class="ellipsis">{subjectOf(it.c)}</b>
                      <small>{#if isLive && live}<span class="soon num">{t('list.nowLeft', { n: Math.max(1, Math.ceil((live.e - now) / 60)) })}</span>
                        {:else if it.key === next?.key && next}<span class="soon num">{t('cap.inMin', { n: Math.ceil((next.b - now) / 60) })}</span>
                        {:else if k}<i class="cl-k {k}">{t(`list.kind.${k}Long`)}</i>{:else if it.c.kind}{it.c.kind}{/if}{#if skipped.has(it.key)}&nbsp;· {t('skip.tag')}{/if}</small></span>
                    {#if isLive && live}<i class="prog" style="width:calc((100% - 90px) * {Math.min(1, (now - live.b) / Math.max(60, live.e - live.b))})"></i>{/if}
                    {#if floorOf(it.c.room) != null}<span class="cl-r on"><Button kind="tinted" size="s" onclick={() => sheets.map(it.c.room!)}>{#snippet icon()}<MapIcon size={14} />{/snippet}{it.c.room}</Button></span>
                    {:else if atBldg2(it.c.room)}<span class="cl-r on" title={it.c.room}><Button kind="tinted" size="s" onclick={() => openLink(BLDG2_2GIS)}>{#snippet icon()}<TwoGisMark size={14} />{/snippet}{[bldg2Room(it.c.room!), t('list.bldg2')].filter(Boolean).join(' · ')}</Button></span>
                    {:else if atDorm(it.c.room)}<span class="cl-r on" title={it.c.room}><Button kind="tinted" size="s" onclick={() => openLink(DORM_2GIS)}>{#snippet icon()}<TwoGisMark size={14} />{/snippet}{t('list.dorm')}</Button></span>
                    {:else if awayOf(it.c.room)}{@const aw = awayOf(it.c.room)!}<span class="cl-r on" title={it.c.room}><Button kind="tinted" size="s" onclick={() => openLink(aw.url)}>{#snippet icon()}<TwoGisMark size={14} />{/snippet}{[t(`list.${aw.k}`), aw.room].filter(Boolean).join(' ')}</Button></span>
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
  {:else if e.school}<Tag tone="neutral">{t('event.schoolOnly', { school: shortOf(e.org) })}</Tag>
  {:else if e.firstYear}<Tag tone="warning">{t('event.firstYear')}</Tag>{/if}
  {#if e.friends.length && !cancelled}
    <span class="fr"><span class="av">{#each e.friends.slice(0, 3) as f (f.id)}<Avatar person={f} size={18} tappable={false} />{/each}</span>
      <span class="ellipsis">{friendsLine(e.friends.map((f) => f.name), over)}</span></span>
  {/if}
{/snippet}

<div class="page scroll stagger opal">
  <PullSearch bind:value={q} placeholder={t('list.search')} />
  <p class="kick">{weekday(dayTs(today) + 12 * 3600)}, {dayMonth(dayTs(today) + 12 * 3600)}</p>
  <header class="hd">
    <span><h1 class="ttl" use:fitTitle use:largeTitle={'afisha'}>{t('common.today')}</h1></span>
    <!-- the map (its home here once KRI took the bar's corner; a guest's corner is the map itself), the Feed full screen, the Gallery, the clubs' news -->
    <span class="tools">
      {#if kriCorner()}<IconButton icon={MapIcon} label={t('map.open')} onclick={openMapFrom} />{/if}
      {#if shown.length}<IconButton icon={Play} label={t('list.inRow')} onclick={(e) => { irisFrom(e); sheets.feed(); }} />{/if}
      <IconButton icon={Images} label={t('gallery.title')} onclick={(e) => { irisFrom(e); sheets.gallery(); }} />
      <IconButton icon={Newspaper} label={t('page.news')} onclick={(e) => { irisFrom(e); sheets.news(); }} />
    </span>
  </header>
  {#if searching}
    <div class="past">
      {#each found as e (e.id)}<EventRow {e} showDate dateLine={dayMonth(e.startsAt)} />
      {:else}<EmptyState inline text={t('clubs.nothing')} />{/each}
    </div>
  {:else}
  <StoryRow />
  {#if showClasses && offToday}<p class="off t-foot">{t('list.dayOff')}</p>{/if}

  {#if hero}
    {@const e = hero}
    {@const mine = e.my?.status === 'going'}
    <!-- the hero: my next event (its ticket and the way there), else the nearest; its cover, or its 3D mark lit on black -->
    <section class="hero" class:pic={heroPic} style="--c:{e.color ?? e.tint}">
      <button class="hit" onpointerdown={() => prefetchEvent(e.id)} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
      {#if heroPic}<Poster item={e} big radius={0} />{:else}<span class="glow"></span><span class="mark"><Emoji name={e.emoji ?? 'sparkles_3d'} size={128} /></span>{/if}
      <div class="shade"></div>
      <div class="hero-tx">
        <span class="when num">{soon(e.startsAt, now)} · {multiDay(e.startsAt, e.endsAt) ? daySpan(e.startsAt, e.endsAt) : time(e.startsAt)}</span>
        <b class="clamp-2">{e.title}</b>
        <span class="where ellipsis">{placeOf(e.place)} · {shortOf(e.org)}{#if e.coHost} × {shortOf(e.coHost)}{/if}</span>
        {#if mine}
          <span class="acts">
            <Button kind="glass" onclick={() => sheets.ticket(e.id)}>{#snippet icon()}<QrCode size={17} />{/snippet}{t('event.ticket')}</Button>
            {#if floorOf(e.place) != null}<Button kind="glass" onclick={() => sheets.map(e.place)}>{#snippet icon()}<MapPin size={17} />{/snippet}{t('route.open')}</Button>{/if}
          </span>
        {:else}<span class="hsub">{@render status(e)}</span>{/if}
      </div>
    </section>
  {/if}
  {#if data.eventsReady}<div class="stats"><StatRow items={stats} /></div>{/if}

  {#if going.length > 1}
    <!-- the rest of my week: one grouped card, a ticket pill at each row's end -->
    <h2 class="sec">{t('list.yours')}</h2>
    <div class="list">
      {#each going.slice(1) as e (e.id)}
        <div class="row mine">
          <button class="hit" onpointerdown={() => prefetchEvent(e.id)} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
          <Poster item={e} size={48} radius={12} />
          <span class="tx"><b class="ellipsis title">{e.title}</b>
            <span class="meta num ellipsis">{soon(e.startsAt, now)} · {multiDay(e.startsAt, e.endsAt) ? daySpan(e.startsAt, e.endsAt) : time(e.startsAt)} · {placeOf(e.place)}</span></span>
          <span class="end"><Button kind="secondary" size="s" onclick={() => sheets.ticket(e.id)}>{#snippet icon()}<QrCode size={15} />{/snippet}{t('event.ticket')}</Button></span>
        </div>
      {/each}
    </div>
  {/if}
  {#if showClasses && askSched}
    <!-- no timetable yet: one card at the top, under my events (owner, Nov 8: an empty "Your events" over this card in
         today's list read as two empty states); no plans at all: no section, the events below are the way on -->
    <div class="ask"><ActionCard icon={CalendarPlus} title={t('sched.cardTitle')} text={t('sched.cardSub')} action={t('sched.cardAdd')} onclick={() => sheets.schedHowTo()} /></div>
  {/if}

  <div class="events-head">
    <h2 class="sec two">{t('list.title')}</h2>
    <label class="cls sw-on">{t('list.classes')}<input type="checkbox" role="switch" checked={showClasses} onchange={toggleClasses} /></label>
  </div>

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
    {#if day.items.length || (showClasses && data.schedule.length)}
      {@const [a, b] = head(day.d)}
      <div class="day">
      <h3 class="dh">{a}<span>&nbsp;/ {b}</span></h3>
      <!-- one timeline: an event's full row, a class's thin one between them -->
      <div class="list">
        {#each day.items as it (it.key)}
          {#if 'c' in it}{@render clRow(it)}
          {:else if 'p' in it}<CastingCard post={it.p} />
          {:else}
            {@const e = it.e}
            <!-- an event: Luma's row; a club's own event shows its team mark by the club -->
            <div class="row" class:cancelled={e.status === 'cancelled'}>
              <button class="hit" onpointerdown={() => prefetchEvent(e.id)} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
              <Poster item={e} size={64} radius={14} dim={e.status === 'cancelled'} />
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
  {#if galleryAt === undefined}<GalleryCard />{/if}

  {#if past.length}
    <!-- where I've been: the events I was signed up for or came to, newest first (their albums, my rating); folded
         into one row until tapped (owner, Nov 15: the main tab is what is ahead) -->
    <div class="pastrow"><Group><Row title={t('list.past')} value={String(past.length)} accessory="disclosure" open={pastOpen} onclick={() => { haptic.select(); pastOpen = !pastOpen; }} /></Group></div>
    {#if pastOpen}
    <div class="past">
      {#each allPast ? past : past.slice(0, 5) as e (e.id)}<EventRow {e} showDate dateLine={dayMonth(e.startsAt)} />{/each}
      {#if past.length > 5 && !allPast}<span class="lnk"><Button kind="plain" size="s" onclick={() => (allPast = true)}>{t('common.more')}</Button></span>{/if}
    </div>
    {/if}
  {/if}

  {#if data.eventsReady && shown.length < 6}
    <!-- the first weeks of the pilot: a short list should read as "more is coming", not as an empty app -->
    <EmptyState icon={Sparkles} title={t('list.moreSoon')} text={t('list.moreSoonText')} action={{ label: t('list.toClubs'), onclick: () => { ui.tab = 'club'; } }} />
  {/if}
  {/if}
  <div class="tail"></div>
</div>

<style>
  /* Opal (design-spec-opal.md): black first, one hero, big left title, near-black cards with a hair rim, grey caps */
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; background: var(--bg); color: var(--text); }
  .hd > span:first-child { min-width: 0; }
  /* the date yields: too narrow for it beside the buttons (320 px, four of them), the buttons take their own line above,
     at the right (wrap-reverse: the second line goes on top, and flex-start is the line's bottom) */
  .hd { display: flex; flex-wrap: wrap-reverse; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 18px; }
  .hd > span:first-child { flex: 1 0 120px; }
  .kick { font: 600 var(--fs-micro)/1.2 var(--font-text); letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-3); margin: 0 0 4px; }
  .ttl { font: 700 var(--fs-title)/1.05 var(--font-display); letter-spacing: -0.04em; }
  .tools { flex: none; display: flex; gap: var(--s-2); margin-left: auto; }
  .off { margin: 12px 4px 0; color: var(--text-2); }
  .pastrow { margin-top: var(--s-4); }
  .pastrow + .past { margin-top: 8px; }
  .past { display: flex; flex-direction: column; gap: 8px; }
  .lnk { align-self: center; }

  .sec { margin: 30px var(--s-1) 12px; font: 700 var(--fs-t3)/1.15 var(--font-display); letter-spacing: -0.02em; }
  .events-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); margin: 34px var(--s-1) 4px; }
  .sec.two { min-width: 0; margin: 0; }
  .cls { flex: none; display: flex; align-items: center; gap: 10px; font: 500 var(--fs-body)/1 var(--font-text); color: var(--text-2); cursor: pointer; }
  /* a day: skipped while off screen (its size remembered once seen); a paint box, so it spans the gutters too (a row's
     press and shadow are never clipped) and takes the heading's top margin itself (inside, it would no longer collapse
     with the one above) */
  .day { margin: 26px calc(-1 * var(--gutter)) 0; padding: 0 var(--gutter); content-visibility: auto; contain-intrinsic-size: auto 360px; }
  .dh { margin: 0 var(--s-1) 10px; font: 700 var(--fs-row)/1.2 var(--font-display); letter-spacing: -0.02em; }
  .dh span { color: var(--text-3); font-weight: 600; }
  .dh span::first-letter { text-transform: none; }
  .hit { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }

  /* the hero: one rich visual, everything else monochrome. A cover; without one the event's 3D mark lit on black */
  .hero { position: relative; height: min(340px, 88vw); overflow: hidden; border-radius: var(--r-xl); background: var(--media);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08), 0 24px 48px -30px var(--c, transparent); transition: transform var(--t-fast) var(--ease); }
  .hero:has(> .hit:active) { transform: scale(0.985); }
  .hero :global(.poster) { position: absolute; inset: 0; }
  .glow { position: absolute; inset: 0; opacity: 0.6; background: radial-gradient(62% 48% at 50% 34%, var(--c), transparent 74%); }
  .mark { position: absolute; left: 50%; top: 32%; transform: translate(-50%, -50%); filter: drop-shadow(0 22px 30px rgba(0, 0, 0, 0.6)); animation: float 6s ease-in-out infinite; }
  @keyframes float { 50% { transform: translate(-50%, calc(-50% - 6px)); } }
  @media (prefers-reduced-motion: reduce) { .mark { animation: none; } }
  .shade { position: absolute; inset: 40% 0 0; background: linear-gradient(transparent, rgba(0, 0, 0, 0.82)); pointer-events: none; }
  .hero:not(.pic) .shade { inset: 50% 0 0; }
  .hero-tx { position: absolute; left: 0; right: 0; bottom: 0; display: flex; flex-direction: column; gap: 4px; padding: var(--s-5); color: var(--on-accent); pointer-events: none; }
  .when { font: 600 var(--fs-micro)/1.2 var(--font-text); letter-spacing: 0.06em; text-transform: uppercase; color: rgba(255, 255, 255, 0.66); }
  .hero-tx b { font: 700 var(--fs-t1)/1.1 var(--font-display); letter-spacing: -0.035em; }
  .where { font: 500 var(--fs-sub)/1.3 var(--font-text); color: rgba(255, 255, 255, 0.66); }
  .acts { position: relative; z-index: 2; display: flex; gap: 8px; margin-top: 12px; pointer-events: auto; }
  .hsub { display: flex; align-items: center; gap: 8px; min-width: 0; margin-top: 6px; }
  .hsub:empty { display: none; }
  .hsub .fr { color: rgba(255, 255, 255, 0.66); }
  .hsub :global(.av) { box-shadow: 0 0 0 1.5px var(--media); }
  .stats { margin: 22px 0 6px; }

  /* the featured post: its own card, the body folded to two lines */
  .pin { margin: 10px 0 0; }
  .pin :global(.card) { display: flex; flex-direction: column; gap: 6px; }
  .pin-top { display: flex; align-items: center; gap: 8px; min-width: 0; font: 500 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .pin b { font: 700 var(--fs-card)/1.25 var(--font-text); }
  .pin-b { font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text-2); }

  /* a day's rows: one grouped card (Opal's), a hairline between them inset to the text */
  .list { display: flex; flex-direction: column; padding: 0 var(--s-4); border-radius: var(--r-group); background: var(--surface); box-shadow: var(--card-rim); }
  .list:empty { display: none; }
  .list > :global(.cc) { margin: 10px 0; background: var(--surface-2); box-shadow: none; }
  .row { position: relative; display: flex; align-items: center; gap: 14px; padding: 14px 0; }
  .row + .row::before { content: ''; position: absolute; top: 0; left: 78px; right: 0; height: 0.5px; background: var(--separator); }
  .row.mine { padding: 10px 0; }
  .row.mine + .row.mine::before { left: 62px; }
  .row :global(.poster) { box-shadow: inset 0 0 0 1px var(--line); transition: transform var(--t-fast) var(--ease); }
  .row:has(> .hit:active) :global(.poster) { transform: scale(0.96); }
  .end { position: relative; z-index: 2; flex: none; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; pointer-events: none; }
  .tx :global(button), .tx :global(a) { pointer-events: auto; }
  .org { display: flex; align-items: center; gap: 6px; min-width: 0; font: 500 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .org :global(.logo) { box-shadow: 0 0 0 1px var(--line); }
  /* a co-hosted event: both marks, the second over the first's edge (as ui/OrgTag) */
  .pair { display: flex; flex: none; }
  .pair :global(.logo + .logo) { margin-left: -5px; box-shadow: 0 0 0 1.5px var(--surface); }
  .org :global(svg) { flex: none; color: var(--accent-text); }
  .org :global(.sv) { color: var(--warning-text); } /* saved: the themed amber */
  .title { font: 700 var(--fs-card)/1.22 var(--font-text); letter-spacing: -0.015em; }
  .cancelled .title { text-decoration: line-through; color: var(--text-2); }
  .meta { display: flex; flex-wrap: wrap; gap: 2px 12px; min-width: 0; font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .meta span { display: inline-flex; align-items: center; gap: 5px; min-width: 0; }
  .meta.ellipsis { display: block; }
  .meta :global(svg) { flex: none; color: var(--text-3); }
  .sub { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .sub:empty { display: none; }
  .fr { display: flex; align-items: center; gap: 6px; min-width: 0; font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .av { flex: none; display: flex; }
  .av :global(.av + .av) { margin-left: -5px; }
  .av :global(.av) { box-shadow: 0 0 0 1.5px var(--surface); }

  /* a class: one thin line between the events; its start in the covers' column, the text on the titles' edge, the room
     at the row's end */
  .cl { min-height: 48px; padding: 6px 0; gap: 14px; cursor: pointer; }
  .cl.done, .cl.skip { opacity: 0.5; } /* "done", not "past": .past is the Past list's column (a finished class stood in a column, Nov 10) */
  .cl.skip .cl-s b { text-decoration: line-through; }
  /* the class on now: its start in the accent (that says "now"), what's left, a thin line of how far it's gone under the text */
  .cl.live .cl-t b { color: var(--accent-text); }
  .soon { font-weight: 600; color: var(--accent-text); }
  .prog { position: absolute; left: 78px; bottom: 0; height: 2px; border-radius: var(--r-full); background: var(--grad-accent); }
  .cl-t { flex: none; width: 64px; display: flex; flex-direction: column; align-items: center; gap: 3px; font: 500 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }
  .cl-t b { font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-2); }
  /* one line: the subject yields (its ellipsis), the kind stays whole and leaves the subject at least 3em */
  .cl-s { flex: 1; min-width: 0; display: flex; align-items: baseline; gap: 6px; container-type: inline-size; }
  .cl-s b { flex: 0 1 auto; min-width: 0; font: 500 var(--fs-body)/1.3 var(--font-text); }
  .cl-s small { flex: none; max-width: calc(100% - 3em - 6px); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  /* a narrow phone (320 px): the subject alone; the live time and its line, the capsule above, say the rest */
  @container (max-width: 120px) { .cl-s small { display: none; } }
  .cl-k { font-style: normal; }
  .cl-k.lecture { color: var(--accent-text); }
  .cl-k.practice { color: var(--success-text); }
  .cl-k.lab { color: var(--warning-text); }
  .cl-r { position: relative; z-index: 2; flex: none; max-width: 42%; font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  /* a room in the main building opens the map on its floor; the dorm and the second building open 2GIS */
  .cl-r.on { display: flex; justify-content: flex-end; }
  .cl-r.on :global(.btn) { max-width: 100%; padding: 0 var(--s-3); } /* a little tighter: the subject's room */
  .free { margin: 0 var(--s-1); color: var(--text-3); }

  .ask { margin-top: 14px; }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
