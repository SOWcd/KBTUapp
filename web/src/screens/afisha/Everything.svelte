<script lang="ts">
  // The global search under the Afisha's pull-down field: events, clubs, people, news, forum posts, places on the campus
  // map and subjects at once, as it's typed. What the app holds is matched here on every keystroke (lib/find.ts); the
  // server is asked once typing pauses, for what it doesn't hold: findable people and older forum posts (logic/search.more).
  // The best match on top, then the groups by their best; a tap opens the thing's own sheet.
  import MapPin from '@lucide/svelte/icons/map-pin';
  import BookOpen from '@lucide/svelte/icons/book-open';
  import MessageSquare from '@lucide/svelte/icons/message-square';
  import { api, type ChannelFeedPost, type ClassItem, type EventCard, type Org, type PersonRef, type Post, type SearchMore, type Subject } from '../../lib/api';
  import { t, tn, i18n, subjectOf } from '../../lib/i18n/index.svelte';
  import { classEmoji } from '../../lib/i18n/subjects';
  import { score, namesOf } from '../../lib/search';
  import { once, order, rank, textScore, type Found, type Kind } from '../../lib/find';
  import { SPOTS, spotNames, roomOf, floorOf } from '../../lib/map';
  import { searchable, nameOf as subjectName, subjectOf as catalogOf } from '../../lib/subjects';
  import { dayMonth } from '../../lib/time';
  import { data } from '../../lib/state/data.svelte';
  import { channel, channelPosts } from '../../lib/state/channel.svelte';
  import { subj, subjIndex, subjReady } from '../../lib/state/subjects.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { ui } from '../../lib/state/ui.svelte';
  import { haptic } from '../../lib/tg';
  import EventRow from '../../ui/EventRow.svelte';
  import ClubRow from '../../ui/ClubRow.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { q, events }: { q: string; events: EventCard[] } = $props();

  type Person = { person: PersonRef; names: (string | null | undefined)[]; sub: string };
  type Place = { name: string; names: string[]; open: string; floor: number | null };
  type Subj = { id: string | null; name: string; names: string[]; c?: ClassItem };
  type Item = { kind: 'event'; x: EventCard } | { kind: 'club'; x: Org } | { kind: 'person'; x: Person } | { kind: 'news'; x: Post }
    | { kind: 'forum'; x: ChannelFeedPost } | { kind: 'place'; x: Place } | { kind: 'subject'; x: Subj };

  // ---- the server's part: once typing pauses, never per keystroke; the last answer stays while the next is on its way
  const key = $derived(q.trim().toLowerCase());
  let more = $state.raw<{ q: string; r: SearchMore } | null>(null);
  let waiting = $state(false);
  const asked = new Map<string, SearchMore>(); // backspacing doesn't ask again
  $effect(() => {
    const k = key;
    if (k.replace(/\s/g, '').length < 2 || !(session.me?.student || session.channel)) { waiting = false; return; }
    const kept = asked.get(k);
    if (kept) { more = { q: k, r: kept }; waiting = false; return; }
    waiting = true;
    const timer = setTimeout(() => {
      api.searchMore(k).then((r) => {
        asked.set(k, r);
        if (asked.size > 30) asked.delete(asked.keys().next().value!);
        if (key === k) more = { q: k, r };
      }, () => {}).finally(() => { if (key === k) waiting = false; });
    }, 350);
    return () => clearTimeout(timer);
  });
  // an older answer's rows stay while they still match what's typed now; this query's own answer counts whole (an @username)
  const fresh = $derived(more?.q === key);

  // ---- what the app holds
  const people = $derived.by((): Person[] => {
    const f = data.friends;
    const local: Person[] = f ? [
      ...f.friends.map((r) => ({ person: r.person, names: [r.person.name, r.fullName, r.person.nick], sub: t('gs.friend') })),
      ...[...f.incoming, ...f.outgoing].map((r) => ({ person: r.person, names: [r.person.name, r.fullName, r.person.nick], sub: r.course ? t('person.course', { n: r.course }) : '' })),
      ...(f.suggest ?? []).map((s) => ({ person: s.person, names: [s.person.name, s.person.realName, s.person.nick], sub: tn('pymk.clubs', s.clubs) })),
    ] : [];
    const far = (more?.r.people ?? []).map((p) => ({ person: p.person, names: [p.person.name, p.person.realName, p.person.nick], sub: p.course ? t('person.course', { n: p.course }) : '' }));
    return once([...local, ...far], (p) => p.person.id);
  });
  const farPeople = $derived(new Set(fresh ? more!.r.people.map((p) => p.person.id) : []));
  const news = $derived(once([...data.posts, ...(data.news?.casts ?? []), ...(data.news?.posts ?? [])], (p) => p.id));
  const posts = $derived(session.channel ? once([...channelPosts(), ...(more?.r.posts ?? [])], (p) => p.id) : []);
  const farPosts = $derived(new Set(fresh ? more!.r.posts.map((p) => p.id) : []));
  const places = $derived.by((): Place[] => SPOTS.map((s) => {
    const name = t(`route.spot.${s.k}` as 'route.spot.canteen');
    return { name, names: spotNames(s), open: s.room ?? name, floor: s.f ?? floorOf(s.room) };
  }));
  const subjects = $derived.by((): Subj[] => {
    const index = subjReady() ? subjIndex() : null;
    const mine = once(data.schedule, (c) => c.subject).map((c): Subj => {
      const s = index && catalogOf(c, index);
      return { id: s?.id ?? null, name: subjectOf(c), names: [c.subject, ...Object.values(c.names ?? {})].filter((x): x is string => !!x), c };
    });
    const all = index ? (subj.all?.subjects ?? []).map((s: Subject): Subj => ({ id: s.id, name: subjectName(s, i18n.lang), names: searchable(s) })) : [];
    return once([...mine, ...all], (s) => s.id ?? s.name);
  });

  // ---- ranked
  const groups = $derived.by(() => {
    const room = roomOf(q.trim()), floor = floorOf(room);
    const out: { [K in Kind]: Found<Extract<Item, { kind: K }>['x']>[] } = {
      event: rank(q, events, (e) => [...namesOf(e, 'title', 'place'), ...namesOf(e.org, 'name', 'short', 'abbr')], 6),
      club: rank(q, [...data.orgs, ...data.small], (o) => namesOf(o, 'name', 'short', 'abbr')),
      person: rank(q, people, (p) => (farPeople.has(p.person.id) ? Math.max(1, score(q, p.names)) : p.names)),
      // a post's title as a name; its text only by whole words, a step below
      news: rank(q, news, (p) => Math.max(score(q, namesOf(p, 'title')), textScore(q, p.body) - 1)),
      forum: rank(q, posts, (p) => (farPosts.has(p.id) ? Math.max(2, textScore(q, p.body)) : textScore(q, p.body))),
      // a room typed by its number ("305", "aud. 251a") is a place too, its floor circled on the map
      place: [...(room && floor != null ? [{ item: { name: t('map.roomTitle', { room }), names: [], open: room, floor }, score: 3 }] : []),
        ...rank(q, places, (p) => p.names)].slice(0, 5),
      subject: rank(q, subjects, (s) => s.names),
    };
    return out;
  });
  const kinds = $derived(order(groups));
  const top = $derived<Item | null>(kinds.length ? ({ kind: kinds[0], x: groups[kinds[0]][0].item } as Item) : null);
  const CAPTION: Record<Kind, () => string> = { event: () => t('list.title'), club: () => t('page.clubs'), person: () => t('gs.people'), news: () => t('page.news'),
    forum: () => t('tab.forum'), place: () => t('gs.places'), subject: () => t('sj.title') };

  // ---- opening
  const tap = (fn: () => void) => () => { haptic.tap(); fn(); };
  const openNews = (p: Post) => {
    const list = news.filter((x) => x.org.id === p.org.id);
    sheets.stories([{ org: p.org, items: list.map((post) => ({ post })), unread: false, cast: false }], 0, list.indexOf(p));
  };
  const openPost = (p: ChannelFeedPost) => { channel.focus = p.id; ui.tab = 'forum'; };
  const openSubject = (s: Subj) => (s.id ? sheets.subject(s.id) : sheets.week());
  const clip = (s: string, n = 90) => { const line = s.replace(/\s+/g, ' ').trim(); return line.length > n ? line.slice(0, n - 1) + '…' : line; };
</script>

{#snippet one(it: Item)}
  {#if it.kind === 'event'}<EventRow e={it.x} showDate dateLine={dayMonth(it.x.startsAt)} wasThere />
  {:else if it.kind === 'club'}<ClubRow org={it.x} />
  {:else if it.kind === 'person'}{@const p = it.x}
    <Row dense title={p.person.name} subtitle={p.sub || undefined} accessory="chevron" onclick={tap(() => sheets.person(p.person.id))}>
      {#snippet lead()}<Avatar person={p.person} size={36} tappable={false} />{/snippet}
    </Row>
  {:else if it.kind === 'news'}{@const p = it.x}
    <Row dense title={clip(p.title || p.body)} subtitle={p.org.name} accessory="chevron" onclick={tap(() => openNews(p))}>
      {#snippet lead()}<OrgLogo org={p.org} size={36} />{/snippet}
    </Row>
  {:else if it.kind === 'forum'}{@const p = it.x}
    <Row dense icon={MessageSquare} title={clip(p.body)} subtitle={`${p.sign} · ${dayMonth(p.at)}`} accessory="chevron" onclick={tap(() => openPost(p))} />
  {:else if it.kind === 'place'}{@const p = it.x}
    <Row dense icon={MapPin} title={p.name} subtitle={p.floor != null ? t('map.title', { n: p.floor }) : undefined} accessory="chevron" onclick={tap(() => sheets.map(p.open))} />
  {:else}{@const s = it.x}
    {#if s.c}{@const c = s.c}
      <Row dense title={s.name} subtitle={t('gs.mine')} accessory="chevron" onclick={tap(() => openSubject(s))}>
        {#snippet lead()}<span class="emo"><Emoji name={classEmoji(c)} size={26} /></span>{/snippet}
      </Row>
    {:else}<Row dense icon={BookOpen} title={s.name} accessory="chevron" onclick={tap(() => openSubject(s))} />{/if}
  {/if}
{/snippet}

{#snippet group(kind: Kind, items: Item[])}
  {#if kind === 'event'}
    <section class="evs"><h3 class="cap">{CAPTION[kind]()}</h3>{#each items as it ((it.x as EventCard).id)}{@render one(it)}{/each}</section>
  {:else}
    <Group caption={CAPTION[kind]()}>{#each items as it, i (i)}{@render one(it)}{/each}</Group>
  {/if}
{/snippet}

<div class="all">
  {#if top}
    {#if top.kind === 'event'}<section class="evs"><h3 class="cap">{t('gs.top')}</h3>{@render one(top)}</section>
    {:else}<Group caption={t('gs.top')}>{@render one(top)}</Group>{/if}
    {#each kinds as kind (kind)}
      {@const rest = groups[kind].filter((f) => f.item !== top?.x).map((f) => ({ kind, x: f.item }) as Item)}
      {#if rest.length}{@render group(kind, rest)}{/if}
    {/each}
  {:else if !waiting}
    <EmptyState inline text={t('clubs.nothing')} />
  {/if}
</div>

<style>
  .all { display: flex; flex-direction: column; gap: var(--s-5); }
  .evs { display: flex; flex-direction: column; gap: 8px; }
  /* the same heading as a Group's caption, over the events' own cards */
  .cap { margin: 0 var(--s-1) 2px; font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; color: var(--text); }
  .emo { display: grid; place-items: center; width: 36px; height: 36px; }
</style>
