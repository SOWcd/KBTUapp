<script lang="ts">
  // A day is one card, one timeline: events and the optional timetable's classes by start time.
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
  import Star from '@lucide/svelte/icons/star';
  import X from '@lucide/svelte/icons/x';
  import { onMount, tick, untrack } from 'svelte';
  import { cubicOut } from 'svelte/easing';
  import type { TransitionConfig } from 'svelte/transition';
  import { calm } from '../../ui/fold';
  import type { ChannelFeedPost, ClassItem, EventCard, Media, Post } from '../../lib/api';
  import { channel } from '../../lib/state/channel.svelte';
  import { count } from '../../lib/stats';
  import { lead as leadHero, load as loadHero, rank as rankHero, save as saveHero, shown as heroShown, stale as heroStale, tapped as heroTapped, type Pick as HeroPick } from '../../lib/hero';
  import { data, skipped, classKey, skipClass, prefetchEvent, canAskRating, dismissEventRating, loadMyPast, ratingBusy, rateFromPrompt, toggleGoing, goingBusy } from '../../lib/state/data.svelte';
  import { touchAhead } from '../../lib/touch';
  import { session, kriCorner } from '../../lib/state/session.svelte';
  import { sheets, openMapFrom, irisFrom } from '../../lib/state/sheets';
  import { ui, toTickets, goTab } from '../../lib/state/ui.svelte';
  import { t, tn, money, subjectOf, friendsLine } from '../../lib/i18n/index.svelte';
  import EventPlace from '../../ui/EventPlace.svelte';
  import { lessonKind } from '../../lib/i18n/subjects';
  import { dayNo, nowTs, parts, weekday, weekdayShort, dayMonth, dayMonthShort, OFFSET, soon, time, dateInput, multiDay, daySpan } from '../../lib/time';
  import { byStart, classesOn, classesLeft } from '../../lib/classes';
  import { noClasses } from '../../lib/academic';
  import { floorOf, atDorm, DORM_2GIS, atBldg2, bldg2Room, BLDG2_2GIS, awayOf } from '../../lib/map';
  import { openLink, haptic, inTelegram, tg } from '../../lib/tg';
  import { endOf, keptTickets } from '../../lib/offlineTickets';
  import { castingOn, tagName } from '../../lib/posts';
  import CastingCard from '../../ui/CastingCard.svelte';
  import { nameOf, shortOf } from '../../lib/short';
  import { service } from '../../lib/clubs';
  import { inner, onTeam } from '../../lib/perms';
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
  import ActionCard from '../../ui/ActionCard.svelte';
  import StoryRow from './StoryRow.svelte';
  import PullSearch from '../../ui/PullSearch.svelte';
  import Everything from './Everything.svelte';
  import GalleryCard from './GalleryCard.svelte';
  import Chip from '../../ui/Chip.svelte';
  import { afishaFilter, filterEvents, choices, active, pick, clearFilter } from '../../lib/state/afisha.svelte';
  import { schoolName } from '../../lib/short';

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
  onMount(() => {
    const id = setInterval(() => {
      const next = nowTs();
      if (data.events.some((e) => e.my?.status === 'going' && endOf(e) > now && endOf(e) <= next)) void loadMyPast();
      now = next;
    }, 30_000);
    return () => clearInterval(id);
  });
  const today = $derived(dayNo(now));
  const dayTs = (d: number) => d * 86400 - OFFSET; // start of local day d as a UTC timestamp

  const featured = $derived(data.posts.find((p) => p.featured));
  const shown = $derived(data.events.filter((e) => e.status !== 'cancelled'));
  const filtering = $derived(active(afishaFilter)); // a school or a type chosen (lib/state/afisha): castings step aside

  type Item = { key: string; at: number } & ({ c: ClassItem; end: number } | { e: EventCard } | { p: Post });
  const classesOf = (d: number): Item[] => classesOn(data.schedule, d).map((x) => ({ key: classKey(d, x.c), at: x.b, end: x.e, c: x.c }));
  // an event of several days that began earlier and still runs sits on today (a casting, 2-12 Nov). Its ids as one string:
  // the days below follow the date and this, not the 30 s clock (every tick rebuilt all the days and re-rendered every row)
  const running = $derived(data.events.filter((e) => dayNo(e.startsAt) < today && endOf(e) > now).map((e) => e.id).join());
  // a club's offline casting while its own event is on is one thing (owner, Nov 26): a line inside that event's row
  // (the soonest one it meets), no card of its own. A casting no event of its club meets keeps its card
  const castIn = $derived.by(() => {
    const by = new Map<number, Post>(), at = nowTs();
    for (const p of data.castings) {
      const c = p.casting;
      if (!c || !castingOn(c, at)) continue;
      const e = data.events.filter((x) => x.status !== 'cancelled' && !by.has(x.id) && (x.org.id === p.org.id || x.coHost?.id === p.org.id)
        && x.startsAt < c.to && endOf(x) > Math.max(c.from, at)).sort((a, b) => a.startsAt - b.startsAt)[0];
      if (e) by.set(e.id, p);
    }
    return by;
  });
  function castLine(p: Post, e: EventCard): string {
    const c = p.casting!, until = dayNo(c.to) === dayNo(c.from) ? time(c.to) : `${dayMonthShort(c.to)}, ${time(c.to)}`;
    // begins after the event does and not yet: its own hours; else what's left of it
    const when = c.from > e.startsAt && c.from > nowTs() ? `${t('casting.offline')} · ${time(c.from)}–${until}` : t('casting.inEventTill', { time: until });
    return c.place ? `${when} · ${c.place}` : when;
  }
  const openCast = (p: Post) => sheets.stories([{ org: p.org, items: [{ post: p }], unread: false, cast: false }], 0);
  const days = $derived.by(() => {
    const by = new Map<number, Item[]>(), on = new Set(running.split(',').map(Number)), inside = new Set([...castIn.values()].map((p) => p.id));
    for (const e of filterEvents(data.events, afishaFilter)) { const d = Math.max(dayNo(e.startsAt), on.has(e.id) ? today : -1); if (d < today) continue; if (!by.has(d)) by.set(d, []); by.get(d)!.push({ key: 'e' + e.id, at: e.startsAt, e }); }
    // an offline casting isn't an event (no sign-up) but it has its hour: on its day, or on today while it runs
    for (const p of data.castings) { if (filtering || inside.has(p.id) || !p.casting || !castingOn(p.casting, nowTs())) continue; const d = Math.max(dayNo(p.casting.from), today); if (!by.has(d)) by.set(d, []); by.get(d)!.push({ key: 'p' + p.id, at: p.casting.from, p }); }
    // the coming week's class days too (so a class day isn't missed), later only event days; today's classes stay
    // here too: their rows are where "I won't go" is tapped (and taken back)
    const week = !showClasses ? [] : Array.from({ length: 7 }, (_, i) => today + i).filter((d) => d === today || data.schedule.some((c) => c.weekday === (parts(dayTs(d) + 12 * 3600).wd || 7)));
    const wanted = [...new Set([...week, ...by.keys()])].sort((a, b) => a - b);
    // one card, one timeline: classes and events by start time; an event still running from an earlier
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

  // "Your events": only the events I'm going to this week (a class card there showed the class twice)
  const going = $derived(shown.filter((e) => e.my?.status === 'going' && endOf(e) > now && e.startsAt - now < 7 * 86400).sort((a, b) => a.startsAt - b.startsAt));
  // the class on now comes alive in its own row (what's left, a thin progress line); the next one within the hour says
  // how soon. Read once for all rows: the row only compares its key.
  const left = $derived(classesLeft(data.schedule, now).filter((x) => !skipped.has(classKey(today, x.c))));
  const live = $derived(left[0] && left[0].b <= now ? { key: classKey(today, left[0].c), ...left[0] } : null);
  const next = $derived.by(() => { const x = left.find((y) => y.b > now); return x && x.b - now <= 3600 ? { key: classKey(today, x.c), ...x } : null; });

  // Opal's one hero: my next event, else the nearest coming one (a real cover first: the hero carries the screen's colour)
  const coming = $derived(shown.filter((e) => endOf(e) > now).sort((a, b) => a.startsAt - b.startsAt));
  // the filters (a school, a type) narrow the days below only, on the list held: the chips are what it has
  const chips = $derived(choices(coming, afishaFilter));
  const matched = $derived(filtering ? filterEvents(coming, afishaFilter).length : coming.length);
  // a kept chip past the row's edge (a school at 320 px) comes into view with the tab: never on unseen
  function showPicked(row: HTMLElement) {
    const on = [...row.querySelectorAll<HTMLElement>('[aria-pressed="true"]')].at(-1);
    if (!on) return;
    const over = on.getBoundingClientRect().right - row.getBoundingClientRect().right;
    if (over > 0) row.scrollLeft += over + 16;
  }
  // the hero, personal (owner, Nov 25; lib/hero.ts ranks): from what the app already holds, each kind in its own order:
  // my ticket, where friends go, my clubs' and follows' events, their newest news, the forum's hottest post of the day,
  // my next class, else the nearest event. The first card is the hero; a swipe brings #2 and #3
  type Card = HeroPick & ({ e: EventCard } | { p: Post } | { f: ChannelFeedPost } | { cl: ClassItem; b: number; end: number });
  // ranked by what was learned before this visit: a show or a tap now never reshuffles the cards in view
  const mem = loadHero(), was: typeof mem = JSON.parse(JSON.stringify(mem));
  const myOrgs = $derived(new Set([...(session.me?.memberships ?? []).map((m) => m.org.id), ...data.orgs.filter((o) => o.subscribed).map((o) => o.id)]));
  const heat = (f: ChannelFeedPost) => f.hearts + f.reactions.reduce((n, r) => n + r.n, 0);
  const cands = $derived.by(() => {
    const out: Card[] = [], ev = (kind: Card['kind'], e: EventCard, pin = false) => out.push({ key: 'e' + e.id, kind, e, today: pin });
    for (const e of going) ev('ticket', e, dayNo(e.startsAt) <= today);
    const open = coming.filter((e) => e.status === 'published' && e.my?.status !== 'going');
    for (const e of open.filter((x) => x.friends.length).sort((a, b) => b.friends.length - a.friends.length || a.startsAt - b.startsAt)) ev('friends', e);
    for (const e of open) if (myOrgs.has(e.org.id) || (e.coHost && myOrgs.has(e.coHost.id))) ev('club', e);
    for (const p of (data.news?.posts ?? []).filter((x) => x.createdAt > now - 3 * 86400).sort((a, b) => +a.read - +b.read || b.createdAt - a.createdAt)) out.push({ key: 'p' + p.id, kind: 'news', p });
    if (session.channel) for (const f of (channel.feed ?? []).filter((x) => x.status === 'live' && x.at > now - 86400 && heat(x) > 0).sort((a, b) => heat(b) - heat(a))) out.push({ key: 'f' + f.id, kind: 'forum', f });
    if (left[0]) out.push({ key: classKey(today, left[0].c), kind: 'class', cl: left[0].c, b: left[0].b, end: left[0].e });
    const nx = coming.find((e) => e.cover || e.video?.poster) ?? coming[0];
    if (nx) ev('next', nx);
    return out;
  });
  // the first card is the moment's (lib/hero.ts lead): my ticket starting soon, else today's biggest, else the week's most
  // popular. It follows the 30 s clock and the store, so it changes through the day on its own (crossfaded in the markup)
  const top = $derived.by((): Card | null => { const x = leadHero(shown, now, heroStale(was, today)); return x && { key: 'e' + x.e.id, kind: x.kind, e: x.e }; });
  // the cards seen this visit keep their places: the forum's feed landing later never swaps one under the finger
  let held = $state({ d: 0, keys: [] as string[] });
  const cards = $derived.by(() => {
    const lead = top ? [top] : [], taken = (x: Card) => lead.some((y) => y.key === x.key);
    const keep = held.d === today ? held.keys.map((k) => cands.find((x) => x.key === k)).filter((x): x is Card => !!x && !taken(x)) : [];
    return [...lead, ...keep, ...rankHero(cands.filter((x) => !taken(x) && !keep.some((y) => y.key === x.key)), was, today)].slice(0, 3);
  });
  let at = $state(0); // the card in view
  const atCard = $derived(Math.min(at, cards.length - 1));
  $effect(() => {
    const i = atCard, c = cards[i];
    if (!c || !data.eventsReady || searching || ui.tab !== 'afisha') return;
    untrack(() => {
      // the lead isn't held (the clock moves it): a new one never shifts the swiped-to cards under the finger
      const from = top ? 1 : 0;
      if (held.d !== today || held.keys.length < i + 1 - from) held = { d: today, keys: cards.slice(from, i + 1).map((x) => x.key) };
      if (heroShown(mem, c, today, i === 0)) { count(`hero.show.${c.kind}`); saveHero(mem); }
    });
  });
  function tap(c: Card) {
    if (heroTapped(mem, c, today)) count(`hero.tap.${c.kind}`);
    saveHero(mem);
  }
  // a new lead fades in on top; the old one stays whole under it as long, then goes (a plain crossfade dipped to the ground)
  const into = (_: Element): TransitionConfig => ({ duration: calm() ? 0 : 420, easing: cubicOut, css: (k) => `opacity: ${k}; z-index: 1` });
  const under = (_: Element): TransitionConfig => ({ duration: calm() ? 0 : 420, css: () => 'z-index: 0' });
  function slid(ev: Event) {
    const el = ev.currentTarget as HTMLElement, a = el.children[0] as HTMLElement, b = el.children[1] as HTMLElement | undefined;
    at = b ? Math.round(el.scrollLeft / (b.offsetLeft - a.offsetLeft)) : 0; // one card's step
  }
  // my soonest ticket as the hero: "Your events" below holds the rest; another card leads: all of them
  const leadEv = $derived(cards[0] && 'e' in cards[0] && cards[0].e.my?.status === 'going' ? cards[0].e.id : null);
  const rest = $derived(going.filter((e) => e.id !== leadEv));
  type Look = { item: { cover: Media | null; emoji: string; color: null }; color: string; title: string; lead: string; line: string; by: string; room: string | null; open: () => void };
  // a card that isn't an event, in the hero's own markup: its picture or a 3D mark on the accent, a title, one line
  function look(c: Exclude<Card, { e: EventCard }>): Look {
    const when = (ts: number) => (dayNo(ts) === today ? time(ts) : dayMonth(ts));
    if ('p' in c) {
      const p = c.p;
      return { item: { cover: p.photo, emoji: p.org.emoji, color: null }, color: p.photo?.color ?? 'var(--accent)', title: p.title || p.body, lead: '',
        line: t('page.news') + ' · ' + when(p.createdAt), by: shortOf(p.org), room: null, open: () => sheets.news() };
    }
    if ('f' in c) {
      const f = c.f;
      return { item: { cover: f.photos[0] ?? null, emoji: 'speech_balloon_3d', color: null }, color: f.photos[0]?.color ?? 'var(--accent)', title: f.body, lead: '',
        line: t('tab.forum') + ' · ' + when(f.at), by: '', room: null, open: () => { channel.focus = f.id; goTab('forum'); } };
    }
    const x = c, live = x.b <= now;
    return { item: { cover: null, emoji: 'books_3d', color: null }, color: 'var(--accent)', title: subjectOf(x.cl), lead: x.cl.begins + '–' + x.cl.ends,
      line: [live ? t('list.nowLeft', { n: Math.max(1, Math.ceil((x.end - now) / 60)) }) : soon(x.b, now), x.cl.room].filter(Boolean).join(' · '), by: '',
      room: floorOf(x.cl.room) != null ? x.cl.room : null, open: () => sheets.week() };
  }
  // one tap signs up from the hero when there is nothing to ask first that this card can't say: a plain open event
  // (the sheet's own rule is longer: a partner's link, a guest list, a club's own event keep the whole-card tap)
  const canGo = (e: EventCard) => e.status === 'published' && (!e.my || e.my.status === 'cancelled') && e.startsAt > now && !(e.regUntil && e.regUntil <= now)
    && !e.externalUrl && !e.guestHost && !e.guestList && !inner(e) && !e.santa && !(e.seats != null && e.taken >= e.seats) && !onTeam(e, session.me?.memberships);
  // the week at a glance, in place of the lone counters: seven days from today, a dot where something is on (the accent:
  // I'm going), a tap goes to that day's card. Built from the days above: nothing is read twice
  const strip = $derived(Array.from({ length: 7 }, (_, i) => {
    const d = today + i, ev = days.find((x) => x.d === d)?.items.filter((x) => 'e' in x) ?? [];
    return { d, on: days.some((x) => x.d === d && (x.items.length || (showClasses && data.schedule.length))), n: ev.length, mine: ev.some((x) => 'e' in x && x.e.my?.status === 'going') };
  }));
  async function toDay(d: number) {
    haptic.select();
    // its rows drawn first, only as far as that day (the list draws a few days per idle moment)
    upto = Math.max(upto, days.slice(0, days.findIndex((x) => x.d === d) + 1).reduce((n, x) => n + x.items.length, 0));
    await tick();
    document.querySelector(`.tab.on .day[data-d="${d}"]`)?.scrollIntoView({ block: 'start', behavior: 'smooth' });
  }

  // no timetable: the one card that asks for it (after the first load: a returning student never sees it flash)
  const askSched = $derived(data.scheduleReady && !!session.me?.student && !data.schedule.length);
  // opened without the network: my kept tickets first, their QR ready for the door (lib/offlineTickets)
  // (with the clock: a ticket whose event ends while the app stays open offline leaves within 30 s)
  const kept = $derived(data.offline ? keptTickets(inTelegram ? tg.user?.id : session.me?.tg.id, now) : []);

  const past = $derived(data.past); // "Past": the last month's Afisha events, mine marked, newest first (the server's order)
  let allPast = $state(false), pastOpen = $state(false);
  // Pick one prompt at a time, including events that finish while this tab is still open.
  const ratePrompt = $derived.by(() => {
    if (!session.me?.student) return;
    const events = new Map([...data.events, ...past, ...(data.myPast ?? [])].map((e) => [e.id, e]));
    return [...events.values()].filter((e) => canAskRating(e, now)).sort((a, b) => endOf(b) - endOf(a))[0];
  });

  // the pull-down search: the app's global one (events, clubs, people, news, the forum, places, subjects)
  let q = $state('');
  const searching = $derived(!!q.trim());
  // KRI's "My tickets": the search goes, my next event's ticket (the hero) comes into view
  onMount(() => {
    toTickets.fn = () => { q = ''; void tick().then(() => (document.querySelector('.tab.on .tix') ?? document.querySelector('.tab.on .heroes'))?.scrollIntoView({ block: 'center', behavior: 'smooth' })); };
    return () => { toTickets.fn = null; };
  });
  // the global search's events: the upcoming ones held, then the last month's that ended (screens/afisha/Everything)
  const searchable = $derived(searching ? [...shown, ...past.filter((p) => !shown.some((e) => e.id === p.id))] : []);

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
                    <!-- the timetable's own name, the same as the capsule's (the short "PE" here, in full there) -->
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
  {:else if e.firstYear}<Tag tone="warning">{t('event.firstYear')}</Tag>
  {:else if service(e.org)}<Tag tone="neutral">{t('clubs.office')}</Tag>{/if}
  {#if e.friends.length && !cancelled}
    <span class="fr"><span class="av">{#each e.friends.slice(0, 3) as f (f.id)}<Avatar person={f} size={18} tappable={false} />{/each}</span>
      <span class="ellipsis">{friendsLine(e.friends.map((f) => f.name), over)}</span></span>
  {/if}
{/snippet}

<!-- one hero card, any kind: the lead's slot (i 0) and the swiped-to ones -->
{#snippet heroCard(c: Card, i: number)}
  {#if 'e' in c}
    {@const e = c.e}
    {@const mine = e.my?.status === 'going'}
    <!-- an event: my ticket and the way there, else what it is and one tap to go -->
    <section class="hero" class:tix={mine && i === 0} class:nopic={!(e.cover || e.video?.poster)} style:--c={e.cover?.color ?? e.video?.poster?.color ?? e.color ?? e.tint} onclickcapture={() => tap(c)}>
      <button class="hit" onpointerdown={(ev) => touchAhead(ev, () => prefetchEvent(e.id))} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
      <span class="art"><Poster item={e} big radius={0} /></span>
      <div class="shade"></div>
      <div class="slab glass glass-sheet">
        <span class="hero-tx">
          <b class="clamp-2">{e.title}</b>
          <span class="where"><span class="ellipsis"><b class="num">{multiDay(e.startsAt, e.endsAt) ? daySpan(e.startsAt, e.endsAt) : time(e.startsAt)}</b> · {soon(e.startsAt, now)}</span><span class="by ellipsis">&nbsp;· {shortOf(e.org)}{#if e.coHost} × {shortOf(e.coHost)}{/if}</span></span>
          <span class="hero-place"><EventPlace {e} pin /></span>
          {#if !mine}<span class="hsub">{@render status(e)}</span>{/if}
        </span>
        <!-- under the thumb, at the slab's end: my ticket, or one tap to sign up -->
        {#if mine}
          <span class="acts">
            <IconButton kind="tinted" size="s" icon={QrCode} label={t('event.ticket')} onclick={() => sheets.ticket(e.id)} />
          </span>
        {:else if e.my?.status === 'hold'}
          <span class="acts"><Button kind="tinted" size="s" onclick={() => sheets.pay(e.id)}>{t('event.pay', { price: money(e.price ?? 0) })}</Button></span>
        {:else if canGo(e)}
          <span class="acts"><Button kind="tinted" size="s" loading={goingBusy.has(e.id)} onclick={() => toggleGoing(e.id, () => sheets.pay(e.id))}>{e.price ? e.freeLeft && session.me?.student?.freeFirst ? t('event.goFree') : t('event.goPrice', { price: money(e.price) }) : t('event.go')}</Button></span>
        {/if}
      </div>
      <span class="rim" aria-hidden="true"></span>
    </section>
  {:else}
    {@const v = look(c)}
    <!-- news, a forum post, my next class: the same card, its picture or a 3D mark, the title and one line -->
    <section class="hero" class:nopic={!v.item.cover} style:--c={v.color} onclickcapture={() => tap(c)}>
      <button class="hit" onclick={v.open} aria-label={v.title}></button>
      <span class="art"><Poster item={v.item} big radius={0} /></span>
      <div class="shade"></div>
      <div class="slab">
        <span class="hero-tx">
          <b class="clamp-2">{v.title}</b>
          <span class="where"><span class="ellipsis">{#if v.lead}<b class="num">{v.lead}</b> · {/if}{v.line}</span>{#if v.by}<span class="by ellipsis">&nbsp;· {v.by}</span>{/if}</span>
        </span>
        {#if v.room}{@const room = v.room}<span class="acts"><IconButton kind="secondary" size="s" icon={MapPin} label={t('route.open')} onclick={() => sheets.map(room)} /></span>{/if}
      </div>
      <span class="rim" aria-hidden="true"></span>
    </section>
  {/if}
{/snippet}

<div class="page scroll stagger">
  <PullSearch bind:value={q} placeholder={t('list.search')} />
  <header class="hd">
    <span><h1 class="ttl" use:fitTitle use:largeTitle={'afisha'}>{t('common.today')}</h1></span>
    <!-- the map (its home here once KRI took the bar's corner; a guest's corner is the map itself), the Feed full screen, the Gallery, the clubs' news -->
    <span class="tools">
      {#if kriCorner()}<IconButton icon={MapIcon} size="s" label={t('map.open')} onclick={openMapFrom} />{/if}
      {#if shown.length}<IconButton icon={Play} size="s" label={t('list.inRow')} onclick={(e) => { irisFrom(e); sheets.feed(); }} />{/if}
      <IconButton icon={Images} size="s" label={t('gallery.title')} onclick={(e) => { irisFrom(e); sheets.gallery(); }} />
      <IconButton icon={Newspaper} size="s" label={t('page.news')} onclick={(e) => { irisFrom(e); sheets.news(); }} />
    </span>
  </header>
  <p class="date" use:fitTitle={20}>{weekday(dayTs(today) + 12 * 3600)}, {dayMonth(dayTs(today) + 12 * 3600)}</p>
  {#if data.eventsReady && weekCount}<p class="kick">{tn('list.week', weekCount)}</p>{/if}
  {#if kept.length}{#await import('../../ui/OfflineTickets.svelte') then m}<div class="offline"><m.default tickets={kept} /></div>{/await}{/if}
  {#if searching}
    <Everything {q} events={searchable} />
  {:else}
  {#if ratePrompt && !ratingBusy.has(ratePrompt.id)}
    {@const e = ratePrompt}
    <div class="rate-prompt">
      <Card>
        <div class="rate-head">
          <div><h2 class="t-body">{t('rate.ask')}</h2><p class="t-foot clamp-2">{e.title}</p></div>
          <IconButton icon={X} label={t('rate.dismiss')} kind="plain" onclick={() => void dismissEventRating(e.id)} />
        </div>
        <div class="rate-stars" role="group" aria-label={t('rate.ask')}>
          {#each [1, 2, 3, 4, 5] as score (score)}
            <button type="button" aria-label={t('rate.score', { n: score })} onclick={() => void rateFromPrompt(e.id, score)}><Star size={23} /></button>
          {/each}
        </div>
      </Card>
    </div>
  {/if}
  <StoryRow />
  {#if showClasses && offToday}<p class="off t-foot">{t('list.dayOff')}</p>{/if}

  {#if cards.length}
    <!-- the hero, personal: the first card, a swipe brings #2 and #3 (snapped); one markup for every kind -->
    <div class="heroes" role="group" aria-label={t('list.heroPicks')} onscroll={slid}>
    {#each cards as c, i (i ? c.key : '')}
      {#if i}{@render heroCard(c, i)}
      {:else}
        <!-- the lead's slot stays put; a new lead fades in over the old in the same cell (no jump, no dip to the ground) -->
        <div class="lead">{#key c.key}<div class="face" in:into out:under>{@render heroCard(c, 0)}</div>{/key}</div>
      {/if}
    {/each}
    </div>
    {#if cards.length > 1}<div class="dots" aria-hidden="true">{#each cards as c, i (c.key)}<i class={{ on: i === atCard }}></i>{/each}</div>{/if}
  {/if}
  {#if data.eventsReady && days.length}
    <nav class="week" aria-label={t('list.title')}>
      {#each strip as w (w.d)}
        {@const ts = dayTs(w.d) + 12 * 3600}
        <button class={['wd', { today: w.d === today, has: w.n }]} disabled={!w.on} aria-label={weekday(ts) + ', ' + dayMonth(ts) + (w.n ? ' · ' + w.n : '')} onclick={() => void toDay(w.d)}>
          <span>{weekdayShort(ts)}</span><b class="num">{parts(ts).d}</b><i class={{ on: w.mine }}></i>
        </button>
      {/each}
    </nav>
  {/if}

  {#if rest.length}
    <!-- the rest of my week (all of it when another card leads): one grouped card, a ticket pill at each row's end -->
    <h2 class="sec">{t('list.yours')}</h2>
    <div class="list" class:tix={leadEv == null}>
      {#each rest as e (e.id)}
        <div class="row mine">
          <button class="hit" onpointerdown={(ev) => touchAhead(ev, () => prefetchEvent(e.id))} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
          <Poster item={e} size={48} radius={12} />
          <span class="tx"><b class="ellipsis title">{e.title}</b>
            <span class="meta num"><span>{soon(e.startsAt, now)} · {multiDay(e.startsAt, e.endsAt) ? daySpan(e.startsAt, e.endsAt) : time(e.startsAt)}</span><EventPlace {e} pin /></span></span>
          <span class="end"><Button kind="secondary" size="s" onclick={() => sheets.ticket(e.id)}>{#snippet icon()}<QrCode size={15} />{/snippet}{t('event.ticket')}</Button></span>
        </div>
      {/each}
    </div>
  {/if}
  {#if showClasses && askSched}
    <!-- no timetable yet: one card at the top, under my events (an empty "Your events" over this card in
         today's list read as two empty states); no plans at all: no section, the events below are the way on -->
    <div class="ask"><ActionCard icon={CalendarPlus} title={t('sched.cardTitle')} action={t('sched.cardAdd')} onclick={() => sheets.schedHowTo()} /></div>
  {/if}

  <div class="events-head">
    <h2 class="sec two">{t('list.title')}</h2>
    <!-- no timetable: nothing to show or hide (kept while off: switching it back on brings the card that asks for one) -->
    {#if data.schedule.length || !showClasses}<label class="cls sw-on">{t('list.classes')}<input type="checkbox" role="switch" checked={showClasses} onchange={toggleClasses} /></label>{/if}
  </div>
  {#if filtering || coming.length > 1}
    <div class="chips" role="group" aria-label={t('list.f.label')} use:showPicked>
      {#each chips.types as k (k)}<Chip selected={afishaFilter.type === k} onclick={() => { haptic.select(); count('do.filter'); pick('type', k); }}>{t(`list.f.${k}`)}</Chip>{/each}
      {#if chips.types.length && chips.schools.length}<i class="sep" aria-hidden="true"></i>{/if}
      {#each chips.schools as s (s)}<Chip selected={afishaFilter.school === s} onclick={() => { haptic.select(); count('do.filter'); pick('school', s); }}>{schoolName(s)}</Chip>{/each}
    </div>
  {/if}
  {#if filtering && !matched}
    <div class="none"><EmptyState title={t('list.f.none')} action={{ label: t('list.f.all'), onclick: () => { haptic.select(); clearFilter(); } }} /></div>
  {/if}

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
      <div class="day" data-d={day.d}>
      <h3 class="dh">{a}<span>&nbsp;/ {b}</span></h3>
      <!-- one timeline: an event's full row, a class's thin one between them -->
      <div class="list">
        {#each day.items as it (it.key)}
          {#if 'c' in it}{@render clRow(it)}
          {:else if 'p' in it}<CastingCard post={it.p} />
          {:else}
            {@const e = it.e}
            {@const cast = castIn.get(e.id)}
            <!-- an event: Luma's row; a club's own event shows its team mark by the club -->
            <div class="row" class:cancelled={e.status === 'cancelled'}>
              <button class="hit" onpointerdown={(ev) => touchAhead(ev, () => prefetchEvent(e.id))} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
              <Poster item={e} size={64} radius={14} dim={e.status === 'cancelled'} />
              <span class="tx">
                <span class="org">{#if e.coHost}<span class="pair"><OrgLogo org={e.org} size={16} /><OrgLogo org={e.coHost} size={16} /></span><span class="ellipsis">{nameOf(e.org)} × {nameOf(e.coHost)}</span>{:else}<OrgLogo org={e.org} size={16} /><span class="ellipsis">{nameOf(e.org)}</span>{/if}{#if inner(e)}<UsersRound size={13} strokeWidth={2.2} />{/if}{#if e.saved && e.status !== 'cancelled'}<Bookmark class="sv" size={13} strokeWidth={2.4} fill="currentColor" aria-label={t('event.saved')} />{/if}</span>
                <b class="clamp-2 title">{e.title}</b>
                <span class="meta num">
                  <span><Clock size={14} strokeWidth={1.75} />{multiDay(e.startsAt, e.endsAt) ? daySpan(e.startsAt, e.endsAt) : time(e.startsAt)}</span>
                  <EventPlace {e} pin />
                  {#if e.price}<span>{money(e.price)}</span>{/if}
                </span>
                {#if cast}<button class="cast ellipsis" onclick={() => openCast(cast)}>{castLine(cast, e)}</button>{/if}
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
    <!-- what happened on campus: the last month's events, newest first, the ones I was at marked (their albums, my
         rating); folded into one row until tapped (owner, Nov 15: the main tab is what is ahead) -->
    <div class="pastrow"><Group><Row title={t('list.past')} value={String(past.length)} accessory="disclosure" open={pastOpen} onclick={() => { haptic.select(); pastOpen = !pastOpen; if (pastOpen) count('do.past'); }} /></Group></div>
    {#if pastOpen}
    <div class="past">
      {#each allPast ? past : past.slice(0, 5) as e (e.id)}<EventRow {e} showDate dateLine={dayMonth(e.startsAt)} wasThere />{/each}
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
  .hd { display: flex; flex-wrap: wrap-reverse; align-items: center; justify-content: space-between; gap: var(--s-3); }
  .hd > span:first-child { flex: 1 0 120px; }
  /* a headline of two lines in two weights (display type): the day, then its date, light; the week's count is a quiet line under them */
  .ttl { font: 600 var(--fs-title)/1.06 var(--font-display); letter-spacing: -0.045em; }
  .date { margin-bottom: var(--s-5); white-space: nowrap; font: var(--fw-light) var(--fs-title)/1.1 var(--font-display); letter-spacing: -0.045em; color: var(--text-3); }
  .date:has(+ .kick) { margin-bottom: var(--s-1); }
  .kick { margin: 0 0 var(--s-5); font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .offline { margin-bottom: var(--s-6); }
  .tools { flex: none; display: flex; gap: var(--s-3); margin-left: auto; }
  .rate-prompt { margin-bottom: var(--s-3); }
  .rate-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); }
  .rate-head > div { min-width: 0; }
  .rate-head h2 { font-weight: 600; }
  .rate-head p { margin-top: 2px; color: var(--text-2); overflow-wrap: anywhere; }
  .rate-stars { display: grid; grid-template-columns: repeat(5, 1fr); gap: var(--s-1); margin-top: var(--s-2); }
  .rate-stars button { display: grid; place-items: center; min-height: var(--tap); border-radius: var(--r-m); background: var(--fill); color: var(--warning-text); }
  .rate-stars button:active { transform: scale(0.94); }
  .off { margin: var(--s-3) var(--s-1) 0; color: var(--text-2); }
  .pastrow { margin-top: var(--s-4); }
  .pastrow + .past { margin-top: 8px; }
  .past { display: flex; flex-direction: column; gap: 8px; }
  .lnk { align-self: center; }

  .sec { margin: var(--s-7) var(--s-1) var(--s-3); font: var(--fw-light) var(--fs-t1)/1.1 var(--font-display); letter-spacing: -0.04em; }
  .events-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); min-height: var(--tap); margin: var(--s-7) var(--s-1) 0; padding-top: var(--s-5); box-shadow: inset 0 0.5px 0 var(--separator); } /* a hairline, then the section's light title */
  .sec.two { min-width: 0; margin: 0; }
  /* the filters: one row of chips under the heading, scrolled sideways edge to edge; types, a hairline, schools */
  .chips { display: flex; align-items: center; gap: var(--s-2); overflow-x: auto; margin: var(--s-2) calc(-1 * var(--gutter)) 0; padding: var(--s-1) var(--gutter); scrollbar-width: none; }
  .chips::-webkit-scrollbar { display: none; }
  .sep { flex: none; width: 0.5px; height: 20px; background: var(--separator); }
  .none { margin-top: var(--s-4); }
  .cls { flex: none; display: flex; align-items: center; gap: 10px; font: 500 var(--fs-body)/1 var(--font-text); color: var(--text-2); cursor: pointer; }
  /* a day: skipped while off screen (its size remembered once seen); a paint box, so it spans the gutters too (a row's
     press and shadow are never clipped) and takes the heading's top margin itself (inside, it would no longer collapse
     with the one above) */
  .day { margin: var(--s-6) calc(-1 * var(--gutter)) 0; padding: 0 var(--gutter); scroll-margin-top: var(--page-top); content-visibility: auto; contain-intrinsic-size: auto 360px; }
  .dh { margin: 0 var(--s-1) 10px; font: 600 var(--fs-row)/1.2 var(--font-display); letter-spacing: -0.025em; }
  .dh span { color: var(--text-3); font-weight: var(--fw-light); }
  .dh span::first-letter { text-transform: none; }
  .hit { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }

  /* the hero: the one rich visual, kept calm (owner, Nov 22: the blurred cover and the circling light read as
     childish). The cover sharp edge to edge, a little dimmed, and most of the card (owner, Nov 24); the words on
     a low slab of the app's own sheet glass along the bottom (base.css .glass-sheet: the sheets' and menus' family; it
     follows the theme and stays legible whatever the cover is): the title, one line of when and where, and my ticket and the way
     there as two round icons at its end. No drop shadow of its own: the halo is the card's light */
  .hero { --halo: 0.62; position: relative; isolation: isolate; display: flex; flex-direction: column; justify-content: flex-end; min-height: 196px; padding: 72px 6px 6px; /* the picture always keeps its strip, a two-line title under it too */
    border-radius: var(--r-xl); background: var(--media); transition: transform var(--t-fast) var(--ease); }
  .hero:has(> .hit:active) { transform: scale(0.985); }
  /* the hero's cards side by side, one in view, snapped; edge to edge so the next one waits just past the gutter. A
     scroller clips, so it leaves room around the cards for their light (the glow reaches 44px under a card) and takes it
     back with its margins */
  .heroes { display: flex; gap: var(--s-3); overflow-x: auto; overscroll-behavior-x: contain; scroll-snap-type: x mandatory; scrollbar-width: none;
    margin: calc(-1 * var(--s-4)) calc(-1 * var(--gutter)) -44px; padding: var(--s-4) 0 44px var(--gutter); }
  .heroes::-webkit-scrollbar { display: none; }
  .heroes::after { content: ''; flex: 0 0 calc(var(--gutter) - var(--s-3)); } /* the end's gutter (a scroller's end padding is lost in older WebKit) */
  /* 100% here is the scroller's box minus its left padding: the page's width plus one gutter, so a card takes one gutter
     less and snaps to its start inside the gutter (centre snapping pushed it past both edges) */
  .heroes { scroll-padding-inline: var(--gutter); }
  .heroes > .hero, .lead { flex: 0 0 calc(100% - var(--gutter)); min-width: 0; scroll-snap-align: start; scroll-snap-stop: always; } /* min-width: a flex item never shrinks below its content (the one-line meta) unless told: the card grew past the edge */
  /* the lead's slot: one grid cell the old and the new card share while they crossfade, so the row never moves; minmax(0):
     the cell, like the card, never grows to the meta's width */
  .lead { display: grid; grid-template-columns: minmax(0, 1fr); }
  .face { grid-area: 1 / 1; display: flex; min-width: 0; }
  .face > .hero { flex: 1; min-width: 0; }
  .dots { display: flex; justify-content: center; gap: 6px; margin-top: var(--s-3); }
  .dots i { width: 6px; height: 6px; border-radius: var(--r-full); background: var(--text-3); opacity: 0.45; transition: opacity var(--t-fast) var(--ease); }
  .dots i.on { opacity: 1; }
  /* Opal's neon under the card, in the cover's own colour (--c): a close halo and a wide pool below. It blooms once as
     the page opens and rests; the shadow is painted once and only its opacity moves. The card no longer clips (the
     cover does), so the light can leave it */
  .hero::before { content: ''; position: absolute; inset: 0; z-index: -1; border-radius: inherit; pointer-events: none; opacity: var(--halo);
    box-shadow: 0 0 14px 0 var(--c, transparent), 0 16px 38px -10px var(--c, transparent); animation: bloom 2.2s var(--ease) 0.2s backwards; }
  /* the halo always shows against the theme (owner: a pale cover's light vanished on the light ground): the cover's hue,
     lifted on black and deepened on light, its colour strengthened in proportion (owner: a cream cover glowed yellow
     when a floor of colour was forced onto its near-grey). Where relative colour isn't known (older iOS) none of it
     applies and the cover's own colour stays */
  :global(:root[data-theme='light']) .hero { --halo: 0.5; }
  @supports (color: oklch(from red l c h)) {
    .hero::before { box-shadow: 0 0 14px 0 var(--cg), 0 16px 38px -10px var(--cg); }
    .hero { --cg: oklch(from var(--c, transparent) max(l, 0.66) min(calc(c * 2.5), 0.2) h); }
    :global(:root[data-theme='light']) .hero { --halo: 0.62; --cg: oklch(from var(--c, transparent) min(l, 0.58) min(calc(c * 2.5), 0.2) h); }
  }
  @keyframes bloom { from { opacity: 0; } 40% { opacity: calc(var(--halo) * 1.5); } }
  .art, .shade, .rim { position: absolute; inset: 0; }
  .art, .shade, .rim { border-radius: inherit; pointer-events: none; }
  .art { overflow: hidden; }
  /* the cover clear at the top (it is the screen's one picture), deeper toward the slab: the glass has something calm to sit on */
  .shade { background: linear-gradient(rgba(0, 0, 0, 0.04), rgba(0, 0, 0, 0.38)); }
  /* no cover: the club's colour lit from the top left and deep at the far corner, the event's 3D mark large and
     tilted at the right, its foot behind the frost (the title's side stays clean) */
  .nopic .shade { background: radial-gradient(90% 130% at 0% 0%, rgba(255, 255, 255, 0.2), transparent 60%), linear-gradient(155deg, transparent 35%, rgba(0, 0, 0, 0.5)); }
  .nopic .art :global(.poster) { align-items: flex-start; justify-content: flex-end; padding: var(--s-1) var(--s-5) 0 0; }
  .nopic .art :global(.poster > *) { transform: rotate(9deg) scale(1.2); transform-origin: 50% 0; }
  /* the rim: a hair of white lit at the top left in the cover's colour, as neon glass is. The light comes round once as the card arrives and rests
     there: a big conic square turning under a ring mask, transform only (and no @property: Button owns --rim) */
  .rim { z-index: 1; overflow: hidden; padding: 1px;
    -webkit-mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0); -webkit-mask-composite: xor;
    mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0); mask-composite: exclude; }
  .rim::before { content: ''; position: absolute; left: 50%; top: 50%; width: 150%; aspect-ratio: 1; margin: -75% 0 0 -75%;
    background: conic-gradient(rgba(255, 255, 255, 0.12) 0deg, rgba(255, 255, 255, 0.1) 95deg, var(--c, rgba(255, 255, 255, 0.22)) 125deg, rgba(255, 255, 255, 0.1) 155deg,
      rgba(255, 255, 255, 0.1) 250deg, var(--c, rgba(255, 255, 255, 0.55)) 284deg, rgba(255, 255, 255, 0.7) 296deg, var(--c, rgba(255, 255, 255, 0.55)) 308deg, rgba(255, 255, 255, 0.12) 345deg);
    animation: arrive 1.8s var(--ease-spring) 0.25s backwards; }
  @keyframes arrive { from { transform: rotate(-200deg); } }
  @media (prefers-reduced-motion: reduce) { .hero::before, .rim::before { animation: none; } }
  /* the slab: the shared sheet glass (body, blur, rim and fringes all from base.css, by theme), a static blur over a
     still picture; 6px in, so its corners follow the card's */
  .slab { position: relative; z-index: 2; /* over the card's own tap: its blur makes it a stacking context, so the buttons' own z-index never left it */ display: flex; align-items: center; gap: 10px; padding: 9px 10px 10px 14px;
    border-radius: var(--r-l); color: var(--text); pointer-events: none; }
  .acts { position: relative; z-index: 2; flex: none; display: flex; gap: 8px; max-width: 55%; pointer-events: auto; }
  .acts :global(.btn) { min-width: 0; }
  .acts :global(.btn.round)::before { inset: -4px; } /* 36 seen, 44 to the finger on every side; 8px apart, so two meet and never overlap */
  /* contain: the words take the width that is left and never ask for more. Without it the one-line meta's full width
     (nowrap) is the card's min-content, and a flex card grows to it: the root of the card past the right edge (PRs 324, 328) */
  .hero-tx { flex: 1; display: flex; flex-direction: column; gap: 2px; min-width: 0; contain: inline-size; }
  .hero-tx > b { font: 700 var(--fs-t3)/1.18 var(--font-display); letter-spacing: -0.02em; }
  .where, .hero-place { min-width: 0; font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .where { display: flex; flex-wrap: wrap; max-height: 1.3em; overflow: hidden; }
  .where > span { flex: 0 1 auto; min-width: 0; }
  @media (max-width: 340px) { .where > .by { display: none; } }
  .where b { font-weight: 600; color: var(--text); }
  .hsub { display: flex; align-items: center; gap: 8px; min-width: 0; margin-top: 5px; }
  .hsub:not(:has(*)) { display: none; } /* nothing to say: no line (:empty misses it, the snippet leaves white space) */
  /* the week: seven even columns on the bare ground (no card: the hero above and the days below are the cards); today
     on the one selected pill (the tab bar's lens), a day with events bold with a dot under it, a quiet day dimmed and
     not a button; the accent dot: I'm going */
  .week { display: grid; grid-template-columns: repeat(7, minmax(0, 1fr)); margin: var(--s-4) 0 0; }
  .wd { display: flex; flex-direction: column; align-items: center; gap: var(--s-1); min-height: var(--tap); padding: 2px 0; color: var(--text); }
  .wd span { font: 600 var(--fs-micro)/1.2 var(--font-text); letter-spacing: 0.06em; text-transform: uppercase; color: var(--text-3); }
  .wd b { position: relative; display: grid; place-items: center; width: var(--ctl-s); height: var(--ctl-s); border-radius: var(--r-full); font: 600 var(--fs-row)/1 var(--font-display); letter-spacing: -0.02em;
    transition: transform 450ms var(--ease-bounce), background-color var(--t-base) var(--ease); }
  .wd:active b { transform: scale(0.88); transition-duration: 80ms; background: var(--fill); }
  .wd.has b { font-weight: 700; }
  .wd.today b { background: linear-gradient(var(--lens-top), transparent 70%), var(--lens); box-shadow: var(--lens-shadow); }
  .wd.today b::after { content: ''; position: absolute; inset: 0; padding: 1px; border-radius: inherit; pointer-events: none;
    background:
      radial-gradient(ellipse 60% 150% at 24% 0%, var(--lens-rim), transparent 72%),
      radial-gradient(ellipse 50% 140% at 76% 100%, var(--lens-rim-low), transparent 72%);
    -webkit-mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude; }
  .wd:disabled:not(.today) { opacity: 0.6; }
  .wd:disabled:not(.today) b { color: var(--text-3); font-weight: 450; }
  .wd i { width: 5px; height: 5px; border-radius: var(--r-full); }
  .wd.has i { background: var(--text-3); }
  .wd i.on { background: var(--accent); }

  /* the featured post: its own card, the body folded to two lines */
  .pin { margin: var(--s-3) 0 0; }
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
  .meta :global(svg) { flex: none; color: var(--text-3); }
  /* the club's casting inside its event: one line in the casting's green, its own tap over the row's (taller to the
     finger than it looks: padding, given back by the margin; the ellipsis clips, so no pseudo hit area) */
  .cast { position: relative; z-index: 2; display: block; max-width: 100%; margin: -6px 0; padding: 6px 0; text-align: left; font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--success-text); }
  .cast:active { opacity: 0.6; }
  .sub { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .sub:empty { display: none; }
  .fr { display: flex; align-items: center; gap: 6px; min-width: 0; font: 500 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .av { flex: none; display: flex; }
  .av :global(.av + .av) { margin-left: -5px; }
  .av :global(.av) { box-shadow: 0 0 0 1.5px var(--surface); }

  /* a class: one thin line between the events; its start in the covers' column, the text on the titles' edge, the room
     at the row's end */
  .cl { min-height: 48px; padding: 6px 0; gap: 14px; cursor: pointer; }
  .cl.done, .cl.skip { opacity: 0.5; } /* "done", not "past": .past is the Past list's column (a finished class stood in a column) */
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

  .ask { margin-top: var(--s-4); }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
