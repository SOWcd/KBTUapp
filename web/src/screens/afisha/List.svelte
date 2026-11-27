<script lang="ts">
  // A day is one card, one timeline: events and the optional timetable's classes by start time.
  import Clock from '@lucide/svelte/icons/clock';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import MapIcon from '@lucide/svelte/icons/map';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import Sparkles from '@lucide/svelte/icons/sparkles';
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
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { ui, toTickets, goTab } from '../../lib/state/ui.svelte';
  import { t, money, subjectOf, friendsLine } from '../../lib/i18n/index.svelte';
  import EventPlace from '../../ui/EventPlace.svelte';
  import { lessonKind } from '../../lib/i18n/subjects';
  import { dayNo, nowTs, parts, weekday, dayMonth, dayMonthShort, OFFSET, soon, time, dateInput, multiDay, daySpan } from '../../lib/time';
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
  import { largeTitle } from '../../ui/title';
  import Button from '../../ui/Button.svelte';
  import Card from '../../ui/Card.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import ActionCard from '../../ui/ActionCard.svelte';
  import StoryRow from './StoryRow.svelte';
  import PullSearch from '../../ui/PullSearch.svelte';
  import HeroArt from './HeroArt.svelte';
  import { coverFor, focusPos } from '../../lib/photo';
  import { glass } from '../../ui/glass';
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

  // TEMP (r4): the three directions side by side for the owner's pick; 1 stays
  const dir = (() => { try { return Number(localStorage.getItem('kbtu.afv')) || 1; } catch { return 1; } })();

  let openPost = $state(false);

  // the clock: a minute is enough for "21 min left", so it is rounded to one and changes once a minute at most; it moves
  // on at midnight (the app can stay open overnight). Only while the Afisha is the tab: back on it, it catches up at once
  const minute = () => Math.floor(nowTs() / 60) * 60;
  let now = $state(minute());
  function step() {
    const next = minute();
    if (next === now) return;
    if (data.events.some((e) => e.my?.status === 'going' && endOf(e) > now && endOf(e) <= next)) void loadMyPast();
    now = next;
  }
  onMount(() => {
    const id = setInterval(() => { if (ui.tab === 'afisha') step(); }, 30_000);
    return () => clearInterval(id);
  });
  $effect(() => { if (ui.tab === 'afisha') untrack(step); });
  // the events over and on now, as id strings: a row's tags follow these, so they re-render only when an event crosses its
  // start or end, not on every tick
  const overIds = $derived(data.events.filter((e) => endOf(e) <= now).map((e) => e.id).join());
  const liveIds = $derived(data.events.filter((e) => e.startsAt <= now && endOf(e) > now).map((e) => e.id).join());
  const overSet = $derived(new Set(overIds.split(',')));
  const liveSet = $derived(new Set(liveIds.split(',')));
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
  // with no picture the lead is a field of one colour: the row is lower then (a tall empty card read as a blank screen)
  const leadPic = $derived.by(() => { const c = cards[0]; return !!c && ('e' in c ? !!(c.e.cover || c.e.video?.poster) : 'p' in c ? !!c.p.photo : 'f' in c ? !!c.f.photos[0] : false); });
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
  {@const over = !cancelled && overSet.has(String(e.id))}
  {@const live = !cancelled && !over && liveSet.has(String(e.id))}
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

<!-- what the slab's glass shows of the cover: the picture again from its small thumb, larger, blurred and dimmed, cut to
     the slab. A still layer drawn once: a live backdrop blur was redrawn on every frame the card moved (a swipe, the page) -->
{#snippet lens(pic: { thumb: string; focus?: [number, number] | null } | null)}
  {#if pic}<span class="lens" aria-hidden="true"><img src={pic.thumb} alt="" decoding="async" draggable="false" style:object-position={focusPos(pic)} /></span>{/if}
{/snippet}

<!-- one hero card, any kind: the lead's slot (i 0) and the swiped-to ones -->
{#snippet heroCard(c: Card, i: number)}
  {#if 'e' in c}
    {@const e = c.e}
    {@const mine = e.my?.status === 'going'}
    <!-- an event: my ticket and the way there, else what it is and one tap to go -->
    {@const art = coverFor(e.cover, 'card') ?? e.video?.poster ?? null}
    {@const pic = !!art}
    <section class="hero" class:theme-dark={dir !== 3} class:tix={mine && i === 0} class:nopic={!pic} style:--c={e.cover?.color ?? e.video?.poster?.color ?? e.color ?? e.tint} onclickcapture={() => tap(c)}>
      <button class="hit" onpointerdown={(ev) => touchAhead(ev, () => prefetchEvent(e.id))} onclick={(ev) => sheets.event(e.id, ev.currentTarget.parentElement?.querySelector('.poster'))} aria-label={e.title}></button>
      <span class="art"><HeroArt pic={art} emoji={e.emoji} color={e.color ?? e.tint} first={i === 0} /></span>
      <div class="shade"></div>
      <div class="slab" use:glass>
        {@render lens(art)}
        <span class="hero-tx">
          <b class="clamp-2">{e.title}</b>
          <span class="where"><span class="ellipsis"><b class="num">{multiDay(e.startsAt, e.endsAt) ? daySpan(e.startsAt, e.endsAt) : time(e.startsAt)}</b> · {soon(e.startsAt, now)}</span><span class="by ellipsis">&nbsp;· {shortOf(e.org)}{#if e.coHost} × {shortOf(e.coHost)}{/if}</span></span>
          <span class="hero-place"><EventPlace {e} pin /></span>
        </span>
        <!-- the slab's foot: who goes and what it is, and under the thumb my ticket or the one tap to sign up -->
        <span class="foot">
          <span class="hsub">{@render status(e)}</span>
          {#if mine}
            <span class="acts"><Button onmedia={dir !== 3} size="m" onclick={() => sheets.ticket(e.id)}>{#snippet icon()}<QrCode size={17} />{/snippet}{t('event.ticket')}</Button></span>
          {:else if e.my?.status === 'hold'}
            <span class="acts"><Button onmedia={dir !== 3} size="m" onclick={() => sheets.pay(e.id)}>{t('event.pay', { price: money(e.price ?? 0) })}</Button></span>
          {:else if canGo(e)}
            <span class="acts"><Button onmedia={dir !== 3} size="m" loading={goingBusy.has(e.id)} onclick={() => toggleGoing(e.id, () => sheets.pay(e.id))}>{e.price ? e.freeLeft && session.me?.student?.freeFirst ? t('event.goFree') : t('event.goPrice', { price: money(e.price) }) : t('event.go')}</Button></span>
          {/if}
        </span>
      </div>
    </section>
  {:else}
    {@const v = look(c)}
    <!-- news, a forum post, my next class: the same card, its picture or a 3D mark, the title and one line -->
    <section class="hero" class:theme-dark={dir !== 3} class:nopic={!v.item.cover} style:--c={v.color} onclickcapture={() => tap(c)}>
      <button class="hit" onclick={v.open} aria-label={v.title}></button>
      <span class="art"><HeroArt pic={v.item.cover} emoji={v.item.emoji} color={v.color} first={i === 0} /></span>
      <div class="shade"></div>
      <div class="slab" use:glass>
        {@render lens(v.item.cover)}
        <span class="hero-tx">
          <b class="clamp-2">{v.title}</b>
          <span class="where"><span class="ellipsis">{#if v.lead}<b class="num">{v.lead}</b> · {/if}{v.line}</span>{#if v.by}<span class="by ellipsis">&nbsp;· {v.by}</span>{/if}</span>
        </span>
        {#if v.room}{@const room = v.room}<span class="foot"><span class="acts"><Button onmedia={dir !== 3} size="m" onclick={() => sheets.map(room)}>{#snippet icon()}<MapPin size={17} />{/snippet}{room}</Button></span></span>{/if}
      </div>
    </section>
  {/if}
{/snippet}

<div class="page scroll stagger v{dir}">
  <PullSearch bind:value={q} placeholder={t('list.search')} />
  <!-- no headline (owner, Nov 27): the clubs' circles, then the one big card. The screen's name stays for a reader and for
       the capsule, which shows it once this has scrolled away -->
  <h1 class="ttl" use:largeTitle={'afisha'}>{t('common.today')}</h1>
  {#if kept.length}{#await import('../../ui/OfflineTickets.svelte') then m}<div class="offline"><m.default tickets={kept} /></div>{/await}{/if}
  {#if searching}
    <Everything {q} events={searchable} />
  {:else}
  <StoryRow feed={shown.length > 0} />
  {#if showClasses && offToday}<p class="off t-foot">{t('list.dayOff')}</p>{/if}

  {#if cards.length}
    <!-- the hero, personal: the first card, a swipe brings #2 and #3 (snapped); one markup for every kind -->
    <div class="heroes" class:short={!leadPic} role="group" aria-label={t('list.heroPicks')} onscroll={slid}>
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

  {#if ratePrompt && !ratingBusy.has(ratePrompt.id)}
    {@const e = ratePrompt}
    <!-- one quiet line under the hero (owner, Nov 27: a card of five grey tiles read as another app): what it asks and of
         which event, the five stars bare at its end, one tap rates; the x leaves it -->
    <div class="rate">
      <span class="rate-tx"><b>{t('rate.ask')}</b><span class="ellipsis">{e.title}</span></span>
      <span class="rate-stars" role="group" aria-label={t('rate.ask')}>
        {#each [1, 2, 3, 4, 5] as score (score)}
          <button type="button" aria-label={t('rate.score', { n: score })} onclick={() => void rateFromPrompt(e.id, score)}><Star size={22} strokeWidth={1.75} /></button>
        {/each}
      </span>
      <button type="button" class="rate-x" aria-label={t('rate.dismiss')} onclick={() => void dismissEventRating(e.id)}><X size={16} /></button>
    </div>
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
  .ttl { position: absolute; width: 1px; height: 1px; overflow: hidden; clip-path: inset(50%); white-space: nowrap; }
  .offline { margin-bottom: var(--s-6); }
  /* the rating: one bare line on the ground between the card and the list (no surface of its own: the hero is the
     card here); the stars are gold outlines, each a 44 px tall target, and a pressed one fills */
  .rate { display: flex; align-items: center; gap: var(--s-1); min-height: var(--row-h); margin: var(--s-4) calc(-1 * var(--s-2)) 0 var(--s-1); }
  .rate-tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; font: 450 var(--fs-cap)/1.3 var(--font-text); color: var(--text-3); }
  .rate-tx b { font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); white-space: nowrap; }
  .rate-stars { flex: none; display: flex; }
  .rate-stars button { display: grid; place-items: center; width: 34px; height: var(--tap); color: var(--warning-text); transition: transform var(--t-fast) var(--ease); }
  .rate-stars button:active { transform: scale(1.18); }
  .rate-stars button:active :global(svg) { fill: currentColor; }
  .rate-x { flex: none; display: grid; place-items: center; width: 34px; height: var(--tap); color: var(--text-3); }
  .rate-x:active { opacity: 0.6; }
  .off { margin: var(--s-3) var(--s-1) 0; color: var(--text-2); }
  .pastrow { margin-top: var(--s-4); }
  .pastrow + .past { margin-top: 8px; }
  .past { display: flex; flex-direction: column; gap: 8px; }
  .lnk { align-self: center; }

  .sec { margin: var(--s-7) var(--s-1) var(--s-3); font: 700 var(--fs-sec)/1.15 var(--font-display); letter-spacing: -0.03em; } /* the hero title's own voice, a step smaller */
  .events-head { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); min-height: var(--tap); margin: var(--s-5) var(--s-1) 0; padding-top: var(--s-4); box-shadow: inset 0 0.5px 0 var(--separator); } /* a hairline, then the section's title */
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
  /* (owner, Nov 27) the hero is the screen's one big card, most of the first screen: the cover tall and whole, and the words
     on a slab of Liquid Glass at its foot. The card is media, so it is dark in both themes (.theme-dark: white words, the
     dark tags and buttons): the glass is clear and takes its colour from the cover, not from the page */
  .hero { --halo: 0.62; position: relative; isolation: isolate; display: flex; flex-direction: column; justify-content: flex-end; height: var(--hh);
    border-radius: var(--r-xl); background: var(--media); color: var(--text); transition: transform var(--t-fast) var(--ease); }
  .hero:has(> .hit:active) { transform: scale(0.985); }
  /* the hero's cards side by side, one in view, snapped; edge to edge so the next one waits just past the gutter. A
     scroller clips, so it leaves room around the cards for their light (the glow reaches 44px under a card) and takes it
     back with its margins */
  .heroes { --hh: clamp(340px, 60vh, 540px); display: flex; gap: var(--s-3); overflow-x: auto; overscroll-behavior-x: contain; scroll-snap-type: x mandatory; scrollbar-width: none;
    margin: calc(-1 * var(--s-4)) calc(-1 * var(--gutter)) -44px; padding: var(--s-4) 0 44px var(--gutter); }
  .heroes::-webkit-scrollbar { display: none; }
  .heroes.short { --hh: clamp(320px, 52vh, 440px); }
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
  :global(:root[data-theme='light']) .hero { --halo: 0.26; }
  @supports (color: oklch(from red l c h)) {
    .hero::before { box-shadow: 0 0 14px 0 var(--cg), 0 16px 38px -10px var(--cg); }
    .hero { --cg: oklch(from var(--c, transparent) max(l, 0.66) min(calc(c * 2.5), 0.2) h); }
    :global(:root[data-theme='light']) .hero { --halo: 0.3; --cg: oklch(from var(--c, transparent) min(l, 0.58) min(calc(c * 2.5), 0.2) h); }
  }
  @keyframes bloom { from { opacity: 0; } 40% { opacity: calc(var(--halo) * 1.5); } }
  .art, .shade { position: absolute; inset: 0; border-radius: inherit; pointer-events: none; }
  .art { overflow: hidden; }
  /* the cover clear at the top (it is the screen's one picture), deeper toward the slab: the glass has something calm to sit on */
  .shade { background: linear-gradient(rgba(0, 0, 0, 0) 36%, rgba(0, 0, 0, 0.5)); box-shadow: inset 0 0 0 0.5px rgba(255, 255, 255, 0.14); }
  /* (the card has no lit rim of its own: the glass is the one lit object on it; two rims 6px apart read as nested boxes) */
  @media (prefers-reduced-motion: reduce) { .hero::before { animation: none; } }
  /* (r4) the words lie on the cover itself, no box inside the card: under them the picture goes soft and dark by
     degrees (the lens: the cover's thumb again, blurred and dimmed, let in through a gradient mask, so there is no edge
     where it starts). A still layer, drawn once: nothing blurs live */
  .slab { position: relative; z-index: 2; /* over the card's own tap */ isolation: isolate; display: flex; flex-direction: column; padding: 96px 18px var(--s-4);
    border-radius: 0 0 var(--r-xl) var(--r-xl); color: var(--text); pointer-events: none; }
  .lens { position: absolute; inset: 0; z-index: -2; overflow: hidden; border-radius: inherit; pointer-events: none;
    -webkit-mask-image: linear-gradient(transparent, rgba(0, 0, 0, 0.55) 56px, black 112px); mask-image: linear-gradient(transparent, rgba(0, 0, 0, 0.55) 56px, black 112px); }
  .lens img { position: absolute; left: 0; bottom: 0; width: 100%; height: var(--hh); object-fit: cover;
    transform: scale(1.12); transform-origin: 50% 100%; filter: blur(20px) saturate(1.7) brightness(0.6); }
  /* TEMP-R4-BEGIN: directions 2 (the glass slab, r3) and 3 (the poster bare, the words under it) */
  .v2 .hero { padding: 6px; }
  .v2 .shade { background: linear-gradient(rgba(0, 0, 0, 0.02) 40%, rgba(0, 0, 0, 0.42)); box-shadow: none; }
  .v2 .hero-tx > b { margin-bottom: 2px; font: 700 var(--fs-sec)/1.14 var(--font-display); letter-spacing: -0.03em; }
  .v2 .sec { font: var(--fw-light) var(--fs-t1)/1.1 var(--font-display); letter-spacing: -0.04em; }
  .v2 .events-head { margin-top: var(--s-7); padding-top: var(--s-5); }
  /* the slab: Liquid Glass, its own recipe (the sheets' glass is a frosted body; this one is a lens over one still
     picture). What it shows of the cover is the lens layer below, so nothing here blurs live. A dimmed body so white
     words read on any cover, a white poster too; depth from a soft shadow onto the picture and a dark foot inside;
     light from a top sheen, a specular rim bright on the arc facing the light and on the one opposite (it follows the
     phone's tilt, --gx), and the warm and cool fringes at the sides */
  .v2 .slab { position: relative; z-index: 2; /* over the card's own tap */ isolation: isolate; display: flex; flex-direction: column; padding: 14px var(--s-4) var(--s-3);
    border-radius: var(--r-l); color: var(--text); pointer-events: none;
    background: linear-gradient(rgba(255, 255, 255, 0.1), rgba(255, 255, 255, 0) 46%), rgba(10, 12, 20, 0.34);
    box-shadow: 0 10px 24px -14px rgba(0, 0, 0, 0.5); }
  .v2 .slab::before, .v2 .slab::after { content: ''; position: absolute; inset: 0; z-index: -1; border-radius: inherit; pointer-events: none; }
  .v2 .slab::before {
    background: radial-gradient(70% 90% at calc(16% + var(--gx, 0) * 40%) -18%, rgba(255, 255, 255, 0.24), transparent 62%);
    box-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.5), inset 0 10px 18px -12px rgba(255, 255, 255, 0.36), inset 0 -18px 24px -16px rgba(0, 0, 0, 0.42),
      inset 2px 0 2px -1px rgba(255, 120, 200, 0.3), inset -2px 0 2px -1px rgba(90, 190, 255, 0.34), inset 0 0 16px rgba(255, 255, 255, 0.06); }
  .v2 .slab::after { z-index: 0; padding: 1.2px;
    background:
      radial-gradient(ellipse 48% 150% at calc(22% + var(--gx, 0) * 38%) 0%, rgba(255, 255, 255, 0.98), rgba(255, 255, 255, 0.34) 42%, transparent 74%),
      radial-gradient(ellipse 40% 140% at calc(80% - var(--gx, 0) * 38%) 100%, rgba(255, 255, 255, 0.62), transparent 72%),
      rgba(255, 255, 255, 0.13);
    -webkit-mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0); -webkit-mask-composite: xor;
    mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0); mask-composite: exclude; }
  /* the lens: laid over the card's whole box from inside the slab (6px in on three sides), so it lines up with the
     cover, then a step larger about the slab, as thick glass magnifies */
  .v2 .lens { background: var(--media); -webkit-mask-image: none; mask-image: none; }
  .v2 .lens img { position: absolute; left: -6px; bottom: -6px; width: calc(100% + 12px); height: var(--hh); object-fit: cover;
    transform: scale(1.14); transform-origin: 50% 86%; filter: blur(18px) saturate(1.8) brightness(0.58); }
  /* the rating: the app's card surface as one capsule row, no tiles inside it; the stars are bare gold outlines, each a
     44 px tall target, and a pressed one fills */
  .v2 .rate { display: flex; align-items: center; gap: var(--s-1); min-height: var(--row-h2); margin: var(--s-5) 0 0; padding: 0 var(--s-1) 0 var(--s-4);
    border-radius: var(--r-l); background: var(--surface); box-shadow: var(--card-rim); }
  .v3 .hero { background: none; color: var(--text); }
  .v3 .hero::before, .v3 .shade, .v3 .lens { display: none; }
  .v3 .art { position: relative; inset: auto; flex: 1; min-height: 0; border-radius: var(--r-xl); box-shadow: var(--shadow-card), var(--card-rim); }
  .v3 .slab { padding: var(--s-3) var(--s-1) 0; border-radius: 0; }
  .v3 .hero-tx { text-shadow: none; }
  .v3 .hero-tx > b { font: 700 var(--fs-sec)/1.14 var(--font-display); letter-spacing: -0.03em; }
  .v3 .hsub :global(.chip) { background: var(--fill); color: var(--text-2); }
  .v3 .heroes > .hero, .v3 .lead { flex-basis: calc(100% - var(--gutter) - var(--s-7)); }
  .v3 .rate { min-height: var(--row-h2); margin: var(--s-5) 0 0; padding: 0 var(--s-1) 0 var(--s-4); border-radius: var(--r-l); background: var(--surface); box-shadow: var(--card-rim); }
  .v3 .sec { font: 600 var(--fs-micro)/1.2 var(--font-text); letter-spacing: 0.08em; text-transform: uppercase; color: var(--text-3); }
  .v3 .events-head { box-shadow: none; padding-top: 0; }
  /* TEMP-R4-END */
  /* over media the tags are white on a clear chip (the accent's blue on a blue cover was 2:1), the place has no underline
     (the whole card opens the event; the pin says it is a place) */
  .hsub :global(.chip) { background: rgba(255, 255, 255, 0.18); color: var(--on-accent); }
  .hsub .fr { color: var(--text-2); }
  .hero-place :global(.place) { text-decoration: none; }
  .foot { display: flex; align-items: center; gap: 10px; min-height: var(--ctl-m); margin-top: var(--s-3); }
  .foot:not(:has(.acts, .hsub *)) { display: none; }
  .acts { position: relative; z-index: 2; flex: none; display: flex; gap: 8px; max-width: 60%; margin-left: auto; pointer-events: auto; }
  .acts :global(.btn) { min-width: 0; }
  .acts :global(.btn.round)::before { inset: -4px; } /* 36 seen, 44 to the finger on every side; 8px apart, so two meet and never overlap */
  /* contain: the words take the width that is left and never ask for more. Without it the one-line meta's full width
     (nowrap) is the card's min-content, and a flex card grows to it: the root of the card past the right edge (PRs 324, 328) */
  .hero-tx { flex: none; display: flex; flex-direction: column; gap: 3px; min-width: 0; contain: inline-size; text-shadow: 0 1px 8px rgba(0, 0, 0, 0.28); }
  .hero-tx > b { margin-bottom: var(--s-1); font: 700 var(--fs-t1)/1.08 var(--font-display); letter-spacing: -0.035em; }
  .where, .hero-place { min-width: 0; font: 500 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  .where { display: flex; flex-wrap: wrap; max-height: 1.3em; overflow: hidden; }
  .where > span { flex: 0 1 auto; min-width: 0; }
  @media (max-width: 340px) { .where > .by { display: none; } }
  .where b { font-weight: 600; color: var(--text); }
  .hsub { flex: 1; display: flex; align-items: center; gap: 8px; min-width: 0; }
  .hsub:not(:has(*)) { display: none; } /* nothing to say: no line (:empty misses it, the snippet leaves white space) */

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
