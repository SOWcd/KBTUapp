<script lang="ts">
  // The Clubs tab, one page and nothing pushed from it: the title with what's alive today; my clubs as a dock of marks
  // (a tap: Studio); who is recruiting now as big covers with the one button; then every club in one list that the chips
  // filter in place (all by the server's rank, recruiting with Apply on each row, followed, an interest, schools), the
  // quiet clubs dimmed at its end. Search (pulled down) swaps the page for what it found.
  import Briefcase from '@lucide/svelte/icons/briefcase';
  import Code from '@lucide/svelte/icons/code';
  import FlaskConical from '@lucide/svelte/icons/flask-conical';
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import Palette from '@lucide/svelte/icons/palette';
  import Plus from '@lucide/svelte/icons/plus';
  import Trophy from '@lucide/svelte/icons/trophy';
  import type { Membership, Org, OrgCategory, OrgRef, Post } from '../../lib/api';
  import { clubLook, lookVars, skinOf } from '../../lib/awards';
  import { byWeight, clubSub, daysLeft, friendsIn, hit, nextByOrg, roundDue, waitsDmp } from '../../lib/clubs';
  import { artOf, coverOf } from '../../lib/covers';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { byRank, canLeave, roleLabel } from '../../lib/perms';
  import { castingState, castingStatus } from '../../lib/posts';
  import { nameOf, shortOf } from '../../lib/short';
  import { chatsFor, currentCastings, data, leaveClub, loadChats, toggleJoin } from '../../lib/state/data.svelte';
  import { asStudent, session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { haptic } from '../../lib/tg';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import ChatAvatar from '../../ui/ChatAvatar.svelte';
  import GovMark from '../../ui/GovMark.svelte';
  import { longPress } from '../../ui/longpress';
  import { menu } from '../../ui/menu';
  import OfficialMark from '../../ui/OfficialMark.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import PullSearch from '../../ui/PullSearch.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';

  let q = $state('');
  const searching = $derived(!!q.trim());
  $effect(() => { if ((session.me?.id ?? null) !== chatsFor) loadChats(); });

  const SCHOOLISH = new Set(['school', 'office']);
  const clubs = $derived(data.orgs.filter((o) => !SCHOOLISH.has(o.kind)));
  const schools = $derived(data.orgs.filter((o) => SCHOOLISH.has(o.kind)).sort((a, b) => a.kind.localeCompare(b.kind) || nameOf(a).localeCompare(nameOf(b), 'ru')));
  const found = $derived(searching ? [...data.orgs, ...data.small].filter((o) => hit(o, q)).sort(byWeight) : []);
  const next = $derived(nextByOrg([...data.events, ...Object.values(data.studio).flat()].filter((e) => e.status === 'published')));

  // mine: a tap opens the club's Studio whatever my role; a held press offers Leave
  const mine = $derived([...(session.me?.memberships ?? [])].sort(byRank));
  const memberOf = $derived(new Set(mine.map((m) => m.org.id)));
  const openMine = (m: Membership) => { haptic.tap(); sheets.studio(m.org.id); };
  const hold = (m: Membership) => (el: HTMLElement) => menu(el, [{ label: t('clubs.open'), onselect: () => openMine(m) }, { label: t('clubs.leave'), destructive: true, onselect: () => void leaveClub(m) }]);

  // recruiting, none of clubs I'm in: castings (come in person), rounds (official first, then the biggest), clubs that
  // take applications any time. The covers show the first ten; the Recruiting chip lists every one
  const outside = (o: Org) => !memberOf.has(o.id) && !o.myRole;
  const castings = $derived(currentCastings().filter((p) => !memberOf.has(p.org.id)));
  const rounds = $derived(data.orgs.filter((o) => o.round && outside(o)).sort((a, b) => +!a.official - +!b.official || b.members - a.members || a.round!.closesAt - b.round!.closesAt));
  const always = $derived(clubs.filter((o) => o.recruiting && !o.round && outside(o)).sort(byWeight));
  type Call = { key: string; org: OrgRef; when: string; soon?: boolean; live?: boolean; sub: string; open: () => void; cta?: { label: string; done: boolean; off?: boolean; run: () => void } };
  const people = (o: Org) => (o.friendsN ? friendsIn(o) : tn('club.members', o.members));
  const story = (p: Post) => sheets.stories([{ org: p.org, items: [{ post: p }], unread: false, cast: false }], 0);
  const calls = $derived<Call[]>([
    ...castings.map((p) => ({ key: `c${p.id}`, org: p.org, when: castingStatus(p.casting!), live: castingState(p.casting!) === 'open', sub: `${t('casting.come')} · ${p.casting!.place}`, open: () => story(p) })),
    ...rounds.map((o) => ({ key: `r${o.id}`, org: o, when: roundDue(o.round!.closesAt), soon: daysLeft(o.round!.closesAt) <= 3, sub: people(o), open: () => sheets.club(o.id),
      cta: { label: t(o.round!.applied ? 'clubs.applied' : 'join.apply'), done: o.round!.applied, run: () => sheets.roundApply(o.id, 'join') } })),
    ...always.map((o) => ({ key: `a${o.id}`, org: o, when: t('clubs.openNow'), sub: people(o), open: () => sheets.club(o.id),
      cta: { label: t(o.myRequest === 'rejected' ? 'join.notNow' : o.myRequest === 'pending' ? 'join.sent' : 'join.apply'), done: !!o.myRequest, off: o.myRequest === 'rejected', run: () => toggleJoin(o.id) } })),
  ]);
  const SHOWN = 10;
  const ctaOf = $derived(new Map(calls.filter((c) => c.cta).map((c) => [c.org.id, c.cta!])));

  // the list and its chips: only the chips that have something behind them
  const live = $derived(clubs.filter((o) => !o.quiet));
  const alive = $derived(clubs.filter((o) => next.has(o.id)).length);
  const pulse = $derived([alive && t('clubs.aliveN', { n: alive }), calls.length && t('clubs.doorsN', { n: calls.length })].filter(Boolean).join(' · '));
  const INTERESTS = [{ key: 'it', icon: Code, tint: 'blue' }, { key: 'art', icon: Palette, tint: 'pink' }, { key: 'sport', icon: Trophy, tint: 'orange' },
    { key: 'business', icon: Briefcase, tint: 'indigo' }, { key: 'science', icon: FlaskConical, tint: 'teal' }, { key: 'volunteer', icon: HeartHandshake, tint: 'green' }] as const;
  type Filter = 'all' | 'recruit' | 'follow' | 'schools' | OrgCategory;
  type Chip = { key: Filter; label: string; n?: number; icon?: typeof Code; tint?: string };
  const recruiting = $derived([...new Map([...castings.flatMap((p) => data.orgs.filter((o) => o.id === p.org.id)), ...[...rounds].sort((a, b) => a.round!.closesAt - b.round!.closesAt), ...always].map((o) => [o.id, o])).values()]);
  const followed = $derived(clubs.filter((o) => o.subscribed && !memberOf.has(o.id)).sort(byWeight));
  const chips = $derived<Chip[]>([
    { key: 'all', label: t('common.all') },
    ...(recruiting.length ? [{ key: 'recruit' as const, label: t('clubs.recruitingNow'), n: recruiting.length }] : []),
    ...(followed.length ? [{ key: 'follow' as const, label: t('clubs.following') }] : []),
    ...INTERESTS.filter((i) => live.some((o) => o.category === i.key)).map((i) => ({ ...i, label: t(`clubs.cat.${i.key}`) })),
    ...(schools.length ? [{ key: 'schools' as const, label: t('clubs.schoolsOffices') }] : []),
  ]);
  let picked = $state<Filter>('all');
  const filter = $derived(chips.some((c) => c.key === picked) ? picked : 'all'); // a chip that went (the last followed club) falls back
  const pick = (f: Filter) => { haptic.tap(); picked = f; };
  const rows = $derived(filter === 'all' ? [...live].sort((a, b) => b.rank - a.rank) : filter === 'recruit' ? recruiting : filter === 'follow' ? followed
    : filter === 'schools' ? schools : live.filter((o) => o.category === filter).sort((a, b) => b.rank - a.rank));
  const quiet = $derived(filter === 'all' ? clubs.filter((o) => o.quiet).sort(byWeight) : []);

  // a row's one line: a school's full name; an open round and its deadline; else what's next or latest there
  function line(o: Org): { text: string; hot: boolean } {
    if (SCHOOLISH.has(o.kind)) return { text: o.abbr && o.abbr !== nameOf(o) ? o.name : '', hot: false };
    if (o.round && outside(o) && !waitsDmp(o)) return { text: `${t('clubs.recruitingNow')} · ${roundDue(o.round.closesAt)}`, hot: true };
    return { text: clubSub(o, next), hot: !waitsDmp(o) && next.has(o.id) };
  }

  let dir = $state<HTMLElement>();
  const allCalls = () => { pick('recruit'); dir?.scrollIntoView({ behavior: 'smooth', block: 'start' }); };

  const chatFaces = $derived(data.chats ? (data.chats.forYou.length ? data.chats.forYou : data.chats.all).slice(0, 3) : []);
</script>

{#snippet row(o: Org)}
  {@const l = line(o)}
  {@const cta = filter === 'recruit' && !searching ? ctaOf.get(o.id) : undefined}
  <div class="row">
    <button class="rt" onclick={() => sheets.club(o.id)}>
      <span class="lg"><OrgLogo org={o} size={52} />{#if l.hot}<i class="dot"></i>{/if}</span>
      <span class="tx">
        <b><span class="ellipsis">{nameOf(o)}</span>{#if o.official && o.kind === 'club'}<OfficialMark size={15} />{/if}{#if o.gov}<GovMark size={14} />{/if}</b>
        {#if l.text}<small class={['ellipsis', { hot: l.hot }]}>{l.text}</small>{/if}
      </span>
      {#if o.friends.length && !cta}<span class="faces">{#each o.friends as p (p.id)}<Avatar person={p} size={24} tappable={false} />{/each}</span>{/if}
    </button>
    {#if cta}<Button kind={cta.done ? 'neutral' : 'primary'} size="s" disabled={cta.off} onclick={cta.run}>{cta.label}</Button>{/if}
  </div>
{/snippet}

<div class="page scroll stagger">
  <PullSearch bind:value={q} placeholder={t('clubs.search')} />

  {#if searching}
    <section class="found">
      {#each found as o (o.id)}{@render row(o)}{:else}<p class="none">{t('clubs.nothing')}</p>{/each}
    </section>
  {:else}
    <header class="head">
      <h1>{t('clubs.clubs')}</h1>
      {#if pulse}<p>{pulse}</p>{/if}
    </header>

    {#if mine.length}
      <section>
        <div class="hd"><h2>{t('clubs.mineTitle')}</h2></div>
        <div class="dock hscroll">
          {#each mine as m (m.org.id)}
            <button class="me press" onclick={() => openMine(m)} {@attach canLeave(m) && longPress(hold(m))}>
              <span class={['ring', { hot: next.has(m.org.id) }]}><OrgLogo org={m.org} size={58} /></span>
              <b class="ellipsis">{shortOf(m.org)}</b>
              <small class="ellipsis">{roleLabel(m)}</small>
            </button>
          {/each}
        </div>
      </section>
    {/if}

    {#if calls.length}
      <section>
        <div class="hd">
          <h2>{t('clubs.recruitingNow')}</h2>
          {#if calls.length > SHOWN}<button class="all" onclick={allCalls}>{t('clubs.allN', { n: recruiting.length })}</button>{/if}
        </div>
        <!-- keyed: castings come in after the rounds, and scroll snap would stay on the card it had, hiding them -->
        {#key castings.length}<div class={['calls', 'hscroll', { one: calls.length === 1 }]}>
          {#each calls.slice(0, SHOWN) as c (c.key)}
            {@const art = artOf(c.org)}
            {@const look = skinOf(c.org)}
            {@const tpl = look ? clubLook(look) : undefined}
            <!-- a template lanyard's picture is see-through: its ground and ink are the look's colours, as on its ticket -->
            <div class={['call', { look: tpl, paper: tpl?.ink }]} style={look && tpl ? lookVars(look) : undefined} style:background={tpl ? undefined : coverOf(c.org)}>
              {#if art}<img class="art" src={art} alt="" loading="lazy" decoding="async" draggable="false" />{/if}
              <i class="shade"></i>
              <button class="open" onclick={c.open} aria-label={c.org.name}></button>
              <span class="top">
                <OrgLogo org={c.org} size={44} />
                <span class={['when', { soon: c.soon, live: c.live }]}>{c.when}</span>
              </span>
              <span class="bot">
                <b class="clamp-2">{nameOf(c.org)}</b>
                <span class="act">
                  <small class="ellipsis">{c.sub}</small>
                  {#if c.cta}<button class={['go', { done: c.cta.done }]} disabled={c.cta.off} onclick={c.cta.run}>{c.cta.label}</button>{/if}
                </span>
              </span>
            </div>
          {/each}
        </div>{/key}
      </section>
    {/if}

    <section class="dir" bind:this={dir}>
      <div class="hd"><h2>{t('clubs.allClubs')}<i>{clubs.length}</i></h2></div>
      <div class="chips hscroll">
        {#each chips as c (c.key)}
          <button class={['chip', { on: filter === c.key }]} aria-pressed={filter === c.key} onclick={() => pick(c.key)}>
            {#if c.icon}<span class="ic" style:--c="var(--tile-{c.tint})"><c.icon size={15} strokeWidth={2.2} /></span>{/if}
            {c.label}{#if c.n}<i>{c.n}</i>{/if}
          </button>
        {/each}
      </div>
      {#each rows as o (o.id)}{@render row(o)}{/each}
      {#if quiet.length}
        <p class="cap">{t('clubs.quiet')}</p>
        <div class="still">{#each quiet as o (o.id)}{@render row(o)}{/each}</div>
      {/if}
    </section>

    <section class="more">
      {#if data.chats?.all.length}
        <button class="tile" onclick={() => sheets.chats(data.chats!.all)}>
          <span class="tt"><span class="badge tg"><TelegramMark size={20} /></span><span class="faces">{#each chatFaces as c (c.id)}<ChatAvatar title={c.title} photo={c.photo} kind={c.kind} size={24} />{/each}</span></span>
          <b>{t('chats.sheet')}</b>
        </button>
      {/if}
      <button class="tile" onclick={() => asStudent(() => sheets.createClub(), 'newclub')}>
        <span class="tt"><span class="badge"><Plus size={20} strokeWidth={2.4} /></span></span>
        <b>{t('create.button')}</b>
      </button>
    </section>
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; }
  section { margin-top: var(--s-7); }
  .found { margin-top: var(--s-1); } /* right under the capsule */

  /* the headline: the tab's name, and under it in the light voice how alive the clubs are today */
  .head { padding-top: var(--s-1); }
  h1 { font: 700 var(--fs-title)/1.1 var(--font-display); letter-spacing: -0.025em; }
  .head p { margin-top: var(--s-1); font: var(--fw-light) var(--fs-card)/1.3 var(--font-display); color: var(--text-2); }
  .tail { height: calc(var(--bottom) + var(--s-6)); }

  .hd { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s-3); margin-bottom: var(--s-3); }
  h2 { font: 700 var(--fs-sec)/1.15 var(--font-display); letter-spacing: -0.022em; }
  h2 i { margin-left: 7px; font-style: normal; font-weight: var(--fw-light); color: var(--text-3); font-variant-numeric: tabular-nums; }
  .all { position: relative; flex: none; font: 600 var(--fs-sub)/1 var(--font-text); color: var(--accent-text); }
  .all::after { content: ''; position: absolute; inset: -14px -8px; }

  /* a shelf runs edge to edge and starts on the gutter */
  .hscroll { gap: 10px; margin: 0 calc(-1 * var(--gutter)); padding: 0 var(--gutter); scroll-padding: 0 var(--gutter); }

  /* my clubs: a dock of marks, as apps on a home screen; a green ring when something is coming up there */
  .dock { gap: var(--s-2); padding-block: var(--s-1); }
  .me { flex: none; width: 76px; display: flex; flex-direction: column; align-items: center; gap: 3px; scroll-snap-align: start; color: var(--text); }
  .ring { display: flex; padding: 3px; border-radius: var(--r-l); box-shadow: inset 0 0 0 2px var(--line-2); }
  .ring.hot { box-shadow: inset 0 0 0 2px var(--success); }
  .me b { max-width: 100%; margin-top: 3px; font: 600 var(--fs-cap)/1.2 var(--font-text); }
  .me small { max-width: 100%; font: 500 var(--fs-micro)/1.2 var(--font-text); color: var(--text-3); }

  /* recruiting: the club's own cover, its name on it, the deadline in the corner and the one button */
  .call { position: relative; flex: none; width: min(312px, 86%); height: 204px; overflow: hidden; border-radius: var(--r-xl); color: var(--on-accent); scroll-snap-align: start; }
  .one .call { width: 100%; }
  .art, .shade { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .shade { background: linear-gradient(180deg, rgba(0, 0, 0, 0.14), rgba(0, 0, 0, 0) 36%, rgba(0, 0, 0, 0.7)); }
  .open { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }
  .open:active { transform: none; opacity: 1; } /* the press is the whole card's */
  .call { transition: transform 450ms var(--ease-bounce); }
  .call:has(.open:active) { transform: scale(0.98); transition-duration: 80ms; }
  .top { position: absolute; inset: 14px 14px auto; display: flex; align-items: flex-start; justify-content: space-between; gap: var(--s-2); }
  .top :global(.logo) { box-shadow: 0 6px 16px rgba(0, 0, 0, 0.28); }
  .when { display: flex; align-items: center; gap: 6px; min-width: 0; padding: 7px 11px; border-radius: var(--r-full); background: rgba(0, 0, 0, 0.44); font: 600 var(--fs-cap)/1 var(--font-text); white-space: nowrap; }
  .when.soon { color: var(--warning); }
  .when.live::before { content: ''; width: 7px; height: 7px; border-radius: var(--r-full); background: var(--success); }
  .bot { position: absolute; inset: auto 16px 14px; display: flex; flex-direction: column; gap: var(--s-2); }
  .bot b { font: 700 var(--fs-sec)/1.12 var(--font-display); letter-spacing: -0.022em; text-shadow: 0 1px 12px rgba(0, 0, 0, 0.3); }
  .act { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); min-height: var(--ctl-s); }
  .act small { min-width: 0; font: 500 var(--fs-sub)/1.3 var(--font-text); opacity: 0.86; }
  .go { position: relative; z-index: 2; flex: none; height: var(--ctl-s); padding: 0 14px; border-radius: var(--r-full); background: var(--on-accent); color: var(--ink); font: 600 var(--fs-sub)/1 var(--font-text); }
  .go::after { content: ''; position: absolute; inset: -4px 0; } /* 44 to the finger */
  .go.done { background: rgba(255, 255, 255, 0.24); color: var(--on-accent); }
  .go:disabled { opacity: 0.6; }
  /* a club's lanyard as the ground (lookVars, the ticket's .club): its colours and ink; on a light paper the foot washed
     in the paper instead of shaded dark, so the dark ink reads */
  .call.look { background: linear-gradient(155deg, var(--c1), var(--c2) 55%, var(--c3)); color: var(--ink); }
  .look .bot b { text-shadow: var(--tsh); }
  .paper .shade { background: linear-gradient(180deg, transparent 38%, var(--c2)); opacity: 0.82; }
  .paper .act small { color: var(--ink2); opacity: 1; }
  .paper .go { background: var(--ink); color: var(--c1); }
  .paper .go.done { background: transparent; box-shadow: inset 0 0 0 1.5px var(--ink2); color: var(--ink); }

  /* the list: chips that filter it in place, then plain rows on the ground */
  .dir { scroll-margin-top: var(--page-top); }
  .chips { margin-bottom: var(--s-2); padding-block: 2px; }
  .chip { flex: none; display: flex; align-items: center; gap: 6px; height: var(--ctl-s); padding: 0 14px; border-radius: var(--r-full); background: var(--surface); box-shadow: var(--card-rim, var(--shadow-card)); font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-2); white-space: nowrap; scroll-snap-align: start; }
  .chip.on { background: var(--text); color: var(--bg); box-shadow: none; }
  .chip i { font-style: normal; font-variant-numeric: tabular-nums; opacity: 0.6; }
  .ic { display: flex; color: var(--c); }
  .on .ic { color: inherit; }

  .row { position: relative; display: flex; align-items: center; gap: var(--s-2); }
  .rt { flex: 1; min-width: 0; display: flex; align-items: center; gap: var(--s-3); padding: 10px 0; text-align: left; color: var(--text); }
  .row :global(.btn) { flex: none; padding-inline: var(--s-3); font-size: var(--fs-sub); }
  .row + .row::before { content: ''; position: absolute; top: 0; left: 64px; right: 0; height: 0.5px; background: var(--separator); }
  .lg { position: relative; flex: none; display: flex; }
  .dot { position: absolute; right: -2px; bottom: -2px; width: 12px; height: 12px; border-radius: var(--r-full); background: var(--success); box-shadow: 0 0 0 2.5px var(--bg); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { display: flex; align-items: center; gap: var(--s-1); font: 600 var(--fs-card)/1.25 var(--font-text); letter-spacing: -0.012em; }
  .tx small { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .tx small.hot { font-weight: 500; color: var(--accent-text); }
  .faces { flex: none; display: flex; }
  .faces > :global(* + *) { margin-left: -7px; }
  .cap { margin: var(--s-5) 0 var(--s-1); font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-3); }
  .still { opacity: 0.62; }
  .none { padding: var(--s-10) 0; text-align: center; font: 450 var(--fs-body)/1.3 var(--font-text); color: var(--text-3); }

  .more { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .more > :only-child { grid-column: 1 / -1; }
  .tile { display: flex; flex-direction: column; justify-content: space-between; gap: var(--s-4); min-width: 0; padding: 14px; border-radius: var(--r-l); background: var(--surface); box-shadow: var(--card-rim, var(--shadow-card)); }
  .tt { display: flex; align-items: center; justify-content: space-between; }
  .badge { display: grid; place-items: center; width: 36px; height: 36px; border-radius: var(--r-s); background: var(--fill); }
  .badge.tg { background: var(--tile-blue); color: var(--on-accent); }
  .tile b { font: 600 var(--fs-body)/1.25 var(--font-text); letter-spacing: -0.01em; }
</style>
