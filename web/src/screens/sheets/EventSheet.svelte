<script lang="ts">
  // Event sheet, tinted by the poster colour, in the Afisha hero's language: what, when and where are words on the
  // picture itself; under it one slab of facts (the price and the seats, the way there, which friends go), then the one
  // action in the bottom bar, alone (Going / price / ticket / waitlist); save and share sit on the picture. Cancelling a sign-up lives on the ticket. Everything secondary follows as plain rows.
  // The organizing team's tools are one group under its own heading: the door (Member+), attendees, edit, cancel (Head+).
  // `preview`: the editor's unsaved form, shown exactly as students will see it (no team tools, buttons inert).
  import Linked from '../../ui/Linked.svelte';
  import Bookmark from '@lucide/svelte/icons/bookmark';
  import Share from '@lucide/svelte/icons/share';
  import Lock from '@lucide/svelte/icons/lock';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import VideoCall from '@lucide/svelte/icons/video';
  import ExternalLink from '@lucide/svelte/icons/external-link';
  import Ticket from '@lucide/svelte/icons/ticket';
  import UserCheck from '@lucide/svelte/icons/user-check';
  import Check from '@lucide/svelte/icons/check';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import MonitorUp from '@lucide/svelte/icons/monitor-up';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import TournamentRows from './TournamentRows.svelte';
  import Hourglass from '@lucide/svelte/icons/hourglass';
  import Gift from '@lucide/svelte/icons/gift';
  import Pencil from '@lucide/svelte/icons/pencil';
  import BookOpen from '@lucide/svelte/icons/book-open';
  import Eye from '@lucide/svelte/icons/eye';
  import ImagePlus from '@lucide/svelte/icons/image-plus';
  import Camera from '@lucide/svelte/icons/camera';
  import Images from '@lucide/svelte/icons/images';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import Link from '@lucide/svelte/icons/link';
  import FileText from '@lucide/svelte/icons/file-text';
  import { shrink } from '../../lib/photo';
  import { FACES } from '../../lib/faces';
  import { burst } from '../../ui/burst';
  import { fly } from '../../ui/fly';
  import { onMount } from 'svelte';
  import AiBadge from '../../ui/AiBadge.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import Plus from '@lucide/svelte/icons/plus';
  import Sheet from '../../ui/Sheet.svelte';
  import CalendarHeart from '@lucide/svelte/icons/calendar-heart';
  import Button from '../../ui/Button.svelte';
  import Poster from '../../ui/Poster.svelte';
  import HeroArt from '../afisha/HeroArt.svelte';
  import EventPlace from '../../ui/EventPlace.svelte';
  import { eventPlace } from '../../lib/map';
  import Santa from './Santa.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import OrgTag from '../../ui/OrgTag.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import EventPlaceRow from '../../ui/EventPlaceRow.svelte';
  import { meetHost } from '../../lib/meet';
  import { eventLinks } from '../../lib/eventLinks';
  import { api, ApiErr, translated, type AlbumPhoto, type EventCard, type DoorAudience, type EventFull, type EventUpdate, type Id, type MeetingAnswer } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, eventById, eventDetails, eventTeamChunk, galleryGone, goingBusy, loadGallery, toggleGoing, toggleSaved, studioChanged, phrase, declineInvite, saveEventRating } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { may, withNick, inner, onTeam, RANK } from '../../lib/perms';
  import { t, tn, money, friendsLine, fmtNum, type Key, placeOf, subjectOf } from '../../lib/i18n/index.svelte';
  import { relDay, time, nowTs, dayMonthShort, parts, at, duration, ago, multiDay, daySpan, endTime } from '../../lib/time';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import { openLink, haptic, inTelegram, shareCard } from '../../lib/tg';
  import { count } from '../../lib/stats';
  import { sheets, registration } from '../../lib/state/sheets';
  import { coverFor, focusPos } from '../../lib/photo';
  import { nameOf, schoolName, shortOf } from '../../lib/short';
  import { service } from '../../lib/clubs';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Section from '../../ui/Section.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Field from '../../ui/Field.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';

  // from: the poster that was tapped, which grows into the header as the sheet opens
  // album: the bot's ph_ link, the guests' album opens over the sheet once its details are in
  let { overlay, id, preview, from, album }: { overlay: Overlay; id: Id; preview?: EventFull; from?: Element | null; album?: boolean } = $props();

  let detail = $state<EventFull | null>(null);
  // a school's own event opened by another school's student (its link): whose it is, nothing else (server seats._event)
  // unset: a verified student with no school known, sent to Settings; the school picked there asks again (the read below)
  // missing: deleted, or a draft (an old bot link, a forwarded one): said so, never a blank sheet
  let onlyFor = $state(''), unset = $state(false), missing = $state(false);
  $effect(() => {
    void session.me?.student?.school;
    if (!preview) eventDetails(id).then((d) => (detail = d)).catch((x) => { detail = null; missing = x instanceof ApiErr && x.code === 'not_found'; if (x instanceof ApiErr && x.message === 'school') { onlyFor = String(x.data.school ?? ''); unset = !!x.data.unset; } });
  });

  // the shared card is the live source (it changes when you tap Going); details add the text
  const e = $derived(preview ?? eventById(id) ?? detail);
  // an online event's link: the row says where it leads, its host always in sight (a typed link may be any https host)
  // the link only from the event just loaded (a card the app holds may carry one since changed or removed); https, a
  // plain host, never Telegram's own (it would open inside Telegram as a deep link): the server's rule, checked again
  const meetUrl = $derived(preview ? preview.onlineUrl : detail?.id === id ? detail.onlineUrl : null);
  const meetAt = $derived(meetHost(meetUrl));
  let pic = $state(0); // which of the header's photos is on screen
  let hero = $state<HTMLDivElement>();
  let land = () => {};
  onMount(() => { if (from && hero) land = fly(from, hero, coverFor(e?.cover, 'card')?.focus); return () => land(); });
  let soon = $state(false), later = $state(false);
  // each a task after a frame was drawn (a frame's own requestAnimationFrame runs before that same frame is drawn when
  // the tap was a touch): the header first, the first screen next, then what is below it
  const after = (fn: () => void) => { let k = 0; const f = requestAnimationFrame(() => (k = setTimeout(fn) as unknown as number)); return () => { cancelAnimationFrame(f); clearTimeout(k); }; };
  onMount(() => { let stop = after(() => { soon = true; stop = after(() => (later = true)); }); return () => stop(); });
  $effect(() => { if (overlay.closing) land(); });
  const about = $derived(preview ? preview.description : detail?.description);
  let raw = $state(false); // the description as typed, not the AI's translation
  const aiAbout = $derived(!preview && !!detail && translated(detail, 'description'));
  // the description's addresses as typed (a translation may mangle one), less those with a row of their own
  const links = $derived(eventLinks(preview ? preview.description : detail?.orig?.description ?? detail?.description,
    [meetUrl, e?.externalUrl, detail?.chat, detail?.discuss]));
  const st = $derived(e?.my?.status);
  // a team event: my team follows my sign-up (made or joined with the same tap, server evteams.signup)
  let seenSt: string | null = null;
  $effect(() => {
    const now = st ?? '';
    if (!preview && (e?.teamMax || e?.santa) && seenSt !== null && now !== seenSt) api.event(id).then((d) => (detail = d)).catch(() => {});
    seenSt = now;
  });
  const going = $derived(st === 'going');
  const full = $derived(!!e && e.seats != null && e.taken >= e.seats && st !== 'going' && st !== 'hold');
  const cancelled = $derived(e?.status === 'cancelled');
  // the horizontal clip plays only where it costs nothing extra: not on the light look, not with Data Saver
  const wv = $derived(e && 'wideVideo' in e ? (e as EventFull).wideVideo : null);
  const wide = $derived(wv?.url && !cancelled && !document.documentElement.classList.contains('lowfx')
    && !(navigator as { connection?: { saveData?: boolean } }).connection?.saveData ? wv.url : null);
  // what it costs, said once under the title (a club's own meeting or a partner's event names no price)
  const cost = $derived(!e ? '' : e.price ? money(e.price) : e.guestHost || inner(e) || e.meeting ? '' : t('event.free'));
  const seatsLeft = $derived(!e?.seats ? '' : e.taken >= e.seats ? t('event.full') : tn('event.seatsLeft', e.seats - e.taken));
  // the header's still picture, and the same one soft under the words (photos swiped sideways and a clip move under them: no lens there)
  const art = $derived(e ? coverFor(e.cover, 'card') ?? e.video?.poster ?? null : null);
  const strip = $derived(!!e && !e.video?.url && !!e.cover && !!e.slides?.length);
  const still = $derived(!wide && !strip && !e?.video?.url);
  // a place that leads somewhere has a row (our map, 2GIS, the meeting's link); one that doesn't is said on the picture only
  const leads = $derived(!e ? false : e.online ? !!(meetUrl && meetAt) : (eventPlace(e.place, e.placeUrl)?.kind ?? 'campus') !== 'campus');
  const started = $derived(!!e && e.startsAt <= nowTs());
  // the registration deadline closes "Going" for those not in yet; a 1st-year takes a paid event's free seat
  const regShut = $derived(!!e?.regUntil && e.regUntil <= nowTs() && st !== 'going' && st !== 'hold' && st !== 'waitlist');
  // still open and I'm not in: said right over the button (closed: the button itself says so)
  const regNote = $derived(!!e?.regUntil && e.regUntil > nowTs() && !cancelled && !started && !e.externalUrl && st !== 'going' && st !== 'hold' && st !== 'waitlist' && !e.santa); // a Santa game: its own row names the deadline
  const freeMe = $derived(!!e?.price && !!e.freeLeft && !!session.me?.student?.freeFirst);
  const canInvite = $derived(!preview && !!session.me?.student && !!e && e.status === 'published' && !started && (e.visibility ?? 'public') === 'public');
  const over = $derived(!!e && (e.endsAt ?? e.startsAt + 3 * 3600) <= nowTs());
  const doorOver = $derived(!!e && (e.endsAt ?? e.startsAt + 6 * 3600) <= nowTs()); // the server's door (DOOR_LATE without an end)
  const register = (runs: boolean) => e && registration(e, runs, session.me?.vol?.org);
  const shut = $derived(started && !e?.lateSignup); // late sign-up: "Going" stays until the end (over comes first)
  // the student's classes around the event that day: the last one before, any that overlap, the first one
  // after — so they see at once whether they make it
  const day = $derived.by(() => {
    if (!e || !data.schedule.length || multiDay(e.startsAt, e.endsAt)) return null; // days of it: no one day's classes to weigh
    const p = parts(e.startsAt);
    const on = (hm: string) => { const [h, m] = hm.split(':').map(Number); return at(p.y, p.m, p.d, h, m); };
    const cls = data.schedule.filter((c) => c.weekday === (p.wd || 7)).map((c) => ({ c, b: on(c.begins), en: on(c.ends) }));
    const end = e.endsAt ?? e.startsAt + 1;
    const clash = cls.filter((x) => x.b < end && x.en > e.startsAt).sort((a, b) => a.b - b.b);
    const before = cls.filter((x) => x.en <= e.startsAt).sort((a, b) => b.en - a.en)[0];
    const after = cls.filter((x) => x.b >= end).sort((a, b) => a.b - b.b)[0];
    return before || clash.length || after ? { before, clash, after } : null;
  });

  const mem = $derived(session.me?.memberships.find((m) => m.org.id === e?.org.id) ?? null);
  const role = $derived(mem?.role ?? null);
  const crew = $derived(!preview && !!e && e.status === 'published' && may(mem, 'door'));
  const head = $derived(may(mem, 'events'));
  // whom the door records (server checkin.set_audience), right under the Mark row where the organizer lands
  const AUD = { both: 'mk.aBoth', guests: 'mk.aGuests', team: 'mk.aTeam' } as const;
  async function setAud(a: DoorAudience) {
    if (!detail) return;
    const was = detail.audience;
    detail.audience = a; haptic.tap();
    try { await api.setAudience(id, a); } catch { detail.audience = was; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // a co-hosted event's other club (server cohosts.py): its event team works the door and reads the list; its Vice+
  // may leave. Editing, price and seats stay the host's
  const coMem = $derived(e?.coHost ? session.me?.memberships.find((m) => m.org.id === e.coHost!.id) ?? null : null);
  const coCrew = $derived(!preview && !!e && e.status === 'published' && !crew && may(coMem, 'events'));
  const coLead = $derived(!preview && !!coMem && RANK[coMem.role] >= RANK.vice);
  // the host club's own people come as guests by its President's or a Vice's yes (server seats.team_ask): ask, or
  // take the ask back while it waits; a yes turns this back into the usual Going
  const teamOnly = $derived(!preview && !!e && !going && st !== 'hold' && !e.guestHost && onTeam(e, session.me?.memberships));
  // ponytail: asking to come as a guest is off (owner, Nov 14, people lost at the Talent Show door): the club's own people
  // read a plain no; the ask flow (server seats.team_ask) stays for when it comes back
  const askable = false as boolean;
  const noGuest = $derived(teamOnly && !cancelled && !over && !e?.externalUrl);
  function setAsk(a: EventCard['teamAsk']) { const card = eventById(id); if (card) card.teamAsk = a; if (detail) detail = { ...detail, teamAsk: a }; }
  async function teamAsk() {
    const was = e?.teamAsk;
    haptic.tap(); setAsk('pending'); // at once; back if the server says no
    try { await api.teamAsk(id); haptic.ok(); say(t('ta.sent'), 'raising_hands_3d_default'); }
    catch { setAsk(was); haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function teamUnask() {
    if (!(await sheets.ask({ title: t('ta.unaskAsk'), ok: t('ta.unask'), cancel: t('common.cancel') }))) return;
    setAsk(undefined);
    try { await api.teamUnask(id); haptic.soft(); }
    catch { setAsk('pending'); haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function leaveCohost() {
    if (!e?.coHost || !(await sheets.ask({ title: t('co.leaveAsk', { club: nameOf(e.org) }), text: t('co.leaveText'), ok: t('co.leave'), cancel: t('common.cancel'), danger: true }))) return;
    const was = e.coHost, card = eventById(id);
    if (card) card.coHost = null; // at once; back if the server says no
    if (detail) detail = { ...detail, coHost: null };
    try { await api.cohostEnd(id); haptic.soft(); studioChanged(); }
    catch { if (card) card.coHost = was; if (detail) detail = { ...detail, coHost: was }; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // volunteering: a short "why", then the organizers answer
  let volWriting = $state(false), volNote = $state('');
  async function volApply() {
    if (!session.me?.student) { sheets.login(); return; }
    try { detail = await api.volunteer(id, volNote); volWriting = false; haptic.ok(); say(t('vol.sentSay'), 'raising_hands_3d_default'); }
    catch (x) { haptic.error(); say(t(x instanceof ApiErr && x.message === 'first_year' ? 'vol.noFirst' : x instanceof ApiErr && x.message === 'full' ? 'vol.full' : 'common.error'), 'pleading_face_3d'); }
  }
  async function volLeave() {
    try { detail = await api.volunteerLeave(id); haptic.soft(); say(phrase('say.volLeft'), 'waving_hand_3d_default'); } catch { haptic.error(); }
  }

  // ---- "+N seats": when it's full, the club's Head+ add seats right here; the waitlist moves in ----
  let adding2 = $state(false);
  async function addSeats(n: number) {
    adding2 = true;
    try { detail = await api.addSeats(id, n); studioChanged(); haptic.ok(); say(t('seats.added', { n }), 'raising_hands_3d_default'); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { adding2 = false; }
  }

  // ---- a leaders meeting: DMP sees every club's answers ----
  let answers = $state<import('../../lib/api').LeadersAnswer[] | null>(null);
  $effect(() => { if (e?.visibility === 'leaders' && head && crew) api.leadersAnswers(id).then((l) => (answers = l)).catch(() => {}); });

  // ---- a club meeting: "can't" says why; the club's Head+ see everyone expected, and after it who came ----
  let meet = $state<MeetingAnswer[] | null>(null);
  const loadMeet = () => api.meetingAnswers(id).then((l) => (meet = l)).catch(() => {});
  $effect(() => { if (e?.meeting && head && crew) void loadMeet(); });
  const meetGroups = $derived.by(() => {
    if (!meet) return [];
    const excused = (a: MeetingAnswer) => a.answer === 'no' && !!a.note;
    return (over
      ? [['meet.came', meet.filter((a) => a.came)], ['meet.excused', meet.filter((a) => !a.came && excused(a))], ['meet.missed', meet.filter((a) => !a.came && !excused(a))]]
      : [['meet.yes', meet.filter((a) => a.answer === 'yes')], ['meet.no', meet.filter((a) => a.answer === 'no')], ['meet.none', meet.filter((a) => a.answer === 'none')]]
    ).filter(([, l]) => (l as MeetingAnswer[]).length) as [Key, MeetingAnswer[]][];
  });
  async function cantCome() {
    const why = await sheets.askText({ title: t('meet.whyTitle'), text: t('meet.whyText'), ok: t('meet.send'), cancel: t('common.cancel'),
      placeholder: t('meet.whyPh'), max: 140 });
    if (why) declineInvite(id, why);
  }

  // ---- the organizer's updates: the newest under the title, the rest one tap away; Head+ write here ----
  const ups = $derived(detail?.updates ?? []);
  let allUps = $state(false);
  let writing = $state(false);
  let draft = $state('');
  let sending = $state(false);
  async function sendUpdate() {
    sending = true;
    try {
      const fresh = await api.postUpdate(id, draft.trim());
      if (detail) detail = { ...detail, updates: fresh };
      draft = ''; writing = false;
      haptic.ok(); say(t('upd.sent'), 'party_popper_3d');
    } catch (err) { haptic.error(); say(err instanceof ApiErr && err.code === 'rate_limited' ? t('upd.tooMany') : t('common.error'), 'warning_3d'); }
    finally { sending = false; }
  }
  // ---- one tap after the event (checked-in people): a face sends the rating at once; a comment can follow ----
  let rated = $state<number | null>(null);
  $effect(() => { if (detail) rated = detail.myRating; });
  let note = $state('');
  let noted = $state(false);
  let rating = $state(false); // rated before: one quiet line until tapped to change (the full faces again)
  let ratingSaving = false;
  async function rateIt(score: number, comment?: string) {
    if (ratingSaving) return;
    ratingSaving = true;
    const was = rated;
    rated = score; rating = true; haptic.select();
    try {
      const fresh = await saveEventRating(id, score, comment);
      if (!fresh) { rated = was; return; }
      detail = fresh;
      if (comment) { noted = true; haptic.ok(); say(t('rate.saved'), 'sparkles_3d'); }
      else say(phrase('say.rated'), FACES[score - 1]);
    } catch { rated = was; haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { ratingSaving = false; }
  }
  // ---- the guests' album: who came adds photos (several at once, one upload after another); a mosaic of the first ----
  const photos = $derived(detail?.photos ?? []);
  const shown = $derived(photos.length >= 6 ? 6 : photos.length >= 3 ? 3 : photos.length); // whole blocks of the mosaic
  let picker = $state<HTMLInputElement>();
  let adding = $state(0);
  async function addPhotos(ev: Event) {
    const el = ev.currentTarget as HTMLInputElement, files = [...(el.files ?? [])].slice(0, 10);
    el.value = '';
    let added = 0;
    adding = files.length;
    for (const file of files) {
      try { detail = await api.addAlbumPhoto(id, await shrink(file)); added++; count('do.photo'); }
      catch (err) {
        haptic.error();
        if (err instanceof ApiErr && err.code === 'forbidden') { say(t('album.full'), 'pleading_face_3d'); break; }
        say(t('ed.photoBad'), 'pleading_face_3d');
      } finally { adding = Math.max(0, adding - 1); }
    }
    adding = 0;
    if (added) { haptic.ok(); burst(); say(tn('album.added', added), 'camera_with_flash_3d'); void loadGallery(); }
  }
  async function removePhoto(p: AlbumPhoto): Promise<AlbumPhoto[] | null> {
    try { detail = await api.removeAlbumPhoto(id, p.id); galleryGone(p); return detail.photos; }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); return null; }
  }

  const hidePhoto = (p: AlbumPhoto) => { galleryGone(p); if (detail) detail = { ...detail, photos: detail.photos.filter((x) => x.id !== p.id) }; }; // reported: gone for me
  // a tile opens its photo, grown out of the tile; the header, "+N" and the bar open all of them, a grid
  let mosaic = $state<HTMLDivElement>();
  const viewAlbum = (i = 0) => sheets.photos(photos, i, removePhoto, hidePhoto, (p) => mosaic?.querySelector(`[data-id="${p.id}"]`));
  const allPhotos = () => sheets.album(() => photos, removePhoto, hidePhoto, detail?.canAddPhotos ? () => picker?.click() : undefined, () => adding);
  let albumDone = false;
  $effect(() => { if (album && detail && !albumDone) { albumDone = true; if (detail.photos.length) allPhotos(); } });

  async function removeUpdate(u: EventUpdate) {
    if (!(await sheets.ask({ title: t('upd.deleteAsk'), ok: t('upd.delete'), cancel: t('common.cancel'), danger: true }))) return;
    try { await api.deleteUpdate(id, u.id); if (detail) detail = { ...detail, updates: detail.updates.filter((x) => x.id !== u.id) }; haptic.soft(); say(t('say.updDeleted'), 'waving_hand_3d_default'); }
    catch { say(t('common.error'), 'warning_3d'); }
  }

  async function cancelEvent() {
    if (!(await sheets.ask({ title: t('studio.cancelAsk'), text: t('studio.cancelText'), ok: t('studio.cancelGo'), cancel: t('tk.keep'), danger: true }))) return;
    try { await api.cancelEvent(id); studioChanged(); haptic.warn(); say(t('say.eventCancelled'), 'crying_face_3d'); }
    catch { say(t('common.error'), 'warning_3d'); }
  }

  function share() {
    if (!e) return; // the Button gives the tap
    count('do.share');
    // absolute date: the card is read later, when "tomorrow" is wrong
    shareCard({ kind: 'ev', id: String(id) }).then((sent) => { if (sent) say(phrase('say.shared'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'warning_3d'); });
  }
  // the web app: Share is the top pill (Overlay.action), the save stays on the picture; inside Telegram both stay there
  $effect(() => { if (!inTelegram) overlay.action = e && !preview ? { icon: Share, label: t('event.share'), run: share } : null; });
  // "My link": the same card with my badge code in its button, so who signs up by it counts for me (EventManage's "Who brought")
  const myLink = $derived(!!mem && !!e && e.status === 'published' && !started && !e.guestHost && !e.externalUrl && !inner(e) && !preview);
  // the team's tools group has a row to show (a guest host's event leaves a Member nothing)
  // a door helper (server crew.py): someone a running club's President or Vice asked to help at this event's door
  const helper = $derived(!preview && !crew && !coCrew && e?.status === 'published' ? detail?.myCrew ?? null : null);
  const crewLead = $derived(!preview && detail?.crew != null && e?.status === 'published' && !over && !e.guestHost && !inner(e));
  const tooled = $derived(!!e && ((crew && (!e.guestHost || head)) || myLink || coCrew || coLead || !!helper));
  function shareMine() {
    if (!e) return;
    haptic.tap(); count('do.share');
    shareCard({ kind: 'ev', id: String(id), mine: '1' })
      .then((sent) => { if (sent) say(t('event.myLinkSent'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'warning_3d'); });
  }
</script>

<Sheet {overlay} icon={CalendarHeart} title={preview ? t('ed.preview') : t('cap.event')} tint={e?.tint}>
  {#if e}
    {#if preview}<p class="pv"><Tag tone="accent"><Eye size={15} />{t('event.preview')}</Tag></p>{/if}
    <div class="hero theme-dark" class:cancelled class:deep={!still} class:pics={strip} class:clip={!wide && !!e.video?.url && !cancelled} bind:this={hero}>
      <!-- the header: the horizontal clip behind it, else the vertical one, else the photos swiped sideways, else the cover
           (none: the club's colour as a mesh with the event's 3D mark, the Afisha hero's own picture) -->
      {#if wide}
        <Poster item={e} big radius={0} />
        <video class="wide" src={wide} poster={wv?.poster?.url} autoplay muted loop playsinline preload="none"></video>
      {:else if strip}
        <div class="strip" onscroll={(s) => (pic = Math.round(s.currentTarget.scrollLeft / s.currentTarget.clientWidth))}>
          {#each [coverFor(e.cover, 'card')!, ...e.slides] as p, i (p.id)}
            <button class="pic" aria-label={t('fc.photo')} onclick={() => sheets.photos([coverFor(e.cover, 'card')!, ...e.slides].map((x, k) => ({ ...x, id: x.id ?? -k, by: null, mine: true, canDelete: false })), i)}>
              <img draggable="false" src={p.url} alt="" decoding="async" loading={i ? 'lazy' : 'eager'} style:object-position={i ? null : focusPos(p)} /></button>
          {/each}
        </div>
        <span class="dots" aria-hidden="true">{#each [e.cover, ...e.slides] as _, k (k)}<i class:on={k === pic}></i>{/each}</span>
      {:else if e.video?.url}
        <Poster item={e} big play radius={0} dim={cancelled} />
      {:else}
        <HeroArt pic={art} emoji={e.emoji} color={e.color ?? e.tint} first />
      {/if}
      <div class="shade"></div>
      <!-- over the picture, the floating layer: whose it is, and the two quiet actions (save, share) in glass; the bar
           below keeps the one main action alone -->
      <div class="top">{#if e.coHost}<span class="org"><OrgTag org={e.org} co={e.coHost} onpick={(o) => sheets.club(o)} /></span>
      {:else}<button class="org" onclick={() => sheets.club(e.org.id)}><OrgTag org={e.org} /></button>{/if}
      <span class="acts" class:on={e.saved} inert={!!preview}>
        <IconButton icon={Bookmark} kind="glass" size="s" on={e.saved} label={e.saved ? t('event.saved') : t('event.save')} onclick={() => toggleSaved(id)} />
        {#if inTelegram}<IconButton icon={Share} kind="glass" size="s" label={t('event.share')} onclick={share} />{/if}</span></div>
      <!-- what, when, where: the words on the picture, read in one look. Under them the picture goes soft and dark (the
           lens: its small thumb again, blurred, a still layer drawn once); taps fall through to the photos -->
      <div class="slab">
        {#if still && art}<span class="lens" aria-hidden="true"><img src={art.thumb} alt="" decoding="async" draggable="false" style:object-position={focusPos(art)} /></span>{/if}
        <div class="tags">
        {#if e.meeting}<Tag tone="onphoto">{t('event.meeting')}</Tag>{:else if e.visibility === 'members'}<Tag tone="onphoto">{t('event.teamOnly')}</Tag>{:else if e.visibility === 'leaders'}<Tag tone="onphoto">{t('event.leaders')}</Tag>{:else if e.firstYear}<Tag tone="warning">{t('event.firstYear')}</Tag>{/if}
        {#if e.school}<Tag tone="onphoto">{t('event.schoolOnly', { school: shortOf(e.org) })}</Tag>{/if}
        {#if service(e.org)}<Tag tone="onphoto">{t('clubs.office')}</Tag>{/if}</div>
        <h2 class="ttl" class:strike={cancelled}>{e.title.replace(/(\p{L})-(\p{L})/gu, '$1\u2011$2')}</h2><!-- "stand-up" stays on one line -->
        {#if cancelled}<p class="cancel">{t('event.cancelledLong')}</p>{/if}
        <p class="when">{multiDay(e.startsAt, e.endsAt) ? daySpan(e.startsAt, e.endsAt) : relDay(e.startsAt)}, {time(e.startsAt)}{endTime(e.startsAt, e.endsAt) ? ' – ' + endTime(e.startsAt, e.endsAt) : ''}</p>
        {#if !e.santa || e.place || e.placeUrl || e.online}<p class="where"><EventPlace {e} pin /></p>{/if}
        {#if e.guestHost}<p class="where">{t('event.with', { host: e.guestHost })} · {t('event.notKbtu')}</p>{/if}
      </div>
    </div>

    <!-- the rest of the first screen and the bar a frame later: in the tap's frame the sheet is still below the screen
         (its rise starts there), only the header shows, flying in from the poster -->
    {#if soon}
    <div class="page">

    {#if going && detail?.mySanta && !cancelled}<Santa {id} {e} mine={detail.mySanta} />{/if}
    <!-- Secret Santa's terms (server santa.py), the same for the whole team: the gift's budget; the wishlists' deadline
         for one not in yet (one who is in reads the draw's time on their card); the gifts day by its name -->
    {#if e.santa && !cancelled && !over}
      <Group>
        {#if e.santa.budget}<Row icon={Gift} title={t('santa.budget')} value={t('santa.upTo', { sum: money(e.santa.budget) })} />{/if}
        {#if !e.santa.drawn && e.regUntil && !going}<Row icon={Hourglass} title={t('santa.until')} value="{dayMonthShort(e.regUntil)}, {time(e.regUntil)}" whole />{/if}
        <Row icon={CalendarHeart} title={t('santa.day')} value="{dayMonthShort(e.startsAt)}, {time(e.startsAt)}" whole />
      </Group>
    {/if}

    {#if detail && !e.meeting && (photos.length || detail.canAddPhotos)}
      <!-- the guests' album first, right under the header (after the event it's what the sheet is about) -->
      <section class="album">
        <!-- engine: Section could take a trailing action (here "Add"); its header in Group's caption size -->
        <div class="al-h">{#if photos.length}<button class="al-all" onclick={allPhotos}><h3 class="fs-t3">{t('album.title')}<span class="n num">{photos.length}</span></h3><ChevronRight size={18} /></button>
          {:else}<h3 class="fs-t3">{t('album.title')}</h3>{/if}
          <!-- after the event the bar's own "Add photos" does it -->
          {#if detail.canAddPhotos && !over}<Button kind="tinted" size="s" disabled={adding > 0} onclick={() => picker?.click()}>{#snippet icon()}<ImagePlus size={16} />{/snippet}{t('album.add')}</Button>{/if}</div>
        {#if shown || adding}
          <div class="mosaic n{Math.min(shown, 3)}" bind:this={mosaic}>
            {#each photos.slice(0, shown) as p, i (p.id)}
              <button class="ph" data-id={p.id} style="background-color:{p.color ?? 'var(--surface-2)'}" aria-label={i === shown - 1 && photos.length > shown ? undefined : t('fc.photo')} onclick={() => (i === shown - 1 && photos.length > shown ? allPhotos() : viewAlbum(i))}>
                <img draggable="false" src={p.thumb} alt="" loading="lazy" decoding="async" />
                {#if i === shown - 1 && photos.length > shown}<span class="more num">+{photos.length - shown}</span>{/if}
              </button>
            {/each}
            {#each { length: adding } as _, i (i)}<span class="ph wait"></span>{/each}
          </div>
        {:else}
          <EmptyState inline text={t('album.empty')} />
        {/if}
        <input type="file" accept="image/*" multiple hidden bind:this={picker} onchange={addPhotos} />
      </section>
    {/if}

    {#if detail && rated && !rating}
      <!-- rated before: one quiet line; a tap brings the faces back to change it -->
      <button class="mine" disabled={!detail.canRate} onclick={() => { rating = true; haptic.tap(); }}>
        <span>{t('rate.mine')}</span><Emoji name={FACES[rated - 1]} size={22} /></button>
    {:else if detail && (detail.canRate || detail.myRating != null)}
      <section class="rate">
        <b class="rq">{rated ? t('rate.thanks') : t('rate.ask')}</b>
        <div class="faces">
          {#each FACES as f, i (i)}<button class:on={rated === i + 1} class:dim={!!rated && rated !== i + 1} disabled={!detail.canRate} onclick={() => rateIt(i + 1, note.trim() || undefined)} aria-label={String(i + 1)}><Emoji name={f} size={34} /></button>{/each}
        </div>
        {#if rated && detail.canRate && !noted}
          <!-- Enter sends too: the form's submit (the button is disabled, so is Enter, while the field is empty) -->
          <form class="rin" onsubmit={(ev) => { ev.preventDefault(); if (note.trim()) void rateIt(rated!, note.trim()); }}>
            <Field label={t('rate.comment')} bind:value={note} maxlength={300} enterkeyhint="send" />
            <Button kind="secondary" size="s" type="submit" disabled={!note.trim()}>{t('rate.add')}</Button>
          </form>
        {/if}
        <p class="fs-sub faint">{t('rate.anon')}</p>
      </section>
    {/if}

    {#if detail?.ratings}
      {@const r = detail.ratings}
      <section class="rsum">
        <div class="rs-top">{#if r.avg != null}<span class="avg num">{fmtNum(r.avg)}</span>{/if}<span><b>{t('rate.title')}</b><i class="fs-sub dim">{tn('rate.count', r.count)}{r.avg == null ? ' · ' + t('rate.few') : ''}</i></span></div>
        {#each [...r.dist].reverse() as n, i (i)}
          <div class="rs-row"><span class="rf"><Emoji name={FACES[4 - i]} size={18} /></span><span class="rbar"><span style="width:{r.count ? (n / r.count) * 100 : 0}%"></span></span><span class="rn num">{n}</span></div>
        {/each}
        {#each r.comments.slice(0, 20) as c, i (i)}<p class="rc"><Emoji name={FACES[c.score - 1]} size={18} />{c.body}</p>{/each}
      </section>
    {/if}

    {#if e.visibility === 'leaders' && head && crew && answers}
      <Group caption="{t('lead.answers')} · {answers.reduce((n, a) => n + a.people.filter((p) => p.answer === 'yes').length, 0)} / {answers.reduce((n, a) => n + a.people.length, 0)}">
        {#each answers as a (a.org.id)}
          <Row dense title={nameOf(a.org)} subtitle={a.people.map((p) => `${p.answer === 'yes' ? '✓' : p.answer === 'no' ? '✕' : '…'} ${p.fullName}`).join(' · ')}>
            {#snippet lead()}<OrgLogo org={a.org} size={28} />{/snippet}
          </Row>
        {/each}
      </Group>
    {/if}

    {#if ups.length}
      <!-- the organizer's updates: the newest under the facts' head in the accent, the rest one tap away -->
      <div class="ups">
        {#each allUps ? ups : ups.slice(0, 1) as u, i (u.id)}
          <Notice tone={i > 0 ? 'neutral' : 'accent'} icon={Megaphone} title="{t('upd.title')} · {ago(u.at)}"
            action={u.canDelete ? { label: t('upd.delete'), onclick: () => removeUpdate(u) } : undefined}><p class="fs-body up-b">{u.body}</p></Notice>
        {/each}
        {#if ups.length > 1 && !allUps}<span class="lnk"><Button kind="plain" size="s" onclick={() => (allUps = true)}>{t('upd.more', { n: ups.length - 1 })}</Button></span>{/if}
      </div>
    {/if}

    <!-- the facts in one slab: what it costs and what is left, the way there (a row only when it leads somewhere: a
         chevron opens the map, an arrow leaves for 2GIS or the meeting), who of mine goes and calling the rest -->
    {#if (!cancelled && !over && (cost || e.seats)) || leads || (!cancelled && (e.friends.length || canInvite))}
    <Group>
      {#if !cancelled && !over && (cost || e.seats)}
        <Row icon={Ticket} title={cost || seatsLeft} value={cost ? seatsLeft || undefined : undefined} invalid={full && !!cost} whole
          subtitle={e.price && e.freeFirst && !started ? (e.freeLeft ? t('event.freeFirst', { n: e.freeLeft, of: e.freeFirst }) : t('event.freeFirstGone')) : undefined} />
      {/if}
      {#if leads}
        <!-- online: the meeting opens outside, the server checked the link (core.online_url) -->
        {#if e.online}<Row icon={VideoCall} title={placeOf(e.place, true)} subtitle={meetAt ?? undefined} accessory="external" onclick={() => openLink(meetUrl!, true)} />
        {:else}<EventPlaceRow {e} />{/if}
      {/if}
      {#if !cancelled && e.friends.length}
        <Row title={friendsLine(e.friends.map((f) => f.name), over)}>
          {#snippet lead()}<span class="stack">{#each e.friends.slice(0, 4) as f (f.id)}<Avatar person={f} size={28} />{/each}</span>{/snippet}
          {#snippet trailing()}{#if canInvite}<IconButton icon={UserPlus} kind="tinted" size="s" label={t('inv.title')} onclick={() => sheets.invite(id, e.title)} />{/if}{/snippet}
        </Row>
      {:else if !cancelled && canInvite}<Row icon={UserPlus} title={t('inv.title')} accessory="chevron" onclick={() => sheets.invite(id, e.title)} />{/if}
    </Group>
    {/if}

    {#if (e.meeting || e.visibility === 'leaders') && st === 'cancelled' && e.my?.cancelReason === 'self' && !started}
      <p class="fs-sub dim note">{e.my.note ? t('meet.yourNo', { why: e.my.note }) : t('meet.yourNoBare')}</p>{/if}
    {#if e.my?.status === 'cancelled' && (e.my.cancelReason === 'receipt_rejected' || e.my.cancelReason === 'hold_expired') && !over}
      <Notice tone="warning" text={t(e.my.cancelReason === 'receipt_rejected' ? 'pay.rejected' : 'pay.holdGone')} />
    {/if}

    <!-- below the first screen: built a frame after the sheet appears, so its rise starts at once -->
    {#if later}
    {#if detail?.teams && !preview && !cancelled}
      {#await eventTeamChunk()}
        <Skeleton n={1} />
      {:then { default: EventTeam }}
        <EventTeam {detail} {going} onchange={(d) => (detail = d)} />
      {:catch}
        <Notice text={t('common.offline')} />
      {/await}
    {/if}
    {#if e.teamMax && !preview}<TournamentRows {id} manage={head} standalone />{/if}

    <!-- the event's own people: everything they do with it in one group of plain rows, under its own heading -->
    {#if tooled || (head && crew)}
      <Group caption={t('event.tools')}>
        {#if crew}
          {#if e.guestHost}{:else if inner(e)}<Row icon={UserCheck} title={t('studio.marks')} accessory="chevron" onclick={() => sheets.scanner(id, true)} />
            {#if head && !doorOver}<Row icon={QrCode} title={t('scr.showQr')} accessory="chevron" onclick={() => sheets.eventQr(id)} />{/if}
          <!-- the registration mode: the scanner and the event's QR on this phone, one switch apart -->
          {:else}<Row icon={ScanLine} title={t('mk.title')} accessory="chevron" onclick={() => register(head)} />
            {#if head && detail && !over && !e.guestHost}<Row icon={UserCheck} title={t('mk.audience')} value={t(AUD[detail.audience ?? 'both'])}
              menu={(['both', 'guests', 'team'] as const).map((a) => ({ label: t(AUD[a]), checked: a === (detail?.audience ?? 'both'), onselect: () => void setAud(a) }))} />{/if}
          {/if}
          {#if head}
            {#if !e.guestHost}<Row icon={UsersRound} title={t('studio.attendees')} accessory="chevron" onclick={() => sheets.attendees(id)} />{/if}
            {#if e.teamMax}<Row icon={UsersRound} title={t('tm.board')} value={detail?.teams?.count ? String(detail.teams.count) : undefined} accessory="chevron" onclick={() => sheets.teams(id)} />{/if}
            <!-- full before it starts: more seats right here, the waitlist moves in -->
            {#if e.seats && !cancelled && !started && e.taken >= e.seats}<Row icon={Plus} title={t('seats.addRow')} disabled={adding2}
              menu={[5, 10, 20].map((n) => ({ label: `+${n}`, onselect: () => void addSeats(n) }))} />{/if}
            <Row icon={Megaphone} title={t('upd.write')} accessory="disclosure" open={writing} onclick={() => (writing = !writing)} />
            <Row icon={Pencil} title={t('studio.edit')} accessory="chevron" onclick={() => sheets.editor(e.org.id, id)} />
          {/if}
        {/if}
        {#if coCrew}
          <Row icon={ScanLine} title={t('mk.title')} accessory="chevron" onclick={() => register(true)} />
          <Row icon={UsersRound} title={t('studio.attendees')} accessory="chevron" onclick={() => sheets.attendees(id)} />
          {#if !over}<Row icon={MonitorUp} title={t('scr.title')} accessory="chevron" onclick={() => sheets.screens(undefined, id)} />{/if}
        {/if}
        <!-- a door helper: the same Mark screen as the club's own (QR, scanner; a «door» helper the lists too) -->
        {#if helper}<Row icon={ScanLine} title={t('mk.title')} accessory="chevron" onclick={() => (helper === 'scan' ? sheets.scannerOnly(id) : sheets.scanner(id, false, true))} />{/if}
        {#if coLead && crewLead}<Row icon={UsersRound} title={t('crew.title')} count={detail?.crew?.length ?? 0} accessory="chevron" onclick={() => sheets.crew(id, () => void api.event(id).then((d) => (detail = d)).catch(() => {}))} />{/if}
        {#if myLink}<Row icon={Link} title={t('event.myLink')} onclick={shareMine} />{/if}
        {#if coLead}<Row tone="destructive" title={t('co.leave')} onclick={leaveCohost} />{/if}
      </Group>
      {#if head && crew && writing}
        <div class="ups">
          <Field label={t('upd.write')} bind:value={draft} multiline rows={2} maxlength={300} placeholder={t('upd.placeholder')} />
          <div class="up-acts"><span class="fs-sub faint">{t('upd.note')}</span>
            <Button kind="primary" size="s" loading={sending} disabled={draft.trim().length < 2} onclick={sendUpdate}>{t('upd.send')}</Button></div>
        </div>
      {/if}
    {/if}

    {#if day && !cancelled && !over}
      <Notice tone={day.clash.length ? 'warning' : 'neutral'} icon={BookOpen} title={t('day.title')}>
        {#if day.before}<p class="fs-body">{t('day.before', { subject: subjectOf(day.before.c), end: day.before.c.ends, gap: duration(e.startsAt - day.before.en) })}</p>{/if}
        {#each day.clash as x (x.c.begins + x.c.subject)}<p class="fs-body warn">{t('day.clash', { subject: subjectOf(x.c), from: x.c.begins, to: x.c.ends })}</p>{/each}
        {#if day.after}<p class="fs-body">{e.endsAt ? t('day.after', { subject: subjectOf(day.after.c), from: day.after.c.begins, gap: duration(day.after.b - e.endsAt) }) : t('day.afterOpen', { subject: subjectOf(day.after.c), from: day.after.c.begins })}</p>{/if}
      </Notice>
    {/if}

    {#if about}
      <Section title={t('event.about')}>
        <p class="fs-body desc selectable"><Linked text={(aiAbout && raw ? detail?.orig?.description : about) ?? ''} /></p><!-- addresses tappable: a tournament's rules, a form -->
        {#if aiAbout}<span class="lnk trn"><Button kind="plain" size="s" onclick={() => (raw = !raw)}>{#snippet icon()}<AiBadge />{/snippet}{raw ? t('ai.showTr') : t('ai.showOrig')}</Button></span>{/if}
      </Section>
    {/if}

    <!-- links and documents: its rules (a PDF the club attached, the pages as pictures in the photo viewer) and the
         description's addresses, each with its host; nothing when it has neither -->
    {#if detail?.doc || links.length}
      <div class="links"><Group caption={t('event.links')}>
        {#if detail?.doc}{@const d = detail.doc}<Row icon={FileText} title={d.title ?? t('event.doc')} subtitle={tn('ed.docPages', d.pages.length)} accessory="chevron" onclick={() => sheets.photos(d.pages.map((x, k) => ({ ...x, id: -k - 1, by: null, mine: true, canDelete: false })), 0)} />{/if}
        {#each links as l (l.url)}<Row icon={Link} title={l.host} subtitle={l.rest || undefined} accessory="external" onclick={() => openLink(l.url)} />{/each}
      </Group></div>
    {/if}

    <!-- volunteers: a student applies with a short "why", the organizers answer; the team sees the count -->
    {#if detail?.volunteers && !preview && !cancelled && !started}
      {@const vo = detail.volunteers}
      {@const canAsk = !crew && vo.mine !== 'asked' && vo.mine !== 'yes' && vo.mine !== 'no' && vo.taken < vo.need}
      <Group>
        <Row icon={HandHeart} title={t('vol.title')} subtitle="{t('vol.left', { n: Math.max(0, vo.need - vo.taken), of: vo.need })}{vo.senior ? ' · ' + t('vol.senior') : ''}" />
        {#if head && crew}
          <Row title={t('vol.open')} value={vo.asked ? String(vo.asked) : undefined} accessory="chevron" onclick={() => sheets.volunteers(id, vo.need)} />
        {:else if !crew}
          {#if vo.mine === 'asked'}
            <Row dense title={t('vol.sent')}>{#snippet trailing()}<Button kind="gray" size="s" onclick={volLeave}>{t('vol.leave')}</Button>{/snippet}</Row>
          {:else if vo.mine === 'yes'}
            <Row dense title={t('vol.youAre')}>{#snippet trailing()}<Button kind="gray" size="s" onclick={volLeave}>{t('vol.stepDown')}</Button>{/snippet}</Row>
          {:else if vo.mine === 'no'}
            <Row dense title={t('vol.notThisTime')} />
          {:else if canAsk && !volWriting}
            <Row tone="action" title={t('vol.want')} onclick={() => { haptic.tap(); volWriting = true; }} />
          {/if}
        {/if}
      </Group>
      {#if canAsk && volWriting}
        <Field label={t('vol.whyPh')} bind:value={volNote} multiline rows={2} maxlength={300} />
        <Button kind="primary" size="m" full onclick={volApply}>{t('vol.send')}</Button>
      {/if}
    {/if}

    {#if e.meeting && head && crew && meet}
      <Section title="{over ? t('meet.after') : t('meet.answers')} · {meet.filter((a) => (over ? a.came : a.answer === 'yes')).length} / {meet.length}">
        {#each meetGroups as [title, list] (title)}
          <Group caption="{t(title)} · {list.length}">
            {#each list as a (a.person.id)}
              <Row dense title={withNick(a.fullName, a.person)} subtitle={a.answer === 'no' ? (a.note ?? t('meet.noWhy')) : a.note ? t('meet.saidNo', { why: a.note }) : undefined} />
            {/each}
          </Group>
        {/each}
      </Section>
    {/if}

    <!-- questions and talk, each a row that says where it goes: KRI (the server reads only a public, published event's
         facts: no row where it would know nothing), the event's chat, the talk under the channel post (Telegram's
         replies and reactions); what was asked here before the Telegram talk stays readable -->
    {@const askKri = session.board && !preview && e.status !== 'draft' && (e.visibility ?? 'public') === 'public'}
    {@const chat = !preview && !cancelled && !over ? detail?.chat : null}
    {@const talkTg = !!detail?.discuss && !preview && !cancelled}
    {@const talkOld = !!detail && !preview && !cancelled && ((detail.commentsOn && !detail.discuss) || !!detail.comments)}
    {#if askKri || chat || talkTg || talkOld}
      <Group>
        {#if askKri}<Row icon={Sparkles} title={t('as.askAi')} accessory="chevron" onclick={() => { haptic.tap(); sheets.assistant({ kind: 'event', id, title: e.title }); }} />{/if}
        {#if chat}<Row icon={MessagesSquare} title={t('chat.open')} accessory="external" onclick={() => openLink(chat)} />{/if}
        {#if talkTg}<Row icon={MessageCircle} title={t('cm.titleEvent')} accessory="external" onclick={() => openLink(detail!.discuss!)} />{/if}
        {#if talkOld}
          <Row icon={MessageCircle} title={t('cm.titleEvent')} value={detail?.comments ? String(detail.comments) : undefined} accessory="chevron"
            onclick={() => (session.me?.student ? sheets.comments('event', id, e.title, (n) => { if (detail) detail = { ...detail, comments: n }; }) : sheets.login())} />
        {/if}
      </Group>
    {/if}
    {#if crew && head && !started}<Group><Row tone="destructive" title={t('studio.cancelEvent')} onclick={cancelEvent} /></Group>{/if}
    <!-- the one report sheet: anyone but the event's own crew -->
    {#if !may(mem, 'door') && !coMem && !preview && session.me?.student}<div class="rep"><Button kind="plain" size="s" onclick={() => sheets.report('event', id, e.title)}>{t('cm.report')}</Button></div>{/if}
    {/if}
    </div>
    {/if}
  {:else if onlyFor}
    {@const gone = t('event.schoolOnlyGone', { school: schoolName(onlyFor) })}
    {#if unset}<EmptyState icon={Lock} title={gone} text={t('event.schoolUnset')} action={{ label: t('event.schoolUnsetGo'), onclick: () => sheets.settings('school') }} />
    {:else}<EmptyState icon={Lock} text={gone} />{/if}
  {:else if missing}
    <EmptyState icon={CalendarHeart} text={t('event.gone')} />
  {/if}

  {#snippet footer()}
    {#if e && soon}
      {#if noGuest}<p class="tnote">{t('ta.cant')}</p>
      {:else if regNote}<p class="tnote">{t('event.regUntil', { when: relDay(e.regUntil!) + ', ' + time(e.regUntil!) })}</p>{/if}<!-- the deadline where the decision is made -->
      {#if askable}<p class="tnote">{t(e.teamAsk === 'pending' ? 'ta.pendingNote' : 'ta.note')}</p>{/if}
      <div class="actions btns" inert={!!preview}>
        {#if cancelled}
          <Button kind="neutral" size="l" full disabled>{t('event.cancelledLong')}</Button>
        {:else if e.visibility === 'leaders' && !crew && !going && !started}
          {#if st === 'cancelled'}
            <Button kind="neutral" size="l" full onclick={() => toggleGoing(id)}>{t('lead.changed')}</Button>
          {:else}
            <div class="ans btns"><Button kind="secondary" size="l" full onclick={() => declineInvite(id)}>{t('lead.no')}</Button>
              <Button kind="primary" size="l" full onclick={() => toggleGoing(id)}>{t('lead.yes')}</Button></div>
          {/if}
        {:else if e.meeting && crew && !going && !started}
          {#if st === 'cancelled'}
            <Button kind="neutral" size="l" full onclick={() => toggleGoing(id)}>{t('meet.changed')}</Button>
          {:else}
            <div class="ans btns"><Button kind="secondary" size="l" full onclick={cantCome}>{t('lead.no')}</Button>
              <Button kind="primary" size="l" full onclick={() => toggleGoing(id)}>{t('lead.yes')}</Button></div>
          {/if}
        {:else if over && detail?.canAddPhotos && !e.meeting}
          <Button kind="primary" size="l" full loading={adding > 0} onclick={() => picker?.click()}>{#snippet icon()}<Camera size={18} />{/snippet}{t('album.addMine')}</Button>
        {:else if over && photos.length && !e.meeting}
          <Button kind="secondary" size="l" full onclick={allPhotos}>{#snippet icon()}<Images size={18} />{/snippet}{t('album.see')}</Button>
        {:else if over}
          <Button kind="neutral" size="l" full disabled>{t('event.over')}</Button>
        {:else if e.externalUrl}
          <Button kind="primary" size="l" full onclick={() => openLink(e.externalUrl!)}>{#snippet icon()}<ExternalLink size={18} />{/snippet}{t(e.externalUrl.startsWith('https://t.me/') ? 'event.externalTg' : 'event.external')}</Button>
        {:else if teamOnly && askable && e.teamAsk === 'pending'}
          <Button kind="neutral" size="l" full onclick={teamUnask}>{#snippet icon()}<Hourglass size={18} />{/snippet}{t('ta.pending')}</Button>
        {:else if teamOnly && askable}
          <Button kind="secondary" size="l" full onclick={teamAsk}>{t('ta.ask')}</Button>
        {:else if teamOnly}
          <Button kind="neutral" size="l" full disabled>{#snippet icon()}<UsersRound size={18} />{/snippet}{t('event.team')}</Button>
        {:else if going && inner(e)}
          <!-- a club's own event: no ticket, just the answer, changeable until it starts -->
          <div class="ans btns">
            {#if !started}<Button kind="secondary" size="l" full onclick={() => (e.meeting ? cantCome() : e.visibility === 'leaders' ? declineInvite(id) : toggleGoing(id))}>{t(e.santa ? 'santa.out' : 'lead.no')}</Button>{/if}
            <span class="yes"><Check size={18} strokeWidth={2.6} />{t(e.santa ? 'santa.in' : 'event.youGo')}</span>
          </div>
        {:else if going}
          <Button kind="primary" size="l" full onclick={() => sheets.ticket(id)}>{#snippet icon()}<Ticket size={18} />{/snippet}{t('event.ticket')}</Button>
        {:else if e.guestList}
          <!-- tickets come from the organizers' imported list (server guests.py): no sign-up here, the ticket shows once matched -->
          <p class="tnote gl">{t('event.guestList')}</p>
        {:else if shut}
          <Button kind="neutral" size="l" full disabled>{t('event.started')}</Button>
        {:else if st === 'hold'}
          <Button kind="primary" size="l" full onclick={() => sheets.pay(id)}>{t('event.pay', { price: money(e.price ?? 0) })}</Button>
        {:else if st === 'waitlist'}
          <Button kind="neutral" size="l" full loading={goingBusy.has(id)} onclick={() => toggleGoing(id)}>{t('event.notifyOn')}</Button>
        {:else if regShut}
          <Button kind="neutral" size="l" full disabled>{t('event.regClosed')}</Button>
        {:else if full}
          <Button kind="secondary" size="l" full loading={goingBusy.has(id)} onclick={() => toggleGoing(id)}>{t('event.notify')}</Button>
        {:else}
          <Button kind="primary" size="l" full loading={goingBusy.has(id)} onclick={() => toggleGoing(id, () => sheets.pay(id))}>{e.price ? freeMe ? t('event.goFree') : t('event.goPrice', { price: money(e.price) }) : t(e.santa ? 'santa.join' : 'event.go')}</Button>
        {/if}
      </div>
    {/if}
  {/snippet}
</Sheet>

<style>
  .links :global(.st) { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; } /* an address's path: one line, never past the screen */
  /* the stack under the header: one gap between blocks, Groups like Settings */
  .page { display: flex; flex-direction: column; gap: var(--s-5); }
  .pv { display: flex; justify-content: center; margin: 0 0 10px; }
  .note { padding: 0 var(--s-4); }
  .lnk { align-self: flex-start; }
  .trn { margin: -6px 0 0 -8px; --plain-ink: var(--text-3); }
  .warn { color: var(--warning-text); font-weight: 600; }
  .desc { color: var(--text); white-space: pre-line; padding: 0 var(--s-1); }
  .rep { display: flex; justify-content: center; --plain-ink: var(--text-3); }

  /* the header is media, dark in both themes (.theme-dark: white words, dark glass): the picture whole, the words on it.
     It grows with a long title, never cuts it */
  .hero { --hh: clamp(300px, 44vh, 380px); position: relative; isolation: isolate; display: flex; flex-direction: column; justify-content: flex-end;
    min-height: var(--hh); margin: 4px 0 var(--s-4); padding-top: 60px; /* the words stay clear of the top row */ border-radius: var(--r-xl); overflow: hidden; background: var(--media); color: var(--text); }
  .hero > :global(.poster.poster) { position: absolute; inset: 0; } /* ui/Poster is a box in the flow */
  .hero.cancelled > :global(.poster:not(.dim)) { filter: grayscale(1); opacity: 0.6; }
  /* the 3D mark sits under the top row's buttons at the hero's size: smaller and lower here */
  .hero :global(.mark) { top: 52px; transform-origin: 100% 0; transform: rotate(8deg) scale(0.82); }
  .wide { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .strip { position: absolute; inset: 0; display: flex; overflow-x: auto; scroll-snap-type: x mandatory; overscroll-behavior-x: contain; scrollbar-width: none; }
  .strip::-webkit-scrollbar { display: none; }
  .pic { flex: 0 0 100%; scroll-snap-align: start; scroll-snap-stop: always; }
  .pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .dots { position: absolute; left: 0; right: 0; bottom: 10px; z-index: 3; display: flex; justify-content: center; gap: 5px; pointer-events: none; }
  .dots i { width: 6px; height: 6px; border-radius: var(--r-full); background: rgba(255, 255, 255, 0.5); box-shadow: 0 0 4px rgba(0, 0, 0, 0.4); transition: transform var(--t-fast); }
  .dots i.on { background: var(--on-accent); transform: scale(1.25); }
  /* the picture clear at the top, deeper toward the words; with no lens under them (photos, a clip) deeper still */
  .shade { position: absolute; inset: 0; border-radius: inherit; pointer-events: none; background: linear-gradient(rgba(0, 0, 0, 0) 36%, rgba(0, 0, 0, 0.5)); box-shadow: inset 0 0 0 0.5px rgba(255, 255, 255, 0.14); }
  .deep .shade { background: linear-gradient(rgba(0, 0, 0, 0) 30%, rgba(0, 0, 0, 0.82)); }
  .top { position: absolute; z-index: 3; left: 12px; right: 12px; top: 12px; display: flex; align-items: center; justify-content: space-between; gap: 8px; pointer-events: none; } /* a long name yields to the buttons, never under them */
  .top > * { pointer-events: auto; }
  .org { flex: 0 1 auto; min-width: 0; display: flex; }
  .org :global(.tag) { max-width: 100%; min-width: 0; }
  .acts { flex: none; display: flex; gap: 8px; }
  .acts.on :global(.ib:first-child svg) { fill: currentColor; color: var(--warning); }

  /* the words (the Afisha hero's slab): the title in the display face, the time in white, the place a step quieter */
  .slab { position: relative; z-index: 2; isolation: isolate; display: flex; flex-direction: column; gap: 3px; padding: 76px 18px var(--s-4); pointer-events: none;
    text-shadow: 0 1px 8px rgba(0, 0, 0, 0.28); }
  .pics .slab { padding-bottom: var(--s-6); } /* the photos' dots under the words */
  .clip .slab { padding-right: 60px; } /* the clip's sound button */
  .lens { position: absolute; inset: 0; z-index: -1; overflow: hidden; pointer-events: none;
    -webkit-mask-image: linear-gradient(transparent, rgba(0, 0, 0, 0.7) 28px, black 56px); mask-image: linear-gradient(transparent, rgba(0, 0, 0, 0.7) 28px, black 56px); }
  /* the picture runs 64px past the lens on every side but the top: a blurred layer fades out at its own edges */
  .lens img { position: absolute; left: -64px; bottom: -64px; width: calc(100% + 128px); max-width: none; /* base.css caps every img at its box */ height: calc(var(--hh) + 64px); object-fit: cover;
    filter: blur(32px) saturate(1.7) brightness(0.6); }
  .tags { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: var(--s-2); text-shadow: none; }
  .tags:not(:has(*)) { display: none; }
  .ttl { margin-bottom: var(--s-1); font: 700 var(--fs-t1)/1.08 var(--font-display); letter-spacing: -0.035em; text-wrap: balance; overflow-wrap: break-word; }
  .strike { text-decoration: line-through; color: var(--text-2); }
  .cancel { font: 600 var(--fs-body)/1.35 var(--font-text); color: var(--danger-text); }
  .when { font: 600 var(--fs-row)/1.25 var(--font-text); letter-spacing: -0.012em; }
  .when::first-letter { text-transform: uppercase; }
  .where { min-width: 0; font: 500 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  .where :global(.place) { text-decoration: none; }

  /* the guests' album: the first photo big, two beside it, three under (whole blocks only) */
  .album { display: flex; flex-direction: column; gap: 10px; }
  .al-h { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); padding: 0 var(--s-1); }
  .al-h .n { margin-left: var(--s-2); font-weight: 450; color: var(--text-3); }
  .al-all { display: flex; align-items: center; gap: 2px; color: var(--text-3); }
  .al-all h3 { color: var(--text); }
  .al-all:active { opacity: 0.6; }
  .mosaic { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; border-radius: var(--r-l); overflow: hidden; }
  .mosaic.n1 { grid-template-columns: 1fr; }
  .mosaic.n2 { grid-template-columns: 1fr 1fr; }
  .ph { position: relative; aspect-ratio: 1; overflow: hidden; display: block; background-size: cover; }
  .mosaic.n1 .ph { aspect-ratio: 16 / 10; }
  .mosaic.n3 .ph:first-child { grid-column: span 2; grid-row: span 2; }
  .ph img { width: 100%; height: 100%; object-fit: cover; display: block; animation: ph-in 420ms ease-out backwards; }
  @keyframes ph-in { from { opacity: 0; } }
  .ph:active img { transform: scale(0.97); transition: transform var(--t-fast); }
  .more { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: var(--on-accent); background: rgba(8, 10, 20, 0.5);
    font: 700 var(--fs-sec)/1 var(--font-display); }
  .ph.wait { background: var(--surface-2); animation: ph-wait 1.1s ease-in-out infinite; }
  @keyframes ph-wait { 50% { opacity: 0.5; } }

  .ups { display: flex; flex-direction: column; gap: var(--s-2); }
  .up-b { white-space: pre-line; overflow-wrap: anywhere; }
  .up-acts { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding-left: var(--s-4); }

  .stack { display: flex; }
  .stack :global(.av + .av) { margin-left: -8px; }
  .stack :global(.av) { box-shadow: 0 0 0 2px var(--surface-solid); }

  /* the footer: the one primary action, alone */
  .actions { display: flex; gap: 8px; align-items: center; }
  .tnote { margin: 0 0 8px; text-align: center; color: var(--text-2); font: 450 var(--fs-sub)/1.3 var(--font-text); }
  .gl { flex: 1; margin: 0; padding: var(--s-2) var(--s-4); text-wrap: pretty; }
  .ans { flex: 1; display: flex; gap: 8px; min-width: 0; }
  .ans > :global(*) { flex: 1 1 0; min-width: 0; } /* two halves, whatever each says */
  @media (max-width: 350px) { .yes :global(svg) { display: none; } } /* the words stay on one line */
  .yes { flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px; min-width: 0; white-space: nowrap; border-radius: var(--r-full);
    background: var(--success-soft); color: var(--success-text); font: 600 var(--fs-body)/1 var(--font-text); }

  /* one tap after the event: bespoke (the faces), on a group's surface */
  .rate { display: flex; flex-direction: column; gap: 10px; padding: var(--s-4); border-radius: var(--r-group); background: var(--surface); text-align: center; }
  .rq { font: 700 var(--fs-row)/1.2 var(--font-display); letter-spacing: -0.015em; }
  .mine { align-self: flex-start; display: flex; align-items: center; gap: 8px; padding: 0 var(--s-1); color: var(--text-2); font: 500 var(--fs-body)/1.2 var(--font-text); }
  .mine:disabled { opacity: 1; }
  .faces { display: flex; justify-content: space-between; gap: 6px; }
  .faces button { flex: 1; aspect-ratio: 1; max-width: 62px; border-radius: var(--r-m); display: flex; align-items: center; justify-content: center; background: var(--fill);
    line-height: 1; transition: transform 260ms cubic-bezier(.2, 1.6, .4, 1), opacity var(--t-base), background-color var(--t-base); }
  .faces button:active { transform: scale(0.9); }
  .faces button.on { transform: scale(1.12); background: var(--accent-soft); box-shadow: inset 0 0 0 2px var(--accent); }
  .faces button.on :global(.emoji) { animation: hop 520ms cubic-bezier(.2, 1.6, .4, 1); }
  @keyframes hop { 30% { transform: translateY(-9px) scale(1.25) rotate(-8deg); } 60% { transform: translateY(0) scale(0.95); } }
  .faces button.dim { opacity: 0.4; }
  .rin { display: flex; flex-direction: column; align-items: flex-end; gap: var(--s-2); text-align: left; }
  .rin > :global(*:first-child) { align-self: stretch; }
  .rsum { display: flex; flex-direction: column; gap: 6px; padding: var(--s-4); border-radius: var(--r-group); background: var(--surface); }
  .rs-top { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
  .avg { font: 800 var(--fs-title)/1 var(--font-display); letter-spacing: -0.03em; }
  .rs-top span:last-child { display: flex; flex-direction: column; gap: 2px; }
  .rs-top b { font: 600 var(--fs-body)/1.2 var(--font-text); }
  .rs-top i { font-style: normal; }
  .rs-row { display: flex; align-items: center; gap: 8px; }
  .rf { width: 22px; display: flex; justify-content: center; }
  .rbar { flex: 1; height: 6px; border-radius: var(--r-full); background: var(--fill); overflow: hidden; }
  .rbar > span { display: block; height: 100%; border-radius: var(--r-full); background: var(--grad-accent); }
  .rn { width: 24px; text-align: right; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-2); }
  .rc { display: flex; gap: 8px; padding-top: 8px; margin-top: 2px; border-top: 0.5px solid var(--separator); font: 450 var(--fs-body)/1.4 var(--font-text); }
  .rc :global(.emoji) { flex: none; }
</style>
