<script lang="ts">
  // Studio → a new event or an edit, full screen, laid out like Luma's create screen (owner, Nov 2: the old one long
  // form was "cluttered, strange"): tinted by the event, a big cover, a big name, Start/End in one card, then a few
  // grouped rows; each row opens a focused panel at the bottom (Telegram's Back closes the panel first), rare things
  // under "More". Publishing runs an instant check first (lib/eventCheck.ts: a trip once went out free while its text
  // asked 7500 tenge) with a one-tap fix per note. A new event or a draft: "Publish" or "Save draft"; a published one:
  // "Save" (the server tells registered people when the time or place moves). Leaving with changes asks.
  // The title sits where the capsule usually is, between Telegram's Back and ⋯ buttons. An official club's Vice+ can
  // make it paid (§4.3): the price and where to send it by Kaspi, fixed once someone has paid, and how many 1st-years
  // come free. A registration deadline closes "Going" before the start; it can close it early on a live one.
  import { onMount, untrack } from 'svelte';
  import { fmtPhone } from '../../lib/phone';
  import MemoAsksForm from './MemoAsks.svelte';
  import X from '@lucide/svelte/icons/x';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import PencilLine from '@lucide/svelte/icons/pencil-line';
  import Trash from '@lucide/svelte/icons/trash-2';
  import ImagePlus from '@lucide/svelte/icons/image-plus';
  import Clapperboard from '@lucide/svelte/icons/clapperboard';
  import MapPin from '@lucide/svelte/icons/map-pin';
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
  import ListChecks from '@lucide/svelte/icons/list-checks';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import Handshake from '@lucide/svelte/icons/handshake';
  import Blend from '@lucide/svelte/icons/blend';
  import Mail from '@lucide/svelte/icons/mail';
  import Plus from '@lucide/svelte/icons/plus';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import Segmented from '../../ui/Segmented.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Notice from '../../ui/Notice.svelte';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import Tag from '../../ui/Tag.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import type { MenuItem } from '../../ui/menu';
  import { check, type Finding } from '../../lib/eventCheck';
  import { api, ApiErr, original, staffEvents, staffOrg, type EventFull, type EventInput, type Id, type Media, type MemoAsks, type OrgRef, type Video } from '../../lib/api';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import { nameOf } from '../../lib/short';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, eventById, studioChanged, phrase } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { hit } from '../../lib/clubs';
  import { nowTs, time, relDay, dateInput, fromInputs, weekdayShort, dayMonthShort, multiDay } from '../../lib/time';
  import { haptic, inTelegram } from '../../lib/tg';
  import { shrink } from '../../lib/photo';
  import { shade, coverColor } from '../../lib/color';
  import ImageIcon from '@lucide/svelte/icons/image';
  import { burst } from '../../ui/burst';
  import Poster from '../../ui/Poster.svelte';
  import CoverFocus from './CoverFocus.svelte';
  import { PICK_EMOJI } from '../../lib/emoji';
  import LookPick from '../../ui/LookPick.svelte';
  import Button from '../../ui/Button.svelte';
  import { may, RANK } from '../../lib/perms';
  import { addressGis } from '../../lib/map';
  import { marked, missing, type Marked } from '../../lib/eventFill';

  // staff: Admin's "an event for a club" (a new one only): the app's admin makes the club's draft with no role in it, the
  // save and the cover going as staff (api staffOrg), then runs it as any event opened from Admin (staffEvents); never
  // its money, its videos or its memo, which stay the club's own. The creator (lent) has its President's editor
  let { overlay, org, id, staff = false }: { overlay: Overlay; org: Id; id?: Id; staff?: boolean } = $props();
  // an event opened from Admin and edited here is staff's too: the club's DMP memo is neither shown nor sent (but to the creator)
  const asStaff = $derived(staff || (!!id && staffEvents.has(id)));
  // his covers and videos go as the club's too (X-Staff-Org)
  $effect(() => { if (!staff && !lent) return; staffOrg.id = org; return () => { staffOrg.id = 0; }; });
  const oversee = $derived(!!data.orgs.find((o) => o.id === org)?.canOversee);
  const mine = $derived(session.me?.memberships.find((m) => m.org.id === org));
  const official = $derived(!!(data.orgs.find((o) => o.id === org) ?? mine?.org)?.official);
  const full = $derived(official || !!data.orgs.find((o) => o.id === org)?.top); // the Ascent's top: an official club's tools
  // a student initiative: no @KBTUevents, its followers told once a week (KBTU's own offices are as official)
  const initiative = $derived(!official && (data.orgs.find((o) => o.id === org) ?? mine?.org)?.kind === 'club');
  // a choice question's options, typed with commas: "S, M, L"
  const opts = (s: string) => [...new Set(s.split(',').map((o) => o.trim()).filter(Boolean))];
  const GUEST_BANNED = /kbtu|\u043a\u0431\u0442\u0443|dmp|\u0434\u043c\u043f|council|\u0441\u043e\u0432\u0435\u0442|school/i; // the server's own rule
  // the name Kaspi prints for the recipient ("Alikhan S.", my short name): mine, as the one setting it up usually takes the money
  const myKaspiName = session.me?.student && !untrack(() => asStaff) ? session.me.name : ''; // the creator never: the club's are used

  const EMOJI = PICK_EMOJI;
  // eleven around the colour wheel and night (10-12, no RGB picker); BRAND when nothing else is set
  const COLORS = ['#F2542D', '#FF8A3D', '#FFB23D', '#7CB518', '#2FBF71', '#14B8A6', '#18A9DB', '#3B6BFF', '#7C4DFF', '#AF52DE', '#FF4FA3', '#2A2340'];
  const BRAND = '#3B6BFF';
  // a 2GIS link anywhere in what was pasted into the place field (2GIS → Share → Copy gives name, address, link)
  const GIS_LINK = /https:\/\/(?:[a-z]+\.)?2gis\.(?:kz|ru|com)\/\S*/i; // the server accepts the same hosts

  let saved = $state<EventFull | null>(null); // the server's copy when editing
  // the creator alone gets its President's editor here (server core.can, lent_full): a new event, or one he made so
  // (the server lends nothing on another's); `plain` is every other admin's, a plain public free event
  const lent = $derived(asStaff && !!session.me?.founder && (staff || !!saved?.lentFull));
  const plain = $derived(staff && !lent);
  // a club that lost the ✓ still sees its paid or partner event's rows, to switch them off (the server allows only that)
  const canPrice = $derived((lent || !staff && may(mine, 'money')) && (full || !!saved?.price));
  // a partner's event (Oct 29): an outside host's, posted by an official club or DMP; the link out instead of tickets
  const canPartner = $derived(full || !plain && oversee || !!saved?.guestHost);
  // a new event starts on a random emoji and colour: fewer look alike when nobody picks
  const any = <T,>(xs: T[]) => xs[Math.floor(Math.random() * xs.length)];
  const blank = { emoji: any(EMOJI), color: any(COLORS), cover: null as Media | null, slides: [] as Media[], videoId: null as Id | null, wideVideoId: null as Id | null, title: '', date: dateInput(nowTs() + 7 * 86400), start: '18:00',
    end: '', endDate: '', place: '', placeUrl: '', description: '', seats: '', firstYear: false, needsPhone: false, vol: false, volN: '5', volSenior: false, teams: false, teamMin: '2', teamMax: '5', teamOnly: false, leaders: false, leadersFrom: 'president' as 'president' | 'vice' | 'head',
    meeting: false, meetingTag: null as Id | null, forBoard: false,
    partner: false, host: '', link: '',
    form: [] as { label: string; kind: 'text' | 'choice'; opts: string; required: boolean }[], // the questions at sign-up
    paid: false, price: '', payTo: myKaspiName, payPhone: '', freeFirst: '', deadline: false, late: false, regDate: '', regTime: '18:00',
    tba: false, memo: { room: { any: true, projector: false, capacity: null } } as MemoAsks };
  let f = $state({ ...blank });
  // a new event named like a casting, by someone who may open the club's recruitment: say that's the better tool
  // ponytail: a word list; the AI event check can tell it from the description once it runs on every event
  const castLike = $derived(!id && /\u043a\u0430\u0441\u0442\u0438\u043d\u0433|\u043d\u0430\u0431\u043e\u0440 \u0432|recruit|casting|\u0456\u0440\u0456\u043a\u0442\u0435\u0443/i.test(f.title)
    && may(session.me?.memberships?.find((x) => x.org.id === org), 'casting'));
  let base = $state(JSON.stringify(blank)); // the form with nothing to lose
  // only after a touch of mine (owner, Oct 13: an untouched new event asked "Leave without saving?"; iOS rewrites a
  // date or time input's value as it renders, so the form differed from its blank by itself): the first touch takes the
  // form as it stands then (capture: before the change lands) as the base
  let touched = $state(false);
  const touch = () => { if (!touched) { base = JSON.stringify(f); touched = true; } };
  const dirty = $derived(touched && JSON.stringify(f) !== base);
  const live = $derived(!!saved && saved.status !== 'draft');
  $effect(() => { overlay.title = live ? t('ed.edit') : t('ed.new'); overlay.icon = live ? PencilLine : CalendarPlus; }); // the capsule's title (SPEC §8.2)
  $effect(() => { overlay.tint = shade(f.color); }); // the sheets it opens (Ask, the AI's fill) take its colour
  let tried = $state(false); // errors show after the first submit
  let busy = $state('');

  // a club meeting (§2b): team-only, the whole club or one tag expected; no seats, deadline, price or 1st-year tag
  const isMeeting = $derived(f.teamOnly && f.meeting);
  let tags = $state<import('../../lib/api').ClubTag[]>([]);
  // a Head with departments calls only those (PLAN 35): the first is picked, the rest of the club's aren't offered
  let ownDepts = $state<Id[]>([]), inDept = $state(false); // in a department only the chat sync gave: none to call
  const deptOnly = $derived(inDept && RANK[session.me?.memberships.find((x) => x.org.id === org)?.role ?? 'member'] < RANK.vice);
  // "For whom" (owner, Nov 4): any team-only event, required or not; picking a department doesn't make it required
  let tagsRead = $state(false);
  const readTags = () => api.teamSetup(org).then((s) => { tags = s.tags; ownDepts = s.myDepts ?? []; inDept = !!s.inDept; tagsRead = true; if (deptOnly && !saved) f.meetingTag = ownDepts[0] ?? null; }).catch(() => {});
  $effect(() => { if (f.teamOnly && !tagsRead) readTags(); });

  const startTs = $derived(fromInputs(f.date, f.start));
  // the end: a time on the start's day, earlier than the start meaning the next day (a night hackathon); an end date
  // of its own for an event of several days (a casting, 2-12 Nov), taken as it is
  const endTs = $derived.by(() => {
    const e = fromInputs(f.endDate || f.date, f.end);
    if (!Number.isFinite(e) || !Number.isFinite(startTs)) return null;
    return f.endDate || e > startTs ? e : e + 86400;
  });
  const regTs = $derived(fromInputs(f.regDate, f.regTime));
  // "Until the end" (late sign-up): free, uncapped, public, ours only (the server checks the same)
  const lateOk = $derived(!f.paid && !(+f.seats > 0) && !f.teamOnly && !f.leaders && !f.partner && !f.teams);
  const regMode = $derived(f.late && lateOk ? 'end' : f.deadline ? 'date' : 'start');
  // a team event (server evteams.py): free, ours, not open until the end
  const teamsOk = $derived(!isMeeting && !f.partner && !f.paid && regMode !== 'end');
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
    place: f.tba || f.place.trim() ? '' : t('ed.need'),
    seats: f.seats === '' || (Number.isInteger(+f.seats) && +f.seats > 0) ? '' : t('ed.need'),
    price: !f.paid || (Number.isInteger(+f.price) && +f.price >= 1 && +f.price <= 1_000_000) ? '' : t('ed.need'),
    payTo: !f.paid || lent || f.payTo.trim().length >= 2 ? '' : t('ed.need'),
    payPhone: !f.paid || lent || /^(\+?7|8)?7\d{9}$/.test(f.payPhone.replace(/[\s()-]/g, '')) ? '' : t('ed.phoneBad'),
    freeFirst: !f.paid || !f.freeFirst || (Number.isInteger(+f.freeFirst) && +f.freeFirst >= 0 && +f.freeFirst <= 5000) ? '' : t('ed.need'),
    host: !f.partner ? '' : !f.host.trim() || f.host.trim().length > 60 ? t('ed.need') : GUEST_BANNED.test(f.host) ? t('ed.partnerOwn') : '',
    link: !f.partner || /^https:\/\/[^\s/?#]+\.[^\s/?#]+(?:[/?#]\S*)?$/.test(f.link.trim()) ? '' : t('ed.partnerLinkBad'),
    form: f.form.some((q) => q.label.trim().length < 2 || q.kind === 'choice' && opts(q.opts).length < 2) ? t('ed.formBad') : '',
    teams: !f.teams || !teamsOk || (Number.isInteger(+f.teamMin) && Number.isInteger(+f.teamMax) && +f.teamMin >= 2 && +f.teamMax <= 10 && +f.teamMin <= +f.teamMax) ? '' : t('ed.teamsBad'),
    reg: regMode !== 'date' ? '' : !Number.isFinite(regTs) ? t('ed.need') : Number.isFinite(startTs) && regTs > startTs ? t('ed.regLate') : !live && regTs <= nowTs() ? t('ed.past') : '',
  });

  // a room from DMP: asked in the weekly memo (the block at the end), no longer an in-app request

  // An example instead of "e.g. …": a real place from the events in the app, another one each time
  // the editor opens; built-in ones until the app has events of its own.
  const realPlaces = [...new Set(data.events.filter((e) => !e.placeUrl && e.place.length <= 30).map((e) => e.place))];
  const example = { place: realPlaces.length ? any(realPlaces) : phrase('ed.placePh') };

  // the place field takes a room or a pasted 2GIS share: the link becomes the route, the text stays the name
  $effect(() => {
    const m = f.place.match(GIS_LINK);
    if (!m) return;
    f.placeUrl = m[0];
    f.place = f.place.replace(m[0], ' ').replace(/\s+/g, ' ').replace(/^[\s,.·-]+|[\s,.·-]+$/g, '').slice(0, 80);
    haptic.ok(); say(phrase('say.gisLink'), 'globe_with_meridians_3d');
  });
  // the Kaspi number written as the phone shows it, as it's typed
  $effect(() => { const v = fmtPhone(f.payPhone); if (v !== f.payPhone) f.payPhone = v; });

  // a photo cover: shrunk on the phone, re-encoded by the server; the emoji and colour stay as the fallback
  let uploading = $state(false);
  let photoIn = $state<HTMLInputElement>();
  async function pickPhoto(ev: Event) {
    const el = ev.currentTarget as HTMLInputElement, file = el.files?.[0];
    el.value = '';
    if (!file) return;
    if (file.size > 30 * 1024 * 1024) { say(t('ed.photoBig'), 'pleading_face_3d'); return; }
    uploading = true;
    try { f.cover = await api.uploadPhoto(await shrink(file)); haptic.ok(); void readColor(true); }
    catch { haptic.error(); say(t('ed.photoBad'), 'pleading_face_3d'); }
    finally { uploading = false; }
  }

  // the photo's own colour (around its focus) is the first dot and gets picked with a new photo; a dot chosen on
  // purpose stays when the focus moves (SPEC §4.8b)
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
    f.cover = null; photoColor = null;
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
        f = { emoji: e.emoji ?? EMOJI[0], color: e.color ?? BRAND, cover: e.cover, slides: e.slides ?? [], videoId: e.video?.id ?? null, wideVideoId: e.wideVideo?.id ?? null, title: e.title, date: dateInput(e.startsAt), start: time(e.startsAt),
          end: e.endsAt ? time(e.endsAt) : '', endDate: multiDay(e.startsAt, e.endsAt) ? dateInput(e.endsAt) : '', place: e.place, placeUrl: e.placeUrl ?? '', description: e.description,
          seats: e.seats ? String(e.seats) : '', firstYear: e.firstYear, needsPhone: !!e.needsPhone, vol: !!e.volunteers, volN: String(e.volunteers?.need ?? 5), volSenior: !!e.volunteers?.senior,
          teams: !!e.teamMax, teamMin: String(e.teamMin ?? 2), teamMax: String(e.teamMax ?? 5), teamOnly: e.visibility === 'members', leaders: e.visibility === 'leaders', leadersFrom: e.leadersFrom ?? 'president',
          meeting: !!e.meeting, meetingTag: e.meetingTag ?? null, forBoard: !!e.forBoard,
          partner: !!e.guestHost, host: e.guestHost ?? '', link: e.guestHost ? e.externalUrl ?? '' : '',
          form: (e.form ?? []).map((q) => ({ label: q.label, kind: q.kind, opts: (q.options ?? []).join(', '), required: q.required })),
          paid: !!e.price, price: e.price ? String(e.price) : '', payTo: e.payToName ?? myKaspiName, payPhone: fmtPhone(e.payPhone ?? ''), freeFirst: e.freeFirst ? String(e.freeFirst) : '',
          deadline: !!e.regUntil, late: !!e.lateSignup, regDate: e.regUntil ? dateInput(e.regUntil) : '', regTime: e.regUntil ? time(e.regUntil) : '18:00',
          tba: !e.place, memo: e.memo ?? {} };
        // a cover's tint used to be the photo's average colour: such an event starts on the photo's dot
        if (e.cover && (photoColor = await coverColor(e.cover)) && e.tint !== shade(f.color)) f.color = photoColor;
        base = JSON.stringify(f);
      }).catch(() => { say(t('common.error'), 'warning_3d'); base = JSON.stringify(f); close(overlay.id); });
    }
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
  $effect(() => {
    if (!overlay.closing) return;
    if (pick) { overlay.closing = false; pick = ''; return; } // an open panel goes first (one Back)
    if (!dirty) { leave(); return; }
    overlay.closing = false;
    if (asking) return;
    asking = true;
    sheets.ask({ title: t('ed.leaveAsk'), text: t('ed.leaveText'), ok: t('ed.leaveGo'), cancel: t('ed.stay'), danger: true }).then((yes) => {
      asking = false;
      if (yes) { base = JSON.stringify(f); close(overlay.id); }
    });
  });

  const input = (): EventInput => ({
    title: f.title.trim(), description: f.description.trim(), startsAt: startTs, endsAt: endTs, place: f.tba ? '' : f.place.trim(),
    ...(asStaff && !lent ? {} : { memo: full && Object.keys(f.memo).length ? $state.snapshot(f.memo) : null }), // a memo to DMP: a recognised club's alone, never the admin's from Admin
    placeUrl: f.placeUrl.trim() || null, emoji: f.emoji, color: f.color, seats: f.seats && !isMeeting ? +f.seats : null, regUntil: regMode === 'date' && !isMeeting && Number.isFinite(regTs) ? regTs : null, lateSignup: regMode === 'end',
    firstYear: f.firstYear && !isMeeting, needsPhone: f.needsPhone && !isMeeting, volunteers: f.vol && !isMeeting && +f.volN > 0 ? Math.min(500, Math.round(+f.volN)) : null, volunteersSenior: f.volSenior, ...(f.teams && teamsOk ? { teamMin: +f.teamMin, teamMax: +f.teamMax } : { teamMin: null, teamMax: null }), visibility: f.partner ? 'public' : f.leaders ? 'leaders' : f.teamOnly ? 'members' : 'public', ...(f.leaders ? { leadersFrom: f.leadersFrom } : {}),
    meeting: isMeeting && !f.partner, meetingTag: f.teamOnly && !f.partner && !f.forBoard ? f.meetingTag : null, forBoard: f.teamOnly && !f.partner && f.forBoard,
    form: isMeeting || f.partner ? [] : f.form.map((q) => ({ label: q.label.trim(), kind: q.kind, ...(q.kind === 'choice' ? { options: opts(q.opts) } : {}), required: q.required })),
    ...(canPartner ? { guestHost: f.partner ? f.host.trim() : null, externalUrl: f.partner ? f.link.trim() : null } : {}),
    // only a changed photo or focus is sent: left out, the server keeps what the event has
    ...(f.cover?.id !== saved?.cover?.id || !f.cover !== !saved?.cover ? { coverId: f.cover?.id ?? null } : {}),
    ...(String(f.cover?.focus ?? '') !== String(saved?.cover?.focus ?? '') ? { coverFocus: f.cover?.focus ?? null } : {}),
    ...(f.videoId !== (saved?.video?.id ?? null) ? { videoId: f.videoId } : {}),
    ...(f.wideVideoId !== (saved?.wideVideo?.id ?? null) ? { wideVideoId: f.wideVideoId } : {}),
    ...(String(f.cover ? f.slides.map((x) => x.id) : []) !== String((saved?.slides ?? []).map((x) => x.id)) ? { slideIds: f.cover ? f.slides.map((x) => x.id!) : [] } : {}),
    // the price only from those who may set it: left out, the server keeps it
    ...(canPrice ? f.paid && !isMeeting && !f.partner ? { price: +f.price, payToName: f.payTo.trim(), payPhone: f.payPhone.trim(), freeFirst: +(f.freeFirst || 0) || null } : { price: null } : {}),
  });

  // the form as students will see it once published; what's still empty shows as a dash, never as an example
  function showPreview() {
    haptic.tap();
    const o = session.me?.memberships.find((m) => m.org.id === org)?.org ?? data.orgs.find((x) => x.id === org)!;
    const i = input();
    sheets.preview({
      ...i, teamMin: i.teamMin ?? undefined, teamMax: i.teamMax ?? undefined, volunteers: i.volunteers ? { need: i.volunteers, senior: !!i.volunteersSenior, taken: 0, mine: null } : null, id: saved?.id ?? 0, org: o, status: 'published', title: i.title || '—', place: i.place || '—',
      startsAt: Number.isFinite(startTs) ? startTs : nowTs() + 7 * 86400, seats: Number.isInteger(i.seats) && i.seats! > 0 ? i.seats : null,
      cover: f.cover, slides: f.cover ? f.slides : [], tint: shade(f.color), taken: saved?.taken ?? 0, freeLeft: i.freeFirst ?? null, externalUrl: i.externalUrl !== undefined ? i.externalUrl : saved?.externalUrl ?? null, guestHost: i.guestHost !== undefined ? i.guestHost : saved?.guestHost ?? null, price: i.price === undefined ? saved?.price ?? null : i.price,
      coHost: saved?.coHost ?? null, my: null, saved: false, friends: [], payToName: null, payPhone: null, badgeName: saved?.badgeName ?? null, photos: [], canAddPhotos: false, comments: 0, commentsOn: true, discuss: null, updates: [], myRating: null, canRate: false, ratings: null,
    });
  }

  async function submit(kind: 'publish' | 'draft' | 'save') {
    tried = true;
    if (Object.values(err).some(Boolean)) { haptic.error(); return; }
    if (vUp.tall >= 0 || vUp.wide >= 0 || slidesUp) { haptic.error(); say(t('ed.videoWait'), 'pleading_face_3d'); return; }
    if (busy) return;
    // teams off on an event that has some: they break up (the server lets them go)
    if (saved?.teams?.count && !(f.teams && teamsOk) && !(await sheets.ask({ title: t('ed.teamsOffAsk'), text: t('ed.teamsOffText'), ok: t('common.save'), cancel: t('common.cancel'), danger: true }))) return;
    busy = kind;
    try {
      const first = !saved;
      let e = saved ? await api.updateEvent(saved.id, input()) : await api.createEvent(org, input());
      if (first && staff) staffEvents.add(e.id); // from here on it is run as Admin runs any event
      if (first) saved = e; // a later step may fail: the retry is an edit of this one (a changed cover too), never a second event
      if (first && coWant && coOk) await api.cohostInvite(e.id, coWant.id).catch(coSay); // the event is saved: the invite can go again from here
      const pub = kind === 'publish' ? await api.publishEvent(e.id) : null;
      if (pub) e = pub;
      const moved = live && e.taken > 0 && (saved!.startsAt !== e.startsAt || saved!.place !== e.place);
      base = JSON.stringify(f);
      studioChanged();
      haptic.ok();
      // a student initiative tells its followers once a week (the server's rule): the toast says if they heard, and when next
      if (kind === 'publish') { burst(); say(pub?.told === undefined || !initiative ? phrase('say.published') : t(pub.told ? 'ed.toldNext' : 'ed.toldLater', { when: dayMonthShort(pub.tellAfter ?? nowTs() + 7 * 86400) }), 'party_popper_3d'); }
      else say(kind === 'draft' ? phrase('say.draftSaved') : moved ? t('say.eventMoved') : phrase('say.eventSaved'), 'sparkles_3d');
      close(overlay.id);
      if (staff) { if (!eventById(e.id)) data.opened.push(e); sheets.manage(e.id, true); } // on to Admin's own view of it
    } catch (x) {
      haptic.error();
      say(x instanceof ApiErr && x.message === 'partner' ? t('ed.partnerBad') : x instanceof ApiErr && x.message === 'taken' ? t('ed.partnerTaken')
        : x instanceof ApiErr && x.message === 'paid' ? t('ed.paidLocked') : x instanceof ApiErr && x.message === 'price' ? t('ed.paidOfficial') : x instanceof ApiErr && x.message === 'kaspi' ? t('ed.payNone')
        : x instanceof ApiErr && x.message === 'cohost' ? t('co.bad') : x instanceof ApiErr && x.message === 'needs_phone' ? t('ed.phoneLocked') : x instanceof ApiErr && x.code === 'conflict' ? t('ed.badSeats') : t('common.error'), 'warning_3d');
    } finally { busy = ''; }
  }

  // a new event from the announcement the club already wrote (the owner, Oct 30): the AI fills what the text says,
  // the rest stays as it was; the form is the preview. With the forum's switch (its policy section names the AI host).
  let filling = $state(false);
  let fillLeft = $state(''); // the pasted announcement when the AI failed: the next try opens with it, nothing to paste again
  // a new event starts with the announcement (owner, Nov 13: the fill existed, nobody found it): a paste screen first,
  // then the form, the AI's rows marked until touched and what it couldn't find listed on top; never a publish unseen
  let step = $state<'paste' | 'form'>(untrack(() => !id && session.board ? 'paste' : 'form'));
  let ai = $state<Marked[]>([]);
  let fromAi = $state(false);
  const unmark = (k: Marked) => { if (ai.includes(k)) ai = ai.filter((x) => x !== k); };
  const lacks = $derived(fromAi ? missing(f) : []);
  async function fillFromText() {
    const text = await sheets.askText({ title: t('ed.fillTitle'), text: t('ed.fillText'), ok: t('ed.fillGo'), cancel: t('common.cancel'), placeholder: t('ed.fillPh'), max: 4000, value: fillLeft });
    if (text) await runFill(text, false);
  }
  let run = 0; // the latest fill: one gone on by hand (or left) is dropped when it answers
  async function runFill(text: string, first: boolean) {
    const me = ++run;
    fillLeft = text;
    touch(); filling = true;
    try {
      const x = await api.eventFill(org, text);
      if (me !== run || gone) return;
      const { price, emoji, color, ...rest } = x; // the server sends only the fields it found, named as the form's
      // from the paste screen a date or time it didn't find stays empty (not next week's default): listed on top, and
      // the form's own rule stops a publish without them
      if (first && Object.keys(x).length) { f.date = rest.date ?? ''; f.start = rest.start ?? ''; }
      Object.assign(f, rest);
      if (!f.cover) { if (emoji) f.emoji = emoji; if (color) f.color = color; } // the cover it picked, where no photo is
      if (price && canPrice) { f.paid = true; f.price = String(price); }
      const got = Object.keys(x).length > 0;
      if (got) { haptic.ok(); fillLeft = ''; ai = marked(x, canPrice); fromAi = true; } else haptic.error();
      say(t(got ? 'ed.filled' : 'ed.fillNone'), got ? 'sparkles_3d' : 'thinking_face_3d');
    } catch (e) {
      if (me !== run || gone) return;
      haptic.error();
      const c = e instanceof ApiErr ? e.code : '';
      say(t(c === 'rate_limited' ? 'as.limit' : c === 'unavailable' ? 'as.busy' : c === 'bad_input' ? 'ed.fillShort' : 'common.error'), 'pleading_face_3d');
    } finally { if (me === run) { filling = false; step = 'form'; } }
  }
  function byHand() { haptic.tap(); run++; filling = false; step = 'form'; }
  // a missing one tapped: its picker, or the place's panel
  function jump(k: 'date' | 'time' | 'place') {
    haptic.tap();
    if (k === 'place') { open('place'); return; }
    const el = panel.querySelector<HTMLInputElement>(`.when input[type=${k}]`);
    el?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    try { el?.showPicker(); } catch { el?.focus(); }
  }

  // the focused panel at the bottom: '' none, else which one
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
    return data.orgs.filter((o) => o.kind === 'club' && o.id !== org && o.id !== co?.org.id && (!q || hit(o, q))).slice(0, 8);
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

  type Panel = '' | 'cover' | 'place' | 'about' | 'price' | 'seats' | 'reg' | 'video' | 'form' | 'vol' | 'teams' | 'partner' | 'cohost' | 'memo' | 'check';
  let pick = $state<Panel>('');
  const open = (p: Panel) => { haptic.tap(); pick = p; if (p === 'place' || p === 'about' || p === 'price') unmark(p); };
  const PANEL: Record<Exclude<Panel, ''>, string> = { cover: 'ed.cover', place: 'ed.place', about: 'ed.about', price: 'ex.price', seats: 'ed.seats',
    reg: 'ex.regUntil', video: 'ed.video', form: 'ed.form', vol: 'ed.vol', teams: 'ed.teams', partner: 'ed.partner', cohost: 'co.invite', memo: 'studio.memoShort', check: 'ex.checkTitle' };

  // the rows' values
  const money = (n: number) => t('ex.tenge', { n: n.toLocaleString('ru-RU') });
  const tickets = $derived(!isMeeting && !f.partner);
  // "Questions at sign-up": "Phone, 2 questions" / "Phone" / "No"
  const askVal = $derived([f.needsPhone ? t('ed.formPhone') : '', f.form.length ? tn('ed.formN', f.form.length) : ''].filter(Boolean).join(', ') || t('ex.no'));
  const priceVal = $derived(f.paid && +f.price > 0 ? money(+f.price) : t('ex.free'));
  const regVal = $derived(regMode === 'end' ? t('ex.untilEnd') : regMode === 'date' && Number.isFinite(regTs) ? relDay(regTs) + ', ' + f.regTime : t('ex.untilStart'));
  const dayText = $derived(Number.isFinite(startTs) ? `${weekdayShort(startTs)}, ${dayMonthShort(startTs)}` : '—');
  // the end's day: its own date when set, else the day the end time falls on (dimmed: nothing chosen)
  const endDay = $derived(endTs != null ? endTs : Number.isFinite(startTs) ? startTs : null);
  const endDayText = $derived(endDay != null ? `${weekdayShort(endDay)}, ${dayMonthShort(endDay)}` : '—');
  const whoVal = $derived(f.leaders ? t('ed.whoLeaders') : f.teamOnly ? t('ed.whoTeam') : t('ed.whoAll'));
  const LEAD = { president: 'ed.leadPres', vice: 'ed.leadVice', head: 'ed.leadHead' } as const;
  const memoN = $derived(Object.keys(f.memo).length);
  const priceBad = $derived(!!(err.price || err.payTo || err.payPhone || err.freeFirst));

  // the pull-downs (2-4 choices) on a row's value
  const whoMenu = $derived<MenuItem[]>([
    { label: t('ed.whoAll'), checked: !f.teamOnly && !f.leaders, onselect: () => { f.teamOnly = false; f.leaders = false; } },
    { label: t('ed.whoTeam'), checked: f.teamOnly, onselect: () => { f.teamOnly = true; f.leaders = false; } },
    ...(oversee ? [{ label: t('ed.whoLeaders'), checked: f.leaders, onselect: () => { f.leaders = true; f.teamOnly = false; } }] : []),
  ]);
  const leadMenu = $derived<MenuItem[]>((['president', 'vice', 'head'] as const).map((k) => ({ label: t(LEAD[k]), checked: f.leadersFrom === k, onselect: () => { f.leadersFrom = k; } })));
  const tagMenu = $derived<MenuItem[]>([
    ...(deptOnly && f.meeting ? [] : [{ label: t('ed.meetingAll'), checked: f.meetingTag == null && !f.forBoard, onselect: () => { f.meetingTag = null; f.forBoard = false; } }]),
    // the board (Head+, from roles; owner, Nov 4): built in, no tag to make
    ...(deptOnly ? [] : [{ label: t('ed.meetingBoard'), checked: f.forBoard, onselect: () => { f.meetingTag = null; f.forBoard = true; } }]),
    ...tags.filter((g) => !deptOnly || ownDepts.includes(g.id)).map((g) => ({ label: g.name, checked: !f.forBoard && f.meetingTag === g.id, onselect: () => { f.meetingTag = g.id; f.forBoard = false; } })),
    ...(tags.length ? [] : [{ label: t('ed.meetingSetup'), onselect: () => sheets.teamSetup(org, readTags) }]),
  ]);
  const vidN = $derived([vids.tall, vids.wide].filter(Boolean).length);

  // "Check my event": on the phone, at once, on every Publish/Save; a price or seats in a meeting's or a partner's
  // text aren't this event's to fix; a live event's Save stops only for a contradiction, never for a missing cover
  const SERIOUS = new Set(['priceText', 'priceDiff', 'past', 'seatsText']);
  const clubNames = $derived.by(() => { const o = data.orgs.find((x) => x.id === org) ?? mine?.org; return o ? [o.name, o.abbr ?? '', o.short] : []; });
  const found = $derived(check({ title: f.title, description: f.description, paid: f.paid, price: f.paid ? +f.price || null : null, tba: f.tba,
    place: f.place, startTs, now: nowTs(), live, cover: !!f.cover, seats: +f.seats || null, club: clubNames })
    .filter((x) => (tickets || !['priceText', 'priceDiff', 'seatsText'].includes(x.id)) && (!live || SERIOUS.has(x.id))));
  const fixable = (x: Finding) => canPrice || !['priceText', 'priceDiff'].includes(x.id);
  const n = (x: number) => x.toLocaleString('ru-RU');
  const noteText = (x: Finding) => ('n' in x ? t(`ex.f.${x.id}`, { n: n(x.n) }) : t(`ex.f.${x.id}`));
  const fixLabel = (x: Finding) => x.id === 'priceText' ? t('ex.fix.paid', { n: n(x.n) }) : x.id === 'priceDiff' ? t('ex.fix.price', { n: n(x.n) })
    : x.id === 'seatsText' ? t('ex.fix.seats', { n: x.n }) : t(`ex.fix.${({ past: 'time', noPlace: 'place', noCover: 'cover', noAbout: 'about', longTitle: 'title', clubInTitle: 'clubTitle' } as const)[x.id]}`);
  // a note's one-tap fix: it changes the form, or opens the one place that needs the person
  function fix(x: Finding) {
    haptic.tap(); touch();
    if (x.id === 'priceText') { f.paid = true; f.price = String(x.n); pick = 'price'; }
    else if (x.id === 'priceDiff') f.price = String(x.n);
    else if (x.id === 'seatsText') f.seats = String(x.n);
    else if (x.id === 'noPlace') { f.tba = false; pick = 'place'; }
    else if (x.id === 'noAbout') pick = 'about';
    else if (x.id === 'noCover') pick = 'cover';
    else if (x.id === 'past') { pick = ''; try { panel.querySelector<HTMLInputElement>('.when input[type=date]')?.showPicker(); } catch { /* old webviews: the field is in sight */ } }
    else if (x.id === 'clubInTitle') f.title = x.clean;
    else if (x.id === 'longTitle') { pick = ''; panel.querySelector<HTMLElement>('.name')?.focus(); }
  }
  // Publish/Save: the check first; nothing found goes straight on
  function publish() {
    if (found.length) { open('check'); return; }
    void submit(live ? 'save' : 'publish');
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
      base = JSON.stringify(f);
      studioChanged();
      say(phrase('say.draftDeleted'), 'waving_hand_3d_default');
      close(overlay.id);
    } catch { say(t('common.error'), 'warning_3d'); } finally { busy = ''; }
  }
</script>

{#snippet tintPhoto()}<button class="tp" class:on={f.color === photoColor} style="--c:{photoColor}" onclick={() => (f.color = photoColor!)} aria-label={t('ed.tintPhoto')}><ImageIcon size={15} strokeWidth={2.4} /></button>{/snippet}

<!-- engine: Field has no date/time type (nor min): these few by hand, in Field's look (.fl) -->
<div class="panel" bind:this={panel} style:--tint={shade(f.color)} oninputcapture={touch} onchangecapture={touch} onclickcapture={touch}>
  <!-- the sheet tinted by the event (Luma): its colour, the cover blurred over it, the page's ground on top for contrast -->
  <div class="wash" aria-hidden="true">{#if f.cover}<img src={f.cover.thumb} alt="" />{/if}<i></i></div>
  <header class="bar">
    {#if !inTelegram}<span class="x"><IconButton icon={X} label={t('common.close')} onclick={() => close(overlay.id)} /></span>{/if}
  </header>

  {#if step === 'paste'}
  <!-- the first step of a new event: its announcement, or by hand -->
  <div class="body paste">
    <h2 class="pt">{t('ed.pasteTitle')}</h2>
    <p class="hint">{t('ed.fillSub')}</p>
    <!-- svelte-ignore a11y_autofocus -->
    <textarea class="ann" bind:value={fillLeft} maxlength="4000" placeholder={t('ed.fillPh')} aria-label={t('ed.pasteTitle')} autofocus></textarea>
    <div class="foot">
      <Button kind="filled" size="l" full loading={filling} disabled={fillLeft.trim().length < 20} onclick={() => runFill(fillLeft, true)}>{#snippet icon()}<Sparkles size={18} />{/snippet}{t('ed.fillGo')}</Button>
      <Button kind="plain" full onclick={byHand}>{t('ed.byHand')}</Button>
    </div>
  </div>
  {:else}
  <div class="body scroll">
    <button class="art" class:busy={uploading} onclick={() => open('cover')} aria-label={t('ed.cover')}>
      <Poster item={{ cover: f.cover, emoji: f.emoji, color: f.color }} size={196} radius={24} />
      <span class="artbtn glass glass-pill"><ImagePlus size={20} /></span>
    </button>
    <!-- the preview: a round eye beside the cover, clear of Telegram's own buttons in the bar above (owner, Nov 13) -->
    <span class="pv"><IconButton icon={Eye} label={t('ed.preview')} onclick={showPreview} /></span>
    <!-- whose event it is, one quiet line under the cover (owner, Nov 13: the box took the form's room); the full
         sentence on a tap -->
    {#if asStaff}<button class="who" onclick={() => { haptic.tap(); say(t('mg.asStaff'), 'locked_3d'); }}><ShieldCheck size={14} strokeWidth={2.4} />
      <span class="ellipsis">{clubNames[2] || clubNames[0]} · {t('ed.asAdmin')}</span></button>{/if}
    {#if !id && session.board}
      <span class="mid"><Button kind="secondary" size="s" loading={filling} onclick={fillFromText}>{#snippet icon()}<Sparkles size={16} />{/snippet}{t('ed.fill')}</Button></span>
    {/if}

    {#if lacks.length}
      <!-- what the announcement didn't say: each one tapped goes to its field -->
      <div class="miss">
        <span>{t('ed.missing')}</span>
        {#each lacks as k (k)}<button class="mk" onclick={() => jump(k)}>{t(k === 'date' ? 'ed.date' : k === 'time' ? 'ed.time' : 'ed.place')}</button>{/each}
        {#if lacks.includes('place')}<p class="hint">{t('ed.missPlace')}</p>{/if}
      </div>
    {/if}
    <!-- engine: Field size="title" with its label for screen readers only (the editor's big name has none in sight) -->
    <textarea class="name" class:bad={tried && err.title} class:ai={ai.includes('title')} oninput={() => unmark('title')} rows="1" bind:value={f.title} maxlength="80" placeholder={t('ex.name')} aria-label={t('ex.name')} enterkeyhint="done"></textarea>
    {#if tried && err.title}<p class="err">{err.title}</p>{/if}
    {#if castLike}
      <!-- a casting made as an event (JCC, Nov 3): the club's recruitment does it properly -->
      <Notice tone="accent" text={t('ed.castHint')} action={{ label: t('ed.castOpen'), onclick: () => { close(overlay.id); sheets.roundSetup(org); } }} />
    {/if}

    <div class="pill when" class:bad={tried && err.when} class:ai={ai.includes('when')} onchangecapture={() => unmark('when')}>
      <i class="line" aria-hidden="true"></i>
      <!-- one line of text ("Mon, 9 Nov  18:00"); the phone's own pickers sit under each part -->
      <div class="wr"><span class="dot"></span><b>{t('ed.start')}</b>
        <label class="tv">{dayText}<input type="date" bind:value={f.date} aria-label={t('ed.date')} /></label>
        <label class="tv">{f.start || '—'}<input type="time" bind:value={f.start} aria-label={t('ed.start')} /></label></div>
      <div class="wr"><span class="dot o"></span><b>{t('ed.end')}</b>
        <label class="tv" class:ph={!f.endDate}>{endDayText}<input type="date" bind:value={f.endDate} min={f.date} aria-label={t('ed.endDate')} /></label>
        <label class="tv" class:ph={!f.end}>{f.end || '—'}<input type="time" bind:value={f.end} aria-label={t('ed.end')} /></label></div>
    </div>
    {#if tried && err.when}<p class="err">{err.when}</p>{/if}

    <button class="pill go" class:bad={tried && err.place} class:ai={ai.includes('place')} onclick={() => open('place')}><MapPin size={20} />
      <span class="gt ellipsis" class:ph={!f.place.trim()}>{f.tba ? t('ed.tba') : f.place.trim() || t('ex.placeAdd')}</span>
      {#if f.placeUrl && !f.tba}<Tag tone="success">{t('event.route')}</Tag>{/if}</button>
    <button class="pill go" class:ai={ai.includes('about')} onclick={() => open('about')}><AlignLeft size={20} />
      <span class="gt clamp-2" class:ph={!f.description.trim()}>{f.description.trim() || t('ex.aboutAdd')}</span></button>

    {#if tickets}
      <Group caption={t('ex.tickets')} footnote={!canPrice && !isMeeting ? (full ? t('ed.paidRight') : t('ed.paidOfficial')) : undefined}>
        {#if canPrice}<Row icon={Ticket} title={t('ex.price')} value={tried && priceBad ? '' : priceVal} invalid={tried && priceBad} accessory="chevron" onclick={() => open('price')} />
        {:else}<Row icon={Ticket} title={t('ex.price')} value={t('ex.free')} />{/if}
        <Row icon={Users} title={t('ed.seats')} value={tried && err.seats ? '' : +f.seats > 0 ? f.seats : t('ex.unlimited')} invalid={tried && !!err.seats} accessory="chevron" onclick={() => open('seats')} />
        <Row icon={Clock} title={t('ex.regUntil')} value={tried && err.reg ? '' : regVal} invalid={tried && !!err.reg} accessory="chevron" onclick={() => open('reg')} />
      </Group>
    {/if}

    <!-- who it is for; "for first-years" is gone from the editor (owner, Nov 13: an event that has it keeps it, sent back
         as it is), the phone is asked in "Questions at sign-up" -->
    {#if !f.partner && !plain}
    <Group caption={t('ex.options')} footnote={f.leaders ? t('ed.leadersHint') : initiative && !f.teamOnly && !onAfisha ? t('ed.noChannel') : undefined}>
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

    <Group caption={t('ex.more')}>
      {#if !plain}<Row icon={Clapperboard} title={t('ed.video')} value={vidN ? String(vidN) : t('ex.no')} accessory="chevron" onclick={() => open('video')} />{/if}
      {#if tickets}<Row icon={ListChecks} title={t('ed.form')} value={tried && err.form ? '' : askVal} invalid={tried && !!err.form} accessory="chevron" onclick={() => open('form')} />{/if}
      {#if tickets && !plain}<Row icon={HandHeart} title={t('ed.vol')} value={f.vol ? f.volN : t('ex.no')} accessory="chevron" onclick={() => open('vol')} />{/if}
      {#if teamsOk || f.teams}<Row icon={UsersRound} title={t('ed.teams')} value={tried && err.teams ? '' : f.teams && teamsOk ? `${f.teamMin}–${f.teamMax}` : t('ex.no')} invalid={tried && !!err.teams} accessory="chevron" onclick={() => open('teams')} />{/if}
      {#if coOk}<Row icon={Blend} title={t('co.invite')} value={coVal} accessory="chevron" onclick={() => open('cohost')} />{/if}
      {#if canPartner && !isMeeting && saved?.guestHost}<Row icon={Handshake} title={t('ed.partner')} value={tried && (err.host || err.link) ? '' : f.partner ? f.host.trim() || t('ed.need') : t('ex.no')}
        invalid={tried && !!(err.host || err.link)} accessory="chevron" onclick={() => open('partner')} />{/if}
      {#if full && !f.placeUrl && !f.leaders && (!asStaff || lent)}<Row icon={Mail} title={t('studio.memoShort')} value={memoN ? String(memoN) : t('ex.no')} accessory="chevron" onclick={() => open('memo')} />{/if}
    </Group>

    <!-- the form's end, as Luma's Create (owner, Nov 2: no floating bar over the form) -->
    <div class="foot">
      {#if live}
        <Button kind="filled" size="l" full loading={busy === 'save'} disabled={!dirty} onclick={publish}>{t('common.save')}</Button>
      {:else}
        <Button kind="filled" size="l" full loading={busy === 'publish'} onclick={publish}>{t('ed.publish')}</Button>
        <Button kind="plain" full loading={busy === 'draft'} disabled={!!busy && busy !== 'draft'} onclick={() => submit('draft')}>{t('ed.saveDraft')}</Button>
      {/if}
      {#if saved?.status === 'draft'}
        <Button kind="plain" destructive full onclick={remove}>{#snippet icon()}<Trash size={18} />{/snippet}{t('ed.delete')}</Button>
      {/if}
    </div>
    <div class="tail"></div>
  </div>
  {/if}

  <!-- the focused panel: one thing at a time; Telegram's Back, the scrim or Done closes it -->
  {#if pick}
    <button class="scrim" onclick={() => (pick = '')} aria-label={t('common.close')}></button>
    <div class="pk glass glass-sheet">
      <header class="pkh"><b>{t(PANEL[pick] as 'ed.cover')}</b>
        {#if pick !== 'check'}<Button kind="tinted" size="s" onclick={() => (pick = '')}>{t('ex.done')}</Button>{/if}</header>
      <div class="pkb scroll">
        {#if pick === 'cover'}
          <div class="btns">
            <Button kind="tinted" full loading={uploading} onclick={() => photoIn?.click()}>{#snippet icon()}<ImagePlus size={18} />{/snippet}{f.cover ? t('ed.photoChange') : t('ed.photo')}</Button>
            {#if f.cover}<Button kind="gray" onclick={dropPhoto}>{#snippet icon()}<X size={16} />{/snippet}{t('ed.photoRemove')}</Button>{/if}
            <input bind:this={photoIn} type="file" accept="image/*" onchange={pickPhoto} hidden />
          </div>
          {#if f.cover}
            <CoverFocus cover={f.cover} onpick={(p) => { f.cover = { ...f.cover!, focus: p }; void readColor(false); }} />
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
            <p class="hint">{t('ed.coverTip')}</p>
            <LookPick bind:emoji={f.emoji} bind:color={f.color} colors={COLORS} />
          {/if}

        {:else if pick === 'place'}
          {#if !f.tba}
            <Field label={t('ed.place')} bind:value={f.place} maxlength={400} placeholder={f.placeUrl ? t('ed.placeName') : example.place} enterkeyhint="done"
              error={tried && err.place ? err.place : undefined} />
          {/if}
          {#if !f.placeUrl && !f.tba && addressGis(f.place)}
            <!-- a typed street address: its 2GIS route offered, seen before saving -->
            <span class="lone"><Button kind="tinted" size="s" onclick={() => { f.placeUrl = addressGis(f.place)!; haptic.ok(); say(phrase('say.gisLink'), 'globe_with_meridians_3d'); }}>
              {#snippet icon()}<MapPin size={16} />{/snippet}{t('ed.gisOffer')}</Button></span>
          {/if}
          {#if f.placeUrl && !f.tba}
            <Group>
              <Row icon={MapPin} title={t('event.route')}>
                {#snippet trailing()}<IconButton icon={X} kind="plain" size="s" label={t('ed.photoRemove')} onclick={() => (f.placeUrl = '')} />{/snippet}
              </Row>
            </Group>
          {:else if !f.tba}
            <p class="hint">{t('ed.placeHint')}</p>
          {/if}
          {#if !f.placeUrl}
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
            {#if lent}<p class="hint">{saved?.payToName ? `${saved.payToName} · ${fmtPhone(saved.payPhone ?? '')}. ` : ''}{t('ed.payClub')}</p>
            {:else}
            <Field label={t('ed.payTo')} bind:value={f.payTo} maxlength={80} placeholder={t('ed.payToPh')} error={tried && err.payTo ? err.payTo : undefined} />
            <Field label={t('ed.payPhone')} bind:value={f.payPhone} type="tel" inputmode="tel" autocomplete="tel" placeholder="+7 (707) 123 45 67" error={tried && err.payPhone ? err.payPhone : undefined} />
            <p class="hint">{t('ed.payHint')}</p>
            {/if}
            <Field label={t('ed.freeFirst')} bind:value={f.freeFirst} type="number" inputmode="numeric" placeholder={t('ed.freeFirstPh')} error={tried && err.freeFirst ? err.freeFirst : undefined} />
            <p class="hint">{t('ed.freeFirstHint')}</p>
          {:else}<p class="hint">{t('ed.paidHint')}</p>{/if}

        {:else if pick === 'seats'}
          <Field label={t('ed.seats')} bind:value={f.seats} type="number" inputmode="numeric" placeholder={t('ed.seatsPh')} error={tried && err.seats ? err.seats : undefined} />

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
          <!-- what a participant is asked, in one place (owner, Nov 13): the phone first, a ready-made one; then the event's
               own questions (Oct 30): up to five, text or a choice; with the forum's policy section -->
          <Group footnote={t('ed.formPhoneHint')}><Row icon={Phone} title={t('ed.formPhone')} accessory="switch" checked={f.needsPhone} onchange={(v) => (f.needsPhone = v)} /></Group>
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
          <Group footnote={teamsOk ? t('ed.teamsHint') : t('ed.teamsFree')}><Row title={t('ed.teamsOn')} accessory="switch" checked={f.teams && teamsOk} disabled={!teamsOk} onchange={(v) => (f.teams = v)} /></Group>
          {#if f.teams && teamsOk}
            <div class="two">
              <Field label={t('ed.teamMin')} bind:value={f.teamMin} type="number" inputmode="numeric" />
              <Field label={t('ed.teamMax')} bind:value={f.teamMax} type="number" inputmode="numeric" />
            </div>
            {#if err.teams}<p class="err">{err.teams}</p>{/if}
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
          <MemoAsksForm bind:memo={f.memo} seats={f.seats} date={f.date} flat />

        {:else if pick === 'check'}
          {#if found.length}
            <p class="sum">{tn('ex.found', found.length)}</p>
            {#each found as x (x.id)}
              <Notice tone={SERIOUS.has(x.id) ? 'warning' : 'neutral'} icon={SERIOUS.has(x.id) ? undefined : Sparkles} text={noteText(x)}
                action={fixable(x) ? { label: fixLabel(x), onclick: () => fix(x) } : undefined} />
            {/each}
          {:else}
            <p class="okay"><CircleCheck size={20} />{t('ex.checkOk')}</p>
          {/if}
          <div class="pkfoot">
            <Button kind="filled" size="l" full loading={busy === 'publish' || busy === 'save'} onclick={() => { pick = ''; void submit(live ? 'save' : 'publish'); }}>
              {found.length ? t(live ? 'ex.saveAnyway' : 'ex.publishAnyway') : live ? t('common.save') : t('ed.publish')}</Button>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  .panel { position: absolute; inset: 0; z-index: var(--z-sheet); display: flex; flex-direction: column; overflow: hidden; background: var(--bg);
    --pill: var(--surface-2); --surface-solid: transparent; } /* its buttons on the event's colour, not navy (Button's solid ground) */
  :global(:root[data-theme='light']) .panel { --pill: rgba(255, 255, 255, 0.62); }
  .wash { position: absolute; inset: 0; background: var(--tint); overflow: hidden; pointer-events: none; }
  .wash img { position: absolute; inset: -20%; width: 140%; height: 140%; object-fit: cover; filter: blur(48px) saturate(1.3); }
  .wash i { position: absolute; inset: 0; background: var(--bg); opacity: 0.5; }
  :global(:root[data-theme='light']) .wash i { opacity: 0.72; }
  .bar { position: absolute; left: 0; right: 0; top: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2)); height: 38px; z-index: 1;
    display: flex; align-items: center; justify-content: center; pointer-events: none; }
  .x { position: absolute; left: var(--s-3); pointer-events: auto; }

  /* the main page's lists on the event's tinted ground: the pills' glass, Settings' rows */
  .body { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; gap: var(--s-3); margin-top: max(48px, var(--top)); padding: var(--s-2) var(--gutter) 0;
    --group-bg: var(--pill); }
  .body > :global(*) { flex-shrink: 0; } /* a scrolling column must not squeeze its rows */
  .body > :global(section) { margin-top: var(--s-4); }
  .tail { height: calc(var(--safe-bottom) + 24px); }
  .ph { color: var(--text-3); }
  .mid { align-self: center; margin-top: calc(-1 * var(--s-1)); }
  .err { margin: -6px var(--s-4) 0; font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--danger-text); }
  .hint { margin: 0 var(--s-4); font: 450 var(--fs-sub)/1.4 var(--font-text); font-style: normal; color: var(--text-3); }
  .bad { box-shadow: inset 0 0 0 1.5px var(--danger); }
  /* the AI filled it: a quiet accent ring and dot until the organiser touches it */
  .ai:not(.bad) { box-shadow: inset 0 0 0 1px var(--accent-text); }
  .pill.ai::after { content: ''; position: absolute; top: 8px; right: 8px; width: 6px; height: 6px; border-radius: 50%; background: var(--accent); }
  .paste { gap: var(--s-2); }
  .pt { margin: var(--s-4) var(--s-4) 0; font: 700 var(--fs-t1)/1.2 var(--font-display); letter-spacing: -0.02em; }
  .ann { width: 100%; min-height: 40vh; resize: none; margin-top: var(--s-2); padding: var(--s-4); border-radius: var(--r-l); background: var(--pill); color: var(--text);
    font: 450 var(--fs-body)/1.45 var(--font-text); }
  .ann::placeholder { color: var(--text-3); }
  .miss { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s-2); padding: 0 var(--s-1); }
  .miss > span { font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .miss .hint { flex-basis: 100%; margin: 0; }
  .mk { padding: 6px var(--s-3); border-radius: var(--r-full); border: 1.5px dashed var(--text-3); color: var(--text); font: 600 var(--fs-sub)/1 var(--font-text); }
  .mk:active { background: var(--fill); }

  .who { align-self: center; max-width: 100%; display: inline-flex; align-items: center; gap: 5px; margin-top: calc(-1 * var(--s-1)); padding: 2px var(--s-2);
    font: 500 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .pv { position: absolute; top: var(--s-3); right: var(--gutter); z-index: 1; }
  .art { position: relative; align-self: center; margin: var(--s-1) 0 var(--s-2); border-radius: var(--r-xl); box-shadow: var(--shadow-card); }
  .art:active { transform: scale(0.98); }
  .art.busy { opacity: 0.6; }
  :global(html.lowfx) .artbtn { background: linear-gradient(var(--fill), var(--fill)), linear-gradient(var(--tint-veil), var(--tint-veil)), var(--tint); } /* no blur: the colour as the capsule's */
  .artbtn { position: absolute; right: -8px; bottom: -8px; width: var(--tap); height: var(--tap); border-radius: 50%; display: grid; place-items: center; color: var(--text); }
  .name { width: 100%; resize: none; field-sizing: content; min-height: 1.2em; padding: var(--s-3) var(--s-4); border-radius: var(--r-l); background: var(--pill);
    color: var(--text); font: 700 var(--fs-t1)/1.18 var(--font-display); letter-spacing: -0.02em; }
  .name::placeholder { color: var(--text-3); }

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
  .line { position: absolute; left: 24px; top: 33px; bottom: 33px; border-left: 1.5px dotted var(--text-3); }

  .foot { display: flex; flex-direction: column; align-items: stretch; gap: var(--s-1); margin-top: var(--s-5); }

  /* the panel */
  .scrim { position: absolute; inset: 0; background: var(--scrim); animation: fade 220ms var(--ease) backwards; }
  @keyframes fade { from { opacity: 0; } }
  .pk { position: absolute; left: var(--s-2); right: var(--s-2); bottom: calc(var(--safe-bottom) + var(--s-2)); max-height: calc(100% - var(--top) - 24px); display: flex; flex-direction: column;
    border-radius: var(--r-xl); animation: rise 380ms var(--ease-spring) backwards;
    background: linear-gradient(var(--tint-veil), var(--tint-veil)), var(--tint); } /* the page's colour, not plain navy (owner, Nov 3); Sheet's .ground the same */
  @keyframes rise { from { transform: translate3d(0, 100%, 0); } }
  .pkh { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); padding: var(--s-4) var(--s-4) var(--s-2) var(--s-5); }
  .pkh b { font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.015em; }
  .pkb { display: flex; flex-direction: column; gap: var(--s-3); padding: var(--s-2) var(--s-4) var(--s-4); }
  .pkb > :global(*) { flex-shrink: 0; }
  .lone { align-self: flex-start; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-2); }
  .sum { margin: 0 var(--s-1); font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  .okay { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-3) var(--s-1); font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--success-text); }
  .pkfoot { display: flex; margin-top: var(--s-1); }
  .sugt { font: 450 var(--fs-body)/1.45 var(--font-text); white-space: pre-line; }
  .sugb { justify-content: flex-end; margin-top: var(--s-1); }

  /* Field's look for the date and time inputs it can't take yet */
  .fl { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .fl > span { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .fl > input { width: 100%; min-width: 0; min-height: var(--ctl-l); padding: 0 var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 450 var(--fs-row)/1.35 var(--font-text); }
  .fl.bad { box-shadow: none; }
  .fl.bad > input { box-shadow: inset 0 0 0 1.5px var(--danger); }

  /* the panels' own pieces: the pictures, the questions */
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
