<script lang="ts">
  // A page pushed from the Clubs tab, live from the store. all: every club under its heading, official first, the quiet
  // ones folded into the last row of Initiatives (search opens them up), then "Create a club"; quiet: those; schools:
  // schools and offices; an interest: its clubs by the server's rank, the first as a wide poster, the next three on a shelf, the rest as rows (quiet clubs aren't in an interest).
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import type { Org, OrgCategory } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { data } from '../../lib/state/data.svelte';
  import { asStudent } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { clubSub, hit, nextByOrg, roundDue, waitsDmp } from '../../lib/clubs';
  import { nameOf } from '../../lib/short';
  import Pane from '../../ui/Pane.svelte';
  import { TAB_ICON } from '../../ui/icons';
  import Section from '../../ui/Section.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import ClubRow from '../../ui/ClubRow.svelte';
  import ClubPoster from '../../ui/ClubPoster.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay, view }: { overlay: Overlay; view: 'all' | 'schools' | 'quiet' | OrgCategory } = $props();

  const title = $derived(view === 'all' ? t('clubs.allClubs') : view === 'schools' ? t('clubs.schoolsOffices') : view === 'quiet' ? t('clubs.quiet') : t(`clubs.cat.${view}`));
  const next = $derived(nextByOrg(data.events));
  const bySize = (a: Org, b: Org) => +!a.gov - +!b.gov || b.members - a.members || b.subscribers - a.subscribers || a.name.localeCompare(b.name, 'ru');
  const SCHOOLISH = new Set(['school', 'office']);
  const clubs = $derived(data.orgs.filter((o) => !SCHOOLISH.has(o.kind)));

  let q = $state('');
  const searching = $derived(!!q.trim());
  const quiet = $derived(clubs.filter((o) => o.quiet).sort(bySize));
  const shown = $derived(searching ? [...clubs, ...data.small.filter((o) => !SCHOOLISH.has(o.kind))].filter((o) => hit(o, q)) : clubs);
  const folded = $derived(!searching && quiet.length > 0);
  const parts = $derived([
    { key: 'official', title: t('clubs.headOfficial'), orgs: shown.filter((o) => o.official).sort(bySize) },
    { key: 'initiatives', title: t('clubs.headInitiatives'), orgs: shown.filter((o) => !o.official && (searching || !o.quiet)).sort((a, b) => +!a.top - +!b.top || bySize(a, b)) },
  ].filter((p) => p.orgs.length || (p.key === 'initiatives' && folded)));

  const schools = $derived(data.orgs.filter((o) => SCHOOLISH.has(o.kind)).sort((a, b) => a.kind.localeCompare(b.kind) || nameOf(a).localeCompare(nameOf(b), 'ru')));
  const interest = $derived(clubs.filter((o) => o.category === view && !o.quiet).sort((a, b) => b.rank - a.rank));
  const lead = (o: Org) => next.get(o.id) ?? (o.round ? `${tn('club.members', o.members)} · ${roundDue(o.round.closesAt)}` : tn('club.members', o.members));
</script>

{#snippet go()}<span class="chev"><ChevronRight size={18} /></span>{/snippet}

<Pane {overlay} {title} icon={TAB_ICON.club}>
  {#if view === 'all'}
    <SearchField bind:value={q} placeholder={t('clubs.search')} />
    {#each parts as p (p.key)}
      <div class="part"><Section title={p.title} count={p.orgs.length}>
        <Group footnote={p.key === 'initiatives' ? t('clubs.initiativeNote') : undefined}>
          {#each p.orgs as o (o.id)}<ClubRow org={o} sub={clubSub(o, next)} hot={!waitsDmp(o) && next.has(o.id)} social />{/each}
          {#if p.key === 'initiatives' && folded}<Row title={tn('clubs.quietN', quiet.length)} accessory="chevron" onclick={() => sheets.clubList('quiet')} />{/if}
        </Group>
      </Section></div>
    {:else}<EmptyState inline text={t('clubs.nothing')} />{/each}
    <div class="part"><Group><Row tone="add" title={t('create.button')} accessory="chevron" onclick={() => asStudent(() => sheets.createClub(), 'newclub')} /></Group></div>
  {:else if view === 'quiet'}
    <Group>{#each quiet as o (o.id)}<ClubRow org={o} social />{/each}</Group>
  {:else if view === 'schools'}
    <Group>
      {#each schools as o (o.id)}<ClubRow org={o} name={nameOf(o)} sub={o.abbr && o.abbr !== nameOf(o) ? o.name : ''}>{#snippet end()}{@render go()}{/snippet}</ClubRow>{/each}
    </Group>
  {:else}
    {#if interest[0]}<ClubPoster org={interest[0]} sub={lead(interest[0])} wide />{/if}
    {#if interest.length > 1}
      <div class="shelf hscroll">{#each interest.slice(1, 4) as o (o.id)}<ClubPoster org={o} sub={next.get(o.id) ?? tn('club.members', o.members)} />{/each}</div>
    {/if}
    {#if interest.length > 4}
      <div class="part"><Group>{#each interest.slice(4) as o (o.id)}<ClubRow org={o} sub={clubSub(o, next)} hot={next.has(o.id)} social />{/each}</Group></div>
    {/if}
  {/if}
</Pane>

<style>
  .part { margin-top: var(--s-6); }
  .shelf { gap: 10px; margin: 10px calc(-1 * var(--gutter)) 0; padding: 0 var(--gutter); scroll-padding: 0 var(--gutter); }
  .chev { display: flex; margin-right: 2px; color: var(--text-3); opacity: 0.6; pointer-events: none; }
</style>
