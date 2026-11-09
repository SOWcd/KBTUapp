<script lang="ts">
  // The Clubs tab, top down (the owner's v3, Nov 9): my clubs; open rounds as cards, at most 8, official first (every
  // round is behind "All"); interests; popular; rows to all clubs, schools and KBTU's chats. The search waits above the
  // top until the list is pulled down (PullSearch, as on every tab but Profile); typing turns the tab into the results.
  import Code from '@lucide/svelte/icons/code';
  import Palette from '@lucide/svelte/icons/palette';
  import Trophy from '@lucide/svelte/icons/trophy';
  import Briefcase from '@lucide/svelte/icons/briefcase';
  import FlaskConical from '@lucide/svelte/icons/flask-conical';
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import LayoutGrid from '@lucide/svelte/icons/layout-grid';
  import GraduationCap from '@lucide/svelte/icons/graduation-cap';
  import PullSearch from '../../ui/PullSearch.svelte';
  import { data, loadChats, chatsFor, currentCastings } from '../../lib/state/data.svelte';
  import Section from '../../ui/Section.svelte';
  import Group from '../../ui/Group.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import ChatAvatar from '../../ui/ChatAvatar.svelte';
  import { type OrgCategory, type OrgRef } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { byWeight, clubSub, hit, nextByOrg, roundDue, waitsDmp } from '../../lib/clubs';
  import { byRank, roleLabel } from '../../lib/perms';
  import Row from '../../ui/Row.svelte';
  import { nameOf } from '../../lib/short';
  import { SvelteSet } from 'svelte/reactivity';
  import { haptic } from '../../lib/tg';
  import ClubPoster from '../../ui/ClubPoster.svelte';
  import ClubRow from '../../ui/ClubRow.svelte';
  import RecruitCard from '../../ui/RecruitCard.svelte';
  import CastingCard from '../../ui/CastingCard.svelte';
  import { castingStatus } from '../../lib/posts';

  let q = $state('');
  const searching = $derived(!!q.trim());
  $effect(() => { if ((session.me?.id ?? null) !== chatsFor) loadChats(); });

  const SCHOOLISH = new Set(['school', 'office']);
  const clubsOnly = $derived(data.orgs.filter((o) => !SCHOOLISH.has(o.kind)));
  const found = $derived(searching ? [...data.orgs].filter((o) => hit(o, q)).sort(byWeight) : []);
  const next = $derived(nextByOrg(data.events));

  // My clubs: the ones I'm in (by my rank; lead: President or Vice there), then the ones I follow
  type Mine = { org: OrgRef; role: string | null; lead: boolean };
  const mine = $derived.by<Mine[]>(() => {
    const ms = [...(session.me?.memberships ?? [])].sort(byRank);
    const inIds = new Set(ms.map((m) => m.org.id));
    return [...ms.map((m) => ({ org: m.org, role: roleLabel(m), lead: m.role === 'president' || m.role === 'vice' })),
      ...clubsOnly.filter((o) => o.subscribed && !inIds.has(o.id)).sort(byWeight).map((o) => ({ org: o, role: null, lead: false }))];
  });
  const openMine = (x: Mine) => { haptic.tap(); if (x.role) sheets.studio(x.org.id); else sheets.club(x.org.id); };
  const allMine = () => { haptic.tap(); sheets.myClubs(mine.map((x) => ({ org: x.org, role: x.role, sub: `${x.role ?? t('clubs.following')} · ${next.get(x.org.id) ?? t('clubs.nothingSoon')}` }))); };
  // a strip name: the short one when the full one runs past the logo's column (StoryRow's rule), measured once each
  const tight = new SvelteSet<number>();
  let pen: CanvasRenderingContext2D | null = null;
  const fit = (o: OrgRef) => (node: HTMLElement) => {
    if (!o.abbr) return;
    pen ??= document.createElement('canvas').getContext('2d');
    if (!pen) return;
    pen.font = getComputedStyle(node).font;
    if (pen.measureText(nameOf(o)).width > 70) tight.add(o.id);
  };

  // Recruiting: castings (come in person) first, then every open round, none of clubs I'm in. The strip: 8 in all, rounds
  // official first, then by members; "All": each one, the rounds soonest first
  const memberOf = $derived(new Set((session.me?.memberships ?? []).map((m) => m.org.id)));
  const rounds = $derived(data.orgs.flatMap((o) => (o.round && !memberOf.has(o.id) && !o.myRole ? [{ org: o, round: o.round }] : [])));
  const castings = $derived(currentCastings().filter((p) => !memberOf.has(p.org.id)));
  const strip = $derived([...rounds].sort((a, b) => +!a.org.official - +!b.org.official || b.org.members - a.org.members || a.round.closesAt - b.round.closesAt).slice(0, Math.max(0, 8 - castings.length)));
  const allRounds = () => { haptic.tap(); sheets.myClubs([...castings.map((p) => ({ org: p.org, role: null, sub: `${t('casting.come')} · ${castingStatus(p.casting!)}` })), ...[...rounds].sort((a, b) => a.round.closesAt - b.round.closesAt).map((r) => ({ org: r.org, role: null, sub: roundDue(r.round.closesAt) }))], t('clubs.recruitingNow')); };

  // interests: the ones with a live club in them. Popular: the server's rank
  const live = $derived(clubsOnly.filter((o) => !o.quiet));
  const INTERESTS = [{ key: 'it', icon: Code, tint: 'blue' }, { key: 'art', icon: Palette, tint: 'pink' }, { key: 'sport', icon: Trophy, tint: 'orange' },
    { key: 'business', icon: Briefcase, tint: 'indigo' }, { key: 'science', icon: FlaskConical, tint: 'teal' }, { key: 'volunteer', icon: HeartHandshake, tint: 'green' }] as const;
  const interests = $derived(INTERESTS.filter((i) => live.some((o) => o.category === i.key)));
  const openInterest = (key: OrgCategory) => { haptic.tap(); sheets.clubList(key); };
  const popular = $derived([...live].sort((a, b) => b.rank - a.rank).slice(0, 8));

  const chatFaces = $derived(data.chats ? (data.chats.forYou.length ? data.chats.forYou : data.chats.all).slice(0, 3) : []);
</script>

<div class="page scroll stagger">
  <PullSearch bind:value={q} placeholder={t('clubs.search')} />

  {#if searching}
    <Section title={t('clubs.found')} count={found.length}>
      <Group>
        {#each found as o (o.id)}<ClubRow org={o} name={nameOf(o)} sub={o.kind === 'school' && o.abbr ? o.name : clubSub(o, next)} hot={!waitsDmp(o) && next.has(o.id)} />
        {:else}<EmptyState inline text={t('clubs.nothing')} />{/each}
      </Group>
    </Section>
  {:else}
    {#if mine.length}
      <Section title={t('clubs.mineTitle')} onmore={allMine}>
        <div class="strip hscroll">
          {#each mine as x (x.org.id)}
            <button class="mc" onclick={() => openMine(x)}>
              <OrgLogo org={x.org} size={64} />
              <b class="ellipsis" {@attach fit(x.org)}>{tight.has(x.org.id) ? x.org.abbr : nameOf(x.org)}</b>
              <small class={['ellipsis', { lead: x.lead }]}>{x.role ?? t('clubs.following')}</small>
            </button>
          {/each}
        </div>
      </Section>
    {/if}

    {#if strip.length || castings.length}
      <Section title={t('clubs.recruitingNow')} onmore={allRounds} moreLabel={t('clubs.allN', { n: rounds.length + castings.length })} loud>
        <!-- keyed: castings come in after the rounds, and scroll snap would stay on the card it had, hiding them -->
        {#key castings.length}<div class="shelf hscroll">
          {#each castings.slice(0, 8) as p (p.id)}<div class="cast"><CastingCard post={p} /></div>{/each}
          {#each strip as r (r.org.id)}<RecruitCard org={r.org} round={r.round} />{/each}
        </div>{/key}
      </Section>
    {/if}

    {#if interests.length}
      <Section title={t('clubs.interests')}>
        <div class="ints">
          {#each interests as i (i.key)}
            <button class="int" style:--c="var(--tile-{i.tint})" onclick={() => openInterest(i.key)}>
              <span class="ic"><i.icon size={20} strokeWidth={2} /></span>
              <b>{t(`clubs.cat.${i.key}`)}</b>
            </button>
          {/each}
        </div>
      </Section>
    {/if}

    {#if popular.length}
      <Section title={t('clubs.popular')}>
        <div class="shelf hscroll">
          {#each popular as o (o.id)}<ClubPoster org={o} sub={next.get(o.id) ?? tn('club.members', o.members)} />{/each}
        </div>
      </Section>
    {/if}

    <div class="rows">
      <Group>
        <Row title={t('clubs.allClubs')} icon={LayoutGrid} tile="gray" value={String(clubsOnly.length)} accessory="chevron" onclick={() => sheets.clubList('all')} />
        <Row title={t('clubs.schoolsOffices')} icon={GraduationCap} tile="gray" value={String(data.orgs.length - clubsOnly.length)} accessory="chevron" onclick={() => sheets.clubList('schools')} />
      </Group>
      {#if data.chats?.all.length}
        <Group>
          <Row title={t('chats.sheet')} accessory="chevron" onclick={() => sheets.chats(data.chats!.all)}>
            {#snippet lead()}<span class="tg"><TelegramMark size={18} /></span>{/snippet}
            {#snippet detail()}<span class="faces">{#each chatFaces as c (c.id)}<ChatAvatar title={c.title} photo={c.photo} kind={c.kind} size={28} />{/each}</span>{/snippet}
          </Row>
        </Group>
      {/if}
    </div>
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; }
  /* the sections a screen's section apart (28), the first right under the capsule (PullSearch's two nodes before it) */
  .page > :global(.sec) { margin-top: var(--s-7); }
  .page > :global(.hold + .sec) { margin-top: var(--s-1); }

  .strip { gap: 14px; margin: 0 calc(-1 * var(--gutter)); padding: 2px var(--gutter) 0; scroll-padding: 0 var(--gutter); }
  .mc { flex: none; width: 70px; display: flex; flex-direction: column; align-items: center; text-align: center; scroll-snap-align: start; }
  .mc b { width: 100%; margin-top: 7px; font: 600 var(--fs-cap)/1.25 var(--font-text); }
  .mc small { width: 100%; font: 500 var(--fs-micro)/1.3 var(--font-text); color: var(--text-3); }
  .mc small.lead { color: var(--accent-text); font-weight: 600; }

  .shelf { gap: 10px; margin: 0 calc(-1 * var(--gutter)); padding: 0 var(--gutter) var(--s-2); scroll-padding: 0 var(--gutter); }

  .cast { flex: none; width: 262px; display: flex; scroll-snap-align: start; }
  .cast :global(.cc) { height: 100%; }

  /* interests: quiet tiles on the card surface, only the small glyph carries the colour */
  .ints { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: var(--s-2); }
  .int { display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px; height: 84px; padding: 0 var(--s-1); border-radius: var(--r-m); background: var(--surface); box-shadow: var(--shadow-card); }
  .ic { position: relative; display: grid; place-items: center; width: 36px; height: 36px; border-radius: var(--r-s); color: var(--c); }
  .ic::before { content: ''; position: absolute; inset: 0; border-radius: inherit; background: var(--c); opacity: 0.13; }
  .int b { max-width: 100%; font: 600 var(--fs-sub)/1.1 var(--font-text); letter-spacing: -0.01em; }
  @media (max-width: 360px) { .int b { font-size: var(--fs-micro); } }

  .rows { display: flex; flex-direction: column; gap: var(--s-3); margin-top: var(--s-7); }
  .tg { display: grid; place-items: center; width: 30px; height: 30px; border-radius: var(--r-xs); background: var(--tile-blue); color: var(--on-accent); }
  .faces { display: flex; }
  .faces :global(.ca + .ca) { margin-left: -8px; }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
