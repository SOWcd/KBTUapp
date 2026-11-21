<script lang="ts">
  // Studio (few buttons, no idle panels; the Admin sheet's way): the name with one + (the Create
  // menu); the event of the day with the door, the screen's one main button; what waits for me; the club's places as
  // plain rows (the Ascent's ladder and the club's profile among them, a tap deeper); then the events by tabs.
  import Plus from '@lucide/svelte/icons/plus';
  import Gift from '@lucide/svelte/icons/gift';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import Users from '@lucide/svelte/icons/users';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import Pencil from '@lucide/svelte/icons/pencil';
  import Eye from '@lucide/svelte/icons/eye';
  import PenLine from '@lucide/svelte/icons/pen-line';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import MountainSnow from '@lucide/svelte/icons/mountain-snow';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import X from '@lucide/svelte/icons/x';
  import { fold } from '../../ui/fold';
  import { fitTitle, largeTitle } from '../../ui/title';
  import AscentPane from './AscentPane.svelte';
  import { api, type CohostInvite, type EventCard, type OfficialPath, type Round } from '../../lib/api';
  import { loadMe, session } from '../../lib/state/session.svelte';
  import { ui, say, open } from '../../lib/state/ui.svelte';
  import { haptic } from '../../lib/tg';
  import { data, loadStudio, studioChanged } from '../../lib/state/data.svelte';
  import { untrack } from 'svelte';
  import { sheets, registration } from '../../lib/state/sheets';
  import { t, tn, placeOf } from '../../lib/i18n/index.svelte';
  import { relDay, time, nowTs, dayNo, dayMonth, duration, at as tsAt } from '../../lib/time';
  import Clock from '@lucide/svelte/icons/clock';
  import { may, byRank, roleName, roleLabel, titleOf } from '../../lib/perms';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Poster from '../../ui/Poster.svelte';
  import EventRow from '../../ui/EventRow.svelte';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import ReceiptIcon from '@lucide/svelte/icons/receipt';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import Mail from '@lucide/svelte/icons/mail';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import { menu, type MenuItem } from '../../ui/menu';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Crown from '@lucide/svelte/icons/crown';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import BookUser from '@lucide/svelte/icons/book-user';
  import Network from '@lucide/svelte/icons/network';
  import FileDown from '@lucide/svelte/icons/file-down';
  import { ApiErr } from '../../lib/api';
  import { shareInvite } from '../../lib/invite';
  import { termJustStarted } from '../../lib/academic';
  import { nameOf } from '../../lib/short';
  import { photosFirst } from '../../lib/faces';
  import Avatar from '../../ui/Avatar.svelte';
  import { creator, pickRole } from '../../lib/state/creator.svelte';

  // onTitle: in a pane, the club's name scrolled under the capsule (the pane's quiet capsule speaks then)
  let { onTitle }: { onTitle?: (gone: boolean) => void } = $props();
  const mine = $derived([...(session.me?.memberships ?? [])].sort(byRank));
  const multi = $derived(!onTitle && mine.length > 1); // a pane is one club's: no picker (each card opens its own)
  const m = $derived(mine.find((x) => x.org.id === ui.club) ?? mine[0]);
  const staff = $derived(may(m, 'events'));
  const vice = $derived(may(m, 'team'));  // applications
  const casting = $derived(may(m, 'casting'));  // recruitment rounds (PLAN "Casting")
  let round = $state<Round | null>(null);
  let claims = $state(0);  // DMP's list: claims waiting for this club's President (refreshClaims, below)
  const refreshRound = () => { const o = m?.org.id; if (o && casting) api.round(o).then((x) => { if (m?.org.id === o) round = x; }).catch(() => {}); else round = null; };
  $effect(() => { void data.rev; void m?.org.id; void casting; refreshRound(); });

  // Vice+: the applications row (§4.5) — how many wait, or whether the club takes them
  let waiting = $state(0);
  $effect(() => {
    const org = m?.org.id;
    void data.rev;
    if (org && vice) api.joinRequests(org).then((l) => { if (m?.org.id === org) waiting = l.length; }).catch(() => {});
    else waiting = 0;
  });
  // Vice+: the removal requests waiting on Team (§2b), on its row
  let removals = $state(0);
  $effect(() => {
    const org = m?.org.id;
    void data.rev;
    if (org && vice) api.teamSetup(org).then((x) => { if (m?.org.id === org) removals = x.removals?.length ?? 0; }).catch(() => {});
    else removals = 0;
  });
  // Vice+: another club asks us to host its event together (server cohosts.py): yes or no right in To do
  let coAsks = $state<CohostInvite[]>([]);
  $effect(() => {
    const org = m?.org.id;
    void data.rev;
    if (org && vice) api.cohostInvites(org).then((l) => { if (m?.org.id === org) coAsks = l; }).catch(() => {});
    else coAsks = [];
  });
  // what a yes signs (collab-review S3): the description, and for an initiative's event our name on its channel post
  const clip = (s: string) => (s.length > 280 ? s.slice(0, 280).trimEnd() + '…' : s);
  async function coAnswer(x: CohostInvite, yes: boolean, mute = false) {
    haptic.tap();
    const club = nameOf(x.host), org = m?.org;
    if (yes && org && !(await sheets.ask({ title: t('co.acceptAsk', { club }), ok: t('co.yes'), cancel: t('common.cancel'),
      text: [clip(x.event.description.trim()), x.channel ? t('co.acceptChannel', { us: nameOf(org), club }) : t('co.acceptPlain')].filter(Boolean).join('\n\n') }))) return;
    coAsks = coAsks.filter((y) => y !== x); // at once; back if the server says no
    try {
      await api.cohostAnswer(x.event.id, yes, mute); haptic.ok();
      if (mute && org) say(t('co.muted', { club }), 'waving_hand_3d_default', () => void api.cohostUnmute(org.id, x.host.id).catch(() => {}));
      else say(t(yes ? 'co.saidYes' : 'co.saidNo'), yes ? 'party_popper_3d' : 'waving_hand_3d_default');
      if (yes) studioChanged();
    }
    catch { coAsks = [x, ...coAsks]; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // Head+ of a student initiative: the Ascent (server clubs.py, official_path), its levels read on each visit
  let path = $state<OfficialPath | null>(null);
  $effect(() => {
    const org = m?.org.id;
    void data.rev;
    if (org && staff && !m?.org.official) api.officialPath(org).then((x) => { if (m?.org.id === org) path = x; }).catch(() => {});
    else path = null;
  });
  // the creator from Admin (lib/state/creator): "view as" any role of the club's model; the server enforces it too
  const asCreator = $derived(!!m && creator.org === m.org.id);
  const viewAs = (ev: MouseEvent) => menu(ev.currentTarget as Element, creator.roles.map((r) => ({
    label: roleName(r.level, titleOf(r)), checked: r.key === creator.role, onselect: () => { haptic.tap(); pickRole(r.key); seg = 0; },
  })));
  const presVice = $derived(m?.role === 'president' || m?.role === 'vice');
  // the volunteers ledger's club (server logic/vol.py): the list for its President and whom she grants, my own hours for each volunteer
  const vol = $derived(session.me?.vol && session.me.vol.org === m?.org.id ? session.me.vol : null);
  const volLine = (x: { minutes: number; misses: number; unmarked: number }) => duration(x.minutes * 60) + (x.misses ? ' · ' + tn('ledg.misses', x.misses) : '') + (x.unmarked ? ' · ' + t('ledg.unmarkedN', { n: x.unmarked }) : '');
  // its ladder and the ask for the ✓ on a page of their own; a row here says the level
  const level = $derived(path ? (['profile', 'round', 'channel', 'collab', 'top'] as const).filter((k) => path!.steps[k]).length : 0);
  const openAscent = () => { if (m && path) { haptic.tap(); open(AscentPane, { org: m.org.id, path, presVice }); } };
  const coNo = (ev: MouseEvent, x: CohostInvite) => menu(ev.currentTarget as Element, [
    { label: t('co.no'), onselect: () => void coAnswer(x, false) },
    { label: t('co.mute'), destructive: true, onselect: () => void coAnswer(x, false, true) },
  ]);
  const recruiting = $derived(data.orgs.find((x) => x.id === m?.org.id)?.recruiting ?? true);
  const members = $derived(data.orgs.find((x) => x.id === m?.org.id)?.members ?? 0);
  // the Team row's faces, from the roster the app loads with it; a dozen is more than a 430 px row holds
  const faces = $derived(photosFirst((m && data.team[m.org.id]) || []).slice(0, 12));

  // kept per club and loaded with the app (the club in view), so Studio opens full; a visit or a change refreshes it
  const events = $derived((m && data.studio[m.org.id]) || []);
  function refresh() { if (m) void loadStudio(m.org.id); }
  $effect(() => { void data.rev; if (m) void untrack(() => loadStudio(m.org.id)); });

  const over = (e: EventCard) => (e.endsAt ?? e.startsAt + 3 * 3600) <= nowTs();
  const upcoming = $derived(events.filter((e) => e.status !== 'draft' && !over(e)));
  const drafts = $derived(events.filter((e) => e.status === 'draft'));
  const past = $derived(events.filter((e) => e.status !== 'draft' && over(e)).reverse());
  const next = $derived(upcoming.find((e) => e.status === 'published'));
  const today = $derived(!!next && dayNo(next.startsAt) === dayNo(nowTs()));
  let seg = $state(0);
  let picking = $state(false);
  // the event of the day is on top with its door: not twice
  const soon = $derived(today ? upcoming.filter((e) => e !== next) : upcoming);
  const segs = $derived(staff ? [[t('studio.upcoming'), soon], [t('studio.drafts'), drafts], [t('studio.past'), past]] as const : [[t('studio.upcoming'), soon], [t('studio.past'), past]] as const);
  const at = $derived(Math.min(seg, segs.length - 1));
  const list = $derived(segs[at][1]);

  // questions under our events that wait for the club's answer (Head+ see the count), the soonest first
  const asking = $derived(events.filter((e) => (e.questions ?? 0) > 0 && e.status === 'published' && !over(e)));
  // a club's own events open its organizer's screen; one we co-host opens as a student sees it, with our door tools (cohosts.py)
  const ours = (e: EventCard) => e.org.id === m?.org.id;
  const qrDay = $derived(!!next && today && staff && ours(next) && next.status === 'published');
  // whoever keeps the club's event reports (an HR role without "events") opens a started one's organizer screen for its report row;
  // on one we co-host, that screen holds our own report (server evreports.py: one per club)
  const reports = (e: EventCard) => !!session.me?.reports && may(m, 'reports') && e.status === 'published' && e.startsAt <= nowTs();
  const openRow = (e: EventCard) => (e.status === 'draft' ? sheets.editor(e.org.id, e.id)
    : ours(e) ? ((staff || reports(e)) ? sheets.manage(e.id) : sheets.event(e.id))
    : m && reports(e) ? sheets.manage(e.id, false, m.org.id) : sheets.event(e.id));
  const checking = $derived(events.filter((e) => (e.toCheck ?? 0) > 0));
  const volunteering = $derived(events.filter((e) => (e.volunteersAsked ?? 0) > 0 && !over(e))); // volunteers waiting for an answer
  const guesting = $derived(events.filter((e) => (e.teamAsks ?? 0) > 0 && !over(e))); // our own people asking to come as guests
  // drafts found in our channel's posts (server autoev.py): check and publish, one tap into the editor
  const found = $derived(staff ? drafts.filter((e) => e.fromPost && !over(e)) : []);
  // the week the coming Wednesday's memo to DMP covers (from Thursday on, the week after next; as the server's _next_week)
  const dayNow = $derived(dayNo(nowTs()));
  const nextWeek = $derived.by(() => { const mon = dayNow + (((2 - ((dayNow + 3) % 7)) % 7) + 7) % 7 + 5; return events.filter((e) => ours(e) && e.status !== 'cancelled' && dayNo(e.startsAt) >= mon && dayNo(e.startsAt) < mon + 7).length; });
  const wednesday = $derived((dayNow + 3) % 7 === 2 && (nowTs() + 5 * 3600) % 86400 < 18 * 3600);
  const memoDue = $derived(may(m, 'memo') && nextWeek > 0 && ((dayNow + 3) % 7 === 1 || wednesday));
  const fresh = $derived(waiting + (round?.counts?.new ?? 0));
  const askRecruit = $derived(vice && !recruiting && !round && termJustStarted());
  // the club's creator alone in it, often not its President: invite them, then hand it over in Team
  // "I am the President" hides it for that club on this device
  const PRES = 'kbtu.presOk';
  let presOk = $state<number[]>((() => { try { return JSON.parse(localStorage.getItem(PRES) ?? '[]'); } catch { return []; } })());
  function iAmPres(id: number) { haptic.tap(); presOk = [...presOk, id]; try { localStorage.setItem(PRES, JSON.stringify(presOk)); } catch { /* blocked */ } }
  // one row: invite them (the ask says how the club is handed over after) or "I am the President"
  const presMenu = (ev: MouseEvent) => { const org = m!.org; menu(ev.currentTarget as Element, [
    { label: t('studio.invitePres'), onselect: async () => { if (await sheets.ask({ title: t('studio.invitePres'), text: t('studio.todoPresHint'), ok: t('studio.invitePresGo'), cancel: t('common.cancel') })) shareInvite(org); } },
    { label: t('studio.todoPresMe'), onselect: () => iAmPres(org.id) },
  ], 'end'); };
  const alone = $derived(m?.role === 'president' && !presOk.includes(m.org.id) && (data.orgs.find((x) => x.id === m.org.id)?.members ?? 2) <= 1);
  const noUser = $derived(m?.role === 'president' && !!session.me && !session.me.tg.username);
  const todo = $derived(noUser || coAsks.length > 0 || claims > 0 || alone || memoDue || askRecruit || asking.length > 0 || checking.length > 0 || volunteering.length > 0 || guesting.length > 0 || found.length > 0);
  // DMP picked (DMP is an org in Studio with wider rights): its registry of every club (the month's numbers,
  // rosters, the ✓, short names, the week's memos) opens from here, and every roster goes to my chat as a CSV
  const dmp = $derived(!!m?.oversee);
  let memos = $state(0);
  $effect(() => { if (dmp) api.registryMemos().then((l) => (memos = l.length)).catch(() => {}); });
  let exporting = $state(false);
  async function exportCsv() {
    exporting = true; haptic.tap();
    try { await api.registryExport(); haptic.ok(); say(t('reg.sent'), 'sparkles_3d'); }
    catch (e) { haptic.error(); say(e instanceof ApiErr && e.message === 'no_dm' ? t('att.noDm') : t('common.error'), 'warning_3d'); }
    finally { exporting = false; }
  }
  // DMP's list (PLAN 95): students who say they're the one listed under another name, for the President (DMP: clubs
  // with none) to confirm
  // this club's claims; DMP's Studio, every club's without a President. An admin's fallback is in the Admin sheet
  const claimOrg = $derived(dmp ? undefined : m?.org.id);
  const refreshClaims = () => { if (m?.role === 'president' || dmp) api.rosterRequests(claimOrg).then((l) => (claims = l.length)).catch(() => {}); else claims = 0; };
  $effect(() => { void data.rev; void m?.org.id; void dmp; refreshClaims(); });
  // Waiting applications (or no casting right) open the inbox; otherwise straight to the round's board or its form.
  const recruitTile = $derived(casting || vice);
  const openRecruit = () => (vice && (waiting || !casting) ? sheets.joinInbox(m!.org.id) : round ? sheets.roundBoard(m!.org.id) : sheets.roundSetup(m!.org.id, null, refreshRound));
  // Secret Santa (server santa.py): one row. No game: its welcome (SantaHi, the one place to start it); a game running:
  // how many play, and its management
  const santa = $derived(events.find((e) => e.santa && e.status === 'published' && (e.endsAt ?? e.startsAt) > nowTs()));
  function startSanta() {
    if (!m) return;
    haptic.tap();
    if (santa) sheets.manage(santa.id); else sheets.santaHi(m.org.id);
  }
  const creates = $derived<MenuItem[]>([
    ...(staff ? [{ label: t('studio.newShort'), icon: Plus, onselect: () => sheets.editor(m!.org.id) }] : []),
    ...(may(m, 'posts') && !m?.storiesLocked ? [{ label: t('studio.postShort'), icon: PenLine, onselect: () => sheets.composer(m!.org.id) }] : []),
    ...(may(m, 'posts') ? [{ label: t('casting.mark'), icon: Megaphone, onselect: () => sheets.composer(m!.org.id, undefined, true) }] : []),
  ]);
  // a club made by mistake (club presidents): its President deletes it while nobody else is in it and no event
  // went out (the server checks it too, logic.delete_org); otherwise the row says why
  const ownClub = $derived(m?.role === 'president' && m.org.kind === 'club' && !m.org.official);
  const emptyClub = $derived(members <= 1 && events.every((e) => e.status === 'draft'));
  async function deleteClub() {
    if (!m || !emptyClub) return;
    const org = m.org;
    if (!(await sheets.ask({ title: t('studio.delAsk', { club: nameOf(org) }), text: t('studio.delText'), ok: t('studio.del'), cancel: t('common.cancel'), danger: true }))) return;
    try {
      await api.deleteOrg(org.id);
      haptic.warn(); say(t('studio.deleted'), 'waving_hand_3d_default');
      await loadMe(); studioChanged();
    } catch { haptic.error(); say(t('studio.delNo'), 'warning_3d'); }
  }
</script>

<div class="page stagger" class:scroll={!onTitle} class:inpane={!!onTitle}>
  {#if m}
    <header class="hd">
      <!-- the club's name switches clubs (A3; no chips row); top right the one way to make something (no
           full-width Create, the event of the day's QR is the screen's one main button) -->
      {#snippet who()}
        <OrgLogo org={m.org} size={46} />
        <span class="name"><span class="h"><h1 class="ellipsis" use:fitTitle use:largeTitle={onTitle ?? 'club'}>{nameOf(m.org)}</h1>{#if multi}<ChevronDown size={20} strokeWidth={2.6} class="chev" />{/if}</span>
          {#if asCreator}
            <button class="t-foot role as" onclick={viewAs} disabled={!creator.roles.length}>{t('studio.asCreator')} · {roleLabel(m)}<ChevronDown size={14} strokeWidth={2.6} /></button>
          {:else}
          <p class="t-foot role">{#if m.role === 'president'}<Crown size={14} strokeWidth={2.6} />{/if}{roleLabel(m)}{members ? ' · ' + tn('studio.members', members) : ''}</p>
          {/if}</span>
      {/snippet}
      <div class="top">
        {#if multi}
          <button class="title" aria-expanded={picking} onclick={() => { haptic.tap(); picking = !picking; }}>{@render who()}</button>
        {:else}<div class="title">{@render who()}</div>{/if}
        {#if creates.length}<IconButton icon={Plus} kind="tinted" label={t('studio.create')} onclick={(ev) => { haptic.tap(); menu(ev.currentTarget as Element, creates); }} />{/if}
      </div>
      {#if picking}
        <div class="pick" transition:fold>
          <Group>
            {#each mine.filter((x) => x.org.id !== m.org.id) as x (x.org.id)}
              <Row dense title={nameOf(x.org)} subtitle={roleLabel(x)} onclick={() => { ui.club = x.org.id; seg = 0; picking = false; }}>
                {#snippet lead()}<OrgLogo org={x.org} size={30} />{/snippet}
              </Row>
            {/each}
          </Group>
        </div>
      {/if}
    </header>

    <!-- the event of the day: its row (a tap: its organizer's screen) and the one main button, the door -->
    {#if today && next}
      <div class="day">
        <Group>
          <Row dense whole title={next.title} subtitle="{relDay(next.startsAt)}, {time(next.startsAt)} · {placeOf(next.place, next.online)}" value="{next.taken}{next.seats ? ' / ' + next.seats : ''}" accessory="chevron" onclick={() => openRow(next)}>
            {#snippet lead()}<Poster item={next} size={44} radius={12} />{/snippet}
          </Row>
          <!-- one we co-host: its people from our side (its row opens it as a student sees it) -->
          {#if staff && !ours(next)}<Row icon={UsersRound} title={t('studio.attendees')} accessory="chevron" onclick={() => sheets.attendees(next.id)} />{/if}
        </Group>
        <!-- one we co-host: its door is our event team's alone (cohosts.py), our plain members don't work it -->
        <!-- the door screen: one QR for guests and the team alike (the server sorts, checkin._team; the scanner a switch inside it) -->
        {#if qrDay}<Button kind="primary" size="l" full onclick={() => (next.guestHost ? sheets.screens(undefined, undefined, undefined, undefined, next.id) : registration(next, true, session.me?.vol?.org))}>{#snippet icon()}<QrCode size={19} />{/snippet}{t('mk.title')}</Button>
        {:else if !next.guestHost && (ours(next) || staff)}<Button kind="primary" size="l" full onclick={() => sheets.scanner(next.id)}>{#snippet icon()}<ScanLine size={19} />{/snippet}{t('studio.scanner')}</Button>{/if}
      </div>
    {/if}

    {#if todo}
      <Group caption={t('studio.todo')}>
        {#if noUser}<!-- "Message the club" is a DM to the President: without a @username nobody can write (lib/clubdm) -->
          <Row icon={TriangleAlert} title={t('studio.noUserT')} subtitle={t('studio.noUserHow')} />{/if}
        {#each coAsks as x (x.event.id)}
          <Row title={x.event.title} subtitle={t('co.ask', { club: nameOf(x.host) })}>
            {#snippet lead()}{#if x.event.cover}<img class="cov" src={x.event.cover.thumb} alt="" />{:else}<OrgLogo org={x.host} size={30} />{/if}{/snippet}
            {#snippet trailing()}<span class="yn"><IconButton icon={X} size="s" kind="gray" label={t('co.no')} onclick={(ev) => coNo(ev, x)} />
              <Button kind="tinted" size="s" onclick={() => coAnswer(x, true)}>{t('co.yes')}</Button></span>{/snippet}
          </Row>
        {/each}
        {#if claims}<Row icon={UsersRound} title={t('ro.reqTitle')} count={claims} accessory="chevron" onclick={() => sheets.rosterRequests(refreshClaims, claimOrg)} />{/if}
        {#if alone}<Row icon={Crown} title={t('studio.todoPres')} accessory="chevron" onclick={presMenu} />{/if}
        {#if memoDue}<Row icon={Mail} title={t('studio.todoMemo')} subtitle={t('studio.todoMemoBy', { n: nextWeek })} accessory="chevron" onclick={() => sheets.memo(m.org.id)} />{/if}
        {#if askRecruit}<Row icon={UserPlus} title={t('studio.todoRecruit')} subtitle={t('studio.todoRecruitHint')} accessory="chevron" onclick={openRecruit} />{/if}
        {#each asking as e (e.id)}
          <Row icon={MessageCircle} title={e.title} subtitle={t('studio.questions')} count={e.questions} accessory="chevron" onclick={() => sheets.comments('event', e.id, e.title, () => void refresh())} />
        {/each}
        {#each checking as e (e.id)}
          <Row icon={ReceiptIcon} title={e.title} subtitle={t('studio.toCheck')} count={e.toCheck} accessory="chevron" onclick={() => sheets.attendees(e.id)} />
        {/each}
        {#each volunteering as e (e.id)}
          <Row icon={HandHeart} title={e.title} subtitle={t('studio.todoVol')} count={e.volunteersAsked} accessory="chevron" onclick={() => sheets.volunteers(e.id, e.needsVolunteers ?? 0)} />
        {/each}
        {#each found as e (e.id)}
          <!-- the post's picture on it; the eye: as students will see it, the pencil: the editor (EventManage's two doors) -->
          <Row title={e.title} subtitle={t('studio.fromPost')}>
            {#snippet lead()}<Poster item={e} size={44} radius={12} />{/snippet}
            {#snippet trailing()}<span class="yn"><IconButton icon={Eye} size="s" label={t('ed.preview')} onclick={() => { haptic.tap(); sheets.draftPreview(e.id); }} />
              <IconButton icon={Pencil} size="s" label={t('studio.edit')} onclick={() => openRow(e)} /></span>{/snippet}
          </Row>
        {/each}
        {#each guesting as e (e.id)}
          <Row icon={UsersRound} title={e.title} subtitle={t('ta.caption')} count={e.teamAsks} accessory="chevron" onclick={() => sheets.manage(e.id)} />
        {/each}
      </Group>
    {/if}

    {#if dmp}
      <Group caption={t('tab.dmp')}>
        <Row icon={BookUser} title={t('reg.title')} subtitle={t('reg.studioSub')} count={data.registry?.length ?? 0} accessory="chevron" onclick={() => sheets.registry()} />
        <Row icon={Mail} title={t('reg.memos')} count={memos} accessory="chevron" onclick={() => sheets.registry()} />
        <Row icon={Network} title={t('ct.dmp')} subtitle={t('ct.dmpSub')} accessory="chevron" onclick={() => sheets.dmpChats()} />
        <Row icon={FileDown} title={t('reg.export')} subtitle={t('reg.exportSub')} disabled={exporting} onclick={exportCsv} />
      </Group>
    {/if}

    <!-- the club's places, the ones used most first; each a plain row one tap from its page (the Admin sheet's way) -->
    <div class="tools"><Group>
      <Row icon={Users} title={t('page.team')} subtitle={removals ? t('team.removals') : undefined} count={removals} accessory="chevron" onclick={() => sheets.team()}>
        <!-- the faces fill what the row leaves: whole ones only (the line wraps the rest out of sight) -->
        {#snippet detail()}<span class="faces" aria-hidden="true">{#each faces as r (r.person.id)}<Avatar person={r.person} size={28} tappable={false} />{/each}</span>
          <span class="n num">{data.team[m.org.id]?.length ?? members}</span>{/snippet}
      </Row>
      {#if recruitTile}<Row icon={UserPlus} title={t('cast.card')} value={fresh ? undefined : round?.open ? t('cast.until', { when: dayMonth(round.closesAt) }) : t(round ? 'cast.intakeClosed' : recruiting ? 'jr.always' : 'studio.recruitClosed')} count={fresh} accessory="chevron" onclick={openRecruit} />{/if}
      {#if may(m, 'memo')}<Row icon={Mail} title={t('studio.memoShort')} accessory="chevron" onclick={() => sheets.memo(m.org.id)} />{/if}
      {#if staff}<Row icon={QrCode} title={t('scr.page')} accessory="chevron" onclick={() => { haptic.tap(); sheets.screens(undefined, undefined, undefined, m.org.id); }} />{/if}
      {#if staff}<Row icon={Gift} title={t('santa.title')} value={santa ? tn('santa.playing', santa.taken) : undefined} accessory="chevron" onclick={startSanta} />{/if}
      {#if path}<Row icon={MountainSnow} title={t('op.title')} value={path.steps.top ? t('op.atTop') : t('op.level', { n: level })} accessory="chevron" onclick={openAscent} />{/if}
      {#if may(m, 'profile')}<Row icon={Pencil} title={t('ce.title')} accessory="chevron" onclick={() => sheets.clubEdit(m.org.id)} />{/if}
      {#if vol?.ledger}<Row icon={HandHeart} title={t('ledg.title')} value={data.vol ? tn('ledg.count', data.vol.people.length) : undefined} accessory="chevron" onclick={() => sheets.volLedger()} />{/if}
      {#if vol?.mine}{@const mine = vol.mine}<Row icon={Clock} title={t('ledg.mine')} value={volLine(mine)} accessory="chevron" onclick={() => sheets.volPerson(mine.id, true)} />{/if}
    </Group></div>

    {#if events.length}
      <div class="events">
        <Segmented label={t('studio.upcoming')} items={segs.map(([label, l], i) => ({ value: i, label: label + (l.length ? ' · ' + l.length : '') }))} value={at} onchange={(v) => (seg = v)} />
        <div class="list">
          {#each list as e (e.id)}<EventRow {e} showDate dateLine={relDay(e.startsAt)} onopen={() => openRow(e)} />
          {:else}<EmptyState inline text={t('studio.empty')} />{/each}
        </div>
      </div>
    {:else if staff}<!-- a club with no event yet: its first one is the screen's one main button -->
      <Button kind="primary" size="l" full onclick={() => sheets.editor(m.org.id)}>{#snippet icon()}<Plus size={20} />{/snippet}{t('ed.new')}</Button>
    {:else}
      <EmptyState inline text={t('studio.none')} />
    {/if}

    <!-- a club made by mistake: shown only while it can go (nobody else in it, no event out; the server checks too) -->
    {#if ownClub && emptyClub}
      <Group><Row tone="destructive" icon={Trash2} title={t('studio.del')} onclick={deleteClub} /></Group>
    {/if}
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; display: flex; flex-direction: column; gap: var(--gap-group); padding: var(--page-top) var(--gutter) 0; }
  .page > :global(*) { flex-shrink: 0; }
  .inpane { position: static; padding: 0; } /* the pane is the scroller, with its own edges */
  .hd p { margin-top: 2px; }
  .title { display: flex; align-items: center; gap: var(--s-3); }
  .name { flex: 1; min-width: 0; }
  .name h1 { font: 800 var(--fs-sec)/1.15 var(--font-display); letter-spacing: -0.025em; }
  .top { display: flex; align-items: center; gap: var(--s-2); }
  .top .title { flex: 1; min-width: 0; }
  button.title { text-align: left; }
  button.title:active { opacity: 0.7; transform: none; }
  .h { display: flex; align-items: center; gap: 4px; min-width: 0; }
  .h :global(.chev) { flex: none; color: var(--text-3); transition: transform var(--t-base) var(--ease); }
  [aria-expanded='true'] .h :global(.chev) { transform: rotate(180deg); }
  .pick { margin-top: var(--s-3); }
  .role { display: flex; align-items: center; gap: 5px; }
  .role :global(svg) { color: var(--gold); }
  .as { padding: 0; border: 0; background: none; color: var(--accent); font: inherit; cursor: pointer; }
  .as :global(svg) { color: currentColor; }
  /* the Team row's faces: as many whole ones as fit (the wrap hides the rest), overlapping */
  /* engine: Row's detail taking the width the title leaves (here: the title keeps its words, the faces get the rest) */
  .tools :global(.row:has(.faces) .txt) { flex: none; max-width: 42%; }
  .tools :global(.row:has(.faces) .end) { flex: 1 1 auto; min-width: 0; justify-content: flex-end; }
  .faces { flex: 0 1 auto; min-width: 0; height: 32px; padding: 2px; display: flex; flex-wrap: wrap; row-gap: 8px; justify-content: flex-end; overflow: hidden; }
  .faces :global(.av) { box-shadow: 0 0 0 2px var(--surface-solid); }
  .faces :global(.av + .av) { margin-left: -8px; }
  @media (max-width: 359px) { .faces { display: none; } } /* no room for a whole face beside the title */
  .n { margin-left: var(--s-1); color: var(--text-3); font-weight: 450; }
  .day { display: flex; flex-direction: column; gap: var(--s-3); }
  .yn { display: flex; align-items: center; gap: var(--s-2); }
  .cov { width: 30px; height: 30px; border-radius: var(--r-xs); object-fit: cover; }
  .events { display: flex; flex-direction: column; gap: var(--s-3); }
  .list { display: flex; flex-direction: column; gap: var(--s-2); }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
