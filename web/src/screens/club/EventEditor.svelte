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
  import { onMount } from 'svelte';
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
  import Tag from '@lucide/svelte/icons/tag';
  import GraduationCap from '@lucide/svelte/icons/graduation-cap';
  import Phone from '@lucide/svelte/icons/phone';
  import Images from '@lucide/svelte/icons/images';
  import ListChecks from '@lucide/svelte/icons/list-checks';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import Handshake from '@lucide/svelte/icons/handshake';
  import Mail from '@lucide/svelte/icons/mail';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ChevronsUpDown from '@lucide/svelte/icons/chevrons-up-down';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import Segmented from '../../ui/Segmented.svelte';
  import { menu } from '../../ui/menu';
  import { check, type Finding } from '../../lib/eventCheck';
  import { api, ApiErr, original, type EventFull, type EventInput, type Id, type Media, type MemoAsks, type Video } from '../../lib/api';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, studioChanged, phrase } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
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

  let { overlay, org, id }: { overlay: Overlay; org: Id; id?: Id } = $props();
  const oversee = $derived(!!data.orgs.find((o) => o.id === org)?.canOversee);
  const mine = $derived(session.me?.memberships.find((m) => m.org.id === org));
  const official = $derived(!!(data.orgs.find((o) => o.id === org) ?? mine?.org)?.official);
  const canPrice = $derived(official && may(mine, 'money'));
  // a partner's event (Oct 29): an outside host's, posted by an official club or DMP; the link out instead of tickets
  const canPartner = $derived(official || oversee);
  // a choice question's options, typed with commas: "S, M, L"
  const opts = (s: string) => [...new Set(s.split(',').map((o) => o.trim()).filter(Boolean))];
  const GUEST_BANNED = /kbtu|\u043a\u0431\u0442\u0443|dmp|\u0434\u043c\u043f|council|\u0441\u043e\u0432\u0435\u0442|school/i; // the server's own rule
  // the name Kaspi prints for the recipient ("Alikhan S.", my short name): mine, as the one setting it up usually takes the money
  const myKaspiName = session.me?.student ? session.me.name : '';

  const EMOJI = PICK_EMOJI;
  // eleven around the colour wheel and night (10-12, no RGB picker); BRAND when nothing else is set
  const COLORS = ['#F2542D', '#FF8A3D', '#FFB23D', '#7CB518', '#2FBF71', '#14B8A6', '#18A9DB', '#3B6BFF', '#7C4DFF', '#AF52DE', '#FF4FA3', '#2A2340'];
  const BRAND = '#3B6BFF';
  // a 2GIS link anywhere in what was pasted into the place field (2GIS → Share → Copy gives name, address, link)
  const GIS_LINK = /https:\/\/(?:[a-z]+\.)?2gis\.(?:kz|ru|com)\/\S*/i; // the server accepts the same hosts

  let saved = $state<EventFull | null>(null); // the server's copy when editing
  // a new event starts on a random emoji and colour: fewer look alike when nobody picks
  const any = <T,>(xs: T[]) => xs[Math.floor(Math.random() * xs.length)];
  const blank = { emoji: any(EMOJI), color: any(COLORS), cover: null as Media | null, slides: [] as Media[], videoId: null as Id | null, wideVideoId: null as Id | null, title: '', date: dateInput(nowTs() + 7 * 86400), start: '18:00',
    end: '', endDate: '', place: '', placeUrl: '', description: '', seats: '', firstYear: false, needsPhone: false, albumOpen: true, vol: false, volN: '5', volSenior: false, teamOnly: false, leaders: false, leadersFrom: 'president' as 'president' | 'vice' | 'head',
    meeting: false, meetingTag: null as Id | null,
    partner: false, host: '', link: '',
    form: [] as { label: string; kind: 'text' | 'choice'; opts: string; required: boolean }[], // the questions at sign-up
    paid: false, price: '', payTo: myKaspiName, payPhone: '', freeFirst: '', deadline: false, regDate: '', regTime: '18:00',
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
  let tried = $state(false); // errors show after the first submit
  let busy = $state('');

  // a club meeting (§2b): team-only, the whole club or one tag expected; no seats, deadline, price or 1st-year tag
  const isMeeting = $derived(f.teamOnly && f.meeting);
  let tags = $state<import('../../lib/api').ClubTag[]>([]);
  // a Head with a department calls only their department (PLAN 35): that one is picked, the rest aren't offered
  let ownDept = $state<Id | null>(null);
  const deptOnly = $derived(ownDept != null && RANK[session.me?.memberships.find((x) => x.org.id === org)?.role ?? 'member'] < RANK.vice);
  $effect(() => { if (isMeeting && !tags.length) api.teamSetup(org).then((s) => { tags = s.tags; ownDept = s.myDept ?? null; if (deptOnly && !saved) f.meetingTag = ownDept; }).catch(() => {}); });

  const startTs = $derived(fromInputs(f.date, f.start));
  // the end: a time on the start's day, earlier than the start meaning the next day (a night hackathon); an end date
  // of its own for an event of several days (a casting, 2-12 Nov), taken as it is
  const endTs = $derived.by(() => {
    const e = fromInputs(f.endDate || f.date, f.end);
    if (!Number.isFinite(e) || !Number.isFinite(startTs)) return null;
    return f.endDate || e > startTs ? e : e + 86400;
  });
  const regTs = $derived(fromInputs(f.regDate, f.regTime));
  // switched on: the day before the event, or its own day when that's already gone
  function deadlineOn(ev: Event) {
    if (!(ev.currentTarget as HTMLInputElement).checked || f.regDate) return;
    const d = Number.isFinite(startTs) ? startTs : nowTs() + 7 * 86400;
    f.regDate = dateInput(d - 86400 > nowTs() ? d - 86400 : d);
  }
  const err = $derived({
    title: f.title.trim() ? '' : t('ed.need'),
    when: !Number.isFinite(startTs) || f.endDate && endTs == null ? t('ed.need') : !live && startTs <= nowTs() ? t('ed.past') : endTs != null && endTs <= startTs ? t('ed.endEarly') : '',
    place: f.tba || f.place.trim() ? '' : t('ed.need'),
    seats: f.seats === '' || (Number.isInteger(+f.seats) && +f.seats > 0) ? '' : t('ed.need'),
    price: !f.paid || (Number.isInteger(+f.price) && +f.price >= 1 && +f.price <= 1_000_000) ? '' : t('ed.need'),
    payTo: !f.paid || f.payTo.trim().length >= 2 ? '' : t('ed.need'),
    payPhone: !f.paid || /^(\+?7|8)?7\d{9}$/.test(f.payPhone.replace(/[\s()-]/g, '')) ? '' : t('ed.phoneBad'),
    freeFirst: !f.paid || !f.freeFirst || (Number.isInteger(+f.freeFirst) && +f.freeFirst >= 0 && +f.freeFirst <= 5000) ? '' : t('ed.need'),
    host: !f.partner ? '' : !f.host.trim() || f.host.trim().length > 60 ? t('ed.need') : GUEST_BANNED.test(f.host) ? t('ed.partnerOwn') : '',
    link: !f.partner || /^https:\/\/[^\s/?#]+\.[^\s/?#]+(?:[/?#]\S*)?$/.test(f.link.trim()) ? '' : t('ed.partnerLinkBad'),
    form: f.form.some((q) => q.label.trim().length < 2 || q.kind === 'choice' && opts(q.opts).length < 2) ? t('ed.formBad') : '',
    reg: !f.deadline ? '' : !Number.isFinite(regTs) ? t('ed.need') : Number.isFinite(startTs) && regTs > startTs ? t('ed.regLate') : !live && regTs <= nowTs() ? t('ed.past') : '',
  });

  // a room from DMP: asked in the weekly memo (the block at the end), no longer an in-app request

  // An example instead of "e.g. …": a real place from the events in the app, another one each time
  // the editor opens; built-in ones until the app has events of its own.
  const realPlaces = [...new Set(data.events.filter((e) => !e.placeUrl && e.place.length <= 30).map((e) => e.place))];
  const example = { place: realPlaces.length ? any(realPlaces) : phrase('ed.placePh') };

  // the place field takes a room or a pasted 2GIS share: the link becomes the route, the text stays the name
  function placeTyped() {
    const m = f.place.match(GIS_LINK);
    if (!m) return;
    f.placeUrl = m[0];
    f.place = f.place.replace(m[0], ' ').replace(/\s+/g, ' ').replace(/^[\s,.·-]+|[\s,.·-]+$/g, '').slice(0, 80);
    haptic.ok(); say(phrase('say.gisLink'), 'globe_with_meridians_3d');
  }

  // a photo cover: shrunk on the phone, re-encoded by the server; the emoji and colour stay as the fallback
  let uploading = $state(false);
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
          seats: e.seats ? String(e.seats) : '', firstYear: e.firstYear, needsPhone: !!e.needsPhone, albumOpen: e.albumOpen ?? true, vol: !!e.volunteers, volN: String(e.volunteers?.need ?? 5), volSenior: !!e.volunteers?.senior, teamOnly: e.visibility === 'members', leaders: e.visibility === 'leaders', leadersFrom: e.leadersFrom ?? 'president',
          meeting: !!e.meeting, meetingTag: e.meetingTag ?? null,
          partner: !!e.guestHost, host: e.guestHost ?? '', link: e.guestHost ? e.externalUrl ?? '' : '',
          form: (e.form ?? []).map((q) => ({ label: q.label, kind: q.kind, opts: (q.options ?? []).join(', '), required: q.required })),
          paid: !!e.price, price: e.price ? String(e.price) : '', payTo: e.payToName ?? myKaspiName, payPhone: fmtPhone(e.payPhone ?? ''), freeFirst: e.freeFirst ? String(e.freeFirst) : '',
          deadline: !!e.regUntil, regDate: e.regUntil ? dateInput(e.regUntil) : '', regTime: e.regUntil ? time(e.regUntil) : '18:00',
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
    memo: Object.keys(f.memo).length ? $state.snapshot(f.memo) : null,
    placeUrl: f.placeUrl.trim() || null, emoji: f.emoji, color: f.color, seats: f.seats && !isMeeting ? +f.seats : null, regUntil: f.deadline && !isMeeting && Number.isFinite(regTs) ? regTs : null,
    firstYear: f.firstYear && !isMeeting, needsPhone: f.needsPhone && !isMeeting, albumOpen: f.albumOpen, volunteers: f.vol && !isMeeting && +f.volN > 0 ? Math.min(500, Math.round(+f.volN)) : null, volunteersSenior: f.volSenior, visibility: f.partner ? 'public' : f.leaders ? 'leaders' : f.teamOnly ? 'members' : 'public', ...(f.leaders ? { leadersFrom: f.leadersFrom } : {}),
    meeting: isMeeting && !f.partner, meetingTag: isMeeting && !f.partner ? f.meetingTag : null,
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
      ...i, volunteers: i.volunteers ? { need: i.volunteers, senior: !!i.volunteersSenior, taken: 0, mine: null } : null, id: saved?.id ?? 0, org: o, status: 'published', title: i.title || '—', place: i.place || '—',
      startsAt: Number.isFinite(startTs) ? startTs : nowTs() + 7 * 86400, seats: Number.isInteger(i.seats) && i.seats! > 0 ? i.seats : null,
      cover: f.cover, slides: f.cover ? f.slides : [], tint: shade(f.color), taken: saved?.taken ?? 0, freeLeft: i.freeFirst ?? null, externalUrl: i.externalUrl !== undefined ? i.externalUrl : saved?.externalUrl ?? null, guestHost: i.guestHost !== undefined ? i.guestHost : saved?.guestHost ?? null, price: i.price === undefined ? saved?.price ?? null : i.price,
      my: null, saved: false, friends: [], payToName: null, payPhone: null, badgeName: saved?.badgeName ?? null, photos: [], canAddPhotos: false, comments: 0, commentsOn: true, discuss: null, updates: [], myRating: null, canRate: false, ratings: null,
    });
  }

  async function submit(kind: 'publish' | 'draft' | 'save') {
    tried = true;
    if (Object.values(err).some(Boolean)) { haptic.error(); return; }
    if (vUp.tall >= 0 || vUp.wide >= 0 || slidesUp) { haptic.error(); say(t('ed.videoWait'), 'pleading_face_3d'); return; }
    if (busy) return;
    busy = kind;
    try {
      let e = saved ? await api.updateEvent(saved.id, input()) : await api.createEvent(org, input());
      const pub = kind === 'publish' ? await api.publishEvent(e.id) : null;
      if (pub) e = pub;
      const moved = live && e.taken > 0 && (saved!.startsAt !== e.startsAt || saved!.place !== e.place);
      base = JSON.stringify(f);
      studioChanged();
      haptic.ok();
      // a student initiative tells its followers once a week (the server's rule): the toast says if they heard, and when next
      if (kind === 'publish') { burst(); say(pub?.told === undefined || official ? phrase('say.published') : t(pub.told ? 'ed.toldNext' : 'ed.toldLater', { when: dayMonthShort(pub.tellAfter ?? nowTs() + 7 * 86400) }), 'party_popper_3d'); }
      else say(kind === 'draft' ? phrase('say.draftSaved') : moved ? t('say.eventMoved') : phrase('say.eventSaved'), 'sparkles_3d');
      close(overlay.id);
    } catch (x) {
      haptic.error();
      say(x instanceof ApiErr && x.message === 'partner' ? t('ed.partnerBad') : x instanceof ApiErr && x.message === 'taken' ? t('ed.partnerTaken')
        : x instanceof ApiErr && x.message === 'paid' ? t('ed.paidLocked') : x instanceof ApiErr && x.message === 'price' ? t('ed.paidOfficial')
        : x instanceof ApiErr && x.code === 'conflict' ? t('ed.badSeats') : t('common.error'), 'warning_3d');
    } finally { busy = ''; }
  }

  // a new event from the announcement the club already wrote (the owner, Oct 30): the AI fills what the text says,
  // the rest stays as it was; the form is the preview. With the forum's switch (its policy section names the AI host).
  let filling = $state(false);
  async function fillFromText() {
    const text = await sheets.askText({ title: t('ed.fillTitle'), text: t('ed.fillText'), ok: t('ed.fillGo'), cancel: t('common.cancel'), placeholder: t('ed.fillPh'), max: 4000 });
    if (!text) return;
    touch(); filling = true;
    try {
      const x = await api.eventFill(org, text);
      const { price, ...rest } = x; // the server sends only the fields it found, named as the form's
      Object.assign(f, rest);
      if (price && canPrice) { f.paid = true; f.price = String(price); }
      const got = Object.keys(x).length > 0;
      if (got) haptic.ok(); else haptic.error();
      say(t(got ? 'ed.filled' : 'ed.fillNone'), got ? 'sparkles_3d' : 'thinking_face_3d');
    } catch (e) {
      haptic.error();
      const c = e instanceof ApiErr ? e.code : '';
      say(t(c === 'rate_limited' ? 'as.limit' : c === 'unavailable' ? 'as.busy' : c === 'bad_input' ? 'ed.fillShort' : 'common.error'), 'pleading_face_3d');
    } finally { filling = false; }
  }

  // the focused panel at the bottom: '' none, else which one
  type Panel = '' | 'cover' | 'place' | 'about' | 'price' | 'seats' | 'reg' | 'video' | 'form' | 'vol' | 'partner' | 'memo' | 'check';
  let pick = $state<Panel>('');
  const open = (p: Panel) => { haptic.tap(); pick = p; };
  const PANEL: Record<Exclude<Panel, ''>, string> = { cover: 'ed.cover', place: 'ed.place', about: 'ed.about', price: 'ex.price', seats: 'ed.seats',
    reg: 'ex.regUntil', video: 'ed.video', form: 'ed.form', vol: 'ed.vol', partner: 'ed.partner', memo: 'studio.memoShort', check: 'ex.checkTitle' };

  // the rows' values
  const money = (n: number) => t('ex.tenge', { n: n.toLocaleString('ru-RU') });
  const tickets = $derived(!isMeeting && !f.partner);
  const priceVal = $derived(f.paid && +f.price > 0 ? money(+f.price) : t('ex.free'));
  const regVal = $derived(f.deadline && Number.isFinite(regTs) ? relDay(regTs) + ', ' + f.regTime : t('ex.untilStart'));
  const dayText = $derived(Number.isFinite(startTs) ? `${weekdayShort(startTs)}, ${dayMonthShort(startTs)}` : '—');
  // the end's day: its own date when set, else the day the end time falls on (dimmed: nothing chosen)
  const endDay = $derived(endTs != null ? endTs : Number.isFinite(startTs) ? startTs : null);
  const endDayText = $derived(endDay != null ? `${weekdayShort(endDay)}, ${dayMonthShort(endDay)}` : '—');
  const whoVal = $derived(f.leaders ? t('ed.whoLeaders') : f.teamOnly ? t('ed.whoTeam') : t('ed.whoAll'));
  const LEAD = { president: 'ed.leadPres', vice: 'ed.leadVice', head: 'ed.leadHead' } as const;
  const memoN = $derived(Object.keys(f.memo).length);
  const priceBad = $derived(!!(err.price || err.payTo || err.payPhone || err.freeFirst));

  // the pull-downs (2-4 choices) on a row's value
  function whoMenu(el: Element) {
    menu(el, [
      { label: t('ed.whoAll'), checked: !f.teamOnly && !f.leaders, onselect: () => { f.teamOnly = false; f.leaders = false; } },
      { label: t('ed.whoTeam'), checked: f.teamOnly, onselect: () => { f.teamOnly = true; f.leaders = false; } },
      ...(oversee ? [{ label: t('ed.whoLeaders'), checked: f.leaders, onselect: () => { f.leaders = true; f.teamOnly = false; } }] : []),
    ], 'end');
  }
  const leadMenu = (el: Element) => menu(el, (['president', 'vice', 'head'] as const).map((k) => ({ label: t(LEAD[k]), checked: f.leadersFrom === k, onselect: () => { f.leadersFrom = k; } })), 'end');
  const tagMenu = (el: Element) => menu(el, [
    ...(deptOnly ? [] : [{ label: t('ed.meetingAll'), checked: f.meetingTag == null, onselect: () => { f.meetingTag = null; } }]),
    ...tags.filter((g) => !deptOnly || g.id === ownDept).map((g) => ({ label: g.name, checked: f.meetingTag === g.id, onselect: () => { f.meetingTag = g.id; } })),
  ], 'end');
  const valueOf = (e: MouseEvent) => (e.currentTarget as Element).querySelector('.v') ?? (e.currentTarget as Element);

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

{#snippet row(Icon: typeof Ticket, title: string, value: string, onclick: (e: MouseEvent) => void, bad = false, updown = false)}
  <button class="r" class:bad {onclick}><Icon size={19} /><b>{title}</b><span class="v">{bad ? t('ed.need') : value}</span>
    {#if updown}<ChevronsUpDown size={16} />{:else}<ChevronRight size={18} />{/if}</button>
{/snippet}
{#snippet toggle(Icon: typeof Ticket, title: string, get: () => boolean, set: (v: boolean) => void)}
  <label class="r"><Icon size={19} /><b>{title}</b><span class="sw-on"><input type="checkbox" role="switch" checked={get()} onchange={(e) => set(e.currentTarget.checked)} /></span></label>
{/snippet}

<div class="panel" bind:this={panel} style:--tint={shade(f.color)} oninputcapture={touch} onchangecapture={touch} onclickcapture={touch}>
  <!-- the sheet tinted by the event (Luma): its colour, the cover blurred over it, the page's ground on top for contrast -->
  <div class="wash" aria-hidden="true">{#if f.cover}<img src={f.cover.thumb} alt="" />{/if}<i></i></div>
  <header class="bar">
    {#if !inTelegram}<button class="x" onclick={() => close(overlay.id)} aria-label={t('common.close')}><X size={22} /></button>{/if}
  </header>

  <div class="body scroll">
    <button class="art" class:busy={uploading} onclick={() => open('cover')} aria-label={t('ed.cover')}>
      <Poster item={{ cover: f.cover, emoji: f.emoji, color: f.color }} size={196} radius={24} />
      <span class="artbtn glass glass-pill"><ImagePlus size={20} /></span>
    </button>
    {#if !id && session.board}
      <button class="fill" class:busy={filling} disabled={filling} onclick={fillFromText}><Sparkles size={16} />{filling ? t('as.thinking') + '…' : t('ed.fill')}</button>
    {/if}

    <textarea class="name" class:bad={tried && err.title} rows="1" bind:value={f.title} maxlength="80" placeholder={t('ex.name')} enterkeyhint="done"></textarea>
    {#if tried && err.title}<p class="err">{err.title}</p>{/if}
    {#if castLike}
      <!-- a casting made as an event (JCC, Nov 3): the club's recruitment does it properly -->
      <div class="cast"><p>{t('ed.castHint')}</p><button onclick={() => { close(overlay.id); sheets.roundSetup(org); }}>{t('ed.castOpen')}</button></div>
    {/if}

    <div class="pill when" class:bad={tried && err.when}>
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

    <button class="pill go" class:bad={tried && err.place} onclick={() => open('place')}><MapPin size={20} />
      <span class="ellipsis" class:ph={!f.place.trim()}>{f.tba ? t('ed.tba') : f.place.trim() || t('ex.placeAdd')}</span>
      {#if f.placeUrl && !f.tba}<span class="chip">{t('event.route')}</span>{/if}</button>
    <button class="pill go" onclick={() => open('about')}><AlignLeft size={20} />
      <span class="clamp-2" class:ph={!f.description.trim()}>{f.description.trim() || t('ex.aboutAdd')}</span></button>

    {#if tickets}
      <h3 class="cap">{t('ex.tickets')}</h3>
      <div class="pill grp">
        {#if canPrice}{@render row(Ticket, t('ex.price'), priceVal, () => open('price'), tried && priceBad)}
        {:else}<div class="r still"><Ticket size={19} /><b>{t('ex.price')}</b><span class="v">{t('ex.free')}</span></div>{/if}
        {@render row(Users, t('ed.seats'), +f.seats > 0 ? f.seats : t('ex.unlimited'), () => open('seats'), tried && !!err.seats)}
        {@render row(Clock, t('ex.regUntil'), regVal, () => open('reg'), tried && !!err.reg)}
      </div>
      {#if !canPrice && !isMeeting}<p class="hint">{official ? t('ed.paidRight') : t('ed.paidOfficial')}</p>{/if}
    {/if}

    <h3 class="cap">{t('ex.options')}</h3>
    <div class="pill grp">
      {#if !f.partner}
        {#if oversee}{@render row(Globe, t('ex.who'), whoVal, (e) => whoMenu(valueOf(e)), false, true)}
        {:else}{@render toggle(Globe, t('ed.teamOnly'), () => f.teamOnly, (v) => (f.teamOnly = v))}{/if}
        {#if f.leaders}{@render row(Crown, t('ex.leadersFrom'), t(LEAD[f.leadersFrom]), (e) => leadMenu(valueOf(e)), false, true)}{/if}
        {#if f.teamOnly}{@render toggle(CalendarCheck, t('ed.meeting'), () => f.meeting, (v) => (f.meeting = v))}{/if}
        {#if isMeeting && tags.length}
          {@render row(Tag, t('ed.meetingWho'), tags.find((g) => g.id === f.meetingTag)?.name ?? t('ed.meetingAll'), (e) => tagMenu(valueOf(e)), false, true)}
        {/if}
      {/if}
      {#if tickets}
        {@render toggle(GraduationCap, t('ed.firstYear'), () => f.firstYear, (v) => (f.firstYear = v))}
        {@render toggle(Phone, t('ed.needsPhone'), () => f.needsPhone, (v) => (f.needsPhone = v))}
      {/if}
      {@render toggle(Images, t('ed.albumOpen'), () => f.albumOpen, (v) => (f.albumOpen = v))}
    </div>
    {#if f.leaders}<p class="hint">{t('ed.leadersHint')}</p>{/if}
    {#if !official && !f.teamOnly && !f.leaders}<p class="hint">{t('ed.noChannel')}</p>{/if}

    <h3 class="cap">{t('ex.more')}</h3>
    <div class="pill grp">
      {@render row(Clapperboard, t('ed.video'), [vids.tall, vids.wide].filter(Boolean).length ? String([vids.tall, vids.wide].filter(Boolean).length) : t('ex.no'), () => open('video'))}
      {#if session.board && tickets}{@render row(ListChecks, t('ed.form'), f.form.length ? String(f.form.length) : t('ex.no'), () => open('form'), tried && !!err.form)}{/if}
      {#if tickets}{@render row(HandHeart, t('ed.vol'), f.vol ? f.volN : t('ex.no'), () => open('vol'))}{/if}
      {#if canPartner && !isMeeting}{@render row(Handshake, t('ed.partner'), f.partner ? f.host.trim() || t('ed.need') : t('ex.no'), () => open('partner'), tried && !!(err.host || err.link))}{/if}
      {#if !f.placeUrl && !f.leaders}{@render row(Mail, t('studio.memoShort'), memoN ? String(memoN) : t('ex.no'), () => open('memo'))}{/if}
      {@render row(Eye, t('ed.preview'), '', showPreview)}
    </div>

    <!-- the form's end, as Luma's Create (owner, Nov 2: no floating bar over the form) -->
    <div class="foot">
      {#if live}
        <Button kind="filled" size="l" full loading={busy === 'save'} disabled={!dirty} onclick={publish}>{t('common.save')}</Button>
      {:else}
        <Button kind="filled" size="l" full loading={busy === 'publish'} onclick={publish}>{t('ed.publish')}</Button>
        <button class="draft" disabled={!!busy} onclick={() => submit('draft')}>{busy === 'draft' ? '…' : t('ed.saveDraft')}</button>
      {/if}
    </div>
    {#if saved?.status === 'draft'}
      <button class="del" onclick={remove}><Trash size={18} />{t('ed.delete')}</button>
    {/if}
    <div class="tail"></div>
  </div>

  <!-- the focused panel: one thing at a time; Telegram's Back, the scrim or Done closes it -->
  {#if pick}
    <button class="scrim" onclick={() => (pick = '')} aria-label={t('common.close')}></button>
    <div class="pk glass glass-sheet">
      <header class="pkh"><b>{t(PANEL[pick] as 'ed.cover')}</b>
        {#if pick !== 'check'}<Button kind="tinted" size="s" onclick={() => (pick = '')}>{t('ex.done')}</Button>{/if}</header>
      <div class="pkb scroll">
        {#if pick === 'cover'}
          <div class="photo">
            <label class="pbtn" class:busy={uploading}><ImagePlus size={18} />{uploading ? t('ed.photoUp') : f.cover ? t('ed.photoChange') : t('ed.photo')}
              <input type="file" accept="image/*" onchange={pickPhoto} disabled={uploading} /></label>
            {#if f.cover}<button class="pdel" onclick={dropPhoto}><X size={16} />{t('ed.photoRemove')}</button>{/if}
          </div>
          {#if f.cover}
            <CoverFocus cover={f.cover} onpick={(p) => { f.cover = { ...f.cover!, focus: p }; void readColor(false); }} />
            <div class="slides">
              {#each f.slides as p, k (p.id)}
                <span class="sl"><img src={p.thumb} alt="" /><button onclick={() => (f.slides = f.slides.filter((_, n) => n !== k))} aria-label={t('ed.photoRemove')}><X size={14} strokeWidth={2.6} /></button></span>
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
            <label class="field" class:bad={tried && err.place}><span class="t-cap">{t('ed.place')}</span>
              <input bind:value={f.place} oninput={placeTyped} maxlength="400" placeholder={f.placeUrl ? t('ed.placeName') : example.place} enterkeyhint="done" /></label>
          {/if}
          {#if !f.placeUrl && !f.tba && addressGis(f.place)}
            <!-- a typed street address: its 2GIS route offered, seen before saving -->
            <button class="gisoffer" onclick={() => { f.placeUrl = addressGis(f.place)!; haptic.ok(); say(phrase('say.gisLink'), 'globe_with_meridians_3d'); }}>
              <MapPin size={16} />{t('ed.gisOffer')}</button>
          {/if}
          {#if f.placeUrl && !f.tba}
            <div class="gis"><MapPin size={17} /><span class="ellipsis">{t('event.route')}</span>
              <button onclick={() => (f.placeUrl = '')} aria-label={t('ed.photoRemove')}><X size={16} /></button></div>
          {:else if !f.tba}
            <p class="hint">{t('ed.placeHint')}</p>
          {/if}
          {#if !f.placeUrl}
            <label class="switch"><span><b>{t('ed.tba')}</b><i class="t-foot">{t('ed.tbaHint')}</i></span><input type="checkbox" role="switch" bind:checked={f.tba} /></label>
          {/if}

        {:else if pick === 'about'}
          <label class="field"><textarea bind:value={f.description} maxlength="2000" rows="7" placeholder={t('ed.aboutPh')}></textarea></label>
          {#if !isMeeting && !f.teamOnly && !f.leaders}<p class="hint">{t('ce.aboutHint')}</p>{/if}<!-- only public events go to the AI (PLAN 9) -->
          {#if session.board}
            {#if suggestion}
              <div class="sug">
                <span class="t-cap"><Sparkles size={13} /> {t('ex.aiSuggest')}</span>
                <p>{suggestion}</p>
                <div class="sugb"><Button kind="gray" size="s" onclick={() => (suggestion = '')}>{t('ex.aiKeep')}</Button>
                  <Button kind="tinted" size="s" onclick={() => { touch(); f.description = suggestion; suggestion = ''; haptic.ok(); }}>{t('ex.aiUse')}</Button></div>
              </div>
            {:else}
              <button class="ai" disabled={writing} class:busy={writing} onclick={aiWrite}><Sparkles size={16} />{writing ? t('as.thinking') + '…' : t('ex.aiWrite')}</button>
              {#if !f.description.trim()}<p class="hint">{t('ex.aiHint')}</p>{/if}
            {/if}
          {/if}

        {:else if pick === 'price'}
          <!-- Free or Paid as a choice in sight, never a switch further down -->
          <Segmented items={[{ value: 'free', label: t('ex.free') }, { value: 'paid', label: t('ex.paidSeg') }]} value={f.paid ? 'paid' : 'free'} label={t('ex.price')}
            onchange={(v) => { touch(); f.paid = v === 'paid'; }} />
          {#if f.paid}
            <label class="field" class:bad={tried && err.price}><span class="t-cap">{t('ed.price')}</span>
              <input bind:value={f.price} type="number" inputmode="numeric" min="1" placeholder="2000" /></label>
            <label class="field" class:bad={tried && err.payTo}><span class="t-cap">{t('ed.payTo')}</span>
              <input bind:value={f.payTo} maxlength="80" placeholder={t('ed.payToPh')} /></label>
            <label class="field" class:bad={tried && err.payPhone}><span class="t-cap">{t('ed.payPhone')}</span>
              <input bind:value={f.payPhone} oninput={() => (f.payPhone = fmtPhone(f.payPhone))} type="tel" inputmode="tel" autocomplete="tel" placeholder="+7 (707) 123 45 67" /></label>
            {#if tried && err.payPhone}<p class="err">{err.payPhone}</p>{/if}
            <p class="hint">{t('ed.payHint')}</p>
            <label class="field" class:bad={tried && err.freeFirst}><span class="t-cap">{t('ed.freeFirst')}</span>
              <input bind:value={f.freeFirst} type="number" inputmode="numeric" min="0" placeholder={t('ed.freeFirstPh')} /></label>
            <p class="hint">{t('ed.freeFirstHint')}</p>
          {:else}<p class="hint">{t('ed.paidHint')}</p>{/if}

        {:else if pick === 'seats'}
          <label class="field" class:bad={tried && err.seats}><span class="t-cap">{t('ed.seats')}</span>
            <input bind:value={f.seats} type="number" inputmode="numeric" min="1" placeholder={t('ed.seatsPh')} /></label>

        {:else if pick === 'reg'}
          <label class="switch"><span><b>{t('ed.deadline')}</b><i class="t-foot">{t('ed.deadlineHint')}</i></span>
            <input type="checkbox" role="switch" bind:checked={f.deadline} onchange={deadlineOn} /></label>
          {#if f.deadline}
            <div class="two">
              <label class="field" class:bad={tried && err.reg}><span class="t-cap">{t('ed.regDate')}</span><input type="date" bind:value={f.regDate} /></label>
              <label class="field" class:bad={tried && err.reg}><span class="t-cap">{t('ed.regTime')}</span><input type="time" bind:value={f.regTime} /></label>
            </div>
            {#if tried && err.reg}<p class="err">{err.reg}</p>{/if}
          {/if}

        {:else if pick === 'video'}
          <!-- two real tiles shaped like their videos -->
          <div class="vslots">
            {#each ['tall', 'wide'] as const as slot (slot)}
              {@const x = vids[slot]}
              <div class="vslot {slot}">
                {#if x}
                  <span class="vframe">{#if x.poster}<img src={x.poster.thumb} alt="" />{:else}<Clapperboard size={22} />{/if}
                    <button class="vx" onclick={() => dropVideo(slot)} aria-label={t('ed.photoRemove')}><X size={16} strokeWidth={2.6} /></button></span>
                  <b>{x.status === 'ready' ? t('ed.videoReady') : t('ed.videoWork')}{#if x.duration} · {mmss(x.duration)}{/if}</b>
                {:else}
                  <label class="vframe add" class:busy={vUp[slot] >= 0}><Clapperboard size={22} />
                    {#if vUp[slot] >= 0}<i class="prog" style:width="{vUp[slot] * 100}%"></i>{/if}
                    <input type="file" accept="video/*" onchange={(ev) => pickVideo(ev, slot)} disabled={vUp[slot] >= 0} /></label>
                  <b>{vUp[slot] >= 0 ? t('ed.videoUp', { n: Math.round(vUp[slot] * 100) }) : t(slot === 'tall' ? 'ed.videoTall' : 'ed.videoWide')}</b>
                {/if}
                <i class="t-foot">{t(slot === 'tall' ? 'ed.videoHint' : 'ed.videoWideHint')}</i>
              </div>
            {/each}
          </div>

        {:else if pick === 'form'}
          <!-- the event's own questions at sign-up (Oct 30): up to five, text or a choice; with the forum's policy section -->
          {#each f.form as q, i (i)}
            <div class="qc">
              <div class="qrow"><input class="ql" bind:value={q.label} maxlength="80" placeholder={t('ed.formQ')} />
                <button class="qx" onclick={() => (f.form = f.form.filter((_, k) => k !== i))} aria-label={t('ed.photoRemove')}><X size={16} /></button></div>
              <div class="mtags"><button class:on={q.kind === 'text'} onclick={() => (q.kind = 'text')}>{t('ed.formText')}</button>
                <button class:on={q.kind === 'choice'} onclick={() => (q.kind = 'choice')}>{t('ed.formChoice')}</button></div>
              {#if q.kind === 'choice'}<input class="ql" bind:value={q.opts} maxlength="300" placeholder={t('ed.formOpts')} />{/if}
              <label class="chk"><input type="checkbox" bind:checked={q.required} />{t('ed.formReq')}</label>
            </div>
          {/each}
          {#if tried && err.form}<p class="err">{err.form}</p>{/if}
          {#if f.form.length < 5}<button class="qadd" onclick={() => (f.form = [...f.form, { label: '', kind: 'text', opts: '', required: false }])}>+ {t('ed.formAdd')}</button>{/if}
          <p class="hint">{t('ed.formHint')}</p>

        {:else if pick === 'vol'}
          <!-- volunteers: students apply, the organizers say yes or no in the event's management -->
          <label class="switch"><span><b>{t('ed.vol')}</b><i class="t-foot">{t('ed.volHint')}</i></span><input type="checkbox" role="switch" bind:checked={f.vol} /></label>
          {#if f.vol}
            <label class="field"><span class="t-cap">{t('ed.volN')}</span><input bind:value={f.volN} type="number" inputmode="numeric" min="1" max="500" /></label>
            <label class="chk"><input type="checkbox" bind:checked={f.volSenior} />{t('ed.volSenior')}</label>
          {/if}

        {:else if pick === 'partner'}
          <label class="switch"><span><b>{t('ed.partner')}</b><i class="t-foot">{t('ed.partnerHint')}</i></span><input type="checkbox" role="switch" bind:checked={f.partner} /></label>
          {#if f.partner}
            <label class="field" class:bad={tried && err.host}><span class="t-cap">{t('ed.partnerHost')}</span>
              <input bind:value={f.host} maxlength="60" placeholder={t('ed.partnerHostPh')} /></label>
            {#if tried && err.host}<p class="err">{err.host}</p>{/if}
            <label class="field" class:bad={tried && err.link}><span class="t-cap">{t('ed.partnerLink')}</span>
              <input bind:value={f.link} type="url" inputmode="url" maxlength="500" placeholder="https://" /></label>
            {#if tried && err.link}<p class="err">{err.link}</p>{/if}
          {/if}

        {:else if pick === 'memo'}
          <MemoAsksForm bind:memo={f.memo} seats={f.seats} date={f.date} flat />

        {:else if pick === 'check'}
          {#if found.length}
            <p class="sum">{tn('ex.found', found.length)}</p>
            {#each found as x (x.id)}
              <div class="note" class:serious={SERIOUS.has(x.id)}>
                <span class="ni">{#if SERIOUS.has(x.id)}<TriangleAlert size={17} />{:else}<Sparkles size={16} />{/if}</span>
                <span class="nt">{noteText(x)}</span>
                {#if fixable(x)}<button class="nfix" onclick={() => fix(x)}>{fixLabel(x)}</button>{/if}
              </div>
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
    --pill: var(--surface-2); }
  :global(:root[data-theme='light']) .panel { --pill: rgba(255, 255, 255, 0.62); }
  .wash { position: absolute; inset: 0; background: var(--tint); overflow: hidden; pointer-events: none; }
  .wash img { position: absolute; inset: -20%; width: 140%; height: 140%; object-fit: cover; filter: blur(48px) saturate(1.3); }
  .wash i { position: absolute; inset: 0; background: var(--bg); opacity: 0.5; }
  :global(:root[data-theme='light']) .wash i { opacity: 0.72; }
  .bar { position: absolute; left: 0; right: 0; top: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2)); height: 38px; z-index: 1;
    display: flex; align-items: center; justify-content: center; pointer-events: none; }
  .x { position: absolute; left: 12px; width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--surface); color: var(--text); pointer-events: auto; }

  .body { position: relative; flex: 1; min-height: 0; display: flex; flex-direction: column; gap: var(--s-3); margin-top: max(48px, var(--top)); padding: var(--s-2) var(--gutter) 0; }
  .body > :global(*) { flex-shrink: 0; } /* a scrolling column must not squeeze its rows */
  .tail { height: calc(var(--safe-bottom) + 24px); }
  .ph { color: var(--text-3); }
  .cast { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-2); margin: 0 var(--s-4); padding: var(--s-3) var(--s-4);
    border-radius: var(--r-m); background: var(--accent-soft); font: 500 var(--fs-sub)/1.35 var(--font-text); color: var(--text); }
  .cast button { font: 650 var(--fs-sub)/1.2 var(--font-text); color: var(--accent-text); }
  .err { margin: -6px var(--s-4) 0; font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--danger-text); }
  .hint { margin: 0 var(--s-1); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
  .bad { box-shadow: inset 0 0 0 1.5px var(--danger); }

  .art { position: relative; align-self: center; margin: var(--s-1) 0 var(--s-2); border-radius: var(--r-xl); box-shadow: var(--shadow-card); }
  .art:active { transform: scale(0.98); }
  .art.busy { opacity: 0.6; }
  .artbtn { position: absolute; right: -8px; bottom: -8px; width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; color: var(--text); }
  .fill, .ai { align-self: center; display: inline-flex; align-items: center; gap: 6px; height: var(--btn-s); padding: 0 var(--s-3); margin-top: calc(-1 * var(--s-1));
    border-radius: var(--r-full); background: var(--pill); color: var(--text); font: 650 var(--fs-sub)/1 var(--font-text); }
  .ai { align-self: flex-start; margin: 0; background: var(--accent-soft); color: var(--accent-text); }
  .fill.busy, .ai.busy { opacity: 0.6; }
  .name { width: 100%; resize: none; field-sizing: content; min-height: 1.2em; padding: var(--s-3) var(--s-4); border-radius: var(--r-l); background: var(--pill);
    color: var(--text); font: 700 var(--fs-t1)/1.18 var(--font-display); letter-spacing: -0.02em; }
  .name::placeholder { color: var(--text-3); }

  .pill { position: relative; display: flex; align-items: center; gap: var(--s-3); width: 100%; min-height: 54px; padding: 0 var(--s-4);
    border-radius: var(--r-l); background: var(--pill); color: var(--text); text-align: left; font: 500 var(--fs-row)/1.3 var(--font-text); }
  .pill > :global(svg) { flex: none; color: var(--text-2); }
  .go { padding-block: var(--s-3); }
  .go > span:not(.chip) { flex: 1; min-width: 0; }
  .chip { flex: none; padding: 4px 8px; border-radius: var(--r-full); background: var(--success-soft); color: var(--success-text); font: 600 var(--fs-cap)/1 var(--font-text); }
  .go:active, .r:active { opacity: 0.7; transform: none; }
  .when { flex-direction: column; align-items: stretch; gap: 0; padding: 0; }
  .wr { position: relative; display: flex; align-items: center; gap: var(--s-2); min-height: 54px; padding: 0 var(--s-3) 0 44px; }
  .wr + .wr::before { content: ''; position: absolute; left: 44px; right: 0; top: 0; height: 0.5px; background: var(--separator); }
  .wr b { flex: 1; min-width: 0; font-weight: 500; color: var(--text-2); }
  .tv { position: relative; flex: none; padding: 7px 8px; border-radius: var(--r-xs); background: var(--fill); color: var(--text); font: 600 var(--fs-body)/1 var(--font-text); white-space: nowrap; }
  .tv input { position: absolute; inset: 0; width: 100%; opacity: 0; }
  .tv.ph { color: var(--text-3); } /* nothing chosen: the end's day as it follows from the start */
  .dot { position: absolute; left: 20px; width: 9px; height: 9px; border-radius: 50%; background: var(--text-2); }
  .dot.o { background: none; box-shadow: inset 0 0 0 1.5px var(--text-2); }
  .line { position: absolute; left: 24px; top: 33px; bottom: 33px; border-left: 1.5px dotted var(--text-3); }
  .cap { margin: var(--s-3) var(--s-1) calc(-1 * var(--s-1)); font: 650 var(--fs-body)/1.2 var(--font-text); color: var(--text-2); }
  .grp { flex-direction: column; align-items: stretch; gap: 0; padding: 0; }
  .r { position: relative; display: flex; align-items: center; gap: var(--s-3); min-height: 54px; padding: 0 var(--s-4); text-align: left; color: var(--text); }
  .r + .r::before { content: ''; position: absolute; left: 47px; right: 0; top: 0; height: 0.5px; background: var(--separator); }
  .r > :global(svg) { flex: none; color: var(--text-2); }
  .r b { flex: 1 1 auto; min-width: 0; font-weight: 500; }
  .r .v { flex: none; max-width: 50%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-2); font-weight: 500; }
  .r.bad { box-shadow: none; }
  .r.bad .v { color: var(--danger-text); }
  .r > :global(svg:last-child) { color: var(--text-3); }
  .r.still { cursor: default; }
  .del { display: flex; align-items: center; justify-content: center; gap: 8px; height: 46px; margin-top: var(--s-1); color: var(--danger-text); font: 620 var(--fs-body)/1 var(--font-text); }

  .foot { display: flex; flex-direction: column; align-items: stretch; gap: var(--s-1); margin-top: var(--s-5); }
  .draft { height: 46px; color: var(--accent-text, var(--accent)); font: 600 var(--fs-body)/1 var(--font-text); }
  .draft:active { opacity: 0.6; }

  /* the panel */
  .scrim { position: absolute; inset: 0; background: var(--scrim); animation: fade 220ms var(--ease) backwards; }
  @keyframes fade { from { opacity: 0; } }
  .pk { position: absolute; left: 8px; right: 8px; bottom: calc(var(--safe-bottom) + 8px); max-height: calc(100% - var(--top) - 24px); display: flex; flex-direction: column;
    border-radius: var(--r-xl); animation: rise 380ms var(--ease-spring) backwards; }
  @keyframes rise { from { transform: translate3d(0, 100%, 0); } }
  .pkh { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); padding: var(--s-4) var(--s-4) var(--s-2) var(--s-5); }
  .pkh b { font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.015em; }
  .pkb { display: flex; flex-direction: column; gap: var(--s-3); padding: var(--s-2) var(--s-4) var(--s-4); }
  .pkb > :global(*) { flex-shrink: 0; }
  .two { display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-2); }
  .sum { margin: 0 var(--s-1); font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  .okay { display: flex; align-items: center; gap: var(--s-2); padding: var(--s-3) var(--s-1); font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--success-text); }
  .pkfoot { display: flex; margin-top: var(--s-1); }

  /* the check's notes, the AI's card */
  .note { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s-2) var(--s-3); padding: var(--s-3) var(--s-3) var(--s-3) var(--s-4); border-radius: var(--r-m);
    background: var(--surface-2); animation: note-in 300ms var(--ease-spring) backwards; }
  @keyframes note-in { from { opacity: 0; transform: translateY(-4px); } }
  .note.serious { background: var(--warning-soft); }
  .ni { flex: none; display: inline-flex; color: var(--text-3); }
  .serious .ni { color: var(--warning-text); }
  .nt { flex: 1 1 160px; min-width: 0; font: 550 var(--fs-body)/1.35 var(--font-text); color: var(--text); }
  .nfix { flex: none; margin-left: auto; height: var(--btn-s); padding: 0 var(--s-3); border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 650 var(--fs-sub)/1 var(--font-text); white-space: nowrap; }
  .serious .nfix { background: var(--accent); color: var(--on-accent); }
  .sug { display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-3) var(--s-4); border-radius: var(--r-m); background: var(--accent-soft);
    animation: note-in 300ms var(--ease-spring) backwards; }
  .sug .t-cap { display: inline-flex; align-items: center; gap: 4px; color: var(--accent-text); }
  .sug p { font: 450 var(--fs-body)/1.45 var(--font-text); color: var(--text); white-space: pre-line; }
  .sugb { display: flex; gap: var(--s-2); justify-content: flex-end; }

  /* the panels' own pieces (the old form's, kept) */
  .chk { display: flex; align-items: center; gap: 10px; padding: 6px 4px 12px; font: 550 var(--fs-body)/1.3 var(--font-text); }
  .chk input { width: 20px; height: 20px; accent-color: var(--accent); }
  .gisoffer { align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px;
    border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 620 var(--fs-sub)/1 var(--font-text); }
  .gis { display: flex; align-items: center; gap: 8px; height: 44px; padding: 0 6px 0 14px; border-radius: var(--r-m);
    background: var(--success-soft); color: var(--success-text); font: 630 var(--fs-body)/1 var(--font-text); }
  .gis span { flex: 1; min-width: 0; }
  .gis button { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: inherit; }
  .qc { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px 2px; border-radius: var(--r-m); background: var(--surface-2); animation: note-in 260ms var(--ease-spring) backwards; }
  .qrow { display: flex; align-items: center; gap: 6px; }
  .ql { flex: 1; min-width: 0; height: 40px; padding: 0 12px; border-radius: var(--r-s); background: var(--fill); color: var(--text); font: 500 var(--fs-body)/1 var(--font-text); }
  .qx { flex: none; width: 34px; height: 34px; display: grid; place-items: center; border-radius: 50%; color: var(--text-3); }
  .qadd { align-self: flex-start; height: 36px; padding: 0 14px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 650 var(--fs-body)/1 var(--font-text); }
  .mtags { display: flex; flex-wrap: wrap; gap: 6px; }
  .mtags button { display: flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px; border-radius: var(--r-full); background: var(--fill);
    font: 600 var(--fs-body)/1 var(--font-text); color: var(--text-2); }
  .mtags button.on { background: var(--text); color: var(--bg); }
  .photo { display: flex; gap: 8px; }
  .pbtn, .pdel { display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 44px; padding: 0 16px; border-radius: var(--r-m);
    font: 630 var(--fs-body)/1 var(--font-text); transition: transform var(--t-fast) var(--ease); }
  .pbtn { flex: 1; background: var(--accent-soft); color: var(--accent-text); position: relative; overflow: hidden; }
  .pbtn input, .sl.add input, .vframe input { position: absolute; inset: 0; opacity: 0; }
  .pbtn.busy { opacity: 0.6; }
  .pdel { background: var(--fill); color: var(--text-2); }
  .pbtn:active, .pdel:active { transform: scale(0.97); }
  .slides { display: flex; flex-wrap: wrap; gap: 8px; }
  .sl { position: relative; width: 58px; height: 58px; border-radius: var(--r-s); overflow: hidden; background: var(--fill); flex: none; }
  .sl img { width: 100%; height: 100%; object-fit: cover; }
  .sl button { position: absolute; right: 3px; top: 3px; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: rgba(20, 22, 32, 0.6); color: var(--on-accent); }
  .sl.add { display: flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent-text); }
  .sl.wait { animation: sl-wait 1.1s ease-in-out infinite; }
  @keyframes sl-wait { 50% { opacity: 0.5; } }
  .tp { display: flex; align-items: center; justify-content: center; color: var(--on-accent); animation: dot 420ms cubic-bezier(.2, 1.4, .4, 1) backwards; }
  @keyframes dot { from { transform: scale(0.3); opacity: 0; } }
  .vslots { display: grid; grid-template-columns: 1fr 1.6fr; gap: 10px; align-items: end; }
  .vslot { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .vslot b { font: 630 var(--fs-sub)/1.2 var(--font-text); }
  .vslot .t-foot { font-style: normal; line-height: 1.3; }
  .vframe { position: relative; overflow: hidden; display: flex; align-items: center; justify-content: center; border-radius: var(--r-m);
    background: var(--accent-soft); color: var(--accent-text); transition: transform var(--t-fast) var(--ease); }
  .tall .vframe { aspect-ratio: 9 / 14; }
  .wide .vframe { aspect-ratio: 16 / 10; }
  .vframe.add:active { transform: scale(0.97); }
  .vframe.busy { opacity: 0.7; }
  .vframe img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .prog { position: absolute; left: 0; bottom: 0; height: 4px; background: var(--accent); transition: width 300ms linear; }
  .vx { position: absolute; right: 6px; top: 6px; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: rgba(20, 22, 32, 0.55); color: var(--on-accent); }
</style>
