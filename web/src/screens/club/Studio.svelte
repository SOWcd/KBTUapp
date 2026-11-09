<script lang="ts">
  // A club of mine, pushed over the Clubs tab (StudioPane; round 5: no My club | All clubs switch): Studio for Head+ and the club's page for a Member: the Team row (the roster
  // as a sheet, with the removal requests waiting), "To do" on top only when something waits (new applications, the memo on
  // Tue-Wed, recruitment at a term's start, questions, receipts to check), the club's next event with the door
  // scanner and "New event", a row of small actions (memo, recruitment, invite, club profile), its events by state.
  // Several clubs → a picker on top. Drafts open the editor; the rest the organizer's screen for Head+
  // (EventManage: money, people, tools), the event sheet for Members. Look of mockup v24: the club's
  // mark by its name, the next event with how full it is, the actions as tiles, the channel's first (Vice+).
  import Plus from '@lucide/svelte/icons/plus';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import Users from '@lucide/svelte/icons/users';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import Pencil from '@lucide/svelte/icons/pencil';
  import PenLine from '@lucide/svelte/icons/pen-line';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import X from '@lucide/svelte/icons/x';
  import { fold } from '../../ui/fold';
  import { fitTitle, largeTitle } from '../../ui/title';
  import Ascent from './Ascent.svelte';
  import { api, type CohostInvite, type EventCard, type Id, type OfficialPath, type Round } from '../../lib/api';
  import { loadMe, session } from '../../lib/state/session.svelte';
  import { ui, say } from '../../lib/state/ui.svelte';
  import { haptic } from '../../lib/tg';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import { data, loadStudio, studioChanged } from '../../lib/state/data.svelte';
  import { tick, untrack } from 'svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn, placeOf } from '../../lib/i18n/index.svelte';
  import { relDay, time, nowTs, dayNo, dayMonth } from '../../lib/time';
  import { may, byRank, roleName, titleOf } from '../../lib/perms';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Poster from '../../ui/Poster.svelte';
  import EventRow from '../../ui/EventRow.svelte';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import ReceiptIcon from '@lucide/svelte/icons/receipt';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import Mail from '@lucide/svelte/icons/mail';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import { menu } from '../../ui/menu';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Section from '../../ui/Section.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import Field from '../../ui/Field.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Crown from '@lucide/svelte/icons/crown';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import BookUser from '@lucide/svelte/icons/book-user';
  import FileDown from '@lucide/svelte/icons/file-down';
  import { ApiErr } from '../../lib/api';
  import { shareInvite } from '../../lib/invite';
  import { termJustStarted } from '../../lib/academic';
  import { nameOf } from '../../lib/short';
  import { photosFirst } from '../../lib/faces';
  import Avatar from '../../ui/Avatar.svelte';

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
  const presVice = $derived(m?.role === 'president' || m?.role === 'vice');
  async function askOfficial() {
    if (!m || !path) return;
    const was = path, org = m.org.id;
    haptic.tap();
    path = { ...path, request: { id: 0, status: 'pending', reason: null, createdAt: nowTs(), decidedAt: null, againAt: null } }; // at once
    try { const x = await api.askOfficial(org); if (m?.org.id === org) path = x; haptic.ok(); say(t('op.sent'), 'party_popper_3d'); }
    catch (e) { path = was; haptic.error(); say(e instanceof ApiErr && e.message === 'president_elsewhere' ? t('op.presElsewhere') : t('common.error'), 'warning_3d'); }
  }
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
  // "Change room" on the day (rooms change on the spot): a KBTU room in one tap; who's coming hears it by the rules
  let moving = $state(false);
  let room = $state('');
  let roomForm = $state<HTMLFormElement>();
  async function startMove() { room = ''; moving = true; await tick(); roomForm?.querySelector('input')?.focus(); }
  async function move() {
    if (!next || !room.trim()) return;
    try { await api.changePlace(next.id, room.trim()); moving = false; haptic.ok(); say(t('studio.moved'), 'sparkles_3d'); refresh(); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }

  let seg = $state(0);
  let picking = $state(false);
  const segs = $derived(staff ? [[t('studio.upcoming'), upcoming], [t('studio.drafts'), drafts], [t('studio.past'), past]] as const : [[t('studio.upcoming'), upcoming], [t('studio.past'), past]] as const);
  const at = $derived(Math.min(seg, segs.length - 1));
  const list = $derived(segs[at][1]);

  // questions under our events that wait for the club's answer (Head+ see the count), the soonest first
  const asking = $derived(events.filter((e) => (e.questions ?? 0) > 0 && e.status === 'published' && !over(e)));
  // a club's own events open its organizer's screen; one we co-host opens as a student sees it, with our door tools (cohosts.py)
  const ours = (e: EventCard) => e.org.id === m?.org.id;
  const openRow = (e: EventCard) => (e.status === 'draft' ? sheets.editor(e.org.id, e.id) : staff && ours(e) ? sheets.manage(e.id) : sheets.event(e.id));
  const checking = $derived(events.filter((e) => (e.toCheck ?? 0) > 0));
  const volunteering = $derived(events.filter((e) => (e.volunteersAsked ?? 0) > 0 && !over(e))); // volunteers waiting for an answer
  const guesting = $derived(events.filter((e) => (e.teamAsks ?? 0) > 0 && !over(e))); // our own people asking to come as guests
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
  const alone = $derived(m?.role === 'president' && !presOk.includes(m.org.id) && (data.orgs.find((x) => x.id === m.org.id)?.members ?? 2) <= 1);
  const todo = $derived(coAsks.length > 0 || claims > 0 || alone || fresh > 0 || memoDue || askRecruit || asking.length > 0 || checking.length > 0 || volunteering.length > 0 || guesting.length > 0);
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
  // "Recruiting" is the round: its tile is always there for the casting team (casting audit: on a day without a round Studio
  // had no way in, so a President made her casting an event); closed, a tap opens the setup. Vice+ without the right:
  // the any-time join requests' sheet while those are on
  // the always-open switch lives in Vice+'s sheet: it opens from the start, not only once a round or a request exists
  // (club presidents, Nov 6)
  const recruitTile = $derived(casting || vice);
  const openRecruit = () => (vice ? sheets.joinInbox(m!.org.id) : round ? sheets.roundBoard(m!.org.id) : sheets.roundSetup(m!.org.id, null, refreshRound));
  // a club made by mistake (club presidents, Nov 6): its President deletes it while nobody else is in it and no event
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
      <!-- the club's name switches clubs (A3; no chips row); the pencil to its page stays top right (not inside the list) -->
      {#snippet who()}
        <OrgLogo org={m.org} size={46} />
        <span class="name"><span class="h"><h1 class="ellipsis" use:fitTitle use:largeTitle={onTitle ?? 'club'}>{nameOf(m.org)}</h1>{#if multi}<ChevronDown size={20} strokeWidth={2.6} class="chev" />{/if}</span>
          <p class="t-foot role">{#if m.role === 'president'}<Crown size={14} strokeWidth={2.6} />{/if}{roleName(m.role, titleOf(m))}{members ? ' · ' + tn('studio.members', members) : ''}</p></span>
      {/snippet}
      <div class="top">
        {#if multi}
          <button class="title" aria-expanded={picking} onclick={() => { haptic.tap(); picking = !picking; }}>{@render who()}</button>
        {:else}<div class="title">{@render who()}</div>{/if}
        {#if vice}<IconButton icon={Pencil} label={t('ce.title')} onclick={() => sheets.clubEdit(m.org.id)} />{/if}
      </div>
      {#if picking}
        <div class="pick" transition:fold>
          <Group>
            {#each mine.filter((x) => x.org.id !== m.org.id) as x (x.org.id)}
              <Row dense title={nameOf(x.org)} subtitle={roleName(x.role, titleOf(x))} onclick={() => { ui.club = x.org.id; seg = 0; picking = false; }}>
                {#snippet lead()}<OrgLogo org={x.org} size={30} />{/snippet}
              </Row>
            {/each}
          </Group>
        </div>
      {/if}
    </header>

    {#if m.role === 'president' && session.me && !session.me.tg.username}
      <!-- "Message the club" is a DM to the President: without a @username nobody can write (lib/clubdm) -->
      <Notice tone="warning" title={t('studio.noUserT')} text={t('studio.noUser')} />
    {/if}

    <div class="team"><Group>
      <Row icon={Users} title={t('page.team')} subtitle={removals ? t('team.removals') : undefined} count={removals} accessory="chevron" onclick={() => sheets.team()}>
        <!-- the faces fill what the row leaves: whole ones only (the line wraps the rest out of sight) -->
        {#snippet detail()}<span class="faces" aria-hidden="true">{#each faces as r (r.person.id)}<Avatar person={r.person} size={28} tappable={false} />{/each}</span>
          <span class="n num">{data.team[m.org.id]?.length ?? members}</span>{/snippet}
      </Row>
    </Group></div>

    {#if todo}
      <Group caption={t('studio.todo')}>
        {#each coAsks as x (x.event.id)}
          <Row title={x.event.title} subtitle={t('co.ask', { club: nameOf(x.host) })}>
            {#snippet lead()}{#if x.event.cover}<img class="cov" src={x.event.cover.thumb} alt="" />{:else}<OrgLogo org={x.host} size={30} />{/if}{/snippet}
            {#snippet trailing()}<span class="yn"><IconButton icon={X} size="s" kind="gray" label={t('co.no')} onclick={(ev) => coNo(ev, x)} />
              <Button kind="tinted" size="s" onclick={() => coAnswer(x, true)}>{t('co.yes')}</Button></span>{/snippet}
          </Row>
        {/each}
        {#if claims}<Row icon={UsersRound} title={t('ro.reqTitle')} count={claims} accessory="chevron" onclick={() => sheets.rosterRequests(refreshClaims, claimOrg)} />{/if}
        {#if alone}
          <Row icon={Crown} title={t('studio.todoPres')} subtitle={t('studio.todoPresHint')} accessory="chevron" onclick={() => shareInvite(m.org)} />
          <Row tone="action" title={t('studio.todoPresMe')} onclick={() => iAmPres(m.org.id)} />
        {/if}
        {#if fresh}<Row icon={UserPlus} title={t('studio.todoApps')} count={fresh} accessory="chevron" onclick={openRecruit} />{/if}
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
        {#each guesting as e (e.id)}
          <Row icon={UsersRound} title={e.title} subtitle={t('ta.caption')} count={e.teamAsks} accessory="chevron" onclick={() => sheets.manage(e.id)} />
        {/each}
      </Group>
    {/if}

    {#if path}<Ascent {path} {presVice} onask={askOfficial} />{/if}

    {#if dmp}
      <Group caption={t('tab.dmp')}>
        <Row icon={BookUser} title={t('reg.title')} subtitle={t('reg.studioSub')} count={data.registry?.length ?? 0} accessory="chevron" onclick={() => sheets.registry()} />
        <Row icon={Mail} title={t('reg.memos')} count={memos} accessory="chevron" onclick={() => sheets.registry()} />
        <Row icon={FileDown} title={t('reg.export')} subtitle={t('reg.exportSub')} disabled={exporting} onclick={exportCsv} />
      </Group>
    {/if}

    <Section title={t('studio.next')}>
      {#if next}
        <article class="hero">
          <button class="ev" onclick={() => openRow(next)}>
            <Poster item={next} size={60} radius={16} />
            <span class="txt">
              <span class="t-foot when" class:now={today}>{relDay(next.startsAt)}, {time(next.startsAt)} · {placeOf(next.place)}</span>
              <b class="t-title clamp-2">{next.title}</b>
            </span>
          </button>
          <!-- how full it is -->
          <div class="seats"><span class="t-foot"><b class="num">{tn('event.going', next.taken)}</b>{next.seats ? ' / ' + next.seats : ''}</span>
            {#if next.seats}<span class="bar"><i style="width:{Math.min(100, (next.taken / next.seats) * 100)}%"></i></span>{/if}</div>
          <div class="acts btns">
            {#if !next.guestHost}<Button kind={today ? 'primary' : 'secondary'} size="m" full onclick={() => sheets.scanner(next.id)}>{#snippet icon()}<ScanLine size={18} />{/snippet}{t('studio.scanner')}</Button>{/if}
            {#if staff}<Button kind="secondary" size="m" full onclick={() => sheets.attendees(next.id)}>{#snippet icon()}<UsersRound size={18} />{/snippet}{t('studio.attendees')}</Button>{/if}
          </div>
          {#if staff && ours(next) && today && !next.placeUrl}
            {#if !moving}
              <Button kind="plain" size="s" full onclick={startMove}>{#snippet icon()}<MapPin size={16} />{/snippet}{t('studio.move')}</Button>
            {:else}
              <form class="moving" bind:this={roomForm} onsubmit={(e) => { e.preventDefault(); void move(); }}>
                <span class="fl"><Field label={t('studio.newRoom')} bind:value={room} maxlength={80} placeholder={next.place || '305'} enterkeyhint="done" /></span>
                <Button kind="primary" size="l" type="submit" disabled={!room.trim()}>{t('common.save')}</Button>
              </form>
            {/if}
          {/if}
        </article>
      {:else}
        <Group><EmptyState inline text={t('studio.none')} /></Group>
      {/if}
    </Section>

    <!-- the actions (were tiles in mockup v24, now Settings' rows): a new event, recruitment while it runs (closed: a
         "To do" at a term's start), the memo to DMP; inviting lives on Team, editing the club up top. First, to Vice+
         (who link chats): the channel whose posts the userbot copies into the news, or "Link" -->
    {#if m.channel !== undefined || staff || may(m, 'posts') || may(m, 'memo') || recruitTile}
      <Group>
        {#if m.channel !== undefined}<Row icon={Megaphone} title={t('studio.channelShort')} subtitle={m.channel ? (m.channel.mirror ? m.channel.title : t('studio.channelOff')) : t('studio.channelLink')} accessory="chevron" onclick={() => sheets.clubEdit(m.org.id, 'chats')} />{/if}
        {#if staff}<Row icon={Plus} title={t('studio.newShort')} subtitle={t('studio.newSub')} accessory="chevron" onclick={() => sheets.editor(m.org.id)} />{/if}
        <!-- the club's news, now circles on Afisha: written from here -->
        {#if may(m, 'posts')}<Row icon={Megaphone} title={t('casting.mark')} subtitle={t('studio.castingSub')} accessory="chevron" onclick={() => sheets.composer(m.org.id, undefined, true)} />{/if}
        {#if may(m, 'posts')}<Row icon={PenLine} title={t('studio.postShort')} subtitle={t('studio.postSub')} accessory="chevron" onclick={() => sheets.composer(m.org.id)} />{/if}
        {#if recruitTile}<Row icon={UserPlus} title={t('cast.card')} subtitle={fresh ? tn('studio.newApps', fresh) : round?.open ? t('cast.until', { when: dayMonth(round.closesAt) }) : t(round ? 'cast.intakeClosed' : recruiting ? 'jr.always' : 'studio.recruitClosed')} count={fresh} accessory="chevron" onclick={openRecruit} />{/if}
        {#if may(m, 'memo')}<Row icon={Mail} title={t('studio.memoShort')} subtitle={t('studio.memoSub')} accessory="chevron" onclick={() => sheets.memo(m.org.id)} />{/if}
      </Group>
    {/if}

    <div class="events">
      <Segmented label={t('studio.upcoming')} items={segs.map(([label, l], i) => ({ value: i, label: label + (l.length ? ' · ' + l.length : '') }))} value={at} onchange={(v) => (seg = v)} />
      <div class="list">
        {#each list as e (e.id)}<EventRow {e} showDate dateLine={relDay(e.startsAt)} onopen={() => openRow(e)} />
        {:else}<EmptyState inline text={t('studio.empty')} />{/each}
      </div>
    </div>

    {#if ownClub}
      <Group><Row tone="destructive" icon={Trash2} title={t('studio.del')} subtitle={emptyClub ? undefined : t('studio.delWhyNot')} disabled={!emptyClub} onclick={deleteClub} /></Group>
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
  /* the Team row's faces: as many whole ones as fit (the wrap hides the rest), overlapping */
  /* engine: Row's detail taking the width the title leaves (here: the title keeps its words, the faces get the rest) */
  .team :global(.txt) { flex: none; max-width: 42%; }
  .team :global(.end) { flex: 1 1 auto; min-width: 0; justify-content: flex-end; }
  .faces { flex: 0 1 auto; min-width: 0; height: 32px; padding: 2px; display: flex; flex-wrap: wrap; row-gap: 8px; justify-content: flex-end; overflow: hidden; }
  .faces :global(.av) { box-shadow: 0 0 0 2px var(--surface-solid); }
  .faces :global(.av + .av) { margin-left: -8px; }
  @media (max-width: 359px) { .faces { display: none; } } /* no room for a whole face beside the title */
  .n { margin-left: var(--s-1); color: var(--text-3); font-weight: 450; }
  .hero { display: flex; flex-direction: column; gap: var(--s-3); padding: 14px; border-radius: var(--r-group); background: var(--surface); }
  .ev { display: flex; gap: var(--s-3); align-items: center; text-align: left; width: 100%; }
  .ev:active { opacity: 0.7; transform: none; }
  .txt { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .when { font-weight: 600; }
  .when.now { color: var(--success-text); }
  .seats { display: flex; flex-direction: column; gap: 6px; }
  .seats b { color: var(--text); font-weight: 600; }
  .bar { height: 6px; border-radius: var(--r-full); background: var(--surface-3); overflow: hidden; }
  .bar i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--accent), var(--accent-2)); }
  .acts { display: flex; gap: var(--s-2); }
  .yn { display: flex; align-items: center; gap: var(--s-2); }
  .cov { width: 30px; height: 30px; border-radius: var(--r-xs); object-fit: cover; }
  /* 320 px: halves of 126 cut "Attendees" in Russian and Kazakh; tighter padding and each by its own word fit both */
  @media (max-width: 359px) { .acts :global(.btn.full) { flex-basis: auto; padding-inline: var(--s-3); gap: 6px; } }
  .moving { display: flex; align-items: flex-end; gap: var(--s-2); }
  .fl { flex: 1; min-width: 0; }
  .events { display: flex; flex-direction: column; gap: var(--s-3); }
  .list { display: flex; flex-direction: column; gap: var(--s-2); }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
