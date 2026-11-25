<script lang="ts">
  // The Clubs tab, one page and no pushed lists: a headline with what's alive; my clubs as a dock of marks (a tap is
  // their Studio); the open doors (castings, rounds, clubs taking people any time), the soonest first; then the whole
  // catalogue as a grid that interest chips filter in place, the quiet clubs folded at its end. Everything is the store's.
  import Code from '@lucide/svelte/icons/code';
  import Palette from '@lucide/svelte/icons/palette';
  import Trophy from '@lucide/svelte/icons/trophy';
  import Briefcase from '@lucide/svelte/icons/briefcase';
  import FlaskConical from '@lucide/svelte/icons/flask-conical';
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import GraduationCap from '@lucide/svelte/icons/graduation-cap';
  import Plus from '@lucide/svelte/icons/plus';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import type { Membership, Org, OrgCategory, OrgRef, Post } from '../../lib/api';
  import { data, loadChats, chatsFor, currentCastings, leaveClub, toggleJoin } from '../../lib/state/data.svelte';
  import { asStudent, session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { byWeight, daysLeft, hit, nextByOrg, roundDue } from '../../lib/clubs';
  import { castingStatus } from '../../lib/posts';
  import { byRank, canLeave, roleLabel } from '../../lib/perms';
  import { nameOf, shortOf } from '../../lib/short';
  import { haptic } from '../../lib/tg';
  import { longPress } from '../../ui/longpress';
  import { menu } from '../../ui/menu';
  import PullSearch from '../../ui/PullSearch.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Button from '../../ui/Button.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import ClubTile from './ClubTile.svelte';

  let q = $state('');
  const searching = $derived(!!q.trim());
  $effect(() => { if ((session.me?.id ?? null) !== chatsFor) loadChats(); });

  const SCHOOLISH = new Set(['school', 'office']);
  const clubs = $derived(data.orgs.filter((o) => !SCHOOLISH.has(o.kind)));
  const next = $derived(nextByOrg([...data.events, ...Object.values(data.studio).flat()].filter((e) => e.status === 'published')));
  const alive = $derived(clubs.filter((o) => next.has(o.id)).length);

  // the dock: every club I'm in, highest role first; a tap is its Studio (owner, Nov 21), a hold offers Leave
  const mine = $derived([...(session.me?.memberships ?? [])].sort(byRank));
  const memberOf = $derived(new Set(mine.map((m) => m.org.id)));
  const openMine = (m: Membership) => { haptic.tap(); sheets.studio(m.org.id); };
  const hold = (m: Membership) => (el: HTMLElement) => menu(el, [{ label: t('clubs.open'), onselect: () => openMine(m) }, { label: t('clubs.leave'), destructive: true, onselect: () => void leaveClub(m) }]);

  // open doors, none of clubs I'm in: come in person first, then rounds closing soonest, then the always-open ones
  type Door = { key: string; org: OrgRef; line: string; soon?: boolean; post?: Post; club?: Org };
  const outside = (o: Org) => !memberOf.has(o.id) && !o.myRole;
  const doors = $derived<Door[]>([
    ...currentCastings().filter((p) => !memberOf.has(p.org.id)).map((p) => ({ key: `c${p.id}`, org: p.org, post: p, line: `${castingStatus(p.casting!)} · ${p.casting!.place}` })),
    ...data.orgs.filter((o) => o.round && outside(o)).sort((a, b) => a.round!.closesAt - b.round!.closesAt)
      .map((o) => ({ key: `r${o.id}`, org: o, club: o, line: roundDue(o.round!.closesAt), soon: daysLeft(o.round!.closesAt) <= 3 })),
    ...clubs.filter((o) => o.recruiting && !o.round && outside(o)).sort(byWeight).map((o) => ({ key: `a${o.id}`, org: o, club: o, line: t('clubs.openNow') })),
  ]);
  let allDoors = $state(false);
  const shownDoors = $derived(allDoors ? doors : doors.slice(0, 4));
  const openDoor = (d: Door) => {
    haptic.tap();
    if (d.post) sheets.stories([{ org: d.post.org, items: [{ post: d.post }], unread: false, cast: false }], 0);
    else sheets.club(d.org.id);
  };

  // the catalogue: interests that have a live club, then schools; gov first, then the server's rank (members and life)
  type Pick = 'all' | 'schools' | OrgCategory;
  const INTERESTS: { key: OrgCategory; icon: typeof Code }[] = [{ key: 'it', icon: Code }, { key: 'art', icon: Palette }, { key: 'sport', icon: Trophy },
    { key: 'business', icon: Briefcase }, { key: 'science', icon: FlaskConical }, { key: 'volunteer', icon: HeartHandshake }];
  let pick = $state<Pick>('all');
  let showQuiet = $state(false);
  const interests = $derived(INTERESTS.filter((i) => clubs.some((o) => !o.quiet && o.category === i.key)));
  const byLife = (a: Org, b: Org) => +!a.gov - +!b.gov || b.rank - a.rank || byWeight(a, b);
  const pool = $derived(pick === 'schools' ? data.orgs.filter((o) => SCHOOLISH.has(o.kind)) : clubs.filter((o) => pick === 'all' || o.category === pick));
  const live = $derived(pool.filter((o) => !o.quiet).sort(byLife));
  const quiet = $derived(pool.filter((o) => o.quiet).sort(byWeight));
  const choose = (p: Pick) => { if (p === pick) return; haptic.select(); pick = p; showQuiet = false; };

  const found = $derived(searching ? [...data.orgs, ...data.small].filter((o) => hit(o, q)).sort(byWeight) : []);
</script>

{#snippet grid(orgs: Org[])}
  <div class="grid">{#each orgs as o (o.id)}<ClubTile org={o} next={next.get(o.id)} />{/each}</div>
{/snippet}

<div class="page scroll">
  <PullSearch bind:value={q} placeholder={t('clubs.search')} />

  {#if searching}
    <h2 class="cap">{t('clubs.found')} <span>{found.length}</span></h2>
    {#if found.length}{@render grid(found)}{:else}<EmptyState inline text={t('clubs.nothing')} />{/if}
  {:else}
    <header class="head">
      <h1>{t('clubs.clubs')}</h1>
      <p>{#if alive}<span>{tn('clubs.aliveN', alive)}</span>{/if}{#if alive && doors.length}<span class="dot"></span>{/if}{#if doors.length}<span>{tn('clubs.doorsN', doors.length)}</span>{/if}</p>
    </header>

    {#if mine.length}
      <section>
        <h2 class="cap">{t('clubs.mineTitle')}</h2>
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

    {#if doors.length}
      <section>
        <h2 class="cap">{t('clubs.recruitingNow')} <span>{doors.length}</span></h2>
        <div class="doors">
          {#each shownDoors as d (d.key)}
            <div class="door">
              <button class="dt" onclick={() => openDoor(d)}>
                <OrgLogo org={d.org} size={44} />
                <span class="dx">
                  <b class="ellipsis">{d.post ? t('casting.come') : nameOf(d.org)}</b>
                  <small class={['ellipsis', { soon: d.soon, now: !!d.post }]}>{d.post ? `${nameOf(d.org)} · ${d.line}` : d.line}</small>
                </span>
              </button>
              {#if d.club?.round}
                <Button kind={d.club.round.applied ? 'neutral' : 'primary'} size="s" onclick={() => sheets.roundApply(d.org.id, 'join')}>{t(d.club.round.applied ? 'clubs.applied' : 'join.apply')}</Button>
              {:else if d.club}
                <Button kind={d.club.myRequest ? 'neutral' : 'primary'} size="s" disabled={d.club.myRequest === 'rejected'} onclick={() => toggleJoin(d.org.id)}>{t(d.club.myRequest === 'rejected' ? 'join.notNow' : d.club.myRequest === 'pending' ? 'clubs.applied' : 'join.apply')}</Button>
              {:else}
                <span class="chev"><ChevronRight size={18} /></span>
              {/if}
            </div>
          {/each}
          {#if doors.length > shownDoors.length}
            <button class="more" onclick={() => { haptic.tap(); allDoors = true; }}>{t('clubs.allN', { n: doors.length })}</button>
          {/if}
        </div>
      </section>
    {/if}

    <section>
      <h2 class="cap">{t('clubs.catalogue')}</h2>
      <div class="chips hscroll">
        <button class="chip" aria-pressed={pick === 'all'} onclick={() => choose('all')}>{t('common.all')} <span>{clubs.length}</span></button>
        {#each interests as i (i.key)}
          <button class="chip" aria-pressed={pick === i.key} onclick={() => choose(i.key)}><i.icon size={15} />{t(`clubs.cat.${i.key}`)}</button>
        {/each}
        <button class="chip" aria-pressed={pick === 'schools'} onclick={() => choose('schools')}><GraduationCap size={15} />{t('clubs.schools')}</button>
      </div>
      {@render grid(live)}
      {#if quiet.length}
        {#if showQuiet}{@render grid(quiet)}
        {:else}<button class="more alone" onclick={() => { haptic.tap(); showQuiet = true; }}>{tn('clubs.quietN', quiet.length)}</button>{/if}
      {/if}
    </section>

    <div class="tail-acts">
      <button class="act" onclick={() => asStudent(() => sheets.createClub(), 'newclub')}><span class="ai"><Plus size={18} /></span>{t('create.button')}</button>
      {#if data.chats?.all.length}
        <button class="act" onclick={() => sheets.chats(data.chats!.all)}><span class="ai"><TelegramMark size={16} /></span>{t('chats.sheet')}</button>
      {/if}
    </div>
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; }
  section { margin-top: var(--s-7); }

  /* the headline: the tab's name, and under it in the light voice how alive the clubs are today */
  .head { padding-top: var(--s-1); }
  h1 { font: 700 var(--fs-title)/1.1 var(--font-display); letter-spacing: -0.025em; }
  .head p { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s-2); margin-top: var(--s-1); font: var(--fw-light) var(--fs-card)/1.3 var(--font-display); color: var(--text-2); }
  .dot { width: 4px; height: 4px; border-radius: var(--r-full); background: var(--text-3); }

  .cap { display: flex; align-items: baseline; gap: 6px; margin-bottom: var(--s-3); font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.015em; }
  .cap span { font-weight: 450; color: var(--text-3); }

  /* my clubs: a dock of marks, as apps on a home screen; a green ring when something is coming up there */
  .dock { gap: var(--s-2); margin: 0 calc(-1 * var(--gutter)); padding: var(--s-1) var(--gutter); scroll-padding: 0 var(--gutter); }
  .me { flex: none; width: 76px; display: flex; flex-direction: column; align-items: center; gap: 3px; scroll-snap-align: start; color: var(--text); }
  .ring { display: flex; padding: 3px; border-radius: var(--r-l); box-shadow: inset 0 0 0 2px var(--line-2); }
  .ring.hot { box-shadow: inset 0 0 0 2px var(--success); }
  .me b { max-width: 100%; margin-top: 3px; font: 600 var(--fs-cap)/1.2 var(--font-text); }
  .me small { max-width: 100%; font: 500 var(--fs-micro)/1.2 var(--font-text); color: var(--text-3); }

  /* open doors: one card of rows, each with its one action at the edge */
  .doors { overflow: hidden; border-radius: var(--r-group); background: var(--surface); box-shadow: var(--card-rim), var(--shadow-card); }
  .door { position: relative; display: flex; align-items: center; gap: var(--s-2); padding-right: var(--s-3); }
  .door + .door::before, .more::before { content: ''; position: absolute; top: 0; left: 68px; right: 0; height: 0.5px; background: var(--separator); }
  .dt { flex: 1; min-width: 0; display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) 0 var(--s-3) var(--s-3); text-align: left; color: var(--text); }
  .dx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .dx b { font: 600 var(--fs-body)/1.25 var(--font-text); }
  .dx small { font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .dx small.soon { color: var(--warning-text); }
  .dx small.now { color: var(--success-text); }
  .door :global(.btn) { flex: none; padding-inline: var(--s-3); font-size: var(--fs-sub); }
  .chev { flex: none; display: flex; color: var(--text-3); }
  .more { position: relative; width: 100%; height: var(--ctl-m); font: 600 var(--fs-body)/1 var(--font-text); color: var(--accent-text); }
  .more.alone { margin-top: var(--s-3); border-radius: var(--r-group); background: var(--surface); box-shadow: var(--card-rim); }
  .more.alone::before { display: none; }

  /* interests: chips that filter the grid in place; the chosen one in ink, as iOS's filter pills */
  .chips { gap: var(--s-2); margin: 0 calc(-1 * var(--gutter)) var(--s-3); padding: 0 var(--gutter); }
  .chip { flex: none; display: flex; align-items: center; gap: 6px; height: var(--ctl-s); padding: 0 14px; border-radius: var(--r-full); background: var(--fill); color: var(--text); font: 600 var(--fs-sub)/1 var(--font-text); transition: background var(--t-fast) var(--ease), color var(--t-fast) var(--ease); }
  .chip span { font-weight: 450; opacity: 0.6; }
  .chip[aria-pressed='true'] { background: var(--text); color: var(--bg); }

  .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .grid + .grid { margin-top: 10px; }

  .tail-acts { display: flex; flex-direction: column; gap: var(--s-2); margin-top: var(--s-7); }
  .act { display: flex; align-items: center; gap: var(--s-3); height: var(--row-h); padding: 0 var(--s-4) 0 var(--s-3); border-radius: var(--r-group); background: var(--surface); box-shadow: var(--card-rim), var(--shadow-card); font: var(--fw-row) var(--fs-body)/1 var(--font-text); color: var(--text); }
  .ai { display: grid; place-items: center; width: 30px; height: 30px; border-radius: var(--r-xs); background: var(--accent-soft); color: var(--accent-text); }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
