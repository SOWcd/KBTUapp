<script lang="ts">
  // Studio → an event: the organizer's screen, not the Afisha's (few
  // buttons: organizers are students on a phone at a door). The card
  // (its pencil the editor, its eye the usual sheet); on the event's day one «Show QR» (the door screen: QR and scanner);
  // who came; rows only when they ask for something (receipts to check, the team's asks, holds, the waitlist,
  // volunteers); the money of a paid event; the rest folded under «More» (shown plainly when three or fewer).
  // ponytail: no "message the participants" yet (no such API; the questions thread and the bot's changes cover it).
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import TournamentRows from '../sheets/TournamentRows.svelte';
  import Pencil from '@lucide/svelte/icons/pencil';
  import Eye from '@lucide/svelte/icons/eye';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import MonitorUp from '@lucide/svelte/icons/monitor-up';
  import { onMount } from 'svelte';
  import ClipboardCheck from '@lucide/svelte/icons/clipboard-check';
  import FileSpreadsheet from '@lucide/svelte/icons/file-spreadsheet';
  import { api, ApiErr, staffEvents, type EventFull, type DoorAudience, type Attendee, type EventCard, type Id, type PersonRef, type TeamAsk } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, eventById, phrase, studioChanged } from '../../lib/state/data.svelte';
  import { readState } from '../../lib/state/readState.svelte';
  import { sheets, registration } from '../../lib/state/sheets';
  import { session } from '../../lib/state/session.svelte';
  import { t, money, placeOf } from '../../lib/i18n/index.svelte';
  import { relDay, time, nowTs, dayNo, dayMonthShort } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import Notice from '../../ui/Notice.svelte';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import { inner, may } from '../../lib/perms';
  import UserCheck from '@lucide/svelte/icons/user-check';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Sheet from '../../ui/Sheet.svelte';
  import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
  import Poster from '../../ui/Poster.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import X from '@lucide/svelte/icons/x';
  import Gift from '@lucide/svelte/icons/gift';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import Field from '../../ui/Field.svelte';
  import { tick as frame } from 'svelte';
  import Share from '@lucide/svelte/icons/share';
  import BellRing from '@lucide/svelte/icons/bell-ring';
  import { shareCard } from '../../lib/tg';
  import SantaTerms, { readTerms, termsFrom, type Terms } from './SantaTerms.svelte';

  // staff: opened from Admin, the app's admin runs it as its organizers do (api staffEvents), never its door or money;
  // the creator runs it as its President would (server app.viewer), all but the club's money and reports (`plain`: the rest)
  // org: opened from the Studio of a club co-hosting it (server cohosts.py): our own report, our door if we run it, the
  // student's view; nothing of the host's
  let { overlay, id, staff = false, org }: { overlay: Overlay; id: Id; staff?: boolean; org?: Id } = $props();

  const e = $derived(eventById(id));
  const co = $derived(!!e && org != null && org !== e.org.id);
  const mem = $derived(session.me?.memberships.find((m) => m.org.id === (co ? org : e?.org.id)));
  const plain = $derived(staff && !session.me?.founder);
  const head = $derived(!co && (staff || may(mem, 'events')));
  const coCrew = $derived(co && may(mem, 'events')); // the co-host's event team: the door, as from the event's sheet
  // Admin put it in staffEvents before opening; it leaves with this screen, so the event's own sheet is a student's again
  $effect(() => () => { if (staff) staffEvents.delete(id); });
  const started = $derived(!!e && e.startsAt <= nowTs());
  const live = $derived(e?.status === 'published');
  // the club's report after its own started event (server evreports.py, REPORTS): its President, Vices, a role given the right
  const reports = $derived(!!session.me?.reports && !staff && may(mem, 'reports') && live && started);

  // everything below comes from the attendee list (Head+), asked again whenever Studio changes (a receipt checked)
  const { state: roster, load: loadRoster } = readState(() => api.attendees(id));
  const list = $derived(roster.value);
  $effect(() => { void data.rev; if (head) void loadRoster(); });
  const of = (s: Attendee['status']) => (list ?? []).filter((a) => a.status === s);
  const going = $derived(of('going'));
  const came = $derived(going.filter((a) => a.checkedInAt).length);
  const price = $derived(e?.price ?? 0);
  const paying = $derived(going.filter((a) => !a.free).length);
  const byReceipts = $derived(going.reduce((n, a) => n + (a.receipt?.amount ?? 0), 0));
  const unread = $derived(going.filter((a) => a.receipt && a.receipt.amount == null).length);
  // receipts the app checked by itself (no person looked): one total to find in Kaspi instead of every receipt
  const auto = $derived(going.filter((a) => a.receipt?.auto));
  const autoSum = $derived(auto.reduce((n, a) => n + (a.receipt?.amount ?? 0), 0));
  // the event's Telegram group: open it, or "Create chat" adds our bot to a group the organizer picks
  let chat = $state<string | null>(null);
  // door helpers (server crew.py): the server sends the list to a running club's President or Vice only
  $effect(() => { if (head) api.event(id).then((x) => { chat = x.chat ?? null; santaN = x.santaN ?? 0; santaTeam = x.santaTeam ?? null; }).catch(() => {}); });
  // Secret Santa (server santa.py): how many play and the one draw; who gives to whom no organizer ever sees
  let santaN = $state(0);
  // before the draw (server santa.view): who is in, who of the club not yet, names only; the budget and the deadline
  // editable here, the reminder to those not in yet (once a day) and the game's card for the club's chat
  let santaTeam = $state<NonNullable<EventFull['santaTeam']> | null>(null);
  const until = (ts: number) => `${dayMonthShort(ts)}, ${time(ts)}`;
  let terms = $state<Terms | null>(null);
  function editTerms() {
    if (!e) return;
    haptic.tap();
    terms = terms ? null : termsFrom(e.santa?.budget, e.regUntil ?? e.startsAt, e.startsAt);
  }
  async function saveTerms() {
    if (!e || !terms) return;
    const r = readTerms(terms);
    if (r.bad || r.budget === null) return;
    const c = eventById(id), was = c ? { santa: c.santa, regUntil: c.regUntil } : null;
    if (c) { c.santa = { drawn: false, budget: r.budget }; c.regUntil = r.until; } // optimistic: the rows show it at once
    terms = null; haptic.ok();
    try { await api.santaSettings(id, { budget: r.budget, regUntil: r.until }); studioChanged(); say(t('santa.saved'), 'party_popper_3d'); }
    catch (err) { if (c && was) { c.santa = was.santa; c.regUntil = was.regUntil; } haptic.error(); say(t(err instanceof ApiErr && err.message === 'until' ? 'santa.badUntil' : 'common.error'), 'warning_3d'); }
  }
  // the reminder's day passed with the page open: its count read again, the button back
  $effect(() => { if (santaTeam?.remindAt && tick >= santaTeam.remindAt) api.event(id).then((x) => (santaTeam = x.santaTeam ?? null)).catch(() => {}); });
  async function remindSanta() {
    haptic.tap();
    const team = santaTeam;
    if (!team || team.remindAt) return;
    if (!team.remind) { say(t('santa.remindNone'), 'pleading_face_3d'); return; }
    if (!(await sheets.ask({ title: t('santa.remindAsk'), text: t('santa.remindText', { n: team.remind }), ok: t('santa.remindGo'), cancel: t('common.cancel') }))) return;
    const was = { ...team };
    santaTeam = { ...team, remind: 0, remindAt: nowTs() + 86400 }; // optimistic
    try { const x = await api.santaRemind(id); santaTeam = { ...team, remind: 0, remindAt: x.nudgeAt }; haptic.ok(); say(t('santa.reminded'), 'party_popper_3d'); }
    catch { santaTeam = was; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  function shareSanta() {
    if (!e) return;
    haptic.tap();
    // the event's own card (server /api/share kind ev): a member opens the game; anyone else sees what a team-only event shows them
    shareCard({ kind: 'ev', id: String(id) }, 'https://t.me/KBTUappBot?startapp=ev_' + id, e.title)
      .then((sent) => { if (sent) say(phrase('say.shared'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'warning_3d'); });
  }
  async function drawSanta() {
    haptic.tap();
    if (santaN < 3) { say(t('santa.few'), 'pleading_face_3d'); return; }
    if (!(await sheets.ask({ title: t('santa.drawAsk'), text: t('santa.drawText'), ok: t('santa.drawGo'), cancel: t('common.cancel') }))) return;
    try {
      const x = await api.santaDraw(id), c = eventById(id);
      if (c) { c.santa = x.santa; c.regUntil = x.regUntil; }
      studioChanged(); haptic.ok(); say(t('santa.done'), 'party_popper_3d');
    } catch (err) { haptic.error(); say(t(err instanceof ApiErr && err.message === 'few' ? 'santa.few' : err instanceof ApiErr && err.message === 'holds' ? 'santa.holds' : 'common.error'), 'warning_3d'); }
  }
  // the team's session (server checkin.crew): who may start a club's session, in the event's own club; its state read
  // with the page and every 10 s (it runs in the page above this one)
  const teamMark = $derived(head && !plain && !!e && e.status !== 'cancelled');
  // the team's count from the Mark screen's own list (server checkin.team): the same numbers there and here
  const { state: teamRoster, load: loadTeam } = readState(() => api.teamList(id));
  const team = $derived(teamRoster.value);
  $effect(() => { void tick; if (teamMark && !e?.guestHost) void loadTeam(); });
  async function openChat() {
    haptic.tap();
    if (chat) { openLink(chat); return; }
    if (!(await sheets.ask({ title: t('chat.ask'), text: t('chat.askText'), ok: t('chat.go'), cancel: t('common.cancel') }))) return;
    try { openLink(await api.chatStart(id)); } catch { say(t('common.error'), 'warning_3d'); }
  }
  // "Who brought" (a member's KPI): signed up by their link, paid (an accepted receipt), came; the ones who came most first
  const brought = $derived.by(() => {
    const by = new Map<Id, { person: PersonRef; signed: number; paid: number; came: number }>();
    for (const a of list ?? []) {
      if (!a.by) continue;
      const x = by.get(a.by.id) ?? by.set(a.by.id, { person: a.by, signed: 0, paid: 0, came: 0 }).get(a.by.id)!;
      x.signed++;
      if (a.status === 'going' && a.receipt && (a.receipt.reviewed || !a.receipt.flags.some((f) => f !== 'spot' && f !== 'partial'))) x.paid++; // a flagged receipt nobody checked isn't paid yet
      if (a.byCame) x.came++;
    }
    return [...by.values()].sort((a, b) => b.came - a.came || b.paid - a.paid || b.signed - a.signed);
  });
  const toCheck = $derived(going.filter((a) => a.receipt?.flags.length && !a.receipt.reviewed).length);

  async function removeEvent() {
    if (!(await sheets.ask({ title: t('studio.deleteAsk'), text: t('studio.deleteText'), ok: t('ed.deleteGo'), cancel: t('tk.keep'), danger: true }))) return;
    // off every Studio list at once (an admin's soft delete too), before their reload says the same
    const gone = () => { for (const [k, l] of Object.entries(data.studio)) data.studio[+k] = l.filter((x) => x.id !== id); studioChanged(); haptic.warn(); say(phrase('say.eventDeleted'), 'waving_hand_3d_default'); close(overlay.id); };
    try { await api.deleteEvent(id); gone(); }
    catch (x) {
      // the app's admin deletes softly (hidden now, gone in a day): a second tap on one still listed is the same "deleted"
      if (x instanceof ApiErr && x.message === 'decided') { gone(); return; }
      haptic.error();
      if (!(x instanceof ApiErr && x.message === 'paid')) { say(t('common.error'), 'warning_3d'); return; }
      // receipts are the only record of money that changed hands: only the creator deletes such an event (say
      // why, and a way to ask him, with the message already written)
      if (await sheets.ask({ title: t('studio.deletePaid'), text: t('studio.deletePaidText'), ok: t('studio.deletePaidAsk'), cancel: t('common.close') }))
        openLink(`https://t.me/Sowers?text=${encodeURIComponent(t('studio.deletePaidMsg', { title: e?.title ?? '' }))}`);
    }
  }
  // "Close registration" (organizers asked to stop sign-ups; theirs and Admin's alike): one tap, closes now, tickets
  // stay; the toast's Undo puts the old deadline back
  const regClosed = $derived(!!e?.regUntil && e.regUntil <= nowTs());
  const regOn = (r: EventCard['regUntil']) => { const x = eventById(id); if (x) x.regUntil = r; };
  async function setReg(until: number | 'now' | null, done: string, was: EventCard['regUntil']) {
    try { regOn((await api.setRegUntil(id, until)).regUntil); studioChanged(); haptic.ok(); say(done, 'locked_3d', () => void setReg(was ?? null, t(!was || was > nowTs() ? 'mg.regOpened' : 'mg.regClosed'), e?.regUntil)); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // a deadline set before closing comes back with "Open registration" while it's ahead (a double tap loses nothing)
  let before = $state<number | null>(null);
  function shut() {
    before = e?.regUntil && e.regUntil > nowTs() ? e.regUntil : null;
    void setReg('now', t('mg.regClosed'), e?.regUntil);
  }
  async function closeReg() {
    if (e?.santa) { await closeSanta(); return; }
    shut();
  }
  // a Santa game's sign-up closed is its deadline come: the bot's round draws within seconds, for good (no Undo)
  async function closeSanta() {
    const few = santaN < 3;
    if (!(await sheets.ask({ title: t('mg.closeRegAsk'), text: t(few ? 'santa.closeFew' : 'santa.closeDraws'), ok: t('mg.closeRegGo'), cancel: t('common.cancel'), danger: true }))) return;
    try { regOn((await api.setRegUntil(id, 'now')).regUntil); studioChanged(); haptic.ok(); say(t(few ? 'mg.regClosed' : 'santa.closeSoon'), 'locked_3d'); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // the door: shut until T-30, or until the club's President or a Vice opens it, from 4 h before (server
  // organizing.open_door; the app's admin never). An hour or more ahead asks twice, the second "Open" after 2 s.
  const doorAt = $derived(e?.doorAt ?? (e ? e.startsAt - 1800 : 0));
  let tick = $state(nowTs());  // a ticking now: "opens at" turns into "open since" at T-30 with the screen open
  onMount(() => { const i = setInterval(() => (tick = nowTs()), 10_000); return () => clearInterval(i); });
  const doorOpen = $derived(doorAt <= tick);
  const opener = $derived(!co && (staff ? !plain : mem?.role === 'president' || mem?.role === 'vice'));
  const setDoor = (at: number) => { const x = eventById(id); if (x) x.doorAt = at; };
  async function openDoor(): Promise<boolean> {
    if (!e) return false;
    const ask = { ok: t('door.openGo'), cancel: t('common.cancel') };
    if (!(await sheets.ask({ ...ask, title: t('door.openAsk'), text: t('door.openText') }))) return false;
    if (e.startsAt - nowTs() > 3600 && !(await sheets.ask({ ...ask, title: t('door.openSure'), text: t('door.openSureText'), wait: 2000 }))) return false;
    const was = doorAt;
    tick = nowTs(); setDoor(tick);
    try { await api.openDoor(id); haptic.ok(); say(t('door.opened'), 'party_popper_3d'); return true; }
    catch { setDoor(was); haptic.error(); say(t('common.error'), 'warning_3d'); return false; }
  }
  // the event's day (or under way), its door ours to work: one «Show QR»; a partner's event has no door, Admin never
  // works it (the creator as its President does); a co-host's event team works it as from the event's sheet
  const ends = $derived(e ? e.endsAt ?? e.startsAt + 6 * 3600 : 0);
  const doorDay = $derived(!!e && live && !e.guestHost && !plain && (co ? coCrew : true) && (started || dayNo(e.startsAt) === dayNo(tick)) && ends > tick);
  async function showQr() {
    if (!e) return;
    haptic.tap();
    // shut yet: today's confirm first (it tells the guests), and «Cancel» cancels; a team-only door asks nothing (no guest to tell)
    if (!doorOpen && opener && aud !== 'team' && e.startsAt - 4 * 3600 <= tick && !(await openDoor())) return;
    registration(e, co || head, session.me?.vol?.org);
  }
  let more = $state(false);
  // the rows under «More», the same conditions as below: three or fewer show plainly, no fold (a fold of two is pointless)
  const folded = $derived(!e ? 0 : [head, head && e.teamMax, head && e.teamMax, head && e.status !== 'cancelled' && !plain, head && e.needsVolunteers,
    head && e.guestHost && teamMark, head && live && !e.guestHost, reports, head && live && !e.guestHost && !e.guestList && !e.meeting && !e.santa?.drawn && (!started || e.lateSignup),
    head && live && !started, head && e.status === 'cancelled'].filter(Boolean).length);
  // whom the door records (server checkin.set_audience): an ordinary public event's, where the team is told apart from
  // guests; the event's organizers set it, the Mark screen counts and lists only that
  const audienced = $derived(head && !plain && !!e && live && !e.guestHost && !inner(e) && ends > tick);
  let aud = $state<DoorAudience>('both');
  $effect(() => { if (audienced) api.event(id).then((x) => (aud = x.audience ?? 'both')).catch(() => {}); });
  const AUD = { both: 'mk.aBoth', guests: 'mk.aGuests', team: 'mk.aTeam' } as const;
  const showTeam = $derived(teamMark && !e?.guestHost && (started || doorDay) && aud !== 'guests');
  const teamOnly = $derived(showTeam && aud === 'team');
  const teamLine = $derived(showTeam && team && (team.rows.length || teamOnly) ? t('mk.team', { n: team.rows.filter((r) => r.at).length, m: team.rows.length }) : undefined);
  async function setAud(a: DoorAudience) {
    const was = aud;
    aud = a; haptic.tap();
    try { await api.setAudience(id, a); } catch { aud = was; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // the club's own people asking to come as guests (server seats.team_ask): the President and the Vices answer here
  let asks = $state<TeamAsk[]>([]);
  $effect(() => { void data.rev; if (opener) api.teamAsks(id).then((l) => (asks = l)).catch(() => {}); });
  async function decide(x: TeamAsk, yes: boolean) {
    haptic.tap();
    asks = asks.filter((y) => y !== x); // at once; back if the server says no
    try { await api.teamDecide(id, x.person.id, yes); haptic.ok(); say(t(yes ? 'ta.saidYes' : 'ta.saidNo'), yes ? 'party_popper_3d' : 'waving_hand_3d_default'); studioChanged(); }
    catch { asks = [x, ...asks]; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // "Change room" on the day (rooms change on the spot; moved here from Studio's home): a KBTU room in one tap,
  // who's coming hears it by the rules (server change_place)
  const roomDay = $derived(head && !plain && live && !e?.placeUrl && !e?.online && !!e && dayNo(e.startsAt) === dayNo(tick) && ends > tick);
  let moving = $state(false), room = $state(''), roomForm = $state<HTMLFormElement>();
  async function startMove() { haptic.tap(); room = ''; moving = true; await frame(); roomForm?.querySelector('input')?.focus(); }
  async function move() {
    if (!room.trim()) return;
    try { await api.changePlace(id, room.trim()); moving = false; haptic.ok(); say(t('studio.moved'), 'sparkles_3d'); studioChanged(); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function cancelEvent() {
    // people signed up and sign-up still open: closing it is often what was meant (their tickets stay, it reopens)
    // (dismissing it goes on to the cancel's own confirm: nothing is cancelled without that OK)
    if (e && e.taken > 0 && !regClosed && !e.santa && !e.guestHost && !e.guestList && !e.meeting
      && await sheets.ask({ title: t('mg.closeInstead'), text: t('mg.closeInsteadText', { n: e.taken }), ok: t('mg.closeReg'), cancel: t('mg.cancelAnyway') })) {
      shut();
      return;
    }
    if (!(await sheets.ask({ title: t('studio.cancelAsk'), text: t('studio.cancelText'), ok: t('studio.cancelGo'), cancel: t('tk.keep'), danger: true }))) return;
    try { await api.cancelEvent(id); studioChanged(); haptic.warn(); say(t('say.eventCancelled'), 'crying_face_3d'); }
    catch { say(t('common.error'), 'warning_3d'); }
  }
</script>

<Sheet {overlay} icon={SlidersHorizontal} full title={t('mg.title')}>
  {#if e}
    <div class="pg">
      {#if staff}<Notice icon={ShieldCheck} text={t('mg.asStaff')} />{/if}
      <Group>
        <!-- the event's two doors on its card: edit it, see it as students do -->
        <Row title={e.title} subtitle="{relDay(e.startsAt)}, {time(e.startsAt)} · {placeOf(e.place, e.online)}">
          {#snippet lead()}<Poster item={e} size={56} radius={16} dim={e.status === 'cancelled'} />{/snippet}
          {#snippet trailing()}<span class="yn">{#if head}<IconButton icon={Pencil} size="s" label={t('studio.edit')} onclick={() => sheets.editor(e.org.id, id)} />{/if}
            <IconButton icon={Eye} size="s" label={t('mg.asStudents')} onclick={() => sheets.event(id)} /></span>{/snippet}
        </Row>
      </Group>

      {#if doorDay}
        <div class="door">
          <Button kind="primary" size="l" full onclick={showQr}>{#snippet icon()}<QrCode size={19} />{/snippet}{t('mk.title')}</Button>
          {#if !doorOpen}<p class="t-foot">{t('door.openAt', { time: time(doorAt) })}</p>{/if}
        </div>
      {/if}

      {#if roomDay}
        {#if !moving}<Group><Row icon={MapPin} title={t('studio.move')} accessory="chevron" onclick={startMove} /></Group>
        {:else}
          <form class="moving" bind:this={roomForm} onsubmit={(ev) => { ev.preventDefault(); void move(); }}>
            <span class="fl"><Field label={t('studio.newRoom')} bind:value={room} maxlength={80} placeholder={e.place || '305'} enterkeyhint="done" /></span>
            <Button kind="primary" size="l" type="submit" disabled={!room.trim()}>{t('common.save')}</Button>
          </form>
        {/if}
      {/if}

      {#if audienced}
        <Group><Row icon={UserCheck} title={t('mk.audience')} value={t(AUD[aud])}
          menu={(['both', 'guests', 'team'] as const).map((a) => ({ label: t(AUD[a]), checked: a === aud, onselect: () => void setAud(a) }))} /></Group>
      {/if}

      {#if head}
        {#if roster.status === 'error'}<EmptyState onretry={loadRoster} />{:else if !list}<Skeleton n={1} />{/if}
        {#if showTeam}
          {#if teamRoster.status === 'error'}<EmptyState onretry={loadTeam} />{:else if !team}<Skeleton n={1} />{/if}
        {/if}
        {#if list || teamLine || (e.needsVolunteers && e.volunteersAsked)}
        <Group>
          {#if teamOnly && teamLine}
            <Row icon={UsersRound} title={teamLine} accessory="chevron" onclick={() => sheets.doorPeople(id)} />
          {:else if !teamOnly && list}
            {#if started || doorDay}<Row icon={UsersRound} title={t('mg.cameOf', { n: came, m: going.length })} subtitle={teamLine} accessory="chevron" onclick={() => sheets.attendees(id)} />
            {:else}<Row icon={UsersRound} title={t('mg.going')} value="{going.length}{e.seats ? ' / ' + e.seats : ''}" accessory="chevron" onclick={() => sheets.attendees(id)} />{/if}
          {/if}
          {#if toCheck}<Row icon={TriangleAlert} title={t('mg.check')} count={toCheck} accessory="chevron" onclick={() => sheets.attendees(id)} />{/if}
          {#if price && of('hold').length}<Row title={t('mg.holds')} value={String(of('hold').length)} accessory="chevron" onclick={() => sheets.attendees(id)} />{/if}
          {#if of('waitlist').length}<Row title={t('mg.waitlist')} value={String(of('waitlist').length)} accessory="chevron" onclick={() => sheets.attendees(id)} />{/if}
          {#if e.needsVolunteers && e.volunteersAsked}<Row icon={HandHeart} title={t('vol.list')} count={e.volunteersAsked} accessory="chevron" onclick={() => sheets.volunteers(id, e.needsVolunteers!)} />{/if}
        </Group>
        {/if}
      {/if}

      <!-- the organizers' own guest list (server organizing.guest_list): whoever has the door, as the door's list -->
      {#if !staff && !e.guestHost && e.status !== 'cancelled' && (co ? coCrew : may(mem, 'door'))}
        <Group><Row icon={FileSpreadsheet} title={t('mk.guestList')} accessory="chevron" onclick={() => { haptic.tap(); sheets.guestList(id); }} /></Group>
      {/if}

      {#if head && e.santa}
        <Group>
          {#if e.santa.drawn || !santaTeam}<Row icon={Gift} title={t(e.santa.drawn ? 'santa.done' : 'santa.title')} value={String(santaN)} />
          {:else}<Row icon={Gift} title={t('santa.inOf', { n: santaTeam.in.length, m: santaTeam.in.length + santaTeam.out.length })} />{/if}
          {#if !e.santa.drawn && live}
            <Row title={t('santa.budget')} value={e.santa.budget ? t('santa.upTo', { sum: money(e.santa.budget) }) : t('santa.budgetPh')} accessory="disclosure" open={!!terms} onclick={editTerms} />
            <Row title={e.regUntil ? `${t('santa.until')} ${until(e.regUntil)}` : t('santa.until')} accessory="disclosure" open={!!terms} onclick={editTerms} />
          {/if}
          {#if e.santa.drawn && e.santa.budget}<Row title={t('santa.budget')} value={t('santa.upTo', { sum: money(e.santa.budget) })} />{/if}
          {#if !e.santa.drawn && live}<Row tone="action" title={t('santa.draw')} onclick={drawSanta} />{/if}
        </Group>
        {#if terms}
          <form class="terms" onsubmit={(ev) => { ev.preventDefault(); void saveTerms(); }}>
            <SantaTerms bind:f={terms} fixed />
            <Button kind="primary" size="l" full type="submit" disabled={readTerms(terms).bad}>{t('common.save')}</Button>
          </form>
        {/if}
        {#if !e.santa.drawn && live && santaTeam}
          <Group>
            <Row icon={BellRing} tone={santaTeam.remindAt ? undefined : 'action'} title={t('santa.remind')}
              subtitle={santaTeam.remindAt ? t('santa.remindAgain', { when: `${relDay(santaTeam.remindAt).toLowerCase()}, ${time(santaTeam.remindAt)}` }) : undefined}
              value={santaTeam.remindAt ? undefined : String(santaTeam.remind)} onclick={remindSanta} />
            <Row icon={Share} tone="action" title={t('santa.share')} onclick={shareSanta} />
          </Group>
          {#if santaTeam.in.length}
            <Group caption="{t('santa.inList')} · {santaTeam.in.length}">
              {#each santaTeam.in as p (p.id)}<Row dense title={p.name}>{#snippet lead()}<Avatar person={p} size={32} tappable={false} />{/snippet}</Row>{/each}
            </Group>
          {/if}
          {#if santaTeam.out.length}
            <Group caption="{t('santa.notYet')} · {santaTeam.out.length}">
              {#each santaTeam.out as p (p.id)}<Row dense title={p.name}>{#snippet lead()}<Avatar person={p} size={32} tappable={false} />{/snippet}</Row>{/each}
            </Group>
          {/if}
        {/if}
      {/if}

      {#if asks.length}
        <Group caption={t('ta.caption')}>
          {#each asks as x (x.person.id)}
            <Row dense title={x.person.name}>
              {#snippet lead()}<Avatar person={x.person} size={36} />{/snippet}
              {#snippet trailing()}<span class="yn"><IconButton icon={X} size="s" kind="gray" label={t('ta.no')} onclick={() => decide(x, false)} />
                <Button kind="tinted" size="s" onclick={() => decide(x, true)}>{t('ta.yes')}</Button></span>{/snippet}
            </Row>
          {/each}
        </Group>
      {/if}

      {#if head && price && list}
        <Group caption={t('mg.money')}>
          <Row title={t('mg.expected')} subtitle="{paying} × {money(price)}" value={money(paying * price)} />
          <Row title={t('mg.byReceipts')} subtitle={unread ? t('mg.unread', { n: unread }) : undefined}>
            {#snippet detail()}<span class="sum num" class:short={byReceipts < paying * price}>{money(byReceipts)}</span>{/snippet}
          </Row>
          {#if auto.length}<Row title={t('mg.auto', { n: auto.length })} subtitle={t('mg.autoHint')} value={money(autoSum)} />{/if}
        </Group>
      {/if}

      {#if head && brought.length}
        <Group caption={t('mg.brought')}>
          {#each brought as x (x.person.id)}
            <Row dense title={x.person.name} accessory="chevron" onclick={() => sheets.person(x.person.id)}
              subtitle={[`${t('mg.broughtSigned')} ${x.signed}`, price && `${t('mg.broughtPaid')} ${x.paid}`, `${t('mg.came')} ${x.came}`].filter(Boolean).join(' · ')}>
              {#snippet lead()}<Avatar person={x.person} size={36} tappable={false} />{/snippet}
            </Row>
          {/each}
        </Group>
      {/if}

      {#if head || reports}
        <Group>
          {#if folded > 3}<Row icon={Ellipsis} title={t('common.more')} accessory="disclosure" open={more} onclick={() => { haptic.tap(); more = !more; }} />{/if}
          {#if more || folded <= 3}
            {#if head}
              <Row icon={UsersRound} title={t('studio.attendees')} accessory="chevron" onclick={() => sheets.attendees(id)} />
              {#if e.teamMax}<Row icon={UsersRound} title={t('tm.board')} accessory="chevron" onclick={() => sheets.teams(id)} />{/if}<!-- a team event (server evteams.py) -->
              {#if e.teamMax}<TournamentRows {id} manage manageBracket={may(mem, 'events')} />{/if}
              {#if e.status !== 'cancelled' && !plain}<Row icon={MessagesSquare} title={t(chat ? 'chat.open' : 'chat.create')} accessory={chat ? 'external' : 'chevron'} onclick={openChat} />{/if}
              <!-- one «Helpers»: the door's (server crew.py, its sheet links the volunteers), else the volunteers -->
              <!-- the door's helpers live under the Mark screen's «Helper» (CrewSheet); here the volunteers who asked -->
              {#if e.needsVolunteers}<Row icon={HandHeart} title={t('mg.helpers')} count={e.volunteersAsked ?? 0} accessory="chevron" onclick={() => sheets.volunteers(id, e.needsVolunteers!)} />{/if}
              <!-- the big screen at the door (/show): connect a laptop, finish, the CSV -->
              <!-- a partner's event has no door of ours: its team is marked here -->
              {#if e.guestHost && teamMark}<Row icon={UserCheck} title={t('scr.team')} accessory="chevron" onclick={() => { haptic.tap(); sheets.screens(undefined, undefined, undefined, undefined, id); }} />{/if}
              {#if live && !e.guestHost}<Row icon={MonitorUp} title={t('scr.title')} accessory="chevron" onclick={() => sheets.screens(undefined, id)} />{/if}
            {/if}
            {#if reports}<Row icon={ClipboardCheck} title={t('evr.title')} accessory="chevron" onclick={() => sheets.eventReport(id, co ? org : undefined)} />{/if}
            {#if head && live && !e.guestHost && !e.guestList && !e.meeting && !e.santa?.drawn && (!started || e.lateSignup)}
              {#if regClosed}<Row title={t('mg.openReg')} onclick={() => setReg(before && before > nowTs() ? before : null, t('mg.regOpened'), e.regUntil)} />
              {:else}<Row title={t('mg.closeReg')} onclick={closeReg} />{/if}
            {/if}
            {#if head && live && !started}<Row tone="destructive" title={t('studio.cancelEvent')} onclick={cancelEvent} />{/if}
            {#if head && e.status === 'cancelled'}<Row tone="destructive" title={t('studio.deleteEvent')} onclick={removeEvent} />{/if}
          {/if}
        </Group>
      {/if}
    </div>
  {/if}
</Sheet>

<style>
  .pg { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-1); }
  .sum { margin-left: auto; color: var(--text-3); }
  .sum.short { color: var(--warning-text); }
  .yn { display: flex; align-items: center; gap: var(--s-2); }
  .door { display: flex; flex-direction: column; align-items: center; gap: var(--s-2); }
  .door .t-foot { color: var(--text-3); }
  .terms { display: flex; flex-direction: column; gap: var(--s-3); }
  .moving { display: flex; align-items: flex-end; gap: var(--s-2); }
  .fl { flex: 1; min-width: 0; }
</style>
