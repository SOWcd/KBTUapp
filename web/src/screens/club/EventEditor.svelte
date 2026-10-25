<script lang="ts">
  // Studio: a new event or an edit, full screen: one form under a live preview, the phone's own date and time pickers.
  // New or draft: Publish / Save draft; published: Save (the server tells registered people when time or place moves).
  // Leaving with changes asks. Paid (§4.3, an official club's Vice+): the price and the Kaspi recipient, fixed once
  // someone has paid, and free seats for 1st-years. A registration deadline can close "Going" before the start.
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
  import { api, ApiErr, original, type EventFull, type EventInput, type Id, type Media, type MemoAsks, type Video } from '../../lib/api';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, studioChanged, phrase } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { nowTs, time, relDay, dateInput, fromInputs } from '../../lib/time';
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

  let { overlay, org, id }: { overlay: Overlay; org: Id; id?: Id } = $props();
  const oversee = $derived(!!data.orgs.find((o) => o.id === org)?.canOversee);
  const mine = $derived(session.me?.memberships.find((m) => m.org.id === org));
  const official = $derived(!!(data.orgs.find((o) => o.id === org) ?? mine?.org)?.official);
  const canPrice = $derived(official && may(mine, 'money'));
  // the recipient's name as Kaspi prints it ("Alikhan S."): mine, since whoever sets it up usually takes the money
  const myKaspiName = session.me?.student ? session.me.name : '';

  const EMOJI = PICK_EMOJI;
  // eleven around the colour wheel plus night; no RGB picker; BRAND when nothing is set
  const COLORS = ['#F2542D', '#FF8A3D', '#FFB23D', '#7CB518', '#2FBF71', '#14B8A6', '#18A9DB', '#3B6BFF', '#7C4DFF', '#AF52DE', '#FF4FA3', '#2A2340'];
  const BRAND = '#3B6BFF';
  // a 2GIS link inside a pasted place (2GIS → Share → Copy gives name, address and link)
  const GIS_LINK = /https:\/\/(?:[a-z]+\.)?2gis\.(?:kz|ru|com)\/\S*/i; // the server accepts the same hosts

  let saved = $state<EventFull | null>(null); // the server's copy when editing
  // a new event starts on a random emoji and colour: fewer look alike when nobody picks
  const any = <T,>(xs: T[]) => xs[Math.floor(Math.random() * xs.length)];
  const blank = { emoji: any(EMOJI), color: any(COLORS), cover: null as Media | null, slides: [] as Media[], videoId: null as Id | null, wideVideoId: null as Id | null, title: '', date: dateInput(nowTs() + 7 * 86400), start: '18:00',
    end: '', place: '', placeUrl: '', description: '', seats: '', firstYear: false, needsPhone: false, albumOpen: true, vol: false, volN: '5', volSenior: false, teamOnly: false, leaders: false, leadersFrom: 'president' as 'president' | 'vice' | 'head',
    meeting: false, meetingTag: null as Id | null,
    paid: false, price: '', payTo: myKaspiName, payPhone: '', freeFirst: '', deadline: false, regDate: '', regTime: '18:00',
    tba: false, memo: { room: { any: true, projector: false, capacity: null } } as MemoAsks };
  let f = $state({ ...blank });
  let base = $state(JSON.stringify(blank)); // the form with nothing to lose
  // the base is the form at my first touch (capture: before the change lands), not the blank: iOS rewrites a date or
  // time input as it renders, so an untouched form already differs from its blank
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
  // one end time: earlier than the start means the next day (a night hackathon)
  // ponytail: events longer than 24 h can't be expressed; add an end date if a club needs one
  const endTs = $derived.by(() => {
    const e = fromInputs(f.date, f.end);
    if (!Number.isFinite(e) || !Number.isFinite(startTs)) return null;
    return e > startTs ? e : e + 86400;
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
    when: !Number.isFinite(startTs) ? t('ed.need') : !live && startTs <= nowTs() ? t('ed.past') : '',
    place: f.tba || f.place.trim() ? '' : t('ed.need'),
    seats: f.seats === '' || (Number.isInteger(+f.seats) && +f.seats > 0) ? '' : t('ed.need'),
    price: !f.paid || (Number.isInteger(+f.price) && +f.price >= 1 && +f.price <= 1_000_000) ? '' : t('ed.need'),
    payTo: !f.paid || f.payTo.trim().length >= 2 ? '' : t('ed.need'),
    payPhone: !f.paid || /^(\+?7|8)?7\d{9}$/.test(f.payPhone.replace(/[\s()-]/g, '')) ? '' : t('ed.phoneBad'),
    freeFirst: !f.paid || !f.freeFirst || (Number.isInteger(+f.freeFirst) && +f.freeFirst >= 0 && +f.freeFirst <= 5000) ? '' : t('ed.need'),
    reg: !f.deadline ? '' : !Number.isFinite(regTs) ? t('ed.need') : Number.isFinite(startTs) && regTs > startTs ? t('ed.regLate') : !live && regTs <= nowTs() ? t('ed.past') : '',
  });

  // a room from DMP is asked in the weekly memo (the block at the end)

  // placeholders are a real title and place from the app's events (built-in ones until there are any), new each time
  const pick = (xs: string[]) => xs[Math.floor(Math.random() * xs.length)];
  const realTitles = data.events.map((e) => e.title).filter((x) => x.length <= 40);
  const realPlaces = [...new Set(data.events.filter((e) => !e.placeUrl && e.place.length <= 30).map((e) => e.place))];
  const example = { title: realTitles.length ? pick(realTitles) : phrase('ed.titlePh'), place: realPlaces.length ? pick(realPlaces) : phrase('ed.placePh') };

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
          end: e.endsAt ? time(e.endsAt) : '', place: e.place, placeUrl: e.placeUrl ?? '', description: e.description,
          seats: e.seats ? String(e.seats) : '', firstYear: e.firstYear, needsPhone: !!e.needsPhone, albumOpen: e.albumOpen ?? true, vol: !!e.volunteers, volN: String(e.volunteers?.need ?? 5), volSenior: !!e.volunteers?.senior, teamOnly: e.visibility === 'members', leaders: e.visibility === 'leaders', leadersFrom: e.leadersFrom ?? 'president',
          meeting: !!e.meeting, meetingTag: e.meetingTag ?? null,
          paid: !!e.price, price: e.price ? String(e.price) : '', payTo: e.payToName ?? myKaspiName, payPhone: fmtPhone(e.payPhone ?? ''), freeFirst: e.freeFirst ? String(e.freeFirst) : '',
          deadline: !!e.regUntil, regDate: e.regUntil ? dateInput(e.regUntil) : '', regTime: e.regUntil ? time(e.regUntil) : '18:00',
          tba: !e.place, memo: e.memo ?? {} };
        // a cover's tint used to be the photo's average colour: such an event starts on the photo's dot
        if (e.cover && (photoColor = await coverColor(e.cover)) && e.tint !== shade(f.color)) f.color = photoColor;
        base = JSON.stringify(f);
      }).catch(() => { say(t('common.error'), 'pleading_face_3d'); base = JSON.stringify(f); close(overlay.id); });
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
    firstYear: f.firstYear && !isMeeting, needsPhone: f.needsPhone && !isMeeting, albumOpen: f.albumOpen, volunteers: f.vol && !isMeeting && +f.volN > 0 ? Math.min(500, Math.round(+f.volN)) : null, volunteersSenior: f.volSenior, visibility: f.leaders ? 'leaders' : f.teamOnly ? 'members' : 'public', ...(f.leaders ? { leadersFrom: f.leadersFrom } : {}),
    meeting: isMeeting, meetingTag: isMeeting ? f.meetingTag : null,
    // only a changed photo or focus is sent: left out, the server keeps what the event has
    ...(f.cover?.id !== saved?.cover?.id || !f.cover !== !saved?.cover ? { coverId: f.cover?.id ?? null } : {}),
    ...(String(f.cover?.focus ?? '') !== String(saved?.cover?.focus ?? '') ? { coverFocus: f.cover?.focus ?? null } : {}),
    ...(f.videoId !== (saved?.video?.id ?? null) ? { videoId: f.videoId } : {}),
    ...(f.wideVideoId !== (saved?.wideVideo?.id ?? null) ? { wideVideoId: f.wideVideoId } : {}),
    ...(String(f.cover ? f.slides.map((x) => x.id) : []) !== String((saved?.slides ?? []).map((x) => x.id)) ? { slideIds: f.cover ? f.slides.map((x) => x.id!) : [] } : {}),
    // the price only from those who may set it: left out, the server keeps it
    ...(canPrice ? f.paid && !isMeeting ? { price: +f.price, payToName: f.payTo.trim(), payPhone: f.payPhone.trim(), freeFirst: +(f.freeFirst || 0) || null } : { price: null } : {}),
  });

  // the form as students will see it once published; what's still empty shows as a dash, never as an example
  function showPreview() {
    haptic.tap();
    const o = session.me?.memberships.find((m) => m.org.id === org)?.org ?? data.orgs.find((x) => x.id === org)!;
    const i = input();
    sheets.preview({
      ...i, volunteers: i.volunteers ? { need: i.volunteers, senior: !!i.volunteersSenior, taken: 0, mine: null } : null, id: saved?.id ?? 0, org: o, status: 'published', title: i.title || '—', place: i.place || '—',
      startsAt: Number.isFinite(startTs) ? startTs : nowTs() + 7 * 86400, seats: Number.isInteger(i.seats) && i.seats! > 0 ? i.seats : null,
      cover: f.cover, slides: f.cover ? f.slides : [], tint: shade(f.color), taken: saved?.taken ?? 0, freeLeft: i.freeFirst ?? null, externalUrl: saved?.externalUrl ?? null, price: i.price === undefined ? saved?.price ?? null : i.price,
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
      if (kind === 'publish') e = await api.publishEvent(e.id);
      const moved = live && e.taken > 0 && (saved!.startsAt !== e.startsAt || saved!.place !== e.place);
      base = JSON.stringify(f);
      studioChanged();
      haptic.ok();
      if (kind === 'publish') { burst(); say(phrase('say.published'), 'party_popper_3d'); }
      else say(kind === 'draft' ? phrase('say.draftSaved') : moved ? t('say.eventMoved') : phrase('say.eventSaved'), 'sparkles_3d');
      close(overlay.id);
    } catch (x) {
      haptic.error();
      say(x instanceof ApiErr && x.message === 'paid' ? t('ed.paidLocked') : x instanceof ApiErr && x.message === 'price' ? t('ed.paidOfficial')
        : x instanceof ApiErr && x.code === 'conflict' ? t('ed.badSeats') : t('common.error'), 'pleading_face_3d');
    } finally { busy = ''; }
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
    } catch { say(t('common.error'), 'pleading_face_3d'); } finally { busy = ''; }
  }
</script>

{#snippet tintPhoto()}<button class="tp" class:on={f.color === photoColor} style="--c:{photoColor}" onclick={() => (f.color = photoColor!)} aria-label={t('ed.tintPhoto')}><ImageIcon size={15} strokeWidth={2.4} /></button>{/snippet}

<div class="panel" bind:this={panel} oninputcapture={touch} onchangecapture={touch} onclickcapture={touch}>
  <header class="bar">
    {#if !inTelegram}<button class="x" onclick={() => close(overlay.id)} aria-label={t('common.close')}><X size={22} /></button>{/if}
  </header>

  <div class="body scroll">
    <button class="preview surface" onclick={showPreview} aria-label={t('ed.preview')}>
      <Poster item={{ cover: f.cover, emoji: f.emoji, color: f.color }} size={68} radius={16} />
      <span class="txt">
        <b class="t-title clamp-2" class:ph={!f.title.trim()}>{f.title.trim() || example.title}</b>
        <span class="t-foot">{Number.isFinite(startTs) ? relDay(startTs) + ', ' + f.start : ''}{f.place.trim() ? ' · ' + f.place.trim() : ''}</span>
      </span>
      <span class="eye"><Eye size={19} /></span>
    </button>

    <section class="cover">
      <h2 class="t-cap">{t('ed.cover')}</h2>
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
        <p class="hint tintnote">{t('ed.tint')}</p>
      {:else}
        <p class="hint">{t('ed.coverTip')}</p>
        <LookPick bind:emoji={f.emoji} bind:color={f.color} colors={COLORS} />
      {/if}
      {#if f.cover}
        <LookPick bind:color={f.color} colors={COLORS} lead={photoColor ? tintPhoto : undefined} />
      {/if}
    </section>

    <section class="cover">
      <h2 class="t-cap">{t('ed.video')}</h2>
      <!-- two real tiles shaped like their videos (the old button looked like a thin line) -->
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
                {#if vUp[slot] >= 0}<i class="bar" style:width="{vUp[slot] * 100}%"></i>{/if}
                <input type="file" accept="video/*" onchange={(ev) => pickVideo(ev, slot)} disabled={vUp[slot] >= 0} /></label>
              <b>{vUp[slot] >= 0 ? t('ed.videoUp', { n: Math.round(vUp[slot] * 100) }) : t(slot === 'tall' ? 'ed.videoTall' : 'ed.videoWide')}</b>
            {/if}
            <i class="t-foot">{t(slot === 'tall' ? 'ed.videoHint' : 'ed.videoWideHint')}</i>
          </div>
        {/each}
      </div>
    </section>

    <label class="field" class:bad={tried && err.title}><span class="t-cap">{t('ed.title')}</span>
      <input bind:value={f.title} maxlength="80" placeholder={example.title} enterkeyhint="next" /></label>
    {#if tried && err.title}<p class="err">{err.title}</p>{/if}

    <label class="field" class:bad={tried && err.when}><span class="t-cap">{t('ed.date')}</span><input type="date" bind:value={f.date} /></label>
    <div class="two">
      <label class="field" class:bad={tried && err.when}><span class="t-cap">{t('ed.start')}</span><input type="time" bind:value={f.start} /></label>
      <label class="field"><span class="t-cap">{t('ed.end')}</span><input type="time" bind:value={f.end} /></label>
    </div>
    {#if tried && err.when}<p class="err">{err.when}</p>{/if}

    {#if !f.tba}
    <label class="field" class:bad={tried && err.place}><span class="t-cap">{t('ed.place')}</span>
      <input bind:value={f.place} oninput={placeTyped} maxlength="400" placeholder={f.placeUrl ? t('ed.placeName') : example.place} enterkeyhint="next" /></label>
    {/if}
    {#if tried && err.place}<p class="err">{err.place}</p>{/if}
    {#if !f.placeUrl}
      <label class="switch">
        <span><b>{t('ed.tba')}</b><i class="t-foot">{t('ed.tbaHint')}</i></span>
        <input type="checkbox" role="switch" bind:checked={f.tba} />
      </label>
    {/if}
    {#if f.placeUrl && !f.tba}
      <!-- off campus: the route instead of a room -->
      <div class="gis"><MapPin size={17} /><span class="ellipsis">{t('event.route')}</span>
        <button onclick={() => (f.placeUrl = '')} aria-label={t('ed.photoRemove')}><X size={16} /></button></div>
    {:else if !f.tba}
      <p class="hint">{t('ed.placeHint')}</p>
    {/if}

    <label class="field"><span class="t-cap">{t('ed.about')}</span>
      <textarea bind:value={f.description} maxlength="2000" rows="4" placeholder={t('ed.aboutPh')}></textarea></label>
    {#if !isMeeting && !f.teamOnly && !f.leaders}<p class="hint">{t('ce.aboutHint')}</p>{/if}<!-- only public events go to the AI (PLAN 9) -->

    {#if !isMeeting}
    <label class="field" class:bad={tried && err.seats}><span class="t-cap">{t('ed.seats')}</span>
      <input bind:value={f.seats} type="number" inputmode="numeric" min="1" placeholder={t('ed.seatsPh')} /></label>

    <label class="switch">
      <span><b>{t('ed.deadline')}</b><i class="t-foot">{t('ed.deadlineHint')}</i></span>
      <input type="checkbox" role="switch" bind:checked={f.deadline} onchange={deadlineOn} />
    </label>
    {#if f.deadline}
      <div class="two">
        <label class="field" class:bad={tried && err.reg}><span class="t-cap">{t('ed.regDate')}</span><input type="date" bind:value={f.regDate} /></label>
        <label class="field" class:bad={tried && err.reg}><span class="t-cap">{t('ed.regTime')}</span><input type="time" bind:value={f.regTime} /></label>
      </div>
      {#if tried && err.reg}<p class="err">{err.reg}</p>{/if}
    {/if}

    {#if canPrice}
      <label class="switch">
        <span><b>{t('ed.paid')}</b><i class="t-foot">{t('ed.paidHint')}</i></span>
        <input type="checkbox" role="switch" bind:checked={f.paid} />
      </label>
      {#if f.paid}
        <label class="field" class:bad={tried && err.price}><span class="t-cap">{t('ed.price')}</span>
          <input bind:value={f.price} type="number" inputmode="numeric" min="1" placeholder="2000" /></label>
        <label class="field" class:bad={tried && err.payTo}><span class="t-cap">{t('ed.payTo')}</span>
          <input bind:value={f.payTo} maxlength="80" placeholder={t('ed.payToPh')} /></label>
        <label class="field" class:bad={tried && err.payPhone}><span class="t-cap">{t('ed.payPhone')}</span>
          <input bind:value={f.payPhone} oninput={() => (f.payPhone = fmtPhone(f.payPhone))} type="tel" inputmode="tel" autocomplete="tel" placeholder="+7 707 123 45 67" /></label>
        {#if tried && err.payPhone}<p class="err">{err.payPhone}</p>{/if}
        <p class="hint">{t('ed.payHint')}</p>
        <label class="field" class:bad={tried && err.freeFirst}><span class="t-cap">{t('ed.freeFirst')}</span>
          <input bind:value={f.freeFirst} type="number" inputmode="numeric" min="0" placeholder={t('ed.freeFirstPh')} /></label>
        <p class="hint">{t('ed.freeFirstHint')}</p>
      {/if}
    {:else if !official && may(mine, 'money')}
      <p class="hint">{t('ed.paidOfficial')}</p>
    {/if}

    <label class="switch">
      <span><b>{t('ed.firstYear')}</b><i class="t-foot">{t('ed.firstYearHint')}</i></span>
      <input type="checkbox" role="switch" bind:checked={f.firstYear} />
    </label>
    <!-- PLAN 71: the phone is asked at the sign-up, only where the event needs it -->
    <label class="switch">
      <span><b>{t('ed.needsPhone')}</b><i class="t-foot">{t('ed.needsPhoneHint')}</i></span>
      <input type="checkbox" role="switch" bind:checked={f.needsPhone} />
    </label>
    <label class="switch">
      <span><b>{t('ed.albumOpen')}</b><i class="t-foot">{t('ed.albumOpenHint')}</i></span>
      <input type="checkbox" role="switch" bind:checked={f.albumOpen} />
    </label>
    <!-- volunteers: students apply, the organizers say yes or no in the event's management -->
    <label class="switch">
      <span><b>{t('ed.vol')}</b><i class="t-foot">{t('ed.volHint')}</i></span>
      <input type="checkbox" role="switch" bind:checked={f.vol} />
    </label>
    {#if f.vol}
      <label class="field"><span class="t-cap">{t('ed.volN')}</span><input bind:value={f.volN} type="number" inputmode="numeric" min="1" max="500" /></label>
      <label class="chk"><input type="checkbox" bind:checked={f.volSenior} />{t('ed.volSenior')}</label>
    {/if}
    {/if}

    {#if oversee}
      <!-- DMP (§4.10): an event for everyone, its own team, or a meeting of every club's leaders -->
      <div class="who">
        <span class="t-cap">{t('ed.who')}</span>
        <div class="seg wide"><button class:on={!f.teamOnly && !f.leaders} onclick={() => { f.teamOnly = false; f.leaders = false; }}>{t('ed.whoAll')}</button>
          <button class:on={f.teamOnly} onclick={() => { f.teamOnly = true; f.leaders = false; }}>{t('ed.whoTeam')}</button>
          <button class:on={f.leaders} onclick={() => { f.leaders = true; f.teamOnly = false; }}>{t('ed.whoLeaders')}</button></div>
        {#if f.leaders}
          <div class="seg wide"><button class:on={f.leadersFrom === 'president'} onclick={() => (f.leadersFrom = 'president')}>{t('ed.leadPres')}</button>
            <button class:on={f.leadersFrom === 'vice'} onclick={() => (f.leadersFrom = 'vice')}>{t('ed.leadVice')}</button>
            <button class:on={f.leadersFrom === 'head'} onclick={() => (f.leadersFrom = 'head')}>{t('ed.leadHead')}</button></div>
          <p class="hint">{t('ed.leadersHint')}</p>
        {/if}
      </div>
    {:else}
      <label class="switch">
        <span><b>{t('ed.teamOnly')}</b><i class="t-foot">{t('ed.teamOnlyHint')}</i></span>
        <input type="checkbox" role="switch" bind:checked={f.teamOnly} />
      </label>
    {/if}
    {#if f.teamOnly}
      <label class="switch">
        <span><b>{t('ed.meeting')}</b><i class="t-foot">{t('ed.meetingHint')}</i></span>
        <input type="checkbox" role="switch" bind:checked={f.meeting} />
      </label>
      {#if isMeeting && tags.length}
        <div class="who">
          <span class="t-cap">{t('ed.meetingWho')}</span>
          <div class="mtags">{#if !deptOnly}<button class:on={f.meetingTag == null} onclick={() => (f.meetingTag = null)}>{t('ed.meetingAll')}</button>{/if}
            {#each tags.filter((g) => !deptOnly || g.id === ownDept) as g (g.id)}<button class:on={f.meetingTag === g.id} style="--c:{g.color}" onclick={() => (f.meetingTag = g.id)}><i></i>{g.name}</button>{/each}</div>
        </div>
      {/if}
    {/if}

    {#if !f.placeUrl && !f.leaders}<MemoAsksForm bind:memo={f.memo} seats={f.seats} date={f.date} />{/if}

    <Button kind="secondary" size="l" full onclick={showPreview}>{#snippet icon()}<Eye size={19} />{/snippet}{t('ed.preview')}</Button>

    {#if saved?.status === 'draft'}
      <button class="del" onclick={remove}><Trash size={18} />{t('ed.delete')}</button>
    {/if}
    <div class="tail"></div>
  </div>

  <footer class="foot glass glass-sheet">
    {#if live}
      <Button kind="primary" size="l" full loading={busy === 'save'} disabled={!dirty} onclick={() => submit('save')}>{t('common.save')}</Button>
    {:else}
      <Button kind="secondary" size="l" loading={busy === 'draft'} onclick={() => submit('draft')}>{t('ed.saveDraft')}</Button>
      <Button kind="primary" size="l" full loading={busy === 'publish'} onclick={() => submit('publish')}>{t('ed.publish')}</Button>
    {/if}
  </footer>
</div>

<style>
  .chk { display: flex; align-items: center; gap: 10px; padding: 6px 4px 12px; font: 550 15px/1.3 var(--font-text); }
  .chk input { width: 20px; height: 20px; accent-color: var(--accent); }
  .who { display: flex; flex-direction: column; gap: 8px; }
  .mtags { display: flex; flex-wrap: wrap; gap: 6px; }
  .mtags button { display: flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-2);
    font: 600 14px/1 var(--font-text); color: var(--text-2); }
  .mtags button.on { background: var(--text); color: var(--bg); }
  .mtags i { width: 9px; height: 9px; border-radius: 50%; background: var(--c); }
  .who .seg.wide { display: flex; }
  .who .seg.wide button { flex: 1; padding: 0 6px; }
  .panel { position: absolute; inset: 0; z-index: var(--z-sheet); display: flex; flex-direction: column; background: var(--glow), var(--bg); }
  .bar { position: absolute; left: 0; right: 0; top: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2)); height: 38px; z-index: 1;
    display: flex; align-items: center; justify-content: center; pointer-events: none; }
  .x { position: absolute; left: 12px; width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--surface); color: var(--text); pointer-events: auto; }

  .body { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 10px; margin-top: max(48px, var(--top)); padding: 6px var(--gutter) 0; }
  .body > :global(*) { flex-shrink: 0; } /* a scrolling column must not squeeze its rows */
  .preview { display: flex; gap: 12px; align-items: center; padding: 10px; margin-bottom: 6px; text-align: left; width: 100%; }
  .preview:active { transform: scale(0.98); }
  .preview .txt { flex: 1; display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .eye { flex: none; width: 36px; height: 36px; margin-right: 2px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--accent-soft); color: var(--accent-text); }
  .ph { color: var(--text-3); }

  .cover { display: flex; flex-direction: column; gap: 10px; margin-bottom: 4px; }
  .photo { display: flex; gap: 8px; }
  .pbtn, .pdel { display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 44px; padding: 0 16px; border-radius: var(--r-m);
    font: 630 14px/1 var(--font-text); transition: transform var(--t-fast) var(--ease); }
  .pbtn { flex: 1; background: var(--accent-soft); color: var(--accent-text); position: relative; overflow: hidden; }
  .pbtn input { position: absolute; inset: 0; opacity: 0; }
  .pbtn.busy { opacity: 0.6; }
  .pdel { background: var(--surface-2); color: var(--text-2); }
  .pbtn .bar { position: absolute; left: 0; bottom: 0; height: 3px; background: var(--accent); transition: width 300ms linear; }
  .vslots { display: grid; grid-template-columns: 1fr 1.6fr; gap: 10px; align-items: end; }
  .vslot { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .vslot b { font: 630 13.5px/1.2 var(--font-text); }
  .vslot .t-foot { font-style: normal; line-height: 1.3; }
  .vframe { position: relative; overflow: hidden; display: flex; align-items: center; justify-content: center; border-radius: 14px;
    background: var(--accent-soft); color: var(--accent-text); transition: transform var(--t-fast) var(--ease); }
  .tall .vframe { aspect-ratio: 9 / 14; }
  .wide .vframe { aspect-ratio: 16 / 10; }
  .vframe.add { box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--accent) 35%, transparent); }
  .vframe.add:active { transform: scale(0.97); }
  .vframe.busy { opacity: 0.7; }
  .vframe input { position: absolute; inset: 0; opacity: 0; }
  .vframe img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .vframe .bar { position: absolute; left: 0; bottom: 0; height: 4px; background: var(--accent); transition: width 300ms linear; }
  .vx { position: absolute; right: 6px; top: 6px; width: 28px; height: 28px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: rgba(20, 22, 32, 0.55); color: #fff; }
  .slides { display: flex; flex-wrap: wrap; gap: 8px; }
  .sl { position: relative; width: 58px; height: 58px; border-radius: 12px; overflow: hidden; background: var(--surface-2); flex: none; }
  .sl img { width: 100%; height: 100%; object-fit: cover; }
  .sl button { position: absolute; right: 3px; top: 3px; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: rgba(20, 22, 32, 0.6); color: #fff; }
  .sl.add { display: flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent-text); }
  .sl.add input { position: absolute; inset: 0; opacity: 0; }
  .sl.wait { animation: sl-wait 1.1s ease-in-out infinite; }
  @keyframes sl-wait { 50% { opacity: 0.5; } }
  .pbtn:active, .pdel:active { transform: scale(0.97); }
  .hint { margin: -4px 4px 0; font: 500 12.5px/1.35 var(--font-text); color: var(--text-3); }
  .tintnote { margin-top: 6px; }
  .gis { display: flex; align-items: center; gap: 8px; height: 44px; padding: 0 6px 0 14px; border-radius: var(--r-m);
    background: var(--success-soft); color: var(--success-text); font: 630 14px/1 var(--font-text); }
  .gis span { flex: 1; min-width: 0; }
  .gis button { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; color: inherit; }
  .cover h2 { margin: 4px 2px 0; }
  .tp { display: flex; align-items: center; justify-content: center; color: #fff; animation: dot 420ms cubic-bezier(.2, 1.4, .4, 1) backwards; }
  @keyframes dot { from { transform: scale(0.3); opacity: 0; } }

  .two { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
  .err { margin: -4px 4px 0; font: 600 12.5px/1.3 var(--font-text); color: var(--danger-text); }


  .del { display: flex; align-items: center; justify-content: center; gap: 8px; height: 46px; margin-top: 6px; color: var(--danger-text); font: 620 15px/1 var(--font-text); }
  .tail { flex: none; height: calc(var(--safe-bottom) + 96px); }

  .foot { position: absolute; left: 10px; right: 10px; bottom: calc(var(--safe-bottom) + 10px); display: flex; gap: 8px; padding: 8px; border-radius: 24px; }
  .foot :global(.btn.full) { flex: 1; width: auto; min-width: 0; }
</style>
