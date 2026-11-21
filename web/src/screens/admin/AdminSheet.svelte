<script lang="ts">
  // The Admin sheet (few tabs and buttons, none doing the same: type an organization and go). Everything starts from the search on top: organizations first, then
  // people, events (a tap runs one as its organizers do in Studio: EventManage, staff) and awards. Before a letter is
  // typed: what waits (its first cards inline, AdminInbox limit), the organizations opened last, the
  // admins' numbers, then the few places that are lists of their own. "An event for a club" and "A club's Studio" are
  // not places: they are on the organization's page (AdminOrg), where the search leads.
  // A moderator has no search: his sheet is the queue itself and his two places.
  import { staffOnly } from '../../lib/state/staffGate.svelte';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import Building from '@lucide/svelte/icons/building-2';
  import MedalIcon from '@lucide/svelte/icons/medal';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import ScrollText from '@lucide/svelte/icons/scroll-text';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import Users from '@lucide/svelte/icons/users';
  import Bell from '@lucide/svelte/icons/bell';
  import MapPinned from '@lucide/svelte/icons/map-pinned';
  import { untrack, type Component } from 'svelte';
  import { api, staffEvents, type AdminOrg, type EventCard, type OrgRef, type StaffRow } from '../../lib/api';
  import { hit } from '../../lib/clubs';
  import { hit as match } from '../../lib/search';
  import { CATALOG, manualMedal, manualTitle } from '../../lib/awards';
  import { adminOrgs, byRecent, loadAdminOrgs, orgLine } from '../../lib/state/adminOrgs.svelte';
  import { data, eventById, loadInbox } from '../../lib/state/data.svelte';
  import { relDay } from '../../lib/time';
  import Poster from '../../ui/Poster.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { session } from '../../lib/state/session.svelte';
  import { open, type Overlay } from '../../lib/state/ui.svelte';
  import { fmtNum, i18n, t } from '../../lib/i18n/index.svelte';
  import { notificationSettings } from '../profile/notificationSettings';
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
  import AdminQueue from './AdminQueue.svelte';
  import AdminStats from './AdminStats.svelte';
  import AdminAwards from './AdminAwards.svelte';
  import AdminPeople from './AdminPeople.svelte';
  import AdminNotify from './AdminNotify.svelte';
  import AdminOrgPane from './AdminOrg.svelte';
  import AwardPane from './AwardPane.svelte';
  import PersonPane from './PersonPane.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  staffOnly(() => overlay, 'staff');
  const admin = $derived(session.me?.role === 'admin');
  const owner = $derived(admin && !!session.me?.founder);
  const percent = $derived(new Intl.NumberFormat(i18n.lang, { style: 'percent', maximumFractionDigits: 1 }));
  const rate = (count: number, sent: number) => sent ? percent.format(count / sent) : '—';
  untrack(() => { if (admin) { void loadAdminOrgs(); void loadInbox(true); } }); // fresh on every opening; what the app holds shows meanwhile

  // ---- the search: organizations and awards on the first key (held already), people and events a beat after the last
  let q = $state('');
  // the search is the admins' alone: a role stepping down to moderator with the sheet open leaves no query, no
  // results and nothing hiding the queue
  const s = $derived(admin ? q.trim().toLowerCase().replace(/^@/, '') : '');
  $effect(() => { if (!admin) q = ''; });
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
  const events = $derived(found?.events);
  // organizations: the admin's own list (hidden ones and offices too), the ones opened last first; until it is read,
  // the clubs the app holds
  const all = $derived<OrgRef[]>((admin ? adminOrgs.list : null) ?? data.orgs);
  // what the server found too (a club approved a moment ago, a name the list doesn't hold): after the ones held
  const clubs = $derived.by(() => {
    if (!s) return [];
    const held = all.filter((o) => hit(o, s) || o.slug.includes(s)).sort(byRecent);
    return [...held, ...(found?.clubs ?? []).filter((o) => !held.some((h) => h.id === o.id))].slice(0, 8);
  });
  const recent = $derived(!admin ? [] : adminOrgs.recent.map((id) => all.find((o) => o.id === id)).filter((o) => !!o).slice(0, 3));
  const awards = $derived(s ? CATALOG.filter((a) => (!a.creator || owner) && match(s, [manualTitle(a)])) : []);
  const line = (o: OrgRef) => ('team' in o ? [(o as AdminOrg).hidden ? t('adm.hiddenTag') : '', o.kind === 'school' ? t('adm.kindSchool') : '', orgLine(o as AdminOrg)].filter(Boolean).join(' · ') : undefined);
  const go = (f: () => unknown) => { haptic.tap(); f(); };
</script>

<!-- a place: the editor's look (EventEditor's rows: a plain grey line icon, no tile) -->
{#snippet place(Icon: Component<any>, title: string, to: () => unknown, count = 0, value?: string)}
  <Row {title} {count} {value} accessory="chevron" onclick={() => go(to)}>{#snippet lead()}<span class="gi"><Icon size={22} strokeWidth={1.9} /></span>{/snippet}</Row>
{/snippet}
{#snippet orgRow(o: OrgRef)}
  <Row dense title={o.name} subtitle={line(o)} accessory="chevron" onclick={() => go(() => open(AdminOrgPane, { org: o }))}>
    {#snippet lead()}<OrgLogo org={o} size={36} />{/snippet}
  </Row>
{/snippet}

<!-- the title is the capsule's, with the shield (not twice) -->
<Sheet {overlay} full title={t('me.admin')} icon={ShieldCheck}>
  {#if admin}<div class="find"><SearchField bind:value={q} placeholder={t('adm.findAll')} /></div>{/if}

  {#if s}
    <div class="page">
      {#if clubs.length}
        <Group caption={t('adm.clubs')}>{#each clubs as o (o.id)}{@render orgRow(o)}{/each}</Group>
      {/if}
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

  <!-- hidden, not gone, while a search is typed: a moderator's queue keeps its decided lines and their Undo -->
  <div class="page stagger" hidden={!!s}>
    {#if admin}
      <AdminInbox limit={3} more={() => open(AdminQueue, {})} />
      {#if recent.length}
        <Group caption={t('adm.recent')}>{#each recent as o (o.id)}{@render orgRow(o)}{/each}</Group>
      {/if}
      <AdminStats />
    {:else}
      <AdminInbox />
    {/if}
    <Group>
      {#if admin}
        {@render place(Building, t('adm.clubs'), () => sheets.adminClubs())}
        {@render place(MedalIcon, t('adm.awards'), () => open(AdminAwards, {}))}
      {/if}
      {@render place(TelegramMark, t('adm.chats'), () => sheets.adminChats())}
      {@render place(MessagesSquare, t('adm.forumChannel'), () => sheets.adminForum())}
      {#if admin}{@render place(Users, t('adm.team'), () => open(AdminPeople, {}))}{/if}
      {#if owner}{@render place(ScrollText, t('audit.title'), () => sheets.adminAudit())}{/if}
      {@render place(Bell, t('adm.notify'), () => open(AdminNotify, {}))}
      <!-- the map's flaws: quiet and last (a card on top pulled from moderation) -->
      {#if data.inbox?.flaws}{@render place(MapPinned, t('mf.title'), () => sheets.mapFlaws(), 0, String(data.inbox.flaws))}{/if}
    </Group>
    {#if admin && data.adminStats?.notificationCounts}
      <Group caption={t('adm.notificationStats')} footnote={t('adm.notificationStats.period')}>
        {#each data.adminStats.notificationCounts as { category, sent, useful, turnedOff } (category)}
          {@const label = notificationSettings.find(([key]) => key === category)?.[1]}
          {#if label}
            <Row dense title={t(label)} subtitle={t('adm.notificationStats.counts', {
              sent: fmtNum(sent), useful: fmtNum(useful), usefulRate: rate(useful, sent), off: fmtNum(turnedOff), offRate: rate(turnedOff, sent),
            })} />
          {/if}
        {/each}
      </Group>
    {/if}
  </div>
</Sheet>

<style>
  .find { margin-bottom: var(--s-5); }
  .page { display: flex; flex-direction: column; gap: var(--s-6); }
  .page[hidden] { display: none; }
  .gi { display: inline-flex; width: 26px; justify-content: center; color: var(--text-2); }
</style>
