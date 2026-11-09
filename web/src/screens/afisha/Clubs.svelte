<script lang="ts">
  // The Clubs tab, top down (the owner's mockup, Nov 8):
  //   My clubs     one strip of logos, my role under each; a club I'm in opens its Studio, one I follow its page
  //   search       RevealSearch; typing turns the tab into the results
  //   Recruiting   open rounds as cards in a row (RecruitCard); my own clubs aren't here
  //   Catalog      official / initiatives / schools and offices: one list
  //   two rows     create a club, KBTU's chats (a club's own chats stay on its page)
  // The Student Government first wherever it shows.
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import RevealSearch from '../../ui/RevealSearch.svelte';
  import { data, loadChats, chatsFor } from '../../lib/state/data.svelte';
  import Section from '../../ui/Section.svelte';
  import Group from '../../ui/Group.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayMonthShort, nowTs, time, weekdayShort } from '../../lib/time';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import { type Org, type OrgRef } from '../../lib/api';
  import { asStudent, session } from '../../lib/state/session.svelte';
  import { byWeight, hit } from '../../lib/clubs';
  import { byRank, roleLabel } from '../../lib/perms';
  import Row from '../../ui/Row.svelte';
  import { nameOf } from '../../lib/short';
  import { SvelteSet } from 'svelte/reactivity';
  import { haptic } from '../../lib/tg';
  import ClubRow from '../../ui/ClubRow.svelte';
  import RecruitCard from '../../ui/RecruitCard.svelte';

  let q = $state('');
  const searching = $derived(!!q.trim());
  $effect(() => { if ((session.me?.id ?? null) !== chatsFor) loadChats(); });

  const SCHOOLISH = new Set(['school', 'office']);
  const clubsOnly = $derived(data.orgs.filter((o) => !SCHOOLISH.has(o.kind)));
  const bySize = (a: Org, b: Org) => +!a.gov - +!b.gov || b.members - a.members || b.subscribers - a.subscribers || a.name.localeCompare(b.name, 'ru');
  const found = $derived(searching ? [...data.orgs].filter((o) => hit(o, q)).sort(byWeight) : []);

  // the catalog: one list at a time. Initiatives: the Ascent's top (server clubs.py) first, then by size
  let seg = $state<'official' | 'initiatives' | 'schools'>('official');
  const segs = $derived([{ value: 'official' as const, label: t('clubs.segOfficial') }, { value: 'initiatives' as const, label: t('clubs.segInitiatives') }, { value: 'schools' as const, label: t('clubs.schools') }]);
  const catalog = $derived(
    seg === 'schools' ? data.orgs.filter((o) => SCHOOLISH.has(o.kind)).sort((a, b) => a.kind.localeCompare(b.kind) || nameOf(a).localeCompare(nameOf(b), 'ru'))
    : seg === 'official' ? clubsOnly.filter((o) => o.official).sort(bySize)
    : clubsOnly.filter((o) => !o.official).sort((a, b) => +!a.top - +!b.top || bySize(a, b)));

  // what's next at each club: its soonest event
  const next = $derived.by(() => {
    const m = new Map<number, string>(), now = nowTs();
    for (const e of [...data.events].sort((a, b) => a.startsAt - b.startsAt))
      if (e.status !== 'cancelled' && e.startsAt > now && !m.has(e.org.id))
        m.set(e.org.id, `${e.startsAt - now < 6 * 86400 ? weekdayShort(e.startsAt) : dayMonthShort(e.startsAt)} ${time(e.startsAt)} · ${e.title}`);
    return m;
  });

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

  // Recruiting: time-limited rounds only, the soonest deadline first (a club taking applications any time says so on its
  // catalog row: 31 of them would flood the strip)
  const mineIds = $derived(new Set(mine.map((x) => x.org.id)));
  const rounds = $derived(data.orgs.flatMap((o) => (o.round && !mineIds.has(o.id) && !o.myRole ? [{ org: o, round: o.round }] : []))
    .sort((a, b) => a.round.closesAt - b.round.closesAt || byWeight(a.org, b.org)));
  const openLine = (o: Org) => (o.recruiting && !o.round && !o.myRole ? t('clubs.openNow') : ''); // takes applications any time
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
  // the row's line: what's next, else its latest event of the last 30 days (quiet, no dot), else its people
  const sub = (o: Org) => next.get(o.id) ?? (o.last ? `${weekdayShort(o.last.startsAt)}, ${dayMonthShort(o.last.startsAt)} · ${o.last.title}` : null) ?? (o.members ? tn('club.members', o.members) : tn('clubs.subscribers', o.subscribers));
  const waiting = (o: Org) => !!o.top && !o.official; // at the Ascent's top: its line says it's waiting for DMP
</script>

<div class="page scroll stagger">
  {#if mine.length && !searching}
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

  <RevealSearch bind:value={q} placeholder={t('clubs.search')} />

  {#if searching}
    <Section title={t('clubs.found')} count={found.length}>
      <Group>
        {#each found as o (o.id)}<ClubRow org={o} name={nameOf(o)} sub={o.kind === 'school' && o.abbr ? o.name : sub(o)} hot={next.has(o.id)} />
        {:else}<EmptyState inline text={t('clubs.nothing')} />{/each}
      </Group>
    </Section>
  {:else}
    {#if rounds.length}
      <Section title={t('clubs.recruitingNow')}>
        <div class="cards hscroll">
          {#each rounds as r (r.org.id)}<RecruitCard org={r.org} round={r.round} />{/each}
        </div>
      </Section>
    {/if}

    {#if data.orgs.length}
      <Section title={t('clubs.catalog')} count={catalog.length}>
        <Segmented items={segs} bind:value={seg} label={t('clubs.catalog')} />
        <Group footnote={seg === 'initiatives' ? t('clubs.initiativeNote') : undefined}>
          {#each catalog as o (o.id)}
            {#if seg === 'schools'}
              <ClubRow org={o} name={nameOf(o)} sub={o.abbr && o.abbr !== nameOf(o) ? o.name : sub(o)}>
                {#snippet end()}<span class="chev"><ChevronRight size={18} /></span>{/snippet}
              </ClubRow>
            {:else}
              <ClubRow org={o} sub={waiting(o) ? t('clubs.awaitsDmp') : [openLine(o), next.get(o.id) ?? (openLine(o) ? '' : sub(o))].filter(Boolean).join(' · ')} hot={!waiting(o) && next.has(o.id)} />
            {/if}
          {:else}<EmptyState inline text={t('clubs.nothing')} />{/each}
        </Group>
      </Section>
    {/if}
  {/if}

  <div class="rows">
    <Group>
      <Row tone="add" title={t('create.button')} accessory="chevron" onclick={() => asStudent(() => sheets.createClub(), 'newclub')} />
      {#if data.chats?.all.length}
        <Row title={t('chats.sheet')} accessory="chevron" onclick={() => sheets.chats(data.chats!.all)}>
          {#snippet lead()}<span class="tg"><TelegramMark size={20} /></span>{/snippet}
        </Row>
      {/if}
    </Group>
  </div>
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; }
  /* the sections a screen's section apart (28), the first right under the capsule */
  .page > :global(.sec) { margin-top: var(--s-7); }
  .page > :global(.sec:first-child) { margin-top: var(--s-1); }

  /* My clubs: the page's edges bled; the 5th logo peeks */
  .strip { gap: 14px; margin: 0 calc(-1 * var(--gutter)); padding: 2px var(--gutter) 0; scroll-padding: 0 var(--gutter); }
  .mc { flex: none; width: 70px; display: flex; flex-direction: column; align-items: center; text-align: center; scroll-snap-align: start; }
  .mc b { width: 100%; margin-top: 7px; font: 600 var(--fs-cap)/1.25 var(--font-text); }
  .mc small { width: 100%; font: 500 var(--fs-micro)/1.3 var(--font-text); color: var(--text-3); }
  .mc small.lead { color: var(--accent-text); font-weight: 600; }

  /* Recruiting: cards in a row */
  .cards { gap: 10px; margin: 0 calc(-1 * var(--gutter)); padding: 0 var(--gutter) var(--s-2); scroll-padding: 0 var(--gutter); }

  .chev { display: flex; margin-right: 2px; color: var(--text-3); opacity: 0.6; pointer-events: none; } /* the tap is the row's */

  .rows { margin-top: var(--s-3); }
  .tg { width: 30px; display: grid; place-items: center; color: var(--text-2); }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
