<script lang="ts">
  // My organizations first as cards; the recruiting shop window follows, or leads for newcomers.
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Button from '../../ui/Button.svelte';
  import Card from '../../ui/Card.svelte';
  import Code from '@lucide/svelte/icons/code';
  import Palette from '@lucide/svelte/icons/palette';
  import Trophy from '@lucide/svelte/icons/trophy';
  import Briefcase from '@lucide/svelte/icons/briefcase';
  import FlaskConical from '@lucide/svelte/icons/flask-conical';
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import LayoutGrid from '@lucide/svelte/icons/layout-grid';
  import GraduationCap from '@lucide/svelte/icons/graduation-cap';
  import PullSearch from '../../ui/PullSearch.svelte';
  import { data, loadChats, chatsFor, currentCastings, leaveClub, toggleJoin } from '../../lib/state/data.svelte';
  import Section from '../../ui/Section.svelte';
  import Group from '../../ui/Group.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import ChatAvatar from '../../ui/ChatAvatar.svelte';
  import { type Membership, type OrgCategory, type OrgRef } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { byWeight, clubSub, hit, nextByOrg, roundDue, waitsDmp } from '../../lib/clubs';
  import { byRank, canLeave, opensStudio, roleLabel } from '../../lib/perms';
  import Row from '../../ui/Row.svelte';
  import { nameOf } from '../../lib/short';
  import { haptic } from '../../lib/tg';
  import { longPress } from '../../ui/longpress';
  import { menu } from '../../ui/menu';
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
  const found = $derived(searching ? [...data.orgs, ...data.small].filter((o) => hit(o, q)).sort(byWeight) : []);
  const next = $derived(nextByOrg([...data.events, ...Object.values(data.studio).flat()].filter((e) => e.status === 'published')));

  type Mine = { org: OrgRef; role: string; membership: Membership; sub: string | undefined };
  const mine = $derived<Mine[]>([...(session.me?.memberships ?? [])].sort(byRank).map((m) => ({ org: m.org, role: roleLabel(m), membership: m, sub: next.get(m.org.id) })));
  const followed = $derived(clubsOnly.filter((o) => o.subscribed && !memberOf.has(o.id)).sort(byWeight));
  const openMine = (x: Mine) => { haptic.tap(); if (opensStudio(x.membership)) sheets.studio(x.org.id); else sheets.club(x.org.id); };
  const hold = (x: Mine) => (el: HTMLElement) => menu(el, [{ label: t('clubs.open'), onselect: () => openMine(x) }, { label: t('clubs.leave'), destructive: true, onselect: () => void leaveClub(x.membership) }]);
  const allMine = () => { haptic.tap(); sheets.myClubs(mine.map((x) => ({ org: x.org, role: x.role, sub: [x.role, x.sub].filter(Boolean).join(' · ') }))); };

  // Recruiting: castings (come in person) first, then every open round, none of clubs I'm in. The strip: 8 in all, rounds
  // official first, then by members; "All": each one, the rounds soonest first
  const memberOf = $derived(new Set((session.me?.memberships ?? []).map((m) => m.org.id)));
  const rounds = $derived(data.orgs.flatMap((o) => (o.round && !memberOf.has(o.id) && !o.myRole ? [{ org: o, round: o.round }] : [])));
  const alwaysOpen = $derived(clubsOnly.filter((o) => o.recruiting && !o.round && !memberOf.has(o.id) && !o.myRole).sort(byWeight));
  const castings = $derived(currentCastings().filter((p) => !memberOf.has(p.org.id)));
  const strip = $derived([...rounds].sort((a, b) => +!a.org.official - +!b.org.official || b.org.members - a.org.members || a.round.closesAt - b.round.closesAt).slice(0, Math.max(0, 8 - castings.length)));
  const allRounds = () => { haptic.tap(); sheets.myClubs([...castings.map((p) => ({ org: p.org, role: null, sub: `${t('casting.come')} · ${castingStatus(p.casting!)}` })), ...[...rounds].sort((a, b) => a.round.closesAt - b.round.closesAt).map((r) => ({ org: r.org, role: null, sub: roundDue(r.round.closesAt) })), ...alwaysOpen.map((org) => ({ org, role: null, sub: t('clubs.openNow') }))], t('clubs.recruitingNow')); };

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
        <div class="mine">
          {#each mine as x (x.org.id)}
            <Card>
              <button class="mc" onclick={() => openMine(x)} {@attach canLeave(x.membership) && longPress(hold(x))}>
                <OrgLogo org={x.org} size={48} />
                <span class="mine-text"><b>{nameOf(x.org)}</b><small>{x.role}</small>{#if x.sub}<span class="activity ellipsis">{x.sub}</span>{/if}</span>
                <ChevronRight size={18} />
              </button>
            </Card>
          {/each}
        </div>
      </Section>
    {/if}

    {#if strip.length || castings.length || alwaysOpen.length}
      <Section title={t('clubs.recruitingNow')} onmore={allRounds} moreLabel={t('clubs.allN', { n: rounds.length + castings.length + alwaysOpen.length })} loud>
        <!-- keyed: castings come in after the rounds, and scroll snap would stay on the card it had, hiding them -->
        {#if strip.length || castings.length}{#key castings.length}<div class="shelf hscroll">
          {#each castings.slice(0, 8) as p (p.id)}<div class="cast"><CastingCard post={p} /></div>{/each}
          {#each strip as r (r.org.id)}<RecruitCard org={r.org} round={r.round} />{/each}
        </div>{/key}{/if}
        {#if alwaysOpen.length}<Group>
          {#each alwaysOpen.slice(0, 3) as o (o.id)}
            <ClubRow org={o} name={nameOf(o)} sub={t('clubs.openNow')}>
              {#snippet end()}<Button kind="secondary" size="s" disabled={o.myRequest === 'rejected'} onclick={() => toggleJoin(o.id)}>{t(o.myRequest === 'rejected' ? 'join.notNow' : o.myRequest === 'pending' ? 'join.sent' : 'join.apply')}</Button>{/snippet}
            </ClubRow>
          {/each}
        </Group>{/if}
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

    {#if followed.length}
      <Section title={t('clubs.following')}>
        <Group>{#each followed as o (o.id)}<ClubRow org={o} name={nameOf(o)} sub={clubSub(o, next)} />{/each}</Group>
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

  .mine { display: flex; flex-direction: column; gap: var(--s-2); }
  .mc { width: 100%; display: flex; align-items: center; gap: var(--s-3); text-align: left; }
  .mc :global(svg) { flex: none; color: var(--text-3); }
  .mine-text { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--s-1); }
  .mine-text b { font: 700 var(--fs-card)/1.25 var(--font-text); letter-spacing: -0.01em; overflow-wrap: anywhere; }
  .mine-text small { font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .activity { margin-top: var(--s-1); font: 500 var(--fs-cap)/1.3 var(--font-text); color: var(--accent-text); }

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
