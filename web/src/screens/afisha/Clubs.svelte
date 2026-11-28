<script lang="ts">
  // The Clubs tab, one page and nothing pushed from it, in the Profile's language: no page title, a stack of cards on
  // one 16 px rhythm. First who is recruiting now, each on the club's own badge: the very lanyard the Profile and the
  // ticket draw (ui/LanyardBand's art, its colours, its medallion top right, its strip at the foot, here with the
  // deadline and the one button); a club with no lanyard yet stands on its logo's colours in the same frame. Then my
  // clubs, a shelf of marks in a card (a
  // tap: Studio); then every club on one grouped card, rows with hairlines, that the chips filter in place (all by the
  // server's rank, recruiting with Apply on each row, followed, an interest, schools), the quiet clubs dimmed at its
  // end; last two tiles, the chats and a new club. Search (pulled down) swaps the page for what it found.
  import Briefcase from '@lucide/svelte/icons/briefcase';
  import Code from '@lucide/svelte/icons/code';
  import FlaskConical from '@lucide/svelte/icons/flask-conical';
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import Palette from '@lucide/svelte/icons/palette';
  import Plus from '@lucide/svelte/icons/plus';
  import Trophy from '@lucide/svelte/icons/trophy';
  import type { Membership, Org, OrgCategory, OrgRef, Post } from '../../lib/api';
  import { clubLook, lookVars, skinOf } from '../../lib/awards';
  import { byWeight, clubSub, hit, nextByOrg, roundDue, service, waitsDmp } from '../../lib/clubs';
  import { coverOf } from '../../lib/covers';
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
  import LanyardBand from '../../ui/LanyardBand.svelte';
  import OfficeMark from '../../ui/OfficeMark.svelte';
  import { longPress } from '../../ui/longpress';
  import { menu } from '../../ui/menu';
  import OfficialMark from '../../ui/OfficialMark.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import OrgMedal from '../../ui/OrgMedal.svelte';
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
  // a badge: the club, what it is in caps (its interest; a casting says to come), its people with my friends' faces, when
  type Call = { key: string; org: OrgRef; tag?: string; when: string; live?: boolean; sub: string; faces?: Org['friends']; open: () => void; cta?: { label: string; done: boolean; off?: boolean; run: () => void } };
  const kind = (o: Org) => (o.category ? t(`clubs.cat.${o.category}`) : undefined);
  const story = (p: Post) => sheets.stories([{ org: p.org, items: [{ post: p }], unread: false, cast: false }], 0);
  const calls = $derived<Call[]>([
    ...castings.map((p) => ({ key: `c${p.id}`, org: p.org, tag: t('casting.come'), when: castingStatus(p.casting!), live: castingState(p.casting!) === 'open', sub: p.casting!.place, open: () => story(p) })),
    ...rounds.map((o) => ({ key: `r${o.id}`, org: o, tag: kind(o), when: roundDue(o.round!.closesAt), sub: tn('club.members', o.members), faces: o.friends, open: () => sheets.club(o.id),
      cta: { label: t(o.round!.applied ? 'clubs.applied' : 'join.apply'), done: o.round!.applied, run: () => sheets.roundApply(o.id, 'join') } })),
    ...always.map((o) => ({ key: `a${o.id}`, org: o, tag: kind(o), when: t('clubs.openNow'), sub: tn('club.members', o.members), faces: o.friends, open: () => sheets.club(o.id),
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

  // a row's one line: a school's full name; else the club's life (what's next or latest there, its people), a green dot
  // when something is coming up. Recruiting is the badges' to say: a row says it only where the badges aren't, in the
  // Recruiting filter and in search, any kind of it in the same words and colour
  function line(o: Org): { text: string; hot: boolean; dot: boolean } {
    if (SCHOOLISH.has(o.kind)) return { text: o.abbr && o.abbr !== nameOf(o) ? o.name : '', hot: false, dot: false };
    const dot = !waitsDmp(o) && next.has(o.id);
    if ((filter === 'recruit' || searching) && outside(o) && !waitsDmp(o) && (o.round || o.recruiting))
      return { text: o.round ? `${t('clubs.openNow')} · ${roundDue(o.round.closesAt)}` : t('clubs.openNow'), hot: true, dot };
    return { text: clubSub(o, next), hot: false, dot };
  }

  let dir = $state<HTMLElement>(), shelf = $state<HTMLElement>();
  // castings come in after the rounds, at the shelf's start: back to it, or scroll snap keeps the card it had and hides them
  $effect(() => { void castings.length; if (shelf) shelf.scrollLeft = 0; });
  const allCalls = () => { pick('recruit'); dir?.scrollIntoView({ behavior: 'smooth', block: 'start' }); };

  const chatFaces = $derived(data.chats ? (data.chats.forYou.length ? data.chats.forYou : data.chats.all).slice(0, 3) : []);
</script>

{#snippet row(o: Org)}
  {@const l = line(o)}
  {@const cta = filter === 'recruit' && !searching ? ctaOf.get(o.id) : undefined}
  <div class="row">
    <button class="rt" onclick={() => sheets.club(o.id)}>
      <span class="lg"><OrgLogo org={o} size={46} />{#if l.dot}<i class="dot"></i>{/if}</span>
      <span class="tx">
        <b><span class="ellipsis">{nameOf(o)}</span>{#if o.official && o.kind === 'club'}<OfficialMark size={15} />{/if}{#if o.gov}<GovMark size={14} />{/if}{#if service(o)}<OfficeMark size={14} />{/if}</b>
        <!-- my friends there: their faces lead the line (at the row's end they read as unread marks) -->
        {#if l.text || o.friends.length}<small class={{ hot: l.hot }}>{#if o.friends.length}<span class="faces">{#each o.friends as p (p.id)}<Avatar person={p} size={18} tappable={false} />{/each}</span>{/if}<span class="ellipsis">{l.text || tn('club.members', o.members)}</span></small>{/if}
      </span>
    </button>
    {#if cta}<Button kind={cta.done ? 'neutral' : 'primary'} size="s" disabled={cta.off} onclick={cta.run}>{cta.label}</Button>{/if}
  </div>
{/snippet}

<div class="page scroll stagger">
  <PullSearch bind:value={q} placeholder={t('clubs.search')} />

  {#if searching}
    <section class="card list found">
      {#each found as o (o.id)}{@render row(o)}{:else}<p class="none">{t('clubs.nothing')}</p>{/each}
    </section>
  {:else}
    {#if calls.length}
      <section class={['calls', 'hscroll', { one: calls.length === 1 }]} aria-label={t('clubs.recruitingNow')} bind:this={shelf}>
        {#each calls.slice(0, SHOWN) as c (c.key)}
          {@const look = skinOf(c.org)}
          {@const tpl = look ? clubLook(look) : undefined}
          <!-- the club's lanyard as the Profile's badge and its ticket draw it; lookVars: the template's colours and ink -->
          <div class={['call', { club: tpl }]} style={look && tpl ? lookVars(look) : undefined} style:background={look ? undefined : coverOf(c.org)}>
            {#if look}<LanyardBand {look} wide qr />{:else}<i class="lit"></i>{/if}
            <button class="open" onclick={c.open} aria-label={c.org.name}></button>
            <span class="medal">{#if look}<OrgMedal {look} logo={c.org.logo ?? null} />{:else}<span class="rim"><OrgLogo org={c.org} size={46} /></span>{/if}</span>
            <span class="id">
              <b class="clamp-2">{nameOf(c.org)}</b>
              {#if c.tag}<i>{c.tag}</i>{/if}
              <small>{#if c.faces?.length}<span class="faces">{#each c.faces as p (p.id)}<Avatar person={p} size={18} tappable={false} />{/each}</span>{/if}<span class="ellipsis">{c.sub}</span></small>
            </span>
            <span class="strip">
              <span class={['when', 'ellipsis', { live: c.live }]}>{c.when}</span>
              {#if c.cta}<button class={['go', { done: c.cta.done }]} disabled={c.cta.off} onclick={c.cta.run}>{c.cta.label}</button>{/if}
            </span>
          </div>
        {/each}
        {#if calls.length > SHOWN}<button class="call rest press" onclick={allCalls}>{t('clubs.allN', { n: recruiting.length })}</button>{/if}
      </section>
    {/if}

    {#if mine.length}
      <section class="card">
        <div class="hd"><h2>{t('clubs.mineTitle')}</h2><span class="n">{mine.length}</span></div>
        <div class="dock hscroll">
          {#each mine as m (m.org.id)}
            <button class="me press" onclick={() => openMine(m)} {@attach canLeave(m) && longPress(hold(m))}>
              <span class={['ring', { hot: next.has(m.org.id) }]}><OrgLogo org={m.org} size={56} /></span>
              <b class="clamp-2">{shortOf(m.org)}</b>
              <small class="ellipsis">{roleLabel(m)}</small>
            </button>
          {/each}
        </div>
      </section>
    {/if}

    <section class="card list dir" bind:this={dir}>
      <div class="hd"><h2>{t('clubs.allClubs')}</h2><span class="n">{clubs.length}</span></div>
      {#if pulse}<p class="pulse">{pulse}</p>{/if}
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

    <section class="duo">
      {#if data.chats?.all.length}
        <button class="tile press" onclick={() => sheets.chats(data.chats!.all)}>
          <span class="tt"><span class="badge tg"><TelegramMark size={20} /></span><span class="faces">{#each chatFaces as c (c.id)}<ChatAvatar title={c.title} photo={c.photo} kind={c.kind} size={24} />{/each}</span></span>
          <b>{t('chats.sheet')}</b>
        </button>
      {/if}
      <button class="tile press" onclick={() => asStudent(() => sheets.createClub(), 'newclub')}>
        <span class="tt"><span class="badge"><Plus size={20} strokeWidth={2.4} /></span></span>
        <b>{t('create.button')}</b>
      </button>
    </section>
  {/if}
  <div class="tail"></div>
</div>

<style>
  /* the Profile's page: cards on the ground, 16 px apart, nothing loose between them */
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; }
  section { margin-top: var(--s-4); }
  .page > section:first-of-type { margin-top: 0; } /* right under the capsule, where the Profile's badge hangs */
  .tail { height: calc(var(--bottom) + var(--s-3)); }

  /* a card: the Profile's surface, its title in the card's own head with the count beside it (Awards' "2 of 16") */
  .card { border-radius: var(--r-l); background: var(--surface); box-shadow: var(--card-rim, var(--shadow-card)); }
  .hd { display: flex; align-items: baseline; justify-content: space-between; gap: var(--s-3); padding: 14px var(--s-4) 0; }
  h2 { font: 700 var(--fs-card)/1.2 var(--font-display); letter-spacing: -0.015em; }
  .n { flex: none; font: 600 var(--fs-body)/1 var(--font-text); color: var(--text-3); font-variant-numeric: tabular-nums; }

  /* a shelf runs to the card's (or the screen's) edges and starts on its padding */
  .hscroll { gap: 10px; padding-inline: var(--s-4); scroll-padding-inline: var(--s-4); }

  /* recruiting: the club's badge, the Profile's own (Hero's .badge): its lanyard's art and colours, the medallion top
     right, the name with its caps line and a grey line under it, and at the foot the lanyard's strip in its own metal,
     here saying until when, the one button on it */
  .calls { margin-inline: calc(-1 * var(--gutter)); padding-inline: var(--gutter); scroll-padding-inline: var(--gutter); gap: var(--s-3); }
  .call { position: relative; flex: none; width: 90%; height: 172px; overflow: hidden; border-radius: var(--r-l); color: var(--on-accent); scroll-snap-align: start;
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.28); transition: transform 450ms var(--ease-bounce); }
  .one .call { width: 100%; }
  .call:has(.open:active) { transform: scale(0.98); transition-duration: 80ms; }
  /* a shelf of badges holds still: one moving scene is the Profile's, ten in a row would cost the scroll */
  .call :global(.band *) { animation-play-state: paused !important; }
  .open { position: absolute; inset: 0; z-index: 1; border-radius: inherit; }
  .open:active { transform: none; opacity: 1; } /* the press is the whole card's */
  .medal { position: absolute; top: 14px; right: 14px; width: 52px; height: 52px; }
  .rim { display: block; padding: 3px; border-radius: var(--r-m); background: rgba(255, 255, 255, 0.85); box-shadow: 0 6px 14px -6px rgba(0, 0, 0, 0.4); }
  .rim :global(.logo) { border-radius: var(--r-s) !important; }
  .id { position: absolute; inset: 18px 80px auto 18px; display: flex; flex-direction: column; }
  .id b { font: 700 var(--fs-t3)/1.12 var(--font-display); letter-spacing: -0.025em; text-shadow: var(--tsh, 0 1px 10px rgba(0, 0, 0, 0.28)); }
  .id i { margin-top: 6px; font: 700 var(--fs-micro)/1.3 var(--font-text); font-style: normal; letter-spacing: 0.12em; text-transform: uppercase; color: var(--role, inherit); }
  .id small { display: flex; align-items: center; gap: 6px; margin-top: 3px; font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--ink2, rgba(255, 255, 255, 0.84)); }
  /* the strip: LanyardHolo's metal for a lanyard (its --h colours), pearl for a club without one */
  .strip { position: absolute; inset: auto 14px 14px; display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); height: var(--ctl-s); padding-left: var(--s-3);
    border-radius: var(--r-s); background: linear-gradient(100deg, var(--h1, white), var(--h2, rgb(232, 236, 246)) 50%, var(--h1, white)); color: var(--h3, var(--ink));
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.5), inset 0 -1px 2px rgba(0, 0, 0, 0.18), 0 4px 12px -6px rgba(0, 0, 0, 0.45); }
  .when { display: flex; align-items: center; gap: 6px; min-width: 0; font: 800 var(--fs-micro)/1 var(--font-text); letter-spacing: 0.12em; text-transform: uppercase; }
  .when.live::before { content: ''; flex: none; width: 7px; height: 7px; border-radius: var(--r-full); background: var(--success); }
  /* the one button: words on the strip itself, no pill in a tray */
  .go { position: relative; z-index: 2; flex: none; height: 100%; padding: 0 var(--s-3); color: inherit; font: 700 var(--fs-sub)/1 var(--font-text); }
  .go::after { content: ''; position: absolute; inset: -4px 0; } /* 44 to the finger */
  .go:not(.done)::before { content: ''; position: absolute; left: 0; top: 25%; bottom: 25%; width: 1px; background: currentColor; opacity: 0.25; }
  .go.done, .go:disabled { opacity: 0.6; }
  /* a club's template lanyard (lookVars, the ticket's .club): the card under its art, its ink */
  .call.club { background: linear-gradient(155deg, var(--c1), var(--c2) 55%, var(--c3)); color: var(--ink); }
  /* no lanyard yet: its logo's colours (coverOf) under a white gleam and a soft shade behind the words */
  .lit { position: absolute; inset: 0; background: radial-gradient(80% 110% at 100% 0%, rgba(255, 255, 255, 0.34), transparent 62%), linear-gradient(90deg, rgba(0, 0, 0, 0.22), transparent 60%); }
  /* past the first ten: the rest, in the list below */
  .call.rest { width: calc(var(--ctl-l) * 2); border-radius: var(--r-l); display: grid; place-items: center; background: var(--surface); box-shadow: var(--card-rim, var(--shadow-card)); color: var(--accent-text); font: 600 var(--fs-body)/1.2 var(--font-text); }

  /* my clubs: a shelf of marks in its card, as the medals in Awards, each name whole on two lines; a green ring only
     where something is coming up (a grey one on the rest was noise in light and nothing in dark) */
  .dock { gap: var(--s-1); padding: var(--s-3) 10px 14px; scroll-padding-inline: 10px; align-items: flex-start; }
  .me { flex: none; width: calc(var(--ctl-m) * 2); display: flex; flex-direction: column; align-items: center; gap: 3px; scroll-snap-align: start; color: var(--text); text-align: center; }
  .ring { display: flex; padding: 3px; border-radius: var(--r-l); }
  .ring.hot { box-shadow: inset 0 0 0 2px var(--success); }
  .me b { max-width: 100%; margin-top: 3px; font: 600 var(--fs-cap)/1.2 var(--font-text); }
  .me small { max-width: 100%; font: 500 var(--fs-micro)/1.2 var(--font-text); color: var(--text-3); }

  /* every club: one grouped card, Settings' rows with a hairline from the name; the chips filter it in place */
  .list { overflow: hidden; }
  .dir { scroll-margin-top: var(--page-top); }
  .pulse { padding: 3px var(--s-4) 0; font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  /* the row runs on under the card's edge: it fades out there instead of being cut mid-word */
  .chips { gap: var(--s-2); padding-block: var(--s-3) var(--s-1); padding-right: var(--s-8);
    -webkit-mask-image: linear-gradient(90deg, black calc(100% - var(--s-8)), transparent); mask-image: linear-gradient(90deg, black calc(100% - var(--s-8)), transparent); }
  .chip { flex: none; display: flex; align-items: center; gap: 6px; height: var(--ctl-s); padding: 0 14px; border-radius: var(--r-full); background: var(--fill); font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-2); white-space: nowrap; scroll-snap-align: start; }
  .chip.on { background: var(--text); color: var(--bg); }
  .chip i { font-style: normal; font-variant-numeric: tabular-nums; color: var(--text-3); }
  .chip.on i { color: inherit; opacity: 0.7; }
  .ic { display: flex; color: var(--c); }
  .on .ic { color: inherit; }

  .row { position: relative; display: flex; align-items: center; gap: var(--s-2); padding-inline: var(--s-4); }
  .rt { flex: 1; min-width: 0; display: flex; align-items: center; gap: var(--s-3); padding: 10px 0; text-align: left; color: var(--text); }
  .row :global(.btn) { flex: none; padding-inline: var(--s-3); font-size: var(--fs-sub); }
  .row + .row::before { content: ''; position: absolute; top: 0; left: 74px; right: 0; height: 0.5px; background: var(--separator); }
  .lg { position: relative; flex: none; display: flex; }
  .dot { position: absolute; right: -2px; bottom: -2px; width: 12px; height: 12px; border-radius: var(--r-full); background: var(--success); box-shadow: 0 0 0 2.5px var(--surface-solid); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { display: flex; align-items: center; gap: var(--s-1); font: 600 var(--fs-body)/1.25 var(--font-text); letter-spacing: -0.01em; }
  .tx small { display: flex; align-items: center; gap: 6px; font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .tx small.hot { font-weight: 500; color: var(--accent-text); }
  .faces { flex: none; display: flex; }
  small > .ellipsis { min-width: 0; }
  .faces > :global(* + *) { margin-left: -6px; }
  .row:last-child { padding-bottom: var(--s-1); }
  .found .row:first-child { padding-top: var(--s-1); }
  .cap { margin-top: var(--s-2); padding: var(--s-3) var(--s-4) var(--s-1); border-top: 0.5px solid var(--separator); font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-3); }
  /* quiet: the mark fades and the name steps back; the words keep their contrast */
  .still .lg { opacity: 0.55; }
  .still .tx b { color: var(--text-2); }
  .still .tx small { color: var(--text-3); }
  .none { padding: var(--s-10) 0; text-align: center; font: 450 var(--fs-body)/1.3 var(--font-text); color: var(--text-3); }

  /* the chats and a new club: two tiles, the Profile's pair under its badge */
  .duo { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-3); }
  .duo > :only-child { grid-column: 1 / -1; }
  .tile { display: flex; flex-direction: column; justify-content: space-between; gap: var(--s-5); min-width: 0; padding: 14px; border-radius: var(--r-l); text-align: left;
    background: radial-gradient(90% 70% at 15% 0%, var(--accent-soft), transparent 70%), var(--surface); box-shadow: var(--card-rim, var(--shadow-card)); }
  .tt { display: flex; align-items: center; justify-content: space-between; }
  .badge { display: grid; place-items: center; width: 36px; height: 36px; border-radius: var(--r-s); background: var(--fill); }
  .badge.tg { background: var(--tile-blue); color: var(--on-accent); }
  .tile b { font: 700 var(--fs-body)/1.25 var(--font-text); letter-spacing: -0.01em; }
</style>
