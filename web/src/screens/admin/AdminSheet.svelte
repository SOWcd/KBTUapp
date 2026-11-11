<script lang="ts">
  // The Admin sheet (owner + review Nov 3, .claude/reports/admin-home-review.md §A): one page, no segments. A search on
  // top (iOS Settings: while typed, the page steps aside for People, Clubs and Awards); "To decide" first whenever
  // something waits (where it stands is fixed for this opening, so a decided last card doesn't jump the page); the
  // admins' numbers card; then the places, one group of rows. A moderator gets the queue and his two places only.
  // Events in the same search (owner, Nov 7): a tap runs one as its organizers do in Studio (EventManage, staff).
  // "An event for a club" (owner, Nov 11: clubs ask the creator to post theirs): pick the club, the usual editor as staff.
  // The map's flaws: a quiet row at the very bottom (owner, Nov 7: the card on top pulled from moderation).
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import Building from '@lucide/svelte/icons/building-2';
  import MedalIcon from '@lucide/svelte/icons/medal';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import ScrollText from '@lucide/svelte/icons/scroll-text';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import Users from '@lucide/svelte/icons/users';
  import Bell from '@lucide/svelte/icons/bell';
  import MapPinned from '@lucide/svelte/icons/map-pinned';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import { untrack, type Component } from 'svelte';
  import { api, staffEvents, type EventCard, type OrgRef, type StaffRow } from '../../lib/api';
  import { hit } from '../../lib/clubs';
  import { hit as match } from '../../lib/search';
  import { CATALOG, manualMedal, manualTitle } from '../../lib/awards';
  import { data, eventById } from '../../lib/state/data.svelte';
  import { relDay } from '../../lib/time';
  import Poster from '../../ui/Poster.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { session } from '../../lib/state/session.svelte';
  import { open, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Medal from '../../ui/Medal.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import AdminInbox from './AdminInbox.svelte';
  import AdminStats from './AdminStats.svelte';
  import AdminAwards from './AdminAwards.svelte';
  import AdminPeople from './AdminPeople.svelte';
  import AdminNotify from './AdminNotify.svelte';
  import AdminEventFor from './AdminEventFor.svelte';
  import AwardPane from './AwardPane.svelte';
  import PersonPane from './PersonPane.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const admin = $derived(session.me?.role === 'admin');
  const owner = $derived(admin && !!session.me?.founder);
  // where the queue stands, once per opening: on top when something waits (moderators: always)
  const queueFirst = untrack(() => !admin || !!data.inbox?.items.length);

  // ---- the search: clubs and awards on the first key (held already), people a beat after the last one (the server)
  let q = $state('');
  const s = $derived(q.trim().toLowerCase().replace(/^@/, ''));
  let people = $state<StaffRow[] | null>(null);
  let found = $state<{ events: EventCard[]; clubs: OrgRef[] } | null>(null);
  $effect(() => {
    const k = s;
    people = null; found = null;
    if (k.length < 2 && !/^\d+$/.test(k)) return;
    const id = setTimeout(() => {
      api.staffSearch(k).then((l) => { if (s === k) people = l; }).catch(() => { if (s === k) people = []; });
      if (admin && k.length >= 2) api.search(k).then((l) => { if (s === k) found = l; }).catch(() => { if (s === k) found = { events: [], clubs: [] }; });
    }, 300);
    return () => clearTimeout(id);
  });
  /** An event from the search, run as its organizers do: its routes go as staff (api staffEvents) while it's open. */
  function manage(e: EventCard) {
    if (!eventById(e.id)) data.opened.push(e);
    staffEvents.add(e.id);
    sheets.manage(e.id, true);
  }
  const status = (e: EventCard) => (e.status === 'draft' ? t('studio.draft') : e.status === 'cancelled' ? t('event.cancelled') : '');
  // clubs: the ones held at once, then the server's (hidden ones too, every language's name)
  const events = $derived(found?.events);
  const clubs = $derived(found ? found.clubs.slice(0, 8) : s ? data.orgs.filter((o) => hit(o, s)).slice(0, 8) : []);
  const awards = $derived(s ? CATALOG.filter((a) => (!a.creator || owner) && match(s, [manualTitle(a)])) : []);
  const go = (f: () => unknown) => { haptic.tap(); f(); };
</script>

<!-- a place: the editor's look (EventEditor's rows: a plain grey line icon, no tile) -->
{#snippet place(Icon: Component<any>, title: string, to: () => unknown)}
  <Row {title} accessory="chevron" onclick={() => go(to)}>{#snippet lead()}<span class="gi"><Icon size={22} strokeWidth={1.9} /></span>{/snippet}</Row>
{/snippet}

<!-- the title is the capsule's, with the shield (not twice) -->
<Sheet {overlay} full title={t('me.admin')} icon={ShieldCheck}>
  {#if admin}<div class="find"><SearchField bind:value={q} placeholder={t('adm.findAll')} /></div>{/if}

  {#if s}
    <div class="page">
      {#if people?.length}
        <Group caption={t('adm.people')}>
          {#each people as p (p.person.id)}
            <Row dense title={p.person.name} subtitle={p.username ? '@' + p.username : undefined} value={p.owner ? t('staff.owner') : p.role !== 'user' ? t(`staff.role.${p.role}`) : undefined}
              accessory="chevron" onclick={() => go(() => open(PersonPane, { row: p }))}>
              {#snippet lead()}<Avatar person={p.person} size={36} tappable={false} />{/snippet}
            </Row>
          {/each}
        </Group>
      {/if}
      {#if events?.length}
        <Group caption={t('adm.events')}>
          {#each events as e (e.id)}
            <Row dense title={e.title} subtitle={[e.org.name, relDay(e.startsAt), status(e)].filter(Boolean).join(' · ')} accessory="chevron" onclick={() => go(() => manage(e))}>
              {#snippet lead()}<Poster item={e} size={36} radius={10} dim={e.status !== 'published'} />{/snippet}
            </Row>
          {/each}
        </Group>
      {/if}
      {#if clubs.length}
        <Group caption={t('adm.clubs')}>
          {#each clubs as o (o.id)}
            <Row dense title={o.name} accessory="chevron" onclick={() => go(() => sheets.adminClubs(o.id))}>
              {#snippet lead()}<OrgLogo org={o} size={36} />{/snippet}
            </Row>
          {/each}
        </Group>
      {/if}
      {#if awards.length}
        <Group caption={t('adm.awards')}>
          {#each awards as a (a.code)}
            <Row dense title={manualTitle(a)} accessory="chevron" onclick={() => go(() => open(AwardPane, { award: a }))}>
              {#snippet lead()}<Medal a={manualMedal(a.code, a.emoji)} size={36} />{/snippet}
            </Row>
          {/each}
        </Group>
      {/if}
      {#if people && !people.length && !events?.length && !clubs.length && !awards.length}<EmptyState inline text={t('adm.nothingFound')} />{/if}
    </div>
  {/if}

  <!-- hidden, not gone, while a search is typed: the queue keeps its decided lines and their Undo -->
  <div class="page stagger" hidden={!!s}>
    {#if queueFirst}<AdminInbox />{/if}
    {#if admin}<AdminStats />{/if}
    {#if !queueFirst}<AdminInbox />{/if}
    <Group>
      {#if admin}
        {@render place(MedalIcon, t('adm.awards'), () => open(AdminAwards, {}))}
        {@render place(Building, t('adm.clubs'), () => sheets.adminClubs())}
        {@render place(CalendarPlus, t('adm.eventFor'), () => open(AdminEventFor, {}))}
      {/if}
      {@render place(TelegramMark, t('adm.chats'), () => sheets.adminChats())}
      {@render place(MessagesSquare, t('adm.forumChannel'), () => sheets.adminForum())}
      {#if admin}{@render place(Users, t('adm.team'), () => open(AdminPeople, {}))}{/if}
      {#if owner}{@render place(ScrollText, t('audit.title'), () => sheets.adminAudit())}{/if}
      {@render place(Bell, t('adm.notify'), () => open(AdminNotify, {}))}
    </Group>
    {#if data.inbox?.flaws}
      <Group><Row title={t('mf.title')} value={String(data.inbox.flaws)} accessory="chevron" onclick={() => go(() => sheets.mapFlaws())}>
        {#snippet lead()}<span class="gi"><MapPinned size={22} strokeWidth={1.9} /></span>{/snippet}</Row></Group>
    {/if}
  </div>
</Sheet>

<style>
  .find { margin-bottom: var(--s-5); }
  .page { display: flex; flex-direction: column; gap: var(--s-7); }
  .page[hidden] { display: none; }
  .gi { display: inline-flex; width: 26px; justify-content: center; color: var(--text-2); }
</style>
