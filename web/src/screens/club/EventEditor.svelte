<script lang="ts">
  // Studio → a new event or an edit, full screen. One calm page does the common case: KRI's line on top (paste the
  // announcement or say it in a few words: the card below fills in, and KRI asks only what is still missing, in that
  // same line; no second mode), the event's card itself with the name typed on its cover, when, where, a few words,
  // tickets, and Publish always under the thumb. Everything else is a named row that pushes its own page, as iOS
  // Settings does (Telegram's Back pops it; one Back). The cover is one photo aimed by itself (lib/photo autoFocus);
  // each format, the Feed's tall slide, the card and a list's thumbnail, can take its own crop or its own photo.
  // Publishing runs an instant check first (lib/eventCheck.ts: a trip once went out free while its text asked 7500
  // tenge) with a one-tap fix per note. A new event or a draft: "Publish" or "Draft"; a published one: "Save" (the
  // server tells registered people when the time or place moves). Leaving with changes asks. An official club's Vice+
  // can make it paid (§4.3). A member without the "events" right makes a draft and sends it to the club's President
  // and Vices, who approve (it goes out) or return it with a reason (server organizing.submit_event).
  import { keyboard } from '../../lib/state/keyboard.svelte';
  import { teamSize } from '../../lib/teams';
  import { onMount, untrack } from 'svelte';
  import { fmtPhone } from '../../lib/phone';
  import MemoAsksForm from './MemoAsks.svelte';
  import X from '@lucide/svelte/icons/x';
  import Gift from '@lucide/svelte/icons/gift';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import PencilLine from '@lucide/svelte/icons/pencil-line';
  import Trash from '@lucide/svelte/icons/trash-2';
  import ImagePlus from '@lucide/svelte/icons/image-plus';
  import Clapperboard from '@lucide/svelte/icons/clapperboard';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import VideoCall from '@lucide/svelte/icons/video';
  import Eye from '@lucide/svelte/icons/eye';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import AlignLeft from '@lucide/svelte/icons/align-left';
  import Ticket from '@lucide/svelte/icons/ticket';
  import Users from '@lucide/svelte/icons/users';
  import Clock from '@lucide/svelte/icons/clock';
  import Globe from '@lucide/svelte/icons/globe';
  import Crown from '@lucide/svelte/icons/crown';
  import CalendarCheck from '@lucide/svelte/icons/calendar-check';
  import TagIcon from '@lucide/svelte/icons/tag';
  import Phone from '@lucide/svelte/icons/phone';
  import GraduationCap from '@lucide/svelte/icons/graduation-cap';
  import ListChecks from '@lucide/svelte/icons/list-checks';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import Handshake from '@lucide/svelte/icons/handshake';
  import Blend from '@lucide/svelte/icons/blend';
  import Mail from '@lucide/svelte/icons/mail';
  import Plus from '@lucide/svelte/icons/plus';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import FileText from '@lucide/svelte/icons/file-text';
  import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
  import RotateCcw from '@lucide/svelte/icons/rotate-ccw';
  import ImageIcon from '@lucide/svelte/icons/image';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import Segmented from '../../ui/Segmented.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Tag from '../../ui/Tag.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Composer from '../../ui/Composer.svelte';
  import { menu, type MenuItem } from '../../ui/menu';
  import { check, type Finding } from '../../lib/eventCheck';
  import { api, ApiErr, original, staffEvents, staffOrg, type CoverFormat, type EventFull, type EventInput, type Id, type Media, type MemoAsks, type OrgRef, type OwnTr, type ReviewReason, type Video } from '../../lib/api';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import { nameOf } from '../../lib/short';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, eventById, studioChanged, phrase } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { useDraft } from '../../lib/draft';
  import { sheets } from '../../lib/state/sheets';
  import { placeOf, t, tn } from '../../lib/i18n/index.svelte';
  import { campusPlace } from '../../lib/campusPlace';
  import CampusPlacePicker from './CampusPlacePicker.svelte';
  import { hit } from '../../lib/clubs';
  import { nowTs, time, relDay, dateInput, fromInputs, weekdayShort, dayMonthShort, multiDay, endTime } from '../../lib/time';
  import { haptic, inTelegram } from '../../lib/tg';
  import { autoFocus, coverFor, shrink } from '../../lib/photo';
  import { shade, coverColor } from '../../lib/color';
  import { burst } from '../../ui/burst';
  import Poster from '../../ui/Poster.svelte';
  import CoverCrop from './CoverCrop.svelte';
  import { PICK_EMOJI } from '../../lib/emoji';
  import LookPick from '../../ui/LookPick.svelte';
  import Button from '../../ui/Button.svelte';
  import { may, RANK } from '../../lib/perms';
  import { eventPlace, EVENT_BUILDINGS, GIS_LINK, isGisLink } from '../../lib/map';
  import { marked, missing, nextQuestion, updateDraft, type ChatFill, type Differs, type Marked } from '../../lib/eventFill';
  import { ONLINE_LINK } from '../../lib/meet';

  // staff: Admin's "an event for a club" (a new one only): the app's admin makes the club's draft with no role in it, the
  // save and the cover going as staff (api staffOrg), then runs it as any event opened from Admin (staffEvents); never
  // its money, its videos or its memo, which stay the club's own. The creator (lent) has its President's editor
  let { overlay, org, id, staff = false }: { overlay: Overlay; org: Id; id?: Id; staff?: boolean } = $props();
  // an event opened from Admin and edited here is staff's too: the club's DMP memo is neither shown nor sent (but to the creator)
  const asStaff = $derived(staff || (!!id && staffEvents.has(id)));
  // his covers and videos go as the club's too (X-Staff-Org)
  $effect(() => { if (!staff && !lent) return; staffOrg.id = org; return () => { staffOrg.id = 0; }; });
  const club = $derived(data.orgs.find((o) => o.id === org));
  const oversee = $derived(!!club?.canOversee);
  const mine = $derived(session.me?.memberships.find((m) => m.org.id === org));
  const official = $derived(!!(club ?? mine?.org)?.official);
  const full = $derived(official || !!club?.top); // the Ascent's top: an official club's tools
  // a student initiative: no @KBTUevents, its followers told once a week (KBTU's own offices are as official)
  const initiative = $derived(!official && (club ?? mine?.org)?.kind === 'club');
  // a choice question's options, typed with commas: "S, M, L"
  const opts = (s: string) => [...new Set(s.split(',').map((o) => o.trim()).filter(Boolean))];
  const GUEST_BANNED = /kbtu|\u043a\u0431\u0442\u0443|dmp|\u0434\u043c\u043f|council|\u0441\u043e\u0432\u0435\u0442|school/i; // the server's own rule
  // the name Kaspi prints for the recipient ("Alikhan S.", my short name): mine, as the one setting it up usually takes the money
  const myKaspiName = session.me?.student && !untrack(() => asStaff) ? session.me.name : ''; // staff from Admin type the club's own

  const EMOJI = PICK_EMOJI;
  // eleven around the colour wheel and night (10-12, no RGB picker); BRAND when nothing else is set
  const COLORS = ['#F2542D', '#FF8A3D', '#FFB23D', '#7CB518', '#2FBF71', '#14B8A6', '#18A9DB', '#3B6BFF', '#7C4DFF', '#AF52DE', '#FF4FA3', '#2A2340'];
  const BRAND = '#3B6BFF';
  const FORMATS = ['feed', 'card', 'list'] as const;
  const FMT_NAME = { feed: 'ed.inFeed', card: 'ed.inCard', list: 'ed.inList' } as const;

  let saved = $state<EventFull | null>(null); // the server's copy when editing
  // the creator alone gets its President's editor here (server core.can, lent_full): a new event, or any club's he opens
  // from Admin; `plain` is every other admin's, a plain public free event
  const lent = $derived(asStaff && !!session.me?.founder && (staff || !!saved?.lentFull));
  const plain = $derived(staff && !lent);
  // a member without the "events" right: the draft is theirs, the publishing the club's President's or a Vice's
  const member = $derived(!asStaff && !!mine && !may(mine, 'events'));
  const review = $derived(saved?.review ?? null);
  // a member's draft waiting for my answer (the club's President or a Vice): Publish here is the approval
  const judge = $derived(!!review?.askedAt && !review.mine && (mine?.role === 'president' || mine?.role === 'vice'));
  // a club that lost the ✓ still sees its paid or partner event's rows, to switch them off (the server allows only that)
  const canPrice = $derived((lent || !staff && may(mine, 'money')) && (full || !!saved?.price));
  // a partner's event: an outside host's, posted by an official club or DMP; the link out instead of tickets
  const canPartner = $derived(!member && (full || !plain && oversee) || !!saved?.guestHost);
  // a new event starts on a random emoji and colour: fewer look alike when nobody picks
  const any = <T,>(xs: T[]) => xs[Math.floor(Math.random() * xs.length)];
  const blank = { emoji: any(EMOJI), color: any(COLORS), cover: null as Media | null, formats: {} as NonNullable<Media['formats']>, slides: [] as Media[], videoId: null as Id | null, wideVideoId: null as Id | null, title: '', date: dateInput(nowTs() + 7 * 86400), start: '18:00',
    end: '', endDate: '', place: '', placeUrl: '', online: false, onlineUrl: '', description: '', cap: '' as '' | 'limited' | 'unlimited', seats: '', firstYear: false, needsPhone: false, santa: false, vol: false, volN: '5', volSenior: false, teams: false, teamMin: '2', teamMax: '5', teamCap: '', teamOnly: false, leaders: false, leadersFrom: 'president' as 'president' | 'vice' | 'head',
    meeting: false, meetingTag: null as Id | null, forBoard: false,
    partner: false, host: '', link: '',
    form: [] as { label: string; kind: 'text' | 'choice'; opts: string; required: boolean }[], // the questions at sign-up
    paid: false, price: '', payTo: myKaspiName, payPhone: '', freeFirst: '', deadline: false, late: false, regDate: '', regTime: '18:00',
    tba: false, memo: { room: { any: true, projector: false, capacity: null } } as MemoAsks };
  let f = $state({ ...blank });
  const PLACE_OPTIONS = { room: 'ed.placeMain', bldg2: 'ed.placeBuilding2', dorm: 'ed.placeDorm', elsewhere: 'ed.placeElsewhere' } as const;
  type PlaceChoice = keyof typeof PLACE_OPTIONS;
  const placeOptions = Object.keys(PLACE_OPTIONS) as PlaceChoice[];
  let placeChoice = $state<PlaceChoice | null>(null);
  const placeKind = $derived(eventPlace(f.place, f.placeUrl)?.kind);
  const placeType = $derived(placeChoice ?? placeKind ?? 'room');
  const placeText = $derived(f.place.trim() || (f.placeUrl.trim() ? '2GIS' : ''));
  const badGis = $derived(!!f.placeUrl.trim() && (f.placeUrl.trim().length > 500 || !isGisLink(f.placeUrl.trim())));

  function choosePlace(choice: PlaceChoice) {
    haptic.select();
    if (choice === placeType) return;
    if (choice === 'bldg2' || choice === 'dorm') f.place = EVENT_BUILDINGS[choice];
    else if (placeType === 'bldg2' || placeType === 'dorm') f.place = '';
    placeChoice = choice;
    f.placeUrl = '';
  }
  // a new event named like a casting, by someone who may open the club's recruitment: say that's the better tool
  // ponytail: a word list; the AI event check can tell it from the description once it runs on every event
  const castLike = $derived(!id && /\u043a\u0430\u0441\u0442\u0438\u043d\u0433|\u043d\u0430\u0431\u043e\u0440 \u0432|recruit|casting|\u0456\u0440\u0456\u043a\u0442\u0435\u0443/i.test(f.title)
    && may(session.me?.memberships?.find((x) => x.org.id === org), 'casting'));
  let base = $state(JSON.stringify(blank)); // the form with nothing to lose
  // only after a touch of mine (an untouched new event asked "Leave without saving?"; iOS rewrites a
  // date or time input's value as it renders, so the form differed from its blank by itself): the first touch takes the
  // form as it stands then (capture: before the change lands) as the base
  let touched = $state(false);
  const touch = () => { if (!touched) { base = JSON.stringify(f); touched = true; } };
  let said = $state(''); // what is being written to KRI: kept with the text draft, so a failed try or a closed app loses nothing
  const dirty = $derived(!!said.trim() || touched && JSON.stringify(f) !== base);
  const live = $derived(!!saved && saved.status !== 'draft');
  const tint = $derived(shade(f.color));
  $effect(() => { overlay.tint = tint; }); // the sheets it opens take its colour
  let tried = $state(false); // errors show after the first submit
  let busy = $state('');

  // a club meeting (§2b): team-only, the whole club or one tag expected; no seats, deadline, price or 1st-year tag
  const isMeeting = $derived(f.teamOnly && f.meeting);
  let tags = $state<import('../../lib/api').ClubTag[]>([]);
  // a Head with departments calls only those (PLAN 35): the first is picked, the rest of the club's aren't offered
  let ownDepts = $state<Id[]>([]), inDept = $state(false); // in a department only the chat sync gave: none to call
  const deptOnly = $derived(inDept && RANK[session.me?.memberships.find((x) => x.org.id === org)?.role ?? 'member'] < RANK.vice);
  // "For whom": any team-only event, required or not; picking a department doesn't make it required
  let tagsRead = $state(false);
  let loadingTags: Promise<void> | undefined;
  const tagNamed = (name?: string) => { const n = name?.toLowerCase(); return n ? tags.find((g) => g.name.toLowerCase() === n && (!deptOnly || ownDepts.includes(g.id))) : undefined; };
  const readTags = () => loadingTags ??= api.teamSetup(org).then((s) => {
    const first = !tagsRead;
    tags = s.tags;
    ownDepts = s.myDepts ?? [];
    inDept = !!s.inDept;
    tagsRead = true;
    if (first && !saved) {
      f.meetingTag = tagNamed(known.department)?.id ?? (deptOnly ? ownDepts[0] ?? null : null);
      if (deptOnly) f.forBoard = false;
    }
  }).catch(() => {}).finally(() => { loadingTags = undefined; });
  $effect(() => { if (f.teamOnly && !tagsRead) readTags(); });

  const startTs = $derived(fromInputs(f.date, f.start));
  // the end: a time on the start's day, earlier than the start meaning the next day (a night hackathon); an end date
  // of its own for an event of several days (a casting, 2-12 Nov), taken as it is
  const endTs = $derived.by(() => {
    if (f.endDate && !f.end) return fromInputs(f.endDate, '23:59'); // a last day with no time: the end is optional
    const e = fromInputs(f.endDate || f.date, f.end);
    if (!Number.isFinite(e) || !Number.isFinite(startTs)) return null;
    return f.endDate || e > startTs ? e : e + 86400;
  });
  const regTs = $derived(fromInputs(f.regDate, f.regTime));
  // "Until the end" (late sign-up): free, uncapped, public, ours only (the server checks the same)
  const lateOk = $derived(!f.paid && f.cap !== 'limited' && !f.teamOnly && !f.leaders && !f.partner && !f.teams);
  const regMode = $derived(f.late && lateOk ? 'end' : f.deadline ? 'date' : 'start');
  // a team event (server evteams.py): ours, not open until the end; paid too (each player pays their own ticket)
  const teamsOk = $derived(!isMeeting && !f.partner && regMode !== 'end');
  // a paid one with a cap on teams holds at most cap x max seats: nobody pays for a place no team can take
  const capSeats = $derived(f.paid && f.teams && teamsOk && +f.teamCap > 0 ? +f.teamCap * +f.teamMax : null);
  const own = $derived(f.cap === 'limited' && +f.seats > 0 ? +f.seats : null);
  const seatsN = $derived(capSeats ? Math.min(own ?? capSeats, capSeats) : own);
  // switched on: the day before the event, or its own day when that's already gone
  function deadlineOn(on: boolean) {
    f.deadline = on;
    if (!on || f.regDate) return;
    const d = Number.isFinite(startTs) ? startTs : nowTs() + 7 * 86400;
    f.regDate = dateInput(d - 86400 > nowTs() ? d - 86400 : d);
  }
  const err = $derived({
    title: f.title.trim() ? '' : t('ed.need'),
    when: !Number.isFinite(startTs) || f.endDate && endTs == null ? t('ed.need') : !live && startTs <= nowTs() ? t('ed.past') : endTs != null && endTs <= startTs ? t('ed.endEarly') : '',
    // online: no place; a link, if any, https with a plain host (the server checks it again)
    place: f.online ? (!f.onlineUrl.trim() || ONLINE_LINK.test(f.onlineUrl.trim()) ? '' : t('ed.onlineBad')) : f.tba ? ''
      : badGis ? t('ed.placeLinkBad') : placeText.length > 80 ? t('ed.placeTooLong') : !placeKind ? t('ed.need')
      : placeType !== placeKind ? t(placeType === 'room' ? 'ed.placeRoomBad' : 'ed.placeElsewhereBad') : '',
    // capacity is a choice, never a default (the server refuses an event without it): a number, or no limit
    seats: isMeeting || f.partner || capSeats ? '' : !f.cap ? t('ed.capNeed') : f.cap === 'unlimited' || Number.isInteger(+f.seats) && +f.seats > 0 ? '' : t('ed.need'),
    price: !f.paid || (Number.isInteger(+f.price) && +f.price >= 1 && +f.price <= 1_000_000) ? '' : t('ed.need'),
    payTo: !f.paid || f.payTo.trim().length >= 2 ? '' : t('ed.need'),
    payPhone: !f.paid || /^(\+?7|8)?7\d{9}$/.test(f.payPhone.replace(/[\s()-]/g, '')) ? '' : t('ed.phoneBad'),
    freeFirst: !f.paid || !f.freeFirst || (Number.isInteger(+f.freeFirst) && +f.freeFirst >= 0 && +f.freeFirst <= 5000) ? '' : t('ed.need'),
    host: !f.partner ? '' : !f.host.trim() || f.host.trim().length > 60 ? t('ed.need') : GUEST_BANNED.test(f.host) ? t('ed.partnerOwn') : '',
    link: !f.partner || /^https:\/\/[^\s/?#]+\.[^\s/?#]+(?:[/?#]\S*)?$/.test(f.link.trim()) ? '' : t('ed.partnerLinkBad'),
    form: f.form.some((q) => q.label.trim().length < 2 || q.kind === 'choice' && opts(q.opts).length < 2) ? t('ed.formBad') : '',
    teams: !f.teams || !teamsOk || (Number.isInteger(+f.teamMin) && Number.isInteger(+f.teamMax) && +f.teamMin >= 2 && +f.teamMax <= 10 && +f.teamMin <= +f.teamMax) ? '' : t('ed.teamsBad'),
    teamCap: !f.teams || !teamsOk || f.teamCap === '' || (Number.isInteger(+f.teamCap) && +f.teamCap >= 2 && +f.teamCap <= 500) ? '' : t('ed.teamCapBad'),
    reg: regMode !== 'date' ? '' : !Number.isFinite(regTs) ? t('ed.need') : Number.isFinite(startTs) && regTs > startTs ? t('ed.regLate') : f.santa && !saved?.santa?.drawn && Number.isFinite(startTs) && regTs > startTs - 3600 ? t('santa.badUntil') : !live && regTs <= nowTs() ? t('ed.past') : '',
  });

  // A pasted 2GIS share can include both the address and the URL.
  const hasCampusPlace = $derived(!!campusPlace(f.place));
  $effect(() => {
    const m = f.place.match(GIS_LINK);
    if (m) f.place = f.place.replace(m[0], ' ').replace(/\s+/g, ' ').replace(/^[\s,.·-]+|[\s,.·-]+$/g, '').slice(0, 80);
    if (m || hasCampusPlace) f.placeUrl = hasCampusPlace ? '' : (m?.[0] ?? '');
    if (m && !hasCampusPlace) { placeChoice = 'elsewhere'; haptic.ok(); say(phrase('say.gisLink'), 'globe_with_meridians_3d'); }
  });
  // the Kaspi number written as the phone shows it, as it's typed
  $effect(() => { const v = fmtPhone(f.payPhone); if (v !== f.payPhone) f.payPhone = v; });

  // ---- the cover: one photo, shrunk on the phone and re-encoded by the server, aimed at its subject by itself; the emoji
  // and colour stay as the fallback. A format's own crop or own photo lives in f.formats (as the server gives it)
  let uploading = $state<'' | 'cover' | CoverFormat>('');
  let photoIn = $state<HTMLInputElement>(), ownIn = $state<HTMLInputElement>();
  async function upload(ev: Event): Promise<Media | null> {
    const el = ev.currentTarget as HTMLInputElement, file = el.files?.[0];
    el.value = '';
    if (!file) return null;
    if (file.size > 30 * 1024 * 1024) { say(t('ed.photoBig'), 'pleading_face_3d'); return null; }
    try { const p = await api.uploadPhoto(await shrink(file)); return { ...p, focus: await autoFocus(p.thumb) }; }
    catch { haptic.error(); say(t('ed.photoBad'), 'pleading_face_3d'); return null; }
  }
  async function pickPhoto(ev: Event) {
    uploading = 'cover';
    const p = await upload(ev);
    uploading = '';
    if (!p) return;
    f.cover = p;
    // the crops made for the old photo mean nothing on this one; a format's own photo stays
    f.formats = Object.fromEntries(Object.entries(f.formats).filter(([, o]) => o.id));
    haptic.ok(); void readColor(true);
  }
  async function pickOwn(ev: Event, k: CoverFormat) {
    uploading = k;
    const p = await upload(ev);
    uploading = '';
    if (!p) return;
    if (p.id === f.cover?.id) { say(t('ed.fmtSame'), 'thinking_face_3d'); return; } // the cover itself: its crop is one drag away
    f.formats = { ...f.formats, [k]: p }; haptic.ok();
  }
  const setCrop = (k: CoverFormat, focus: [number, number]) => { const o = f.formats[k]; f.formats = { ...f.formats, [k]: o?.id ? { ...o, focus } : { focus } }; };
  function resetFormat(k: CoverFormat) { haptic.soft(); f.formats = Object.fromEntries(Object.entries(f.formats).filter(([x]) => x !== k)); }
  // the event's picture as every Poster takes it: the cover with its formats
  const art = $derived({ cover: f.cover ? { ...f.cover, formats: f.formats } : null, emoji: f.emoji, color: f.color });
  const fmtTag = (k: CoverFormat) => (f.formats[k]?.id ? t('ed.fmtPhoto') : f.formats[k] ? t('ed.fmtCrop') : '');

  // the photo's own colour (around its focus) is the first dot and gets picked with a new photo; a dot chosen on
  // purpose stays (SPEC §4.8b)
  let photoColor = $state<string | null>(null);
  async function readColor(pick: boolean) {
    if (!f.cover) return;
    const was = photoColor, c = await coverColor(f.cover);
    if (!f.cover) return;
    photoColor = c;
    if (c && (pick || f.color === was)) f.color = c;
  }
  function dropPhoto() {
    if (f.color === photoColor) f.color = BRAND;
    f.cover = null; f.formats = {}; photoColor = null;
  }

  // the event's videos (server video.py): the vertical one plays in the Feed, the horizontal one behind the event's
  // sheet (PLAN 32). Sent in pieces with a progress bar, then compressed on the server while the form stays usable;
  // their status lives beside the form (f has only the ids), so the polling doesn't make it dirty
  type Slot = 'tall' | 'wide';
  const KEY = { tall: 'videoId', wide: 'wideVideoId' } as const;
  let vids = $state<Record<Slot, Video | null>>({ tall: null, wide: null });
  let vUp = $state<Record<Slot, number>>({ tall: -1, wide: -1 }); // the upload's share done, -1 when none is running
  async function pickVideo(ev: Event, slot: Slot) {
    const el = ev.currentTarget as HTMLInputElement, file = el.files?.[0];
    el.value = '';
    if (!file) return;
    if (file.size > 500 * 1024 * 1024) { say(t('ed.videoBig'), 'pleading_face_3d'); return; }
    if (slot === 'tall' && (await seconds(file)) > 60.5) { haptic.error(); say(t('ed.videoLong'), 'pleading_face_3d'); return; }
    vUp[slot] = 0;
    try { const x = await api.uploadVideo(file, (d) => (vUp[slot] = d), slot === 'wide'); vids[slot] = x; f[KEY[slot]] = x.id; haptic.ok(); }
    catch { haptic.error(); say(t('ed.videoBad'), 'pleading_face_3d'); }
    finally { vUp[slot] = -1; }
  }
  // the length before sending hundreds of megabytes (0 when the webview can't read it: the server checks again)
  function seconds(file: Blob): Promise<number> {
    return new Promise((done) => {
      const v = document.createElement('video'), url = URL.createObjectURL(file);
      const end = (n: number) => { URL.revokeObjectURL(url); done(n); };
      v.preload = 'metadata';
      v.onloadedmetadata = () => end(Number.isFinite(v.duration) ? v.duration : 0);
      v.onerror = () => end(0);
      setTimeout(() => end(0), 4000);
      v.src = url;
    });
  }
  for (const slot of ['tall', 'wide'] as const) {
    $effect(() => {
      const x = vids[slot];
      if (!x || !['queued', 'working', 'uploading'].includes(x.status)) return;
      const id = x.id, timer = setInterval(() => api.video(id).then((y) => { if (vids[slot]?.id === id) vids[slot] = y; }).catch(() => {}), 3000);
      return () => clearInterval(timer);
    });
    $effect(() => { const x = vids[slot]; if (x?.status === 'failed') { say(t(x.error === 'too_long' ? 'ed.videoLong' : 'ed.videoBad'), 'pleading_face_3d'); vids[slot] = null; f[KEY[slot]] = null; } });
  }
  function dropVideo(slot: Slot) { vids[slot] = null; f[KEY[slot]] = null; }

  // the event's rules (a PDF, an organizer's ask): put at once, not on Save; the server keeps only its pages as
  // pictures (organizing.put_doc), the event's page opens them in the photo viewer
  let docUp = $state(false), docName = $state(''); // docName: the title while it uploads (the row's own words would wrap)
  let docPick = $state<HTMLInputElement>();
  async function pickDoc(ev: Event) {
    const input = ev.currentTarget as HTMLInputElement, file = input.files?.[0];
    input.value = '';
    if (!file || !saved) return;
    if (file.size > 5 * 1024 * 1024) { haptic.error(); say(t('ed.docBig'), 'pleading_face_3d'); return; }
    const name = await sheets.askText({ title: t('ed.docName'), placeholder: t('event.doc'), value: saved.doc?.title ?? t('event.doc'), max: 40, line: true, ok: t('common.save'), cancel: t('common.cancel') });
    if (name == null || !saved) return;
    docUp = true; docName = name;
    try { const e = await api.putEventDoc(saved.id, file, name === t('event.doc') ? '' : name); saved = { ...saved, doc: e.doc }; haptic.ok(); }
    catch (err) { haptic.error(); say(t(err instanceof ApiErr && (err.message === 'too_many_pages' || err.message === 'too_big') ? 'ed.docBig' : 'ed.docBad'), 'pleading_face_3d'); }
    finally { docUp = false; }
  }
  async function dropDoc() {
    if (!saved) return;
    const was = saved.doc;
    saved = { ...saved, doc: null }; // optimistic; back if the server says no
    try { await api.dropEventDoc(saved.id); haptic.soft(); } catch { if (saved) saved = { ...saved, doc: was }; haptic.error(); }
  }

  // more photos after the cover, swiped sideways in the Feed and the sheet (PLAN 33): nine at most, in the order picked
  const SLIDES = 9;
  let slidesUp = $state(0); // how many are being sent
  async function pickSlides(ev: Event) {
    const el = ev.currentTarget as HTMLInputElement, files = [...(el.files ?? [])].slice(0, SLIDES - f.slides.length);
    el.value = '';
    if (!files.length) return;
    slidesUp = files.length;
    for (const file of files) {
      try {
        if (file.size > 30 * 1024 * 1024) say(t('ed.photoBig'), 'pleading_face_3d');
        // the same picture twice is the same upload: kept once, and never the cover again
        else { const p = await api.uploadPhoto(await shrink(file)); if (p.id !== f.cover?.id && !f.slides.some((x) => x.id === p.id)) f.slides = [...f.slides, p]; }
      }
      catch { haptic.error(); say(t('ed.photoBad'), 'pleading_face_3d'); }
      slidesUp--;
    }
    haptic.ok();
  }
  const mmss = (s: number) => `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, '0')}`;

  let panel: HTMLDivElement;
  let gone = false;

  onMount(() => {
    panel.animate([{ transform: 'translate3d(0,100%,0)' }, { transform: 'none' }], { duration: 380, easing: 'cubic-bezier(.2,.9,.25,1)' });
    if (id) {
      api.event(id).then(async (got) => {
        const e = original(got); // the text as typed, never a translation (PLAN 9)
        saved = e;
        vids = { tall: e.video ?? null, wide: e.wideVideo ?? null };
        f = { emoji: e.emoji ?? EMOJI[0], color: e.color ?? BRAND, cover: e.cover, formats: e.cover?.formats ?? {}, slides: e.slides ?? [], videoId: e.video?.id ?? null, wideVideoId: e.wideVideo?.id ?? null, title: e.title, date: dateInput(e.startsAt), start: time(e.startsAt),
          end: endTime(e.startsAt, e.endsAt), endDate: multiDay(e.startsAt, e.endsAt) ? dateInput(e.endsAt) : '', place: e.place, placeUrl: e.placeUrl ?? '', online: !!e.online, onlineUrl: e.onlineUrl ?? '', description: e.description,
          cap: e.seats ? 'limited' : 'unlimited', seats: e.seats ? String(e.seats) : '', firstYear: e.firstYear, needsPhone: !!e.needsPhone, santa: !!e.santa, vol: !!e.volunteers, volN: String(e.volunteers?.need ?? 5), volSenior: !!e.volunteers?.senior,
          teams: !!e.teamMax, teamMin: String(e.teamMin ?? 2), teamMax: String(e.teamMax ?? 5), teamCap: e.teamCap ? String(e.teamCap) : '', teamOnly: e.visibility === 'members', leaders: e.visibility === 'leaders', leadersFrom: e.leadersFrom ?? 'president',
          meeting: !!e.meeting, meetingTag: e.meetingTag ?? null, forBoard: !!e.forBoard,
          partner: !!e.guestHost, host: e.guestHost ?? '', link: e.guestHost ? e.externalUrl ?? '' : '',
          form: (e.form ?? []).map((q) => ({ label: q.label, kind: q.kind, opts: (q.options ?? []).join(', '), required: q.required })),
          paid: !!e.price, price: e.price ? String(e.price) : '', payTo: e.payToName ?? myKaspiName, payPhone: fmtPhone(e.payPhone ?? ''), freeFirst: e.freeFirst ? String(e.freeFirst) : '',
          deadline: !!e.regUntil, late: !!e.lateSignup, regDate: e.regUntil ? dateInput(e.regUntil) : '', regTime: e.regUntil ? time(e.regUntil) : '18:00',
          tba: !e.place && !e.placeUrl && !e.online, memo: e.memo ?? {} };
        if (campusPlace(e.place)) { f.place = placeOf(e.place); f.placeUrl = ''; }
        // a cover's tint used to be the photo's average colour: such an event starts on the photo's dot
        if (e.cover && (photoColor = await coverColor(e.cover)) && e.tint !== shade(f.color)) f.color = photoColor;
        base = JSON.stringify(f);
        restoreText();
      }).catch(() => { say(t('common.error'), 'warning_3d'); base = JSON.stringify(f); close(overlay.id); });
    } else restoreText();
    return hideChrome();
  });

  function leave() {
    if (gone) return;
    gone = true;
    const a = panel.animate([{ transform: 'none' }, { transform: 'translate3d(0,100%,0)' }], { duration: 260, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }
  // Back, ✕ or a swipe: leave at once, or ask first when something would be lost
  let asking = false;
  function discard(yes: boolean) {
    asking = false;
    if (yes) { discardText(); base = JSON.stringify(f); close(overlay.id); }
  }
  $effect(() => {
    if (!overlay.closing) return;
    if (stack.length) { overlay.closing = false; back(); return; } // an open page goes first (one Back)
    if (!dirty) { leave(); return; }
    overlay.closing = false;
    if (asking) return;
    asking = true;
    sheets.ask({ title: t('ed.leaveAsk'), text: t('ed.leaveText'), ok: t('ed.leaveGo'), cancel: t('ed.stay'), danger: true }).then(discard);
  });

  // "Only for <school>" (server organizing._school_only): a school's own org alone; sent once touched, else kept
  const school = $derived([club ?? mine?.org].find((o) => o?.kind === 'school'));
  let schoolOnly = $state<boolean>();
  // the fill found the announcement in all three languages: sent with the save while its title and description stand
  let ownTr: { tr: OwnTr; title: string; description: string } | undefined;
  const formatsOut = () => Object.fromEntries(FORMATS.map((k) => { const o = f.cover ? f.formats[k] : undefined; return [k, o ? { id: o.id ?? null, focus: o.focus ?? null } : null]; }));
  const input = (): EventInput => ({
    ...(ownTr && ownTr.title === f.title.trim() && ownTr.description === f.description.trim() ? { tr: ownTr.tr } : {}),
    ...(schoolOnly === undefined ? {} : { schoolOnly }),
    title: f.title.trim(), description: f.description.trim(), startsAt: startTs, endsAt: endTs, place: f.tba || f.online ? '' : placeText,
    ...(asStaff && !lent || member ? {} : { memo: full && Object.keys(f.memo).length ? $state.snapshot(f.memo) : null }), // a memo to DMP: a recognised club's organizers' alone, never the admin's from Admin
    placeUrl: f.online || f.tba ? null : f.placeUrl.trim() || null, online: f.online, onlineUrl: f.online ? f.onlineUrl.trim() || null : null, emoji: f.emoji, color: f.color, seats: !isMeeting ? seatsN : null, regUntil: regMode === 'date' && !isMeeting && Number.isFinite(regTs) ? regTs : null, lateSignup: regMode === 'end',
    firstYear: f.firstYear && !isMeeting, needsPhone: f.needsPhone && !isMeeting, santa: f.santa && !isMeeting && !f.partner, volunteers: f.vol && !isMeeting && +f.volN > 0 ? Math.min(500, Math.round(+f.volN)) : null, volunteersSenior: f.volSenior, ...(f.teams && teamsOk ? { teamMin: +f.teamMin, teamMax: +f.teamMax, teamCap: +f.teamCap > 0 ? +f.teamCap : null } : { teamMin: null, teamMax: null, teamCap: null }), visibility: f.partner ? 'public' : f.leaders ? 'leaders' : f.teamOnly ? 'members' : 'public', ...(f.leaders ? { leadersFrom: f.leadersFrom } : {}),
    meeting: isMeeting && !f.partner, meetingTag: f.teamOnly && !f.partner && !f.forBoard ? f.meetingTag : null, forBoard: f.teamOnly && !f.partner && f.forBoard,
    form: isMeeting || f.partner ? [] : f.form.map((q) => ({ label: q.label.trim(), kind: q.kind, ...(q.kind === 'choice' ? { options: opts(q.opts) } : {}), required: q.required })),
    ...(canPartner ? { guestHost: f.partner ? f.host.trim() : null, externalUrl: f.partner ? f.link.trim() : null } : {}),
    // only a changed photo, crop or format is sent: left out, the server keeps what the event has
    ...(f.cover?.id !== saved?.cover?.id || !f.cover !== !saved?.cover ? { coverId: f.cover?.id ?? null } : {}),
    ...(String(f.cover?.focus ?? '') !== String(saved?.cover?.focus ?? '') ? { coverFocus: f.cover?.focus ?? null } : {}),
    ...(JSON.stringify(f.cover ? f.formats : {}) !== JSON.stringify(saved?.cover?.formats ?? {}) ? { coverFormats: formatsOut() } : {}),
    ...(f.videoId !== (saved?.video?.id ?? null) ? { videoId: f.videoId } : {}),
    ...(f.wideVideoId !== (saved?.wideVideo?.id ?? null) ? { wideVideoId: f.wideVideoId } : {}),
    ...(String(f.cover ? f.slides.map((x) => x.id) : []) !== String((saved?.slides ?? []).map((x) => x.id)) ? { slideIds: f.cover ? f.slides.map((x) => x.id!) : [] } : {}),
    // the price only from those who may set it: left out, the server keeps it
    ...(canPrice ? f.paid && !isMeeting && !f.partner ? { price: +f.price, payToName: f.payTo.trim(), payPhone: f.payPhone.trim(), freeFirst: +(f.freeFirst || 0) || null } : { price: null } : {}),
  });

  // the form as students will see it once published; what's still empty shows as a dash, never as an example
  function showPreview() {
    haptic.tap();
    const o = mine?.org ?? club!;
    const i = input();
    sheets.preview({
      ...i, santa: i.santa ? { drawn: false } : undefined, teamMin: i.teamMin ?? undefined, teamMax: i.teamMax ?? undefined, volunteers: i.volunteers ? { need: i.volunteers, senior: !!i.volunteersSenior, taken: 0, mine: null } : null, id: saved?.id ?? 0, guestList: !!saved?.guestList, ageCheck: !!saved?.ageCheck, org: o, status: 'published', title: i.title || '—', online: !!i.online, onlineUrl: i.onlineUrl ?? null,
      startsAt: Number.isFinite(startTs) ? startTs : nowTs() + 7 * 86400, seats: Number.isInteger(i.seats) && i.seats! > 0 ? i.seats : null,
      cover: art.cover, slides: f.cover ? f.slides : [], tint: shade(f.color), taken: saved?.taken ?? 0, freeLeft: i.freeFirst ?? null, externalUrl: i.externalUrl !== undefined ? i.externalUrl : saved?.externalUrl ?? null, guestHost: i.guestHost !== undefined ? i.guestHost : saved?.guestHost ?? null, price: i.price === undefined ? saved?.price ?? null : i.price,
      coHost: saved?.coHost ?? null, my: null, saved: false, friends: [], payToName: null, payPhone: null, badgeName: saved?.badgeName ?? null, photos: [], canAddPhotos: false, comments: 0, commentsOn: true, discuss: null, updates: [], myRating: null, canRate: false, ratings: null,
    });
  }

  // publish: out now (a member's draft I answer: my yes); send: a member's own to the club's President and Vices
  async function submit(kind: 'publish' | 'draft' | 'save' | 'send') {
    tried = true;
    if (Object.values(err).some(Boolean)) { haptic.error(); return; }
    if (vUp.tall >= 0 || vUp.wide >= 0 || slidesUp || uploading) { haptic.error(); say(t('ed.videoWait'), 'pleading_face_3d'); return; }
    if (busy) return;
    const sentAt = textDraft.stamp();
    busy = kind;
    try {
      // Resolve member access before saving and ask before dropping a requested restriction.
      if (fromChat && f.teamOnly && !tagsRead) {
        await readTags();
        if (!tagsRead) { say(t('common.error'), 'warning_3d'); return; }
      }
      const tag = tags.find(g => g.id === f.meetingTag);
      if (known.paid && (!f.paid || !tickets || !canPrice)
        || known.visibility === 'leaders' && !f.leaders || known.visibility === 'members' && !f.teamOnly
        || known.forBoard && !f.forBoard || known.schoolOnly && !schoolOnly
        || known.department && (f.forBoard || tag?.name.toLowerCase() !== known.department.toLowerCase())
        || known.cohost && !coWant && !saved || known.partner && !f.partner) {
        const actual = [audienceVal, tickets && priceVal, f.partner && f.host, known.cohost && t('co.invite') + ' · ' + coVal].filter(Boolean).join(' · ');
        if (!await sheets.ask({ title: t('ed.chatReview'), text: actual, ok: t('common.save'), cancel: t('common.cancel') })) return;
      }
      // teams off on an event that has some: they break up (the server lets them go)
      if (saved?.teams?.count && !(f.teams && teamsOk) && !(await sheets.ask({ title: t('ed.teamsOffAsk'), text: t('ed.teamsOffText'), ok: t('common.save'), cancel: t('common.cancel'), danger: true }))) return;
      if (kind === 'draft' && fromChat && tickets && f.paid && !await sheets.ask({
        title: t('ed.chatReview'), text: [priceVal, f.payTo, f.payPhone].join(' · '), ok: t('ed.saveDraft'), cancel: t('common.cancel'),
      })) return;
      const first = !saved;
      let e = saved ? await api.updateEvent(saved.id, input()) : await api.createEvent(org, input());
      if (first && staff) staffEvents.add(e.id); // from here on it is run as Admin runs any event
      if (first) saved = e; // a later step may fail: the retry is an edit of this one (a changed cover too), never a second event
      if (first && coWant && coOk) await api.cohostInvite(e.id, coWant.id).catch(coSay); // the event is saved: the invite can go again from here
      const pub = kind === 'publish' ? await (judge ? api.reviewEvent(e.id, true) : api.publishEvent(e.id)) : null;
      if (pub) e = pub;
      if (kind === 'send') e = await api.submitEvent(e.id);
      const moved = live && e.taken > 0 && (saved!.startsAt !== e.startsAt || saved!.place !== e.place);
      discardText(sentAt);
      base = JSON.stringify(f);
      studioChanged();
      haptic.ok();
      // a student initiative tells its followers once a week (the server's rule): the toast says if they heard, and when next
      if (kind === 'publish') { burst(); say(pub?.told === undefined || !initiative ? phrase('say.published') : t(pub.told ? 'ed.toldNext' : 'ed.toldLater', { when: dayMonthShort(pub.tellAfter ?? nowTs() + 7 * 86400) }), 'party_popper_3d'); }
      else if (kind === 'send') say(t('rv.sent'), 'party_popper_3d');
      else say(kind === 'draft' ? phrase('say.draftSaved') : moved ? t('say.eventMoved') : phrase('say.eventSaved'), 'sparkles_3d');
      close(overlay.id);
      if (staff) { if (!eventById(e.id)) data.opened.push(e); sheets.manage(e.id, true); } // on to Admin's own view of it
    } catch (x) {
      haptic.error();
      say(x instanceof ApiErr && x.message === 'partner' ? t('ed.partnerBad') : x instanceof ApiErr && x.message === 'taken' ? t('ed.partnerTaken')
        : x instanceof ApiErr && x.message === 'paid' ? t('ed.paidLocked') : x instanceof ApiErr && x.message === 'price' ? t('ed.paidOfficial')
        : x instanceof ApiErr && x.message === 'drafts' ? t('rv.limit')
        : x instanceof ApiErr && x.message === 'cohost' ? t('co.bad') : x instanceof ApiErr && x.message === 'needs_phone' ? t('ed.phoneLocked') : x instanceof ApiErr && x.message === 'santa_signed' ? t('santa.locked') : x instanceof ApiErr && x.message === 'santa_until' ? t('santa.badUntil') : x instanceof ApiErr && x.message === 'santa_audience' ? t('santa.audience') : x instanceof ApiErr && x.code === 'conflict' ? t('ed.badSeats') : t('common.error'), 'warning_3d');
    } finally { busy = ''; }
  }
  // the club's President or a Vice sends a member's draft back: a reason from the list, never typed words
  const REASONS: ReviewReason[] = ['details', 'when', 'cover', 'repeat', 'later'];
  function giveBack(ev: MouseEvent) {
    const eid = saved?.id;
    if (!eid) return;
    menu(ev.currentTarget as Element, REASONS.map((r) => ({ label: t(`rv.why.${r}`), onselect: async () => {
      try { await api.reviewEvent(eid, false, r); haptic.ok(); studioChanged(); say(t('rv.returnedSay'), 'sparkles_3d'); base = JSON.stringify(f); discardText(); close(overlay.id); }
      catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    } })), 'end');
  }

  // ---- the text that must not be lost: the name, the description, the place and what was being written to KRI
  const textFields = ['title', 'description', 'place', 'placeUrl'] as const;
  type TextField = typeof textFields[number];
  type TextDraft = { fields: Partial<Record<TextField, { before: string; value: string }>>; announcement: string };
  const textDraft = useDraft<TextDraft>(untrack(() => `kb-editor-${org}-${id ?? 'new'}`));
  const mayKeepText = $derived(!asStaff && !staffOrg.full && !!mine);
  let textBase = $state<Record<TextField, string> | null>(null);

  function restoreText() {
    if (!mayKeepText) return;
    textBase = { title: f.title, description: f.description, place: f.place, placeUrl: f.placeUrl };
    const draft = textDraft.read();
    if (!draft) return;
    for (const k of textFields) {
      const field = draft.fields?.[k];
      // A newer server edit of this field takes precedence. Other unsaved fields still recover.
      if (field?.before === f[k] && typeof field.value === 'string') { f[k] = field.value; touched = true; }
    }
    if (typeof draft.announcement === 'string') said = draft.announcement;
  }
  $effect(() => {
    if (!textBase || !mayKeepText) return;
    const fields: TextDraft['fields'] = {};
    for (const k of textFields) if (f[k] !== textBase[k]) fields[k] = { before: textBase[k], value: f[k] };
    textDraft.track(said.trim() || Object.keys(fields).length ? { fields, announcement: said } : null);
  });
  function discardText(at?: number) {
    if (textBase) textDraft.discard(at);
    textBase = null;
    said = '';
  }

  // ---- KRI (with the forum's switch: its policy section names the AI host). One line, one flow: the first message is
  // the announcement or a few words, the server fills what it says; then KRI's line asks the next thing the card still
  // lacks (lib/eventFill nextQuestion over the form as it stands, so a row filled by hand is never asked) and the
  // answer goes into the same field. The form is the conversation's memory and its preview; never a publish unseen.
  const kriOn = $derived(!id && !!session.board);
  let known = $state<ChatFill>({}); // what KRI was told that the form can't say by itself (free on purpose, no limit on purpose, a department's name)
  let turns = $state(0);
  let filling = $state(false);
  const str = (v: string) => v.trim() || undefined;
  // the form as facts (lib/eventFill ChatFill): only what is set; a default nobody chose is no fact
  function facts(): ChatFill {
    const d = known;
    return {
      ...d, title: str(f.title), description: str(f.description),
      date: f.date && (f.date !== blank.date || d.date) ? f.date : undefined, start: f.start && (f.start !== blank.start || d.start) ? f.start : undefined,
      end: f.end || undefined, endDate: f.endDate || undefined,
      place: f.online || f.tba ? undefined : str(placeText), placeUrl: f.online || f.tba ? undefined : str(f.placeUrl),
      online: f.online || undefined, onlineUrl: f.online ? str(f.onlineUrl) : undefined, tba: f.tba && !f.online || undefined,
      paid: f.paid ? true : d.paid === false ? false : undefined, price: f.paid && +f.price > 0 ? +f.price : undefined,
      payTo: f.paid ? str(f.payTo) : undefined, payPhone: f.paid ? str(f.payPhone) : undefined, freeFirst: f.paid && +f.freeFirst > 0 ? +f.freeFirst : undefined,
      seats: f.cap === 'limited' && +f.seats > 0 ? +f.seats : f.cap === 'unlimited' ? 0 : undefined,
      registration: f.late ? 'end' : f.deadline ? 'date' : d.registration === 'start' ? 'start' : undefined,
      regDate: f.deadline ? f.regDate || undefined : undefined, regTime: f.deadline ? f.regTime || undefined : undefined,
      teams: f.teams ? true : d.teams === false ? false : undefined, teamMin: f.teams ? +f.teamMin || undefined : undefined, teamMax: f.teams ? +f.teamMax || undefined : undefined,
      teamCap: !f.teams ? undefined : +f.teamCap > 0 ? +f.teamCap : d.teamCap === 0 ? 0 : undefined,
      visibility: f.leaders ? 'leaders' : f.teamOnly ? 'members' : d.visibility === 'public' ? 'public' : undefined,
      meeting: f.teamOnly && f.meeting || undefined, partner: f.partner ? true : d.partner === false ? false : undefined,
      guestHost: f.partner ? str(f.host) : undefined, externalUrl: f.partner ? str(f.link) : undefined,
    };
  }
  const kriNext = $derived(turns ? nextQuestion(facts(), canPrice) : 'event');
  const num = (v?: number) => (v ? String(v) : '');
  // a fact into the form, each by its own row's rules (what this person may not set stays as it is)
  const PUT: { [K in keyof ChatFill]-?: (v: ChatFill[K] | undefined) => void } = {
    title: (v) => { f.title = v ?? ''; }, description: (v) => { f.description = v ?? ''; },
    date: (v) => { f.date = v ?? ''; }, start: (v) => { f.start = v ?? ''; }, end: (v) => { f.end = v ?? ''; }, endDate: (v) => { f.endDate = v ?? ''; },
    emoji: (v) => { if (v && !f.cover) f.emoji = v; }, color: (v) => { if (v && !f.cover) f.color = v; }, // the look it picked, where no photo is
    tr: () => {}, // after the name and the description are in (tell)
    place: (v) => { placeChoice = null; f.place = v ?? ''; if (v) f.tba = false; }, placeUrl: (v) => { f.placeUrl = v ?? ''; },
    online: (v) => { f.online = !!v; if (v) f.tba = false; }, onlineUrl: (v) => { f.onlineUrl = v ?? ''; }, tba: (v) => { f.tba = !!v; },
    paid: (v) => { f.paid = canPrice && !!v; }, price: (v) => { if (canPrice) f.price = num(v); },
    payTo: (v) => { if (canPrice && v) f.payTo = v; }, payPhone: (v) => { if (canPrice && v) f.payPhone = v; }, freeFirst: (v) => { if (canPrice) f.freeFirst = num(v); },
    seats: (v) => { f.cap = v ? 'limited' : v === 0 ? 'unlimited' : ''; f.seats = num(v); },
    registration: (v) => { f.late = v === 'end'; deadlineOn(v === 'date'); }, regDate: (v) => { if (v) f.regDate = v; }, regTime: (v) => { if (v) f.regTime = v; },
    teams: (v) => { f.teams = !!v; }, teamMin: (v) => { f.teamMin = String(v ?? 2); }, teamMax: (v) => { f.teamMax = String(v ?? 5); }, teamCap: (v) => { f.teamCap = num(v); },
    needsPhone: (v) => { f.needsPhone = !!v; }, santa: (v) => { f.santa = !!v; },
    volunteers: (v) => { f.vol = !plain && !!v; f.volN = String(v ?? 5); }, volSenior: (v) => { f.volSenior = !plain && !!v; },
    form: (v) => { f.form = (v ?? []).map((q) => ({ label: q.label, kind: q.kind, opts: (q.options ?? []).join(', '), required: q.required })); },
    visibility: (v) => { f.teamOnly = !plain && v === 'members'; f.leaders = !plain && oversee && v === 'leaders'; },
    leadersFrom: (v) => { f.leadersFrom = v ?? 'president'; }, meeting: (v) => { f.meeting = !plain && !!v; }, forBoard: (v) => { f.forBoard = !plain && !!v; },
    schoolOnly: (v) => { if (school) schoolOnly = v; },
    cohost: (v) => {
      const name = v?.toLowerCase(), clubs = name && coOk ? data.orgs.filter((o) => o.kind === 'club' && o.id !== org && [o.name, o.short, o.abbr].some((x) => x?.toLowerCase() === name)) : [];
      if (clubs.length === 1) coWant = clubs[0];
    },
    department: (v) => { const g = tagNamed(v); if (g) { f.meetingTag = g.id; f.forBoard = false; } }, // not read yet: readTags takes it from `known`
    memo: (v) => { if (v && full && !member && (!asStaff || lent)) f.memo = v; },
    partner: (v) => { f.partner = canPartner && !!v; }, guestHost: (v) => { if (canPartner) f.host = v ?? ''; }, externalUrl: (v) => { if (canPartner) f.link = v ?? ''; },
  };
  // which question's answer may overwrite a row already filled; said in passing, it only waits in "differs" for a tap
  const ANSWERS: Partial<Record<string, Differs>> = { date: 'date', start: 'start', place: 'place', price: 'price' };
  async function tell() {
    const text = said.trim();
    if (!text || filling) return;
    haptic.tap(); touch(); filling = true;
    const asked = kriNext, was = facts();
    try {
      // only the message and the event's own facts: never the payment contacts
      const { title, date, endDate, start, end, place, description, paid, price, seats, registration, regDate, regTime, teams, teamMin, teamMax, teamCap, online, tba, visibility, meeting, partner } = was;
      const patch = await api.eventFill(org, text, { title, date, endDate, start, end, place, description, paid, price, seats, registration, regDate, regTime, teams,
        teamMin, teamMax, teamCap, online, tba, visibility, meeting, partner }, asked);
      if (gone) return;
      const next = updateDraft(was, patch);
      // what the form already says is never overwritten in passing: the new value waits for a tap ("differs")
      const wait: typeof differs = [];
      for (const k of ['date', 'start', 'end', 'place', 'price'] as const) {
        if (was[k] === undefined || next[k] === undefined || String(next[k]) === String(was[k]) || ANSWERS[asked] === k) continue;
        wait.push({ k, v: String(next[k]) });
        Object.assign(next, { [k]: was[k] });
      }
      if (was.place && next.online && asked !== 'place') { // a meeting link over a place already set: the same
        if (next.onlineUrl) wait.push({ k: 'onlineUrl', v: next.onlineUrl });
        Object.assign(next, { online: was.online, onlineUrl: was.onlineUrl, tba: was.tba, place: was.place, placeUrl: was.placeUrl });
      }
      const keys = [...new Set([...Object.keys(was), ...Object.keys(next)])] as (keyof ChatFill)[];
      const changed = keys.filter((k) => JSON.stringify(was[k]) !== JSON.stringify(next[k]));
      for (const k of changed) (PUT[k] as ((v: unknown) => void) | undefined)?.(next[k]);
      // the announcement came in all three languages: sent with the save while its name and description stand
      if (changed.includes('tr')) ownTr = next.tr && { tr: next.tr, title: f.title.trim(), description: f.description.trim() };
      known = next;
      differs = [...differs.filter((d) => !wait.some((w) => w.k === d.k)), ...wait.filter((w) => w.k !== 'price' || canPrice)];
      const got = (k: keyof ChatFill) => (changed.includes(k) ? next[k] : undefined);
      ai = [...new Set([...ai, ...marked({ title: got('title') as string, date: got('date') as string, endDate: got('endDate') as string, start: got('start') as string,
        end: got('end') as string, place: got('place') as string, description: got('description') as string, price: got('price') as number }, canPrice)])];
      if (changed.length || wait.length) { haptic.ok(); said = ''; turns++; fromAi = true; fromChat = true; }
      else { haptic.error(); say(t('ed.fillNone'), 'thinking_face_3d'); }
    } catch (e) {
      if (gone) return;
      haptic.error();
      const c = e instanceof ApiErr ? e.code : '';
      say(t(c === 'rate_limited' ? 'as.limit' : c === 'unavailable' ? 'as.busy' : c === 'bad_input' ? 'ed.fillShort' : 'common.error'), 'pleading_face_3d');
    } finally { filling = false; }
  }
  let ai = $state<Marked[]>([]);
  let fromAi = $state(false);
  let fromChat = $state(false);
  const unmark = (k: Marked) => { if (ai.includes(k)) ai = ai.filter((x) => x !== k); };
  const lacks = $derived(fromAi ? missing({ ...f, place: placeText, tba: f.tba || f.online }) : []);
  let differs = $state<{ k: Differs | 'onlineUrl'; v: string }[]>([]);
  const DIFF_KEY = { date: 'ed.date', start: 'ed.start', end: 'ed.end', place: 'ed.place', price: 'ex.price', onlineUrl: 'ed.onlineLink' } as const;
  function take(d: { k: Differs | 'onlineUrl'; v: string }) {
    haptic.tap();
    if (d.k === 'price') { f.paid = true; f.price = d.v; } else if (d.k === 'onlineUrl') { f.online = true; f.onlineUrl = d.v; f.tba = false; }
    else if (d.k === 'place') { PUT.place(d.v); f.placeUrl = ''; } else f[d.k] = d.v;
    differs = differs.filter((x) => x !== d);
  }
  // a missing one tapped: its picker, or the place's page
  function jump(k: 'date' | 'time' | 'place') {
    haptic.tap();
    if (k === 'place') { open('place'); return; }
    const el = panel.querySelector<HTMLInputElement>(`.when input[type=${k}]`);
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    try { el?.showPicker(); } catch { el?.focus(); }
  }

  // "Invite a club" (server cohosts.py): one club of the app hosts it with us once its Vice+ says yes. A saved event
  // invites at once; a new one after its first save. Only an open event (not the team's, a meeting, a partner's)
  let coWant = $state<OrgRef | null>(null);
  let coQ = $state('');
  const co = $derived(saved ? saved.cohost ?? null : coWant ? { org: coWant, status: 'new' as const } : null);
  const coOk = $derived(!isMeeting && !f.teamOnly && !f.leaders && !f.partner && saved?.status !== 'cancelled' && (!!co || lent || may(mine, 'events')));
  const coShort = (o: OrgRef) => (o.name.length > 12 && o.abbr) || nameOf(o); // the row's value has a third of 375 px: a long name by its abbreviation
  // an official co-host's yes takes an initiative's event to the afisha (server seats.on_afisha)
  const onAfisha = $derived(co?.status === 'accepted' && (co.org.official || co.org.kind !== 'club'));
  const coVal = $derived(!co || co.status === 'declined' ? t('ex.no') : co.status === 'pending' ? t('co.pendingShort', { club: coShort(co.org) }) : coShort(co.org));
  const coFound = $derived.by(() => {
    const q = coQ.trim();
    return data.orgs.filter((o) => (o.kind === 'club' || o.kind === 'school') && o.id !== org && o.id !== co?.org.id && (!q || hit(o, q))).slice(0, 8);
  });
  const coSay = (x: unknown) => say(t(x instanceof ApiErr && x.message === 'declined' ? 'co.declinedOnce' : x instanceof ApiErr && x.code === 'rate_limited' ? 'co.limit'
    : x instanceof ApiErr && x.message === 'cohost' ? 'co.bad' : 'common.error'), 'pleading_face_3d');
  async function pickCo(o: OrgRef) {
    haptic.tap(); coQ = '';
    if (!saved) { coWant = o; return; }
    const was = saved.cohost ?? null;
    saved = { ...saved, cohost: { org: o, status: 'pending' } }; // at once; back if the server says no
    try { const r = await api.cohostInvite(saved.id, o.id); saved = { ...saved, cohost: r.cohost ?? null }; haptic.ok(); say(t('co.sent'), 'party_popper_3d'); }
    catch (x) { saved = { ...saved, cohost: was }; haptic.error(); coSay(x); }
  }
  async function dropCo() {
    if (!saved) { coWant = null; haptic.soft(); return; }
    const was = saved.cohost ?? null;
    if (was?.status === 'accepted' && !(await sheets.ask({ title: t('co.removeAsk', { club: nameOf(was.org) }), text: t('co.removeText'), ok: t('co.remove'), cancel: t('common.cancel'), danger: true }))) return;
    saved = { ...saved, cohost: null };
    try { await api.cohostEnd(saved.id); haptic.soft(); if (was?.status === 'accepted') studioChanged(); }
    catch { saved = { ...saved, cohost: was }; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }

  // ---- the pages: the main one, and a stack pushed over it ('more' and 'cover' push a second level)
  type Page = 'cover' | `cover.${CoverFormat}` | 'place' | 'about' | 'price' | 'seats' | 'reg' | 'who' | 'more' | 'video' | 'form' | 'vol' | 'teams' | 'partner' | 'cohost' | 'memo' | 'check';
  let stack = $state<Page[]>([]);
  const pick = $derived<Page | ''>(stack.at(-1) ?? '');
  const fmt = $derived(pick.startsWith('cover.') ? pick.slice(6) as CoverFormat : null);
  const open = (p: Page) => { haptic.tap(); stack = [...stack, p]; if (p === 'place' || p === 'about' || p === 'price') unmark(p); };
  const back = () => { stack = stack.slice(0, -1); };
  const only = (p?: Page) => { stack = p ? [p] : []; };
  const PAGE: Record<Exclude<Page, `cover.${CoverFormat}`>, string> = { cover: 'ed.cover', place: 'ed.place', about: 'ed.about', price: 'ex.price', seats: 'ed.seats',
    reg: 'ex.regUntil', who: 'ex.who', more: 'ex.more', video: 'ed.video', form: 'ed.form', vol: 'ed.vol', teams: 'ed.teams', partner: 'ed.partner', cohost: 'co.invite', memo: 'studio.memoShort', check: 'ex.checkTitle' };
  const pageTitle = $derived(!pick ? '' : fmt ? t(FMT_NAME[fmt]) : t(PAGE[pick as keyof typeof PAGE] as 'ed.cover'));
  // the capsule's title (SPEC §8.2), between Telegram's Back and ⋯: the event, or the page that is open
  $effect(() => { overlay.title = pageTitle || (live ? t('ed.edit') : t('ed.new')); overlay.icon = live ? PencilLine : CalendarPlus; });

  // the rows' values
  const money = (n: number) => t('ex.tenge', { n: n.toLocaleString('ru-RU') });
  const tickets = $derived(!isMeeting && !f.partner);
  // "Questions at sign-up": "Phone, 2 questions" / "Phone" / "No"
  const askVal = $derived([f.needsPhone ? t('ed.formPhone') : '', f.santa ? t('santa.title') : '', f.form.length ? tn('ed.formN', f.form.length) : ''].filter(Boolean).join(', ') || t('ex.no'));
  const priceVal = $derived(f.paid && +f.price > 0 ? money(+f.price) : t('ex.free'));
  const regVal = $derived(regMode === 'end' ? t('ex.untilEnd') : regMode === 'date' && Number.isFinite(regTs) ? relDay(regTs) + ', ' + f.regTime : t('ex.untilStart'));
  // the day shows as soon as it's set, a time or not (a fill without one left it looking empty)
  const dayTs = $derived(fromInputs(f.date, '12:00'));
  const dayText = $derived(Number.isFinite(dayTs) ? `${weekdayShort(dayTs)}, ${dayMonthShort(dayTs)}` : '—');
  // the end's day: its own date when set, else the day the end time falls on (dimmed: nothing chosen)
  const endDay = $derived(f.endDate ? fromInputs(f.endDate, '12:00') : endTs != null ? endTs : Number.isFinite(dayTs) ? dayTs : null);
  const endDayText = $derived(endDay != null ? `${weekdayShort(endDay)}, ${dayMonthShort(endDay)}` : '—');
  const whoVal = $derived(f.leaders ? t('ed.whoLeaders') : f.teamOnly ? t('ed.whoTeam') : t('ed.whoAll'));
  const audienceVal = $derived([whoVal, f.teamOnly && (f.forBoard ? t('ed.meetingBoard') : tags.find(g => g.id === f.meetingTag)?.name),
    (schoolOnly ?? !!saved?.school) && school && t('ed.schoolOnly', { school: nameOf(school) })].filter(Boolean).join(' · '));
  const LEAD = { president: 'ed.leadPres', vice: 'ed.leadVice', head: 'ed.leadHead' } as const;
  const memoN = $derived(Object.keys(f.memo).length);
  const priceBad = $derived(!!(err.price || err.payTo || err.payPhone || err.freeFirst));
  const vidN = $derived([vids.tall, vids.wide].filter(Boolean).length);
  // the card's own line, as the Afisha writes it: the day, the time, the place
  const placeVal = $derived(f.online ? t('event.online') : f.tba ? t('ed.tba') : placeText && placeOf(placeText));
  const cardLine = $derived([dayText, f.start, placeVal].filter(Boolean).join(' · '));
  // what "More" holds that is switched on, so the row says it without being opened
  const moreBad = $derived(!!(err.form || err.teams || err.teamCap || err.host || err.link));
  const moreVal = $derived([askVal !== t('ex.no') && tickets ? t('ed.form') : '', f.teams && teamsOk ? t('ed.teams') : '', f.vol && tickets ? t('ed.vol') : '', vidN ? t('ed.video') : '',
    saved?.doc ? t('event.doc') : '', co && co.status !== 'declined' ? coShort(co.org) : '', f.partner ? t('ed.partner') : ''].filter(Boolean).join(', '));

  // the pull-downs (2-4 choices) on a row's value
  const whoMenu = $derived<MenuItem[]>([
    { label: t('ed.whoAll'), checked: !f.teamOnly && !f.leaders, onselect: () => { f.teamOnly = false; f.leaders = false; } },
    { label: t('ed.whoTeam'), checked: f.teamOnly, onselect: () => { f.teamOnly = true; f.leaders = false; } },
    ...(oversee ? [{ label: t('ed.whoLeaders'), checked: f.leaders, onselect: () => { f.leaders = true; f.teamOnly = false; } }] : []),
  ]);
  const leadMenu = $derived<MenuItem[]>((['president', 'vice', 'head'] as const).map((k) => ({ label: t(LEAD[k]), checked: f.leadersFrom === k, onselect: () => { f.leadersFrom = k; } })));
  const tagMenu = $derived<MenuItem[]>([
    ...(deptOnly && f.meeting ? [] : [{ label: t('ed.meetingAll'), checked: f.meetingTag == null && !f.forBoard, onselect: () => { f.meetingTag = null; f.forBoard = false; } }]),
    // the board (Head+, from roles): built in, no tag to make
    ...(deptOnly ? [] : [{ label: t('ed.meetingBoard'), checked: f.forBoard, onselect: () => { f.meetingTag = null; f.forBoard = true; } }]),
    ...tags.filter((g) => !deptOnly || ownDepts.includes(g.id)).map((g) => ({ label: g.name, checked: !f.forBoard && f.meetingTag === g.id, onselect: () => { f.meetingTag = g.id; f.forBoard = false; } })),
    ...(tags.length ? [] : [{ label: t('ed.meetingSetup'), onselect: () => sheets.teamSetup(org, readTags) }]),
  ]);

  // "Check my event": on the phone, at once, on every Publish/Save; a price or seats in a meeting's or a partner's
  // text aren't this event's to fix; a live event's Save stops only for a contradiction, never for a missing cover
  const SERIOUS = new Set(['priceText', 'priceDiff', 'past', 'seatsText']);
  const clubNames = $derived.by(() => { const o = club ?? mine?.org; return o ? [o.name, o.abbr ?? '', o.short] : []; });
  const found = $derived(check({ title: f.title, description: f.description, paid: f.paid, price: f.paid ? +f.price || null : null, tba: f.tba || f.online,
    place: placeText, startTs, now: nowTs(), live, cover: !!f.cover, seats: own, club: clubNames })
    .filter((x) => (tickets || !['priceText', 'priceDiff', 'seatsText'].includes(x.id)) && (!live || SERIOUS.has(x.id))));
  const fixable = (x: Finding) => canPrice || !['priceText', 'priceDiff'].includes(x.id);
  const n = (x: number) => x.toLocaleString('ru-RU');
  const noteText = (x: Finding) => ('n' in x ? t(`ex.f.${x.id}`, { n: n(x.n) }) : t(`ex.f.${x.id}`));
  const fixLabel = (x: Finding) => x.id === 'priceText' ? t('ex.fix.paid', { n: n(x.n) }) : x.id === 'priceDiff' ? t('ex.fix.price', { n: n(x.n) })
    : x.id === 'seatsText' ? t('ex.fix.seats', { n: x.n }) : t(`ex.fix.${({ past: 'time', noPlace: 'place', noCover: 'cover', noAbout: 'about', longTitle: 'title', clubInTitle: 'clubTitle' } as const)[x.id]}`);
  // a note's one-tap fix: it changes the form, or opens the one place that needs the person
  function fix(x: Finding) {
    haptic.tap(); touch();
    if (x.id === 'priceText') { f.paid = true; f.price = String(x.n); only('price'); }
    else if (x.id === 'priceDiff') f.price = String(x.n);
    else if (x.id === 'seatsText') { f.cap = 'limited'; f.seats = String(x.n); }
    else if (x.id === 'noPlace') { f.tba = false; only('place'); }
    else if (x.id === 'noAbout') only('about');
    else if (x.id === 'noCover') only('cover');
    else if (x.id === 'past') { only(); try { panel.querySelector<HTMLInputElement>('.when input[type=date]')?.showPicker(); } catch { /* old webviews: the field is in sight */ } }
    else if (x.id === 'clubInTitle') f.title = x.clean;
    else if (x.id === 'longTitle') { only(); panel.querySelector<HTMLElement>('.name')?.focus(); }
  }
  // the one main button: what it does for this person and this event
  const goKind = $derived<'save' | 'publish' | 'send'>(live || member && !!review?.askedAt ? 'save' : member ? 'send' : 'publish');
  const goLabel = $derived(goKind === 'save' ? t('common.save') : goKind === 'send' ? t(review?.reason ? 'rv.sendAgain' : 'rv.send') : judge ? t('rv.approve') : t('ed.publish'));
  // Publish/Save: the check first; nothing found goes straight on
  function publish() {
    if (Object.values(err).some(Boolean)) {
      tried = true; haptic.error();
      // the first row that stops it comes into sight, or its page opens
      if (err.title) panel.querySelector<HTMLElement>('.name')?.focus();
      else if (err.place) only('place'); else if (err.seats) only('seats'); else if (priceBad) only('price'); else if (err.reg) only('reg');
      else if (err.form) only('form'); else if (err.teams || err.teamCap) only('teams'); else if (err.host || err.link) only('partner');
      return;
    }
    if (goKind !== 'save' && (found.length || fromChat) || goKind === 'save' && found.length) { only('check'); return; }
    void submit(goKind);
  }

  // the AI writes the description from a few words (the announcement fill, its description only): a card to take or leave
  let writing = $state(false);
  let suggestion = $state('');
  async function aiWrite() {
    haptic.tap(); writing = true;
    try {
      const x = await api.eventFill(org, `${f.title}. ${f.description}`.trim());
      if (x.description) suggestion = x.description; else say(t('ed.fillNone'), 'thinking_face_3d');
    } catch (e) {
      const c = e instanceof ApiErr ? e.code : '';
      say(t(c === 'rate_limited' ? 'as.limit' : c === 'unavailable' ? 'as.busy' : c === 'bad_input' ? 'ed.fillShort' : 'common.error'), 'warning_3d');
    } finally { writing = false; }
  }

  async function remove() {
    if (!saved || busy) return;
    if (!(await sheets.ask({ title: t('ed.deleteAsk'), ok: t('ed.deleteGo'), cancel: t('tk.keep'), danger: true }))) return;
    busy = 'delete';
    try {
      await api.deleteEvent(saved.id);
      discardText();
      base = JSON.stringify(f);
      studioChanged();
      say(phrase('say.draftDeleted'), 'waving_hand_3d_default');
      close(overlay.id);
    } catch { say(t('common.error'), 'warning_3d'); } finally { busy = ''; }
  }
</script>

{#snippet tintPhoto()}<button class="tp" class:on={f.color === photoColor} style="--c:{photoColor}" onclick={() => (f.color = photoColor!)} aria-label={t('ed.tintPhoto')}><ImageIcon size={15} strokeWidth={2.4} /></button>{/snippet}

<!-- engine: Field has no date/time type (nor min): these few by hand, in Field's look (.fl) -->
<div class="panel" class:hinted={member && goKind === 'send'} bind:this={panel} style:--tint={tint} style:--kbh="{keyboard.h}px" oninputcapture={touch} onchangecapture={touch} onclickcapture={touch}>
  <!-- the sheet tinted by the event: its colour, the cover blurred over it, the page's ground on top for contrast -->
  <div class="wash" aria-hidden="true">{#if f.cover}<img src={f.cover.thumb} alt="" />{/if}<i></i></div>
  <header class="bar">
    {#if !inTelegram}<span class="x"><IconButton icon={X} label={t('common.close')} onclick={() => close(overlay.id)} /></span>{/if}
  </header>

  <div class="body scroll" inert={!!pick}>
    {#if kriOn}
      <!-- KRI: one line that says what it needs next, one field to answer in; the card below is the result -->
      <div class="kri" class:busy={filling}>
        <p class="kq"><Sparkles size={15} strokeWidth={2.4} /><span>{filling ? t('as.thinking') : t(`ed.chat.${kriNext}`)}</span></p>
        <Composer bind:value={said} placeholder={t(kriNext === 'payTo' ? 'ed.payTo' : kriNext === 'payPhone' ? 'ed.payPhone' : turns ? 'ed.chatPh' : 'ed.kriPh')}
          maxlength={4000} sending={filling} onsend={tell} pill />
      </div>
    {/if}
    {#if lacks.length}
      <!-- what the announcement didn't say: each one tapped goes to its field -->
      <div class="miss">
        <span>{t('ed.missing')}</span>
        {#each lacks as k (k)}<button class="mk" onclick={() => jump(k)}>{t(k === 'date' ? 'ed.date' : k === 'time' ? 'ed.time' : 'ed.place')}</button>{/each}
      </div>
    {/if}
    {#if differs.length}
      <!-- the new text says otherwise: the form's value stays; a tap takes the new one -->
      <div class="miss">
        <span>{t('ed.differs')}</span>
        {#each differs as d (d.k)}<button class="mk" onclick={() => take(d)}>{t(DIFF_KEY[d.k])}: {d.k === 'price' ? `${d.v} ₸` : d.v}</button>{/each}
      </div>
    {/if}

    {#if review?.reason && review.mine}<Notice tone="warning" text={t('rv.returned', { why: t(`rv.why.${review.reason}`) })} />
    {:else if review?.askedAt && review.mine}<Notice tone="accent" text={t('rv.waiting')} />
    {:else if judge}<Notice tone="accent" text={t('rv.from')} />{/if}

    <!-- the event's card as the Afisha shows it, and the form's first field: the name is typed on the cover itself -->
    <div class="card" class:bad={tried && err.title} class:busy={uploading === 'cover'}>
      <button class="art" onclick={() => open('cover')} aria-label={t('ed.cover')}><Poster item={art} big radius={0} fmt="card" /></button>
      <i class="veil" aria-hidden="true"></i>
      <div class="tools">
        <button class="tool glass glass-pill" onclick={showPreview} aria-label={t('ed.preview')}><Eye size={18} /></button>
        <button class="tool glass glass-pill" onclick={() => open('cover')}><ImagePlus size={18} /><span>{t('ed.cover')}</span></button>
      </div>
      <div class="words">
        <!-- engine: Field size="title" with its label for screen readers only (the card's big name has none in sight) -->
        <textarea class="name" class:ai={ai.includes('title')} oninput={() => unmark('title')} rows="1" bind:value={f.title} maxlength="80" placeholder={t('ex.name')} aria-label={t('ex.name')} enterkeyhint="done"></textarea>
        <p class="line ellipsis">{cardLine}</p>
      </div>
    </div>
    {#if tried && err.title}<p class="err">{err.title}</p>{/if}
    <!-- whose event it is, one quiet line under the card; the full sentence on a tap -->
    {#if asStaff}<button class="who" onclick={() => { haptic.tap(); say(t('mg.asStaff'), 'locked_3d'); }}><ShieldCheck size={14} strokeWidth={2.4} />
      <span class="ellipsis">{clubNames[2] || clubNames[0]} · {t('ed.asAdmin')}</span></button>{/if}
    {#if castLike}
      <!-- a casting made as an event (JCC): the club's recruitment does it properly -->
      <Notice tone="accent" text={t('ed.castHint')} action={{ label: t('ed.castOpen'), onclick: () => { close(overlay.id); sheets.roundSetup(org); } }} />
    {/if}

    <div class="pill when" class:bad={tried && err.when} class:ai={ai.includes('when')} onchangecapture={() => unmark('when')}>
      <i class="rail" aria-hidden="true"></i>
      <!-- one line of text ("Mon, 9 Nov  18:00"); the phone's own pickers sit under each part -->
      <div class="wr"><span class="dot"></span><b>{t('ed.start')}</b>
        <label class="tv">{dayText}<input type="date" bind:value={f.date} aria-label={t('ed.date')} /></label>
        <label class="tv">{f.start || '—'}<input type="time" bind:value={f.start} aria-label={t('ed.start')} /></label></div>
      <div class="wr"><span class="dot o"></span><b>{t('ed.end')}</b>
        <label class="tv" class:ph={!f.endDate}>{endDayText}<input type="date" bind:value={f.endDate} min={f.date} aria-label={t('ed.endDate')} /></label>
        <label class="tv" class:ph={!f.end}>{f.end || '—'}<input type="time" bind:value={f.end} aria-label={t('ed.end')} /></label></div>
    </div>
    {#if tried && err.when}<p class="err">{err.when}</p>{/if}

    <button class="pill go" class:bad={tried && err.place} class:ai={ai.includes('place')} onclick={() => open('place')}>{#if f.online}<VideoCall size={20} />{:else}<MapPin size={20} />{/if}
      <span class="gt ellipsis" class:ph={!placeVal}>{placeVal || t('ex.placeAdd')}</span>
      {#if f.placeUrl && !f.tba && !f.online}<Tag tone="success">{t('event.route')}</Tag>{/if}</button>
    <button class="pill go" class:ai={ai.includes('about')} onclick={() => open('about')}><AlignLeft size={20} />
      <span class="gt clamp-2" class:ph={!f.description.trim()}>{f.description.trim() || t('ex.aboutAdd')}</span></button>

    {#if tickets}
      <Group caption={t('ex.tickets')} footnote={!canPrice && !isMeeting && !member ? (full ? t('ed.paidRight') : t('ed.paidOfficial')) : undefined}>
        {#if canPrice}<Row icon={Ticket} title={t('ex.price')} value={tried && priceBad ? '' : priceVal} invalid={tried && priceBad} accessory="chevron" onclick={() => open('price')} />
        {:else}<Row icon={Ticket} title={t('ex.price')} value={t('ex.free')} />{/if}
        <Row icon={Users} title={t('ed.seats')} value={tried && err.seats ? '' : seatsN ? String(seatsN) : f.cap === 'unlimited' ? t('ex.unlimited') : t('ed.capPick')} invalid={tried && !!err.seats} accessory="chevron" onclick={() => open('seats')} />
        <Row icon={Clock} title={t('ex.regUntil')} value={tried && err.reg ? '' : regVal} invalid={tried && !!err.reg} accessory="chevron" onclick={() => open('reg')} />
      </Group>
    {/if}

    <Group>
      {#if !f.partner && !plain || school}<Row icon={Globe} title={t('ex.who')} value={audienceVal} accessory="chevron" onclick={() => open('who')} />{/if}
      <Row icon={SlidersHorizontal} title={t('ex.more')} value={tried && moreBad ? '' : moreVal} invalid={tried && moreBad} accessory="chevron" onclick={() => open('more')} />
    </Group>

    {#if saved?.status === 'draft' && (!member || review?.mine)}
      <Button kind="plain" destructive full onclick={remove}>{#snippet icon()}<Trash size={18} />{/snippet}{t('ed.delete')}</Button>
    {/if}
  </div>

  <!-- the main action, always under the thumb -->
  {#if !pick}
    <footer class="dock">
      {#if member && goKind === 'send'}<p class="dh">{t('rv.sendHint')}</p>{/if}
      <div class="acts glass glass-pill">
        {#if !live && goKind !== 'save'}<Button kind="gray" size="l" loading={busy === 'draft'} disabled={!!busy && busy !== 'draft'} onclick={() => submit('draft')}>{t('ed.saveDraft')}</Button>{/if}
        {#if judge}<Button kind="gray" size="l" onclick={giveBack}>{t('rv.return')}</Button>{/if}
        <span class="main"><Button kind="filled" size="l" full loading={busy === goKind} disabled={goKind === 'save' && !dirty} onclick={publish}>{goLabel}</Button></span>
      </div>
    </footer>
  {/if}

  <!-- a page pushed over the main one: one thing at a time; Telegram's Back or Done pops it -->
  {#if pick}
    {#key pick}
    <div class="page">
      <!-- the same ground as the main page: no seam between the two as one slides over the other -->
      <div class="wash" aria-hidden="true">{#if f.cover}<img src={f.cover.thumb} alt="" />{/if}<i></i></div>
      <div class="pg scroll">
        {#if !inTelegram}<h2 class="pt">{pageTitle}</h2>{/if}
        {#if pick === 'cover'}
          <!-- one photo, three formats: each as it will look, each a tap from its own crop or its own photo -->
          <div class="fmts">
            {#each FORMATS as k (k)}
              <button class="fm f-{k}" onclick={() => (f.cover ? open(`cover.${k}`) : photoIn?.click())}>
                <span class="fr"><Poster item={art} big radius={0} fmt={k} /></span>
                <b>{t(FMT_NAME[k])}</b>
                <i class:set={!!fmtTag(k)}>{fmtTag(k) || ' '}</i>
              </button>
            {/each}
          </div>
          <p class="hint">{t(f.cover ? 'ed.fmtTip' : 'ed.coverTip')}</p>
          <div class="btns">
            <Button kind="tinted" full loading={uploading === 'cover'} onclick={() => photoIn?.click()}>{#snippet icon()}<ImagePlus size={18} />{/snippet}{f.cover ? t('ed.photoChange') : t('ed.photo')}</Button>
            {#if f.cover}<Button kind="gray" onclick={dropPhoto}>{#snippet icon()}<X size={16} />{/snippet}{t('ed.photoRemove')}</Button>{/if}
          </div>
          {#if f.cover}
            <div class="slides">
              {#each f.slides as p, k (p.id)}
                <!-- engine: IconButton xs, a remove mark on a thumbnail -->
                <span class="sl"><img src={p.thumb} alt="" /><button class="rmx" onclick={() => (f.slides = f.slides.filter((_, n) => n !== k))} aria-label={t('ed.photoRemove')}><X size={14} strokeWidth={2.6} /></button></span>
              {/each}
              {#each { length: slidesUp } as _, k (k)}<span class="sl wait"></span>{/each}
              {#if f.slides.length + slidesUp < SLIDES}
                <label class="sl add" aria-label={t('ed.slidesAdd')}><ImagePlus size={20} /><input type="file" accept="image/*" multiple onchange={pickSlides} disabled={slidesUp > 0} /></label>
              {/if}
            </div>
            <p class="hint">{t('ed.slidesHint')}</p>
            <LookPick bind:color={f.color} colors={COLORS} lead={photoColor ? tintPhoto : undefined} />
            <p class="hint">{t('ed.tint')}</p>
          {:else}
            <LookPick bind:emoji={f.emoji} bind:color={f.color} colors={COLORS} />
          {/if}

        {:else if fmt && f.cover}
          <!-- one format at its real shape: drag the photo, or give this format a photo of its own -->
          {@const k = fmt}
          <CoverCrop photo={coverFor(art.cover, k) as Media} fmt={k} onpick={(p) => setCrop(k, p)} />
          <Group>
            <Row icon={ImagePlus} title={t(uploading === k ? 'ed.docUp' : 'ed.fmtOwn')} accessory="chevron" onclick={() => ownIn?.click()} />
            {#if f.formats[k]}<Row icon={RotateCcw} title={t('ed.fmtReset')} onclick={() => resetFormat(k)} />{/if}
          </Group>
          <input bind:this={ownIn} type="file" accept="image/*" onchange={(ev) => pickOwn(ev, k)} hidden />

        {:else if pick === 'place'}
          <!-- online or a place: one or the other, and "place unknown" only for a place -->
          <Group><Row title={t('event.online')} accessory="switch" checked={f.online} onchange={(v) => { f.online = v; if (v) f.tba = false; }} /></Group>
          {#if f.online}
            <Field label={t('ed.onlineLink')} bind:value={f.onlineUrl} type="url" inputmode="url" maxlength={500} placeholder="https://meet.google.com/…" enterkeyhint="done"
              error={tried && err.place ? err.place : undefined} />
          {:else}
            {#if !f.tba}
              <Group>
                {#each placeOptions as choice (choice)}
                  <Row title={t(PLACE_OPTIONS[choice])} accessory="check" checked={placeType === choice} onclick={() => choosePlace(choice)} />
                {/each}
              </Group>
              {#if placeType === 'room'}
                <CampusPlacePicker bind:value={() => f.place, (v) => { placeChoice = 'room'; f.place = v; }} placeholder="305"
                  error={tried && err.place ? err.place : undefined} />
              {:else if placeType === 'elsewhere'}
                <Field label={t('ed.placeAddress')} bind:value={() => f.place, (v) => { placeChoice = 'elsewhere'; f.place = v; }} maxlength={600} enterkeyhint="done"
                  error={tried && err.place && !badGis ? err.place : undefined} />
                <Field label={t('ed.placeLink')} bind:value={f.placeUrl} type="url" inputmode="url" maxlength={500} placeholder="https://2gis.kz/…" enterkeyhint="done"
                  error={tried && badGis ? err.place : undefined} />
              {/if}
            {/if}
            <Group footnote={t('ed.tbaHint')}><Row title={t('ed.tba')} accessory="switch" checked={f.tba} onchange={(v) => (f.tba = v)} /></Group>
          {/if}

        {:else if pick === 'about'}
          <Field label={t('ed.about')} multiline rows={7} bind:value={f.description} maxlength={2000} placeholder={t('ed.aboutPh')} />
          {#if !isMeeting && !f.teamOnly && !f.leaders}<p class="hint">{t('ce.aboutHint')}</p>{/if}<!-- only public events go to the AI (PLAN 9) -->
          {#if session.board}
            {#if suggestion}
              <Notice tone="accent" title={t('ex.aiSuggest')}>
                <p class="sugt">{suggestion}</p>
                <div class="btns sugb"><Button kind="gray" size="s" onclick={() => (suggestion = '')}>{t('ex.aiKeep')}</Button>
                  <Button kind="tinted" size="s" onclick={() => { touch(); f.description = suggestion; suggestion = ''; haptic.ok(); }}>{t('ex.aiUse')}</Button></div>
              </Notice>
            {:else}
              <span class="lone"><Button kind="tinted" size="s" loading={writing} onclick={aiWrite}>{#snippet icon()}<Sparkles size={16} />{/snippet}{t('ex.aiWrite')}</Button></span>
              {#if !f.description.trim()}<p class="hint">{t('ex.aiHint')}</p>{/if}
            {/if}
          {/if}

        {:else if pick === 'price'}
          <!-- Free or Paid as a choice in sight, never a switch further down -->
          <Segmented items={[{ value: 'free', label: t('ex.free') }, { value: 'paid', label: t('ex.paidSeg') }]} value={f.paid ? 'paid' : 'free'} label={t('ex.price')}
            onchange={(v) => { touch(); f.paid = v === 'paid'; }} />
          {#if f.paid}
            <Field label={t('ed.price')} bind:value={f.price} type="number" inputmode="numeric" placeholder="2000" error={tried && err.price ? err.price : undefined} />
            <Field label={t('ed.payTo')} bind:value={f.payTo} maxlength={80} placeholder={t('ed.payToPh')} error={tried && err.payTo ? err.payTo : undefined} />
            <Field label={t('ed.payPhone')} bind:value={f.payPhone} type="tel" inputmode="tel" autocomplete="tel" placeholder="+7 (707) 123 45 67" error={tried && err.payPhone ? err.payPhone : undefined} />
            <p class="hint">{t('ed.payHint')}</p>
            <Field label={t('ed.freeFirst')} bind:value={f.freeFirst} type="number" inputmode="numeric" placeholder={t('ed.freeFirstPh')} error={tried && err.freeFirst ? err.freeFirst : undefined} />
            <p class="hint">{t('ed.freeFirstHint')}</p>
          {:else}<p class="hint">{t('ed.paidHint')}</p>{/if}

        {:else if pick === 'seats'}
          <!-- limited or not: picked by hand, nothing chosen until then -->
          <Segmented items={[{ value: 'limited', label: t('ed.capLimited') }, { value: 'unlimited', label: t('ex.unlimited') }]} value={f.cap} label={t('ed.seats')}
            onchange={(v) => { touch(); f.cap = v; }} />
          {#if f.cap === 'limited'}<Field label={t('ed.seats')} bind:value={f.seats} type="number" inputmode="numeric" placeholder="50" error={tried && err.seats ? err.seats : undefined} />
          {:else if f.cap === 'unlimited'}<p class="hint">{t('ed.capOpen')}</p>
          {:else if tried && err.seats}<p class="err">{err.seats}</p>{/if}

        {:else if pick === 'reg'}
          <!-- until the start, a date before it, or (free and uncapped) the end: one choice in sight -->
          <Segmented items={[{ value: 'start', label: t('ex.untilStart') }, { value: 'date', label: t('ex.untilDate') }, ...(lateOk ? [{ value: 'end', label: t('ex.untilEnd') }] : [])]}
            value={regMode} label={t('ex.regUntil')} onchange={(v) => { touch(); f.late = v === 'end'; deadlineOn(v === 'date'); }} />
          {#if regMode === 'end'}<p class="hint">{t('ed.lateHint')}</p>
          {:else if !lateOk}<p class="hint">{t('ed.lateOnly')}</p>{/if}
          {#if regMode === 'date'}
            <div class="two">
              <label class="fl" class:bad={tried && err.reg}><span>{t('ed.regDate')}</span><input type="date" bind:value={f.regDate} /></label>
              <label class="fl" class:bad={tried && err.reg}><span>{t('ed.regTime')}</span><input type="time" bind:value={f.regTime} /></label>
            </div>
            {#if tried && err.reg}<p class="err">{err.reg}</p>{/if}
            <p class="hint">{t('ed.deadlineHint')}</p>
          {/if}

        {:else if pick === 'who'}
          <!-- who it is for; "for first-years" is gone from the editor (an event that has it keeps it, sent back
               as it is), the phone is asked in "Questions at sign-up" -->
          {#if !f.partner && !plain}
            <Group footnote={f.leaders ? t('ed.leadersHint') : initiative && !f.teamOnly && !onAfisha ? t('ed.noChannel') : undefined}>
              {#if oversee}<Row icon={Globe} title={t('ex.who')} value={whoVal} menu={whoMenu} />
              {:else}<Row icon={Globe} title={t('ed.teamOnly')} accessory="switch" checked={f.teamOnly} onchange={(v) => (f.teamOnly = v)} />{/if}
              {#if f.leaders}<Row icon={Crown} title={t('ex.leadersFrom')} value={t(LEAD[f.leadersFrom])} menu={leadMenu} />{/if}
              {#if f.teamOnly && tagsRead}
                <Row icon={TagIcon} title={t('ed.meetingWho')} menu={tagMenu}
                  value={f.forBoard ? t('ed.meetingBoard') : tags.find((g) => g.id === f.meetingTag)?.name ?? t('ed.meetingAll')} />
              {/if}
              <!-- a Head with a department calls only theirs (PLAN 35): required puts their department back -->
              {#if f.teamOnly}<Row icon={CalendarCheck} title={t('ed.meeting')} accessory="switch" checked={f.meeting} onchange={(v) => { f.meeting = v; if (v && deptOnly) { f.meetingTag = ownDepts.includes(f.meetingTag ?? -1) ? f.meetingTag : ownDepts[0] ?? null; f.forBoard = false; } }} />{/if}
            </Group>
          {/if}
          {#if school}<Group footnote={t('ed.schoolOnlyHint')}>
            <Row icon={GraduationCap} title={t('ed.schoolOnly', { school: nameOf(school) })} accessory="switch" checked={schoolOnly ?? !!saved?.school} onchange={(v) => (schoolOnly = v)} />
          </Group>{/if}

        {:else if pick === 'more'}
          <!-- the rare things, each a row with its own page -->
          {#if tickets || teamsOk || f.teams}
            <Group caption={t('ex.tickets')}>
              {#if tickets}<Row icon={ListChecks} title={t('ed.form')} value={tried && err.form ? '' : askVal} invalid={tried && !!err.form} accessory="chevron" onclick={() => open('form')} />{/if}
              {#if teamsOk || f.teams}<Row icon={UsersRound} title={t('ed.teams')} value={tried && (err.teams || err.teamCap) ? '' : f.teams && teamsOk ? `${teamSize(+f.teamMin, +f.teamMax)}${+f.teamCap > 0 ? ' · ' + t('ed.teamCapN', { n: +f.teamCap }) : ''}` : t('ex.no')} invalid={tried && !!(err.teams || err.teamCap)} accessory="chevron" onclick={() => open('teams')} />{/if}
              {#if tickets && !plain}<Row icon={HandHeart} title={t('ed.vol')} value={f.vol ? f.volN : t('ex.no')} accessory="chevron" onclick={() => open('vol')} />{/if}
            </Group>
          {/if}
          <input class="doc-in" type="file" accept="application/pdf" bind:this={docPick} onchange={pickDoc} /><!-- outside: Rows' lines need them adjacent -->
          <Group>
            {#if !plain}<Row icon={Clapperboard} title={t('ed.video')} value={vidN ? String(vidN) : t('ex.no')} accessory="chevron" onclick={() => open('video')} />{/if}
            {#if saved && !plain && !member}
              {#if saved.doc && !docUp}<Row icon={FileText} title={saved.doc.title ?? t('event.doc')} value={tn('ed.docPages', saved.doc.pages.length)}
                menu={[{ label: t('ed.docReplace'), onselect: () => docPick?.click() }, { label: t('ed.photoRemove'), destructive: true, onselect: dropDoc }]} />
              {:else if docUp}<Row icon={FileText} title={docName} value={t('ed.docUp')} />
              {:else}<Row icon={FileText} title={t('ed.docAdd')} accessory="chevron" onclick={() => docPick?.click()} />{/if}
            {/if}
            {#if coOk}<Row icon={Blend} title={t('co.invite')} value={coVal} accessory="chevron" onclick={() => open('cohost')} />{/if}
            {#if canPartner && !isMeeting && (saved?.guestHost || known.partner)}<Row icon={Handshake} title={t('ed.partner')} value={tried && (err.host || err.link) ? '' : f.partner ? f.host.trim() || t('ed.need') : t('ex.no')}
              invalid={tried && !!(err.host || err.link)} accessory="chevron" onclick={() => open('partner')} />{/if}
            {#if full && !member && !f.placeUrl && !f.leaders && (!asStaff || lent)}<Row icon={Mail} title={t('studio.memoShort')} value={memoN ? String(memoN) : t('ex.no')} accessory="chevron" onclick={() => open('memo')} />{/if}
          </Group>

        {:else if pick === 'video'}
          <!-- two real tiles shaped like their videos -->
          <div class="vslots">
            {#each ['tall', 'wide'] as const as slot (slot)}
              {@const x = vids[slot]}
              <div class="vslot {slot}">
                {#if x}
                  <span class="vframe">{#if x.poster}<img src={x.poster.thumb} alt="" />{:else}<Clapperboard size={22} />{/if}
                    <!-- engine: IconButton xs over a picture -->
                    <button class="rmx vx" onclick={() => dropVideo(slot)} aria-label={t('ed.photoRemove')}><X size={16} strokeWidth={2.6} /></button></span>
                  <b>{x.status === 'ready' ? t('ed.videoReady') : t('ed.videoWork')}{#if x.duration} · {mmss(x.duration)}{/if}</b>
                {:else}
                  <label class="vframe add" class:busy={vUp[slot] >= 0}><Clapperboard size={22} />
                    {#if vUp[slot] >= 0}<i class="prog" style:width="{vUp[slot] * 100}%"></i>{/if}
                    <input type="file" accept="video/*" onchange={(ev) => pickVideo(ev, slot)} disabled={vUp[slot] >= 0} /></label>
                  <b>{vUp[slot] >= 0 ? t('ed.videoUp', { n: Math.round(vUp[slot] * 100) }) : t(slot === 'tall' ? 'ed.videoTall' : 'ed.videoWide')}</b>
                {/if}
                <i class="hint">{t(slot === 'tall' ? 'ed.videoHint' : 'ed.videoWideHint')}</i>
              </div>
            {/each}
          </div>

        {:else if pick === 'form'}
          <!-- what a participant is asked, in one place: the phone first, a ready-made one; then the event's
               own questions (Oct 30): up to five, text or a choice; with the forum's policy section -->
          <Group footnote={t('ed.formPhoneHint')}><Row icon={Phone} title={t('ed.formPhone')} accessory="switch" checked={f.needsPhone} onchange={(v) => (f.needsPhone = v)} /></Group>
          <!-- Secret Santa (server santa.py): sign-up asks a wishlist, the draw is in the event's management; fixed once drawn -->
          {#if !f.partner}<Group footnote={t('santa.edHint')}><Row icon={Gift} title={t('santa.title')} accessory="switch" checked={f.santa} disabled={!!saved?.santa?.drawn} onchange={(v) => (f.santa = v)} /></Group>{/if}
          {#if session.board}
          {#each f.form as q, i (i)}
            <div class="qc">
              <div class="qrow"><Field label={t('cast.qText')} bind:value={q.label} maxlength={80} placeholder={t('ed.formQ')} />
                <IconButton icon={X} kind="plain" size="s" label={t('ed.photoRemove')} onclick={() => (f.form = f.form.filter((_, k) => k !== i))} /></div>
              <Segmented items={[{ value: 'text', label: t('ed.formText') }, { value: 'choice', label: t('ed.formChoice') }]} bind:value={q.kind} label={t('cast.qText')} />
              {#if q.kind === 'choice'}<Field label={t('ed.formOptsL')} bind:value={q.opts} maxlength={300} placeholder={t('ed.formOpts')} />{/if}
              <Group><Row title={t('ed.formReq')} accessory="switch" checked={q.required} onchange={(v) => (q.required = v)} /></Group>
            </div>
          {/each}
          {#if tried && err.form}<p class="err">{err.form}</p>{/if}
          {#if f.form.length < 5}<span class="lone"><Button kind="tinted" size="s" onclick={() => (f.form = [...f.form, { label: '', kind: 'text', opts: '', required: false }])}>
            {#snippet icon()}<Plus size={16} />{/snippet}{t('ed.formAdd')}</Button></span>{/if}
          <p class="hint">{t('ed.formHint')}</p>
          {/if}

        {:else if pick === 'vol'}
          <!-- volunteers: students apply, the organizers say yes or no in the event's management -->
          <Group footnote={t('ed.volHint')}><Row title={t('ed.vol')} accessory="switch" checked={f.vol} onchange={(v) => (f.vol = v)} /></Group>
          {#if f.vol}
            <Field label={t('ed.volN')} bind:value={f.volN} type="number" inputmode="numeric" />
            <Group><Row title={t('ed.volSenior')} accessory="switch" checked={f.volSenior} onchange={(v) => (f.volSenior = v)} /></Group>
          {/if}

        {:else if pick === 'teams'}
          <!-- team events: captains make teams and invite by link, the organizers form the rest (Teams in the event's screen) -->
          <Group footnote={!teamsOk ? t('ed.teamsFree') : f.paid ? t('ed.teamsPaid') : t('ed.teamsHint')}><Row title={t('ed.teamsOn')} accessory="switch" checked={f.teams && teamsOk} disabled={!teamsOk} onchange={(v) => (f.teams = v)} /></Group>
          {#if f.teams && teamsOk}
            <div class="two">
              <Field label={t('ed.teamMin')} bind:value={f.teamMin} type="number" inputmode="numeric" />
              <Field label={t('ed.teamMax')} bind:value={f.teamMax} type="number" inputmode="numeric" />
            </div>
            {#if err.teams}<p class="err">{err.teams}</p>{/if}
            <Field label={t('ed.teamCap')} bind:value={f.teamCap} type="number" inputmode="numeric" placeholder={t('ex.unlimited')}
              error={err.teamCap || undefined} />
            {#if capSeats}<p class="t-foot capn">{t('ed.teamCapSeats', { n: capSeats })}</p>{/if}
          {/if}

        {:else if pick === 'partner'}
          <Group footnote={t('ed.partnerHint')}><Row title={t('ed.partner')} accessory="switch" checked={f.partner} onchange={(v) => (f.partner = v)} /></Group>
          {#if f.partner}
            <Field label={t('ed.partnerHost')} bind:value={f.host} maxlength={60} placeholder={t('ed.partnerHostPh')} error={tried && err.host ? err.host : undefined} />
            <Field label={t('ed.partnerLink')} bind:value={f.link} type="url" inputmode="url" maxlength={500} placeholder="https://" error={tried && err.link ? err.link : undefined} />
          {/if}

        {:else if pick === 'cohost'}
          {#if co && co.status !== 'declined'}
            <Group footnote={t('co.hint')}>
              <Row title={nameOf(co.org)} subtitle={t(co.status === 'accepted' ? 'co.accepted' : co.status === 'pending' ? 'co.pending' : 'co.afterSave')}>
                {#snippet lead()}<OrgLogo org={co.org} size={30} />{/snippet}
                {#snippet trailing()}<IconButton icon={X} kind="gray" size="s" label={t('co.remove')} onclick={dropCo} />{/snippet}
              </Row>
            </Group>
          {:else}
            {#if co}<p class="hint">{t('co.declined', { club: nameOf(co.org) })}</p>{/if}
            <SearchField bind:value={coQ} placeholder={t('co.search')} />
            <Group footnote={t('co.hint')}>
              {#each coFound as o (o.id)}
                <Row dense title={nameOf(o)} onclick={() => pickCo(o)}>{#snippet lead()}<OrgLogo org={o} size={30} />{/snippet}</Row>
              {:else}<Row dense title={t('co.none')} />{/each}
            </Group>
          {/if}

        {:else if pick === 'memo'}
          <MemoAsksForm bind:memo={f.memo} seats={f.cap === 'limited' ? f.seats : ''} date={f.date} flat />

        {:else if pick === 'check'}
          {#if fromChat}
            <Group>
              <Row title={t('ex.who')} value={audienceVal} />
              {#if tickets}
                <Row title={t('ex.price')} value={priceVal} />
                {#if f.paid}
                  <Row title={t('ed.payTo')} value={f.payTo} />
                  <Row title={t('ed.payPhone')} value={f.payPhone} accessory="chevron" onclick={() => open('price')} />
                {/if}
                <Row title={t('ed.seats')} value={seatsN ? String(seatsN) : f.cap === 'unlimited' ? t('ex.unlimited') : t('ed.capPick')} />
                <Row title={t('ex.regUntil')} value={regVal} />
              {:else if f.partner}
                <Row title={t('ed.partnerHost')} value={f.host} />
                <Row title={t('ed.partnerLink')} value={f.link} accessory="chevron" onclick={() => open('partner')} />
              {/if}
            </Group>
          {/if}
          {#if found.length}
            <p class="sum">{tn('ex.found', found.length)}</p>
            {#each found as x (x.id)}
              <Notice tone={SERIOUS.has(x.id) ? 'warning' : 'neutral'} icon={SERIOUS.has(x.id) ? undefined : Sparkles} text={noteText(x)}
                action={fixable(x) ? { label: fixLabel(x), onclick: () => fix(x) } : undefined} />
            {/each}
          {:else}
            <p class="okay"><CircleCheck size={20} />{t('ex.checkOk')}</p>
          {/if}
        {/if}
      </div>
      <!-- the page's one button: Done, or on the check the action itself -->
      <footer class="dock">
        <div class="acts glass glass-pill">
          {#if pick === 'check'}
            <span class="main"><Button kind="filled" size="l" full loading={busy === goKind} onclick={() => { only(); void submit(goKind); }}>
              {found.length && goKind !== 'send' ? t(live ? 'ex.saveAnyway' : 'ex.publishAnyway') : goLabel}</Button></span>
          {:else}
            <span class="main"><Button kind="filled" size="l" full onclick={back}>{t('ex.done')}</Button></span>
          {/if}
        </div>
      </footer>
    </div>
    {/key}
  {/if}
  <input bind:this={photoIn} type="file" accept="image/*" onchange={pickPhoto} hidden />
</div>

<style>
  .doc-in { display: none; }
  .panel { position: absolute; inset: 0; z-index: var(--z-sheet); display: flex; flex-direction: column; overflow: hidden; background: var(--bg);
    --pill: var(--surface-2); --surface-solid: transparent; /* its buttons on the event's colour, not navy (Button's solid ground) */
    --up: max(0px, var(--kbh, 0px) - var(--safe-bottom)); --dock-h: calc(var(--safe-bottom) + 84px); }
  .panel.hinted { --dock-h: calc(var(--safe-bottom) + 108px); } /* the line over the bar: who publishes a member's draft */
  :global(:root[data-theme='light']) .panel { --pill: rgba(255, 255, 255, 0.62); }
  .wash { position: absolute; inset: 0; background: var(--tint); overflow: hidden; pointer-events: none; }
  .wash img { position: absolute; inset: -20%; width: 140%; height: 140%; object-fit: cover; filter: blur(48px) saturate(1.3); }
  .wash i { position: absolute; inset: 0; background: var(--bg); opacity: 0.5; }
  :global(:root[data-theme='light']) .wash i { opacity: 0.72; }
  .bar { position: absolute; left: 0; right: 0; top: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2)); height: 38px; z-index: 3;
    display: flex; align-items: center; justify-content: center; pointer-events: none; }
  .x { position: absolute; left: var(--s-3); pointer-events: auto; }

  /* the main page: the lists on the event's tinted ground, the pills' glass, Settings' rows */
  .body, .pg { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; gap: var(--s-3);
    padding: calc(max(48px, var(--top)) + var(--s-2)) var(--gutter) calc(var(--dock-h) + var(--s-5) + var(--up)); /* up to the screen's edge under Telegram's buttons, never cut at them */
    --group-bg: var(--pill); }
  .body > :global(*), .pg > :global(*) { flex-shrink: 0; } /* a scrolling column must not squeeze its rows */
  .body > :global(section), .pg > :global(section) { margin-top: var(--s-2); }
  .ph { color: var(--text-3); }
  .err { margin: -6px var(--s-4) 0; font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--danger-text); }
  .capn { margin: -6px var(--s-4) 0; }
  .hint { margin: 0 var(--s-4); font: 450 var(--fs-sub)/1.4 var(--font-text); font-style: normal; color: var(--text-3); }
  .bad { box-shadow: inset 0 0 0 1.5px var(--danger); }
  /* the AI filled it: a quiet accent ring and dot until the organiser touches it */
  .ai:not(.bad) { box-shadow: inset 0 0 0 1px var(--accent-text); }
  .pill.ai::after { content: ''; position: absolute; top: 8px; right: 8px; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
  .miss { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s-2); padding: 0 var(--s-1); }
  .miss > span { font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .mk { padding: 6px var(--s-3); border-radius: var(--r-full); border: 1.5px dashed var(--text-3); color: var(--text); font: 600 var(--fs-sub)/1 var(--font-text); }
  .mk:active { background: var(--fill); }

  /* KRI: its line, then the field (Composer's pill) */
  .kri { display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-3) var(--s-3) var(--s-2); border-radius: var(--r-l); background: var(--pill); box-shadow: var(--card-rim); }
  .kq { display: flex; align-items: flex-start; gap: var(--s-2); padding: 0 var(--s-1); font: 500 var(--fs-body)/1.35 var(--font-text); color: var(--text); }
  .kq > :global(svg) { flex: none; margin-top: 3px; color: var(--accent-text); }
  .kq span { animation: say 320ms var(--ease) backwards; }
  .kri.busy .kq span { color: var(--text-2); animation: think 1.2s ease-in-out infinite; }
  @keyframes say { from { opacity: 0; transform: translate3d(0, 4px, 0); } }
  @keyframes think { 50% { opacity: 0.5; } }

  /* the card: the cover in the Afisha card's shape, the name typed over it */
  .card { position: relative; isolation: isolate; overflow: hidden; display: flex; flex-direction: column; justify-content: flex-end; min-height: 216px;
    border-radius: var(--r-xl); background: var(--tint); box-shadow: var(--shadow-card), var(--card-rim); transition: opacity var(--t-base) var(--ease); }
  .card.busy { opacity: 0.6; }
  .card.bad { box-shadow: inset 0 0 0 1.5px var(--danger); }
  .art { position: absolute; inset: 0; z-index: -2; }
  .art:active { transform: none; }
  .veil { position: absolute; inset: 0; z-index: -1; pointer-events: none; background: linear-gradient(to top, rgba(0, 0, 0, 0.74), rgba(0, 0, 0, 0.28) 48%, rgba(0, 0, 0, 0) 76%); }
  .tools { position: absolute; top: var(--s-3); right: var(--s-3); display: flex; gap: var(--s-2); }
  .tool { display: inline-flex; align-items: center; justify-content: center; gap: 6px; min-width: 38px; height: 38px; padding: 0 var(--s-3); border-radius: var(--r-full);
    color: var(--text); font: 600 var(--fs-sub)/1 var(--font-text); }
  .tool:active { transform: scale(0.94); }
  .words { display: flex; flex-direction: column; gap: 2px; padding: 72px var(--s-4) var(--s-4); pointer-events: none; }
  .name { pointer-events: auto; width: 100%; resize: none; field-sizing: content; min-height: 1.18em; padding: 0; background: none; border-radius: var(--r-xs);
    color: var(--on-accent); font: 700 var(--fs-t1)/1.18 var(--font-display); letter-spacing: -0.02em; text-shadow: 0 1px 12px rgba(0, 0, 0, 0.35); }
  .name::placeholder { color: rgba(255, 255, 255, 0.62); }
  .card:has(.name.ai):not(.bad) { box-shadow: inset 0 0 0 1.5px var(--accent-text); }
  .line { font: 500 var(--fs-body)/1.3 var(--font-text); color: rgba(255, 255, 255, 0.82); }

  .who { align-self: center; max-width: 100%; display: inline-flex; align-items: center; gap: 5px; padding: 2px var(--s-2);
    font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }

  .pill { position: relative; display: flex; align-items: center; gap: var(--s-3); width: 100%; min-height: 54px; padding: 0 var(--s-4);
    border-radius: var(--r-l); background: var(--pill); color: var(--text); text-align: left; font: var(--fw-row) var(--fs-row)/1.3 var(--font-text); }
  .pill > :global(svg) { flex: none; color: var(--text-2); }
  .go { padding-block: var(--s-3); }
  .gt { flex: 1; min-width: 0; }
  .go:active { background: var(--fill); transform: none; }
  .when { flex-direction: column; align-items: stretch; gap: 0; padding: 0; }
  .wr { position: relative; display: flex; align-items: center; gap: var(--s-2); min-height: 54px; padding: 0 var(--s-3) 0 44px; }
  .wr + .wr::before { content: ''; position: absolute; left: 44px; right: 0; top: 0; height: 0.5px; background: var(--separator); }
  .wr b { flex: 1; min-width: 0; font-weight: var(--fw-row); color: var(--text-2); }
  .tv { position: relative; flex: none; padding: 7px var(--s-2); border-radius: var(--r-xs); background: var(--fill); color: var(--text); font: 600 var(--fs-body)/1 var(--font-text); white-space: nowrap; }
  .tv input { position: absolute; inset: 0; width: 100%; opacity: 0; }
  .tv.ph { color: var(--text-3); } /* nothing chosen: the end's day as it follows from the start */
  .dot { position: absolute; left: 20px; width: 9px; height: 9px; border-radius: 50%; background: var(--text-2); }
  .dot.o { background: none; box-shadow: inset 0 0 0 1.5px var(--text-2); }
  .rail { position: absolute; left: 24px; top: 33px; bottom: 33px; border-left: 1.5px dotted var(--text-3); }

  /* the action bar: glass over the page's end, above the home indicator; under the keyboard while one is up */
  .dock { position: absolute; left: 0; right: 0; bottom: 0; z-index: 2; display: flex; flex-direction: column; gap: var(--s-2);
    padding: 0 var(--s-3) calc(var(--safe-bottom) + var(--s-3)); pointer-events: none; }
  .acts { display: flex; align-items: center; gap: var(--s-2); padding: 6px; border-radius: var(--r-xl); pointer-events: auto; }
  .main { flex: 1; min-width: 0; display: flex; }
  .dh { align-self: center; padding: 0 var(--s-4); text-align: center; font: 500 var(--fs-cap)/1.3 var(--font-text); color: var(--text-2); }

  /* a pushed page: the same tinted ground, in from the right as iOS pushes */
  .page { position: absolute; inset: 0; z-index: 1; display: flex; flex-direction: column; background: var(--bg);
    animation: push 340ms var(--ease-spring) backwards; }
  @keyframes push { from { transform: translate3d(100%, 0, 0); } }
  :global(html.lowfx) .page { animation: none; }
  .pt { padding: 0 var(--s-1); font: 700 var(--fs-t1)/1.15 var(--font-display); letter-spacing: -0.02em; }
  .lone { align-self: flex-start; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-2); }
  .sum { margin: 0 var(--s-1); font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  .okay { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-3) var(--s-1); font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--success-text); }
  .sugt { font: 450 var(--fs-body)/1.45 var(--font-text); white-space: pre-line; }
  .sugb { justify-content: flex-end; margin-top: var(--s-1); }

  /* Field's look for the date and time inputs it can't take yet */
  .fl { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .fl > span { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .fl > input { width: 100%; min-width: 0; min-height: var(--ctl-l); padding: 0 var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 450 var(--fs-row)/1.35 var(--font-text); }
  .fl.bad { box-shadow: none; }
  .fl.bad > input { box-shadow: inset 0 0 0 1.5px var(--danger); }

  /* the cover's three formats, each at its own shape and all on one baseline */
  .fmts { display: flex; align-items: flex-end; justify-content: center; gap: var(--s-3); padding: var(--s-2) 0; }
  .fm { display: flex; flex-direction: column; align-items: center; gap: 6px; min-width: 0; }
  .fm:active .fr { transform: scale(0.96); }
  .fr { position: relative; display: block; overflow: hidden; border-radius: var(--r-s); background: var(--surface-2); box-shadow: var(--shadow-card), var(--card-rim); transition: transform var(--t-fast) var(--ease); }
  .f-feed .fr { width: 84px; aspect-ratio: 9 / 16; }
  .f-card .fr { width: 148px; aspect-ratio: 16 / 10; }
  .f-list .fr { width: 64px; aspect-ratio: 1; }
  .fm b { font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text); }
  .fm i { font: 500 var(--fs-cap)/1 var(--font-text); font-style: normal; color: var(--text-3); }
  .fm i.set { color: var(--accent-text); }

  /* the pages' own pieces: the pictures, the questions */
  .btns { display: flex; gap: var(--s-2); }
  .qc { display: flex; flex-direction: column; gap: var(--s-2); padding-bottom: var(--s-3); border-bottom: 0.5px solid var(--separator); }
  .qrow { display: flex; align-items: flex-end; gap: var(--s-1); }
  .qrow > :global(:first-child) { flex: 1; min-width: 0; }
  .qrow > :global(:last-child) { margin-bottom: 7px; }
  .slides { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  .sl { position: relative; width: 58px; height: 58px; border-radius: var(--r-s); overflow: hidden; background: var(--fill); flex: none; }
  .sl img { width: 100%; height: 100%; object-fit: cover; }
  .sl.add input, .vframe input { position: absolute; inset: 0; opacity: 0; }
  .rmx { position: absolute; right: 3px; top: 3px; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: rgba(20, 22, 32, 0.6); color: var(--on-accent); }
  .rmx::after { content: ''; position: absolute; inset: -11px; } /* 44 to the finger */
  .sl.add { display: flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent-text); }
  .sl.wait { animation: sl-wait 1.1s ease-in-out infinite; }
  @keyframes sl-wait { 50% { opacity: 0.5; } }
  .tp { display: flex; align-items: center; justify-content: center; color: var(--on-accent); animation: dot 420ms cubic-bezier(.2, 1.4, .4, 1) backwards; }
  @keyframes dot { from { transform: scale(0.3); opacity: 0; } }
  .vslots { display: grid; grid-template-columns: 1fr 1.6fr; gap: 10px; align-items: end; }
  .vslot { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .vslot b { font: 600 var(--fs-sub)/1.2 var(--font-text); }
  .vslot .hint { margin: 0; line-height: 1.3; }
  .vframe { position: relative; overflow: hidden; display: flex; align-items: center; justify-content: center; border-radius: var(--r-m);
    background: var(--accent-soft); color: var(--accent-text); transition: transform var(--t-fast) var(--ease); }
  .tall .vframe { aspect-ratio: 9 / 14; }
  .wide .vframe { aspect-ratio: 16 / 10; }
  .vframe.add:active { transform: scale(0.97); }
  .vframe.busy { opacity: 0.7; }
  .vframe img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .prog { position: absolute; left: 0; bottom: 0; height: 4px; background: var(--accent); transition: width 300ms linear; }
  .vx { right: 6px; top: 6px; width: 28px; height: 28px; }
  .vx::after { inset: -8px; }
</style>
