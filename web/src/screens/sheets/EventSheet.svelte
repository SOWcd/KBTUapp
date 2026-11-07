<script lang="ts">
  // Event sheet, tinted by the poster colour. The bottom bar holds the one primary action
  // (Going / price / ticket / waitlist) plus save and share. Cancelling lives on the ticket.
  // The organizing team also gets its tools here: scanner (Member+), attendees, edit, cancel (Head+).
  // `preview`: the editor's unsaved form, shown exactly as students will see it (no team tools, buttons inert).
  import Bookmark from '@lucide/svelte/icons/bookmark';
  import Share from '@lucide/svelte/icons/share';
  import CalendarClock from '@lucide/svelte/icons/calendar-clock';
  import Clock from '@lucide/svelte/icons/clock';
  import GraduationCap from '@lucide/svelte/icons/graduation-cap';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import MapIcon from '@lucide/svelte/icons/map';
  import ExternalLink from '@lucide/svelte/icons/external-link';
  import Ticket from '@lucide/svelte/icons/ticket';
  import UserCheck from '@lucide/svelte/icons/user-check';
  import Check from '@lucide/svelte/icons/check';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import MonitorUp from '@lucide/svelte/icons/monitor-up';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import Pencil from '@lucide/svelte/icons/pencil';
  import BookOpen from '@lucide/svelte/icons/book-open';
  import Eye from '@lucide/svelte/icons/eye';
  import ImagePlus from '@lucide/svelte/icons/image-plus';
  import Camera from '@lucide/svelte/icons/camera';
  import Images from '@lucide/svelte/icons/images';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import Link from '@lucide/svelte/icons/link';
  import { shrink } from '../../lib/photo';
  import { FACES } from '../../lib/faces';
  import { burst } from '../../ui/burst';
  import { fly } from '../../ui/fly';
  import { onMount } from 'svelte';
  import AiBadge from '../../ui/AiBadge.svelte';
  import AskAi from '../../ui/AskAi.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import CalendarHeart from '@lucide/svelte/icons/calendar-heart';
  import Button from '../../ui/Button.svelte';
  import Poster from '../../ui/Poster.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import OrgTag from '../../ui/OrgTag.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import TwoGisMark from '../../ui/TwoGisMark.svelte';
  import { floorOf } from '../../lib/map';
  import { api, ApiErr, translated, type AlbumPhoto, type EventFull, type EventUpdate, type Id, type MeetingAnswer } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, eventById, eventDetails, goingBusy, toggleGoing, toggleSaved, studioChanged, phrase, declineInvite } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { may, withNick, inner, onTeam, RANK } from '../../lib/perms';
  import { t, tn, money, friendsLine, fmtNum, type Key, placeOf, subjectOf } from '../../lib/i18n/index.svelte';
  import { relDay, time, nowTs, dayMonth, parts, at, duration, ago, multiDay, daySpan } from '../../lib/time';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import { openLink, haptic, shareCard } from '../../lib/tg';
  import { sheets } from '../../lib/state/sheets';
  import { focusPos } from '../../lib/photo';
  import { nameOf } from '../../lib/short';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Section from '../../ui/Section.svelte';
  import Notice from '../../ui/Notice.svelte';
  import Field from '../../ui/Field.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  // from: the poster that was tapped, which grows into the header as the sheet opens
  // album: the bot's ph_ link, the guests' album opens over the sheet once its details are in
  let { overlay, id, preview, from, album }: { overlay: Overlay; id: Id; preview?: EventFull; from?: Element | null; album?: boolean } = $props();

  let detail = $state<EventFull | null>(null);
  $effect(() => { if (!preview) eventDetails(id).then((d) => (detail = d)).catch(() => {}); });

  // the shared card is the live source (it changes when you tap Going); details add the text
  const e = $derived(preview ?? eventById(id) ?? detail);
  let pic = $state(0); // which of the header's photos is on screen
  let hero = $state<HTMLDivElement>();
  let land = () => {};
  onMount(() => { if (from && hero) land = fly(from, hero, e?.cover?.focus); return () => land(); });
  let soon = $state(false), later = $state(false);
  // each a task after a frame was drawn (a frame's own requestAnimationFrame runs before that same frame is drawn when
  // the tap was a touch): the header first, the first screen next, then what is below it
  const after = (fn: () => void) => { let k = 0; const f = requestAnimationFrame(() => (k = setTimeout(fn) as unknown as number)); return () => { cancelAnimationFrame(f); clearTimeout(k); }; };
  onMount(() => { let stop = after(() => { soon = true; stop = after(() => (later = true)); }); return () => stop(); });
  $effect(() => { if (overlay.closing) land(); });
  const about = $derived(preview ? preview.description : detail?.description);
  let raw = $state(false); // the description as typed, not the AI's translation (PLAN 9)
  const aiAbout = $derived(!preview && !!detail && translated(detail, 'description'));
  const st = $derived(e?.my?.status);
  const going = $derived(st === 'going');
  const full = $derived(!!e && e.seats != null && e.taken >= e.seats && st !== 'going' && st !== 'hold');
  const cancelled = $derived(e?.status === 'cancelled');
  // the horizontal clip plays only where it costs nothing extra: not on the light look, not with Data Saver (PLAN 32)
  const wv = $derived(e && 'wideVideo' in e ? (e as EventFull).wideVideo : null);
  const wide = $derived(wv?.url && !cancelled && !document.documentElement.classList.contains('lowfx')
    && !(navigator as { connection?: { saveData?: boolean } }).connection?.saveData ? wv.url : null);
  const pct = $derived(e && e.seats ? Math.min(100, Math.round((e.taken / e.seats) * 100)) : 0);
  const started = $derived(!!e && e.startsAt <= nowTs());
  // the registration deadline closes "Going" for those not in yet; a 1st-year takes a paid event's free seat (§4.3)
  const regShut = $derived(!!e?.regUntil && e.regUntil <= nowTs() && st !== 'going' && st !== 'hold' && st !== 'waitlist');
  const freeMe = $derived(!!e?.price && !!e.freeLeft && !!session.me?.student?.freeFirst);
  const canInvite = $derived(!preview && !!session.me?.student && !!e && e.status === 'published' && !started && (e.visibility ?? 'public') === 'public');
  const over = $derived(!!e && (e.endsAt ?? e.startsAt + 3 * 3600) <= nowTs());
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
  // a co-hosted event's other club (server cohosts.py): its event team works the door and reads the list; its Vice+
  // may leave. Editing, price and seats stay the host's
  const coMem = $derived(e?.coHost ? session.me?.memberships.find((m) => m.org.id === e.coHost!.id) ?? null : null);
  const coCrew = $derived(!preview && !!e && e.status === 'published' && !crew && may(coMem, 'events'));
  const coLead = $derived(!preview && !!coMem && RANK[coMem.role] >= RANK.vice);
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

  // ---- "+N seats" (§4.2): when it's full, the club's Head+ add seats right here; the waitlist moves in ----
  let adding2 = $state(false);
  async function addSeats(n: number) {
    adding2 = true;
    try { detail = await api.addSeats(id, n); studioChanged(); haptic.ok(); say(t('seats.added', { n }), 'raising_hands_3d_default'); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { adding2 = false; }
  }

  // ---- a leaders meeting (§4.10): DMP sees every club's answers ----
  let answers = $state<import('../../lib/api').LeadersAnswer[] | null>(null);
  $effect(() => { if (e?.visibility === 'leaders' && head && crew) api.leadersAnswers(id).then((l) => (answers = l)).catch(() => {}); });

  // ---- a club meeting (§2b): "can't" says why; the club's Head+ see everyone expected, and after it who came ----
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
  async function rateIt(score: number, comment?: string) {
    const was = rated;
    rated = score; rating = true; haptic.select();
    try {
      detail = await api.rate(id, score, comment);
      if (comment) { noted = true; haptic.ok(); say(t('rate.saved'), 'sparkles_3d'); }
      else say(phrase('say.rated'), FACES[score - 1]);
    } catch { rated = was; haptic.error(); say(t('common.error'), 'warning_3d'); }
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
      try { detail = await api.addAlbumPhoto(id, await shrink(file)); added++; }
      catch (err) {
        haptic.error();
        if (err instanceof ApiErr && err.code === 'forbidden') { say(t('album.full'), 'pleading_face_3d'); break; }
        say(t('ed.photoBad'), 'pleading_face_3d');
      } finally { adding = Math.max(0, adding - 1); }
    }
    adding = 0;
    if (added) { haptic.ok(); burst(); say(tn('album.added', added), 'camera_with_flash_3d'); }
  }
  async function removePhoto(p: AlbumPhoto): Promise<AlbumPhoto[] | null> {
    try { detail = await api.removeAlbumPhoto(id, p.id); return detail.photos; }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); return null; }
  }

  const hidePhoto = (p: AlbumPhoto) => { if (detail) detail = { ...detail, photos: detail.photos.filter((x) => x.id !== p.id) }; }; // reported: gone for me
  const viewAlbum = (i = 0) => sheets.photos(photos, i, removePhoto, hidePhoto);
  let albumDone = false;
  $effect(() => { if (album && detail && !albumDone) { albumDone = true; if (detail.photos.length) viewAlbum(); } });

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
    // absolute date: the card is read later, when "tomorrow" is wrong
    shareCard({ kind: 'ev', id: String(id), title: e.title, when: `${dayMonth(e.startsAt)}, ${time(e.startsAt)}`, place: placeOf(e.place), img: e.cover?.url ?? e.video?.poster?.url ?? '' },
      'https://t.me/KBTUappBot?startapp=ev_' + id, e.title).then((sent) => { if (sent) say(phrase('say.shared'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'warning_3d'); });
  }
  // "My link": the same card with my badge code in its button, so who signs up by it counts for me (EventManage's "Who brought")
  const myLink = $derived(!!mem && !!e && e.status === 'published' && !started && !e.guestHost && !e.externalUrl && !inner(e) && !preview);
  // the team's tools group has a row to show (a guest host's event leaves a Member nothing)
  // a door helper (server crew.py): someone a running club's President or Vice asked to help at this event's door
  const helper = $derived(!preview && !crew && !coCrew && e?.status === 'published' ? detail?.myCrew ?? null : null);
  const crewLead = $derived(!preview && detail?.crew != null && e?.status === 'published' && !over && !e.guestHost && !inner(e));
  const tooled = $derived(!!e && ((crew && (!e.guestHost || head)) || myLink || coCrew || coLead || !!helper));
  function shareMine() {
    if (!e) return;
    haptic.tap();
    shareCard({ kind: 'ev', id: String(id), mine: '1' }, `https://t.me/KBTUappBot?startapp=ev_${id}_${session.me?.qr?.split('_')[1] ?? ''}`, e.title)
      .then((sent) => { if (sent) say(t('event.myLinkSent'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'warning_3d'); });
  }
</script>

<Sheet {overlay} icon={CalendarHeart} title={preview ? t('ed.preview') : t('cap.event')} tint={e?.tint}>
  {#if e}
    {#if preview}<p class="pv"><Tag tone="accent"><Eye size={15} />{t('event.preview')}</Tag></p>{/if}
    <div class="hero" class:cancelled bind:this={hero}>
      <!-- the header (PLAN 32/33): the horizontal clip behind it, else the vertical one, else the photos swiped sideways, else the cover -->
      {#if wide}
        <Poster item={e} big radius={22} />
        <video class="wide" src={wide} poster={wv?.poster?.url} autoplay muted loop playsinline preload="none"></video>
      {:else if !e.video?.url && e.cover && e.slides?.length}
        <div class="strip" onscroll={(s) => (pic = Math.round(s.currentTarget.scrollLeft / s.currentTarget.clientWidth))}>
          {#each [e.cover, ...e.slides] as p, i (p.id)}
            <button class="pic" onclick={() => sheets.photos([e.cover!, ...e.slides].map((x, k) => ({ ...x, id: x.id ?? -k, by: null, mine: true, canDelete: false })), i)}>
              <img src={p.url} alt="" decoding="async" loading={i ? 'lazy' : 'eager'} style:object-position={i ? null : focusPos(p)} /></button>
          {/each}
        </div>
        <span class="dots" aria-hidden="true">{#each [e.cover, ...e.slides] as _, k (k)}<i class:on={k === pic}></i>{/each}</span>
      {:else}
        <Poster item={e} big play radius={22} dim={cancelled} />
      {/if}
      {#if e.coHost}<span class="org"><OrgTag org={e.org} co={e.coHost} onpick={(o) => sheets.club(o)} /></span>
      {:else}<button class="org" onclick={() => sheets.club(e.org.id)}><OrgTag org={e.org} /></button>{/if}
      {#if e.meeting}<span class="tag"><Tag tone="onphoto">{t('event.meeting')}</Tag></span>{:else if e.visibility === 'members'}<span class="tag"><Tag tone="onphoto">{t('event.teamOnly')}</Tag></span>{:else if e.visibility === 'leaders'}<span class="tag"><Tag tone="onphoto">{t('event.leaders')}</Tag></span>{:else if e.firstYear}<span class="tag"><Tag tone="warning">{t('event.firstYear')}</Tag></span>{/if}
    </div>

    <div class="head">
      <h2 class="fs-sec" class:strike={cancelled}>{e.title}</h2>
      {#if cancelled}<p class="cancel">{t('event.cancelledLong')}</p>{/if}
      {#if e.guestHost}<p class="fs-sub dim">{t('event.with', { host: e.guestHost })} · {t('event.notKbtu')}</p>{/if}
    </div>

    <!-- the rest of the first screen and the bar a frame later: in the tap's frame the sheet is still below the screen
         (its rise starts there), only the header shows, flying in from the poster -->
    {#if soon}
    <div class="page">

    {#if detail && !e.meeting && (photos.length || detail.canAddPhotos)}
      <!-- the guests' album first, right under the header (after the event it's what the sheet is about) -->
      <section class="album">
        <!-- engine: Section could take a trailing action (here "Add"); its header in Group's caption size -->
        <div class="al-h"><h3 class="fs-t3">{t('album.title')}{#if photos.length}<span class="n num">{photos.length}</span>{/if}</h3>
          <!-- after the event the bar's own "Add photos" does it -->
          {#if detail.canAddPhotos && !over}<Button kind="tinted" size="s" disabled={adding > 0} onclick={() => picker?.click()}>{#snippet icon()}<ImagePlus size={16} />{/snippet}{t('album.add')}</Button>{/if}</div>
        {#if shown || adding}
          <div class="mosaic n{Math.min(shown, 3)}">
            {#each photos.slice(0, shown) as p, i (p.id)}
              <button class="ph" style="background-color:{p.color ?? 'var(--surface-2)'}" onclick={() => viewAlbum(i)}>
                <img src={p.thumb} alt="" loading="lazy" decoding="async" />
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

    {#if ups.length || (head && crew)}
      <!-- the organizer's updates: the newest under the title in the accent, the rest one tap away -->
      <div class="ups">
        {#each allUps ? ups : ups.slice(0, 1) as u, i (u.id)}
          <Notice tone={i > 0 ? 'neutral' : 'accent'} icon={Megaphone} title="{t('upd.title')} · {ago(u.at)}"
            action={u.canDelete ? { label: t('upd.delete'), onclick: () => removeUpdate(u) } : undefined}><p class="fs-body up-b">{u.body}</p></Notice>
        {/each}
        {#if ups.length > 1 && !allUps}<span class="lnk"><Button kind="plain" size="s" onclick={() => (allUps = true)}>{t('upd.more', { n: ups.length - 1 })}</Button></span>{/if}
        {#if head && crew}
          {#if writing}
            <Field label={t('upd.write')} bind:value={draft} multiline rows={2} maxlength={300} placeholder={t('upd.placeholder')} />
            <div class="up-acts"><span class="fs-sub faint">{t('upd.note')}</span>
              <Button kind="primary" size="s" loading={sending} disabled={draft.trim().length < 2} onclick={sendUpdate}>{t('upd.send')}</Button></div>
          {:else}
            <span class="lnk"><Button kind="tinted" size="s" onclick={() => (writing = true)}>{#snippet icon()}<Megaphone size={16} />{/snippet}{t('upd.write')}</Button></span>
          {/if}
        {/if}
      </div>
    {/if}

    <Group>
      <Row icon={CalendarClock} title={multiDay(e.startsAt, e.endsAt) ? daySpan(e.startsAt, e.endsAt) : relDay(e.startsAt)} subtitle="{time(e.startsAt)}{e.endsAt ? ' – ' + time(e.endsAt) : ''}" />
      {#if e.placeUrl}
        <!-- off campus: the place opens in 2GIS, so it wears their mark -->
        <Row title={e.place} subtitle={t('event.route')} accessory="external" onclick={() => openLink(e.placeUrl!)}>{#snippet lead()}<span class="gis"><TwoGisMark size={22} /></span>{/snippet}</Row>
      {:else if floorOf(e.place) != null}
        <Row icon={MapIcon} title={e.place} subtitle={floorOf(e.place) ? t('map.onFloor', { n: floorOf(e.place)! }) : t('map.onBasement')} accessory="chevron" onclick={() => sheets.map(e.place)} />
      {:else}
        <Row icon={MapPin} title={placeOf(e.place)} subtitle={e.price ? money(e.price) : e.guestHost ? undefined : t('event.free')} />
      {/if}
      {#if e.regUntil && !cancelled && !started}
        <Row icon={Clock} title={e.regUntil <= nowTs() ? t('event.regClosed') : t('event.regUntil', { when: relDay(e.regUntil) + ', ' + time(e.regUntil) })} />
      {/if}
      {#if e.price && e.freeFirst && !cancelled && !started}
        <Row icon={GraduationCap} title={e.freeLeft ? t('event.freeFirst', { n: e.freeLeft, of: e.freeFirst }) : t('event.freeFirstGone')} />
      {/if}
    </Group>

    {#if (e.meeting || e.visibility === 'leaders') && st === 'cancelled' && e.my?.cancelReason === 'self' && !started}
      <p class="fs-sub dim note">{e.my.note ? t('meet.yourNo', { why: e.my.note }) : t('meet.yourNoBare')}</p>{/if}
    {#if e.my?.status === 'cancelled' && (e.my.cancelReason === 'receipt_rejected' || e.my.cancelReason === 'hold_expired') && !over}
      <Notice tone="warning" text={t(e.my.cancelReason === 'receipt_rejected' ? 'pay.rejected' : 'pay.holdGone')} />
    {/if}
    {#if e.seats && !cancelled && !over}
      <div class="seats">
        <div class="bar"><span style="width:{pct}%" class:full={pct >= 100}></span></div>
        <div class="fs-sub dim sr"><span>{tn('event.going', e.taken)}</span><span class:red={full}>{full ? t('event.full') : tn('event.seatsLeft', Math.max(0, e.seats - e.taken))}</span></div>
        {#if head && crew && !started && e.taken >= e.seats}
          <div class="addseats"><span class="fs-sub dim">{t('seats.add')}</span>{#each [5, 10, 20] as n (n)}<Button kind="tinted" size="s" disabled={adding2} onclick={() => addSeats(n)}>+{n}</Button>{/each}</div>
        {/if}
      </div>
    {/if}

    <!-- below the first screen: built a frame after the sheet appears, so its rise starts at once -->
    {#if later}
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

    {#if detail?.chat && !preview && !cancelled && !over}
      <Button kind="secondary" size="m" full onclick={() => openLink(detail!.chat!)}>{#snippet icon()}<MessagesSquare size={18} />{/snippet}{t('chat.open')}</Button>
    {/if}

    {#if day && !cancelled && !over}
      <Notice tone={day.clash.length ? 'warning' : 'neutral'} icon={BookOpen} title={t('day.title')}>
        {#if day.before}<p class="fs-body">{t('day.before', { subject: subjectOf(day.before.c), end: day.before.c.ends, gap: duration(e.startsAt - day.before.en) })}</p>{/if}
        {#each day.clash as x (x.c.begins + x.c.subject)}<p class="fs-body warn">{t('day.clash', { subject: subjectOf(x.c), from: x.c.begins, to: x.c.ends })}</p>{/each}
        {#if day.after}<p class="fs-body">{e.endsAt ? t('day.after', { subject: subjectOf(day.after.c), from: day.after.c.begins, gap: duration(day.after.b - e.endsAt) }) : t('day.afterOpen', { subject: subjectOf(day.after.c), from: day.after.c.begins })}</p>{/if}
      </Notice>
    {/if}

    {#if tooled}
      <Group>
        {#if crew}
          {#if e.guestHost}{:else if inner(e)}<Row icon={UserCheck} title={t('studio.marks')} accessory="chevron" onclick={() => sheets.scanner(id, true)} />
          {:else}<Row icon={ScanLine} title={t('studio.scanner')} accessory="chevron" onclick={() => sheets.scanner(id)} />{/if}
          {#if head}
            {#if !e.guestHost}<Row icon={UsersRound} title={t('studio.attendees')} accessory="chevron" onclick={() => sheets.attendees(id)} />{/if}
            <Row icon={Pencil} title={t('studio.edit')} accessory="chevron" onclick={() => sheets.editor(e.org.id, id)} />
          {/if}
        {/if}
        {#if coCrew}
          <Row icon={ScanLine} title={t('studio.scanner')} accessory="chevron" onclick={() => sheets.scanner(id)} />
          <Row icon={UsersRound} title={t('studio.attendees')} accessory="chevron" onclick={() => sheets.attendees(id)} />
          {#if !e.price && !over}<Row icon={MonitorUp} title={t('scr.title')} accessory="chevron" onclick={() => sheets.screens(undefined, id)} />{/if}
        {/if}
        {#if helper}<Row icon={ScanLine} title={t('studio.scanner')} accessory="chevron" onclick={() => (helper === 'scan' ? sheets.scannerOnly(id) : sheets.scanner(id))} />{/if}
        {#if coLead && crewLead}<Row icon={UsersRound} title={t('crew.title')} count={detail?.crew?.length ?? 0} accessory="chevron" onclick={() => sheets.crew(id, () => void api.event(id).then((d) => (detail = d)).catch(() => {}))} />{/if}
        {#if myLink}<Row icon={Link} title={t('event.myLink')} onclick={shareMine} />{/if}
        {#if coLead}<Row tone="destructive" title={t('co.leave')} onclick={leaveCohost} />{/if}
      </Group>
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

    {#if !cancelled && (e.friends.length || canInvite)}
      <Group>
        <Row dense icon={e.friends.length ? undefined : UsersRound} title={e.friends.length ? friendsLine(e.friends.map((f) => f.name), over) : t('inv.nudge')}>
          {#snippet lead()}<span class="stack">{#each e.friends.slice(0, 4) as f (f.id)}<Avatar person={f} size={28} />{/each}</span>{/snippet}
          {#snippet trailing()}{#if canInvite}<Button kind="tinted" size="s" onclick={() => sheets.invite(id, e.title)}>{#snippet icon()}<UserPlus size={16} strokeWidth={2.3} />{/snippet}{t('inv.button')}</Button>{/if}{/snippet}
        </Row>
      </Group>
    {/if}

    {#if about}
      <Section title={t('event.about')}>
        <p class="fs-body desc selectable">{aiAbout && raw ? detail?.orig?.description : about}</p>
        {#if aiAbout}<span class="lnk trn"><Button kind="plain" size="s" onclick={() => (raw = !raw)}>{#snippet icon()}<AiBadge />{/snippet}{raw ? t('ai.showTr') : t('ai.showOrig')}</Button></span>{/if}
      </Section>
    {/if}
    <!-- the server reads only a public, published event's facts: no row where it would know nothing -->
    {#if !preview && e.status !== 'draft' && (e.visibility ?? 'public') === 'public'}<AskAi ctx={{ kind: 'event', id, title: e.title }} hint={t('as.askEvent')} />{/if}
    {@const talkTg = !!detail?.discuss && !preview && !cancelled}
    <!-- what was asked here before the Telegram talk stays readable -->
    {@const talkOld = !!detail && !preview && !cancelled && ((detail.commentsOn && !detail.discuss) || !!detail.comments)}
    {#if talkTg || talkOld}
      <Group>
        <!-- the talk lives under the channel post, with Telegram's replies and reactions -->
        {#if talkTg}<Row icon={MessageCircle} title={t('cm.titleEvent')} subtitle={t('cm.inTelegram')} accessory="external" onclick={() => openLink(detail!.discuss!)} />{/if}
        {#if talkOld}
          <Row icon={MessageCircle} title={t('cm.titleEvent')} subtitle={detail?.comments ? tn('cm.count', detail.comments) : t('cm.askNudge')} accessory="chevron"
            onclick={() => (session.me?.student ? sheets.comments('event', id, e.title, (n) => { if (detail) detail = { ...detail, comments: n }; }) : sheets.login())} />
        {/if}
      </Group>
    {/if}
    {#if crew && head && !started}<div class="kill"><Button kind="danger" size="m" full onclick={cancelEvent}>{t('studio.cancelEvent')}</Button></div>{/if}
    <!-- the one report sheet: anyone but the event's own crew -->
    {#if !may(mem, 'door') && !coMem && !preview && session.me?.student}<div class="rep"><Button kind="plain" size="s" onclick={() => sheets.report('event', id, e.title)}>{t('cm.report')}</Button></div>{/if}
    {/if}
    </div>
    {/if}
  {/if}

  {#snippet footer()}
    {#if e && soon}
      <div class="actions btns" inert={!!preview}>
        <span class="sv" class:on={e.saved}><Button kind="gray" size="l" round on={e.saved} label={e.saved ? t('event.saved') : t('event.save')} onclick={() => toggleSaved(id)}>
          {#snippet icon()}<Bookmark size={20} fill={e.saved ? 'currentColor' : 'none'} />{/snippet}</Button></span>
        <Button kind="gray" size="l" round label={t('event.share')} onclick={share}>{#snippet icon()}<Share size={20} />{/snippet}</Button>
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
          <Button kind="secondary" size="l" full onclick={() => viewAlbum()}>{#snippet icon()}<Images size={18} />{/snippet}{t('album.see')}</Button>
        {:else if over}
          <Button kind="neutral" size="l" full disabled>{t('event.over')}</Button>
        {:else if e.externalUrl}
          <Button kind="primary" size="l" full onclick={() => openLink(e.externalUrl!)}>{#snippet icon()}<ExternalLink size={18} />{/snippet}{t('event.external')}</Button>
        {:else if !going && st !== 'hold' && !e.guestHost && onTeam(e, session.me?.memberships)}
          <Button kind="neutral" size="l" full disabled>{#snippet icon()}<UsersRound size={18} />{/snippet}{t('event.team')}</Button>
        {:else if going && inner(e)}
          <!-- a club's own event: no ticket, just the answer, changeable until it starts -->
          <div class="ans btns">
            {#if !started}<Button kind="secondary" size="l" full onclick={() => (e.meeting ? cantCome() : e.visibility === 'leaders' ? declineInvite(id) : toggleGoing(id))}>{t('lead.no')}</Button>{/if}
            <span class="yes"><Check size={18} strokeWidth={2.6} />{t('event.youGo')}</span>
          </div>
        {:else if going}
          <Button kind="primary" size="l" full onclick={() => sheets.ticket(id)}>{#snippet icon()}<Ticket size={18} />{/snippet}{t('event.ticket')}</Button>
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
          <Button kind="primary" size="l" full loading={goingBusy.has(id)} onclick={() => toggleGoing(id, () => sheets.pay(id))}>{e.price ? freeMe ? t('event.goFree') : t('event.goPrice', { price: money(e.price) }) : t('event.go')}</Button>
        {/if}
      </div>
    {/if}
  {/snippet}
</Sheet>

<style>
  /* the stack under the header: one gap between blocks, Groups like Settings */
  .page { display: flex; flex-direction: column; gap: var(--s-5); }
  .head { display: flex; flex-direction: column; gap: var(--s-1); margin-bottom: var(--s-5); padding: 0 var(--s-1); }
  .strike { text-decoration: line-through; color: var(--text-2); }
  .cancel { font: 600 var(--fs-body)/1.35 var(--font-text); color: var(--danger-text); }
  .pv { display: flex; justify-content: center; margin: 0 0 10px; }
  .note { padding: 0 var(--s-4); }
  .lnk { align-self: flex-start; }
  .trn { margin: -6px 0 0 -8px; --plain-ink: var(--text-3); }
  .warn { color: var(--warning-text); font-weight: 600; }
  .desc { color: var(--text); white-space: pre-line; padding: 0 var(--s-1); }
  .kill { margin-top: var(--s-1); }
  .rep { display: flex; justify-content: center; --plain-ink: var(--text-3); }
  .gis { width: 24px; display: grid; place-items: center; }

  /* the header: art (the poster, the photos swiped sideways, the clip) */
  .hero { position: relative; height: 210px; margin: 4px 0 16px; border-radius: var(--r-l); overflow: hidden; }
  .wide { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .strip { position: absolute; inset: 0; display: flex; overflow-x: auto; scroll-snap-type: x mandatory; overscroll-behavior-x: contain; scrollbar-width: none; }
  .strip::-webkit-scrollbar { display: none; }
  .pic { flex: 0 0 100%; scroll-snap-align: start; scroll-snap-stop: always; }
  .pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .dots { position: absolute; left: 0; right: 0; bottom: 10px; display: flex; justify-content: center; gap: 5px; pointer-events: none; }
  .dots i { width: 6px; height: 6px; border-radius: var(--r-full); background: rgba(255, 255, 255, 0.5); box-shadow: 0 0 4px rgba(0, 0, 0, 0.4); transition: transform var(--t-fast); }
  .dots i.on { background: var(--on-accent); transform: scale(1.25); }
  .org { position: absolute; left: 12px; top: 12px; }
  .org :global(.chip) { height: 26px; padding: 0 10px 0 6px; font-size: var(--fs-cap); gap: 6px; -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); }
  .tag { position: absolute; right: 12px; top: 12px; }

  /* the guests' album: the first photo big, two beside it, three under (whole blocks only) */
  .album { display: flex; flex-direction: column; gap: 10px; }
  .al-h { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); padding: 0 var(--s-1); }
  .al-h .n { margin-left: var(--s-2); font-weight: 450; color: var(--text-3); }
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

  /* seats: a thin bar, how many are going and how many are left */
  .seats { display: flex; flex-direction: column; gap: 7px; padding: 0 var(--s-1); }
  .bar { height: 6px; border-radius: var(--r-full); background: var(--fill); overflow: hidden; }
  .bar span { display: block; height: 100%; border-radius: var(--r-full); background: var(--accent); transition: width var(--t-slow) var(--ease); }
  .bar span.full { background: var(--danger); }
  .sr { display: flex; justify-content: space-between; }
  .red { color: var(--danger-text); }
  .addseats { display: flex; align-items: center; gap: 6px; margin-top: var(--s-1); }
  .addseats .fs-sub { margin-right: auto; }

  .ups { display: flex; flex-direction: column; gap: var(--s-2); }
  .up-b { white-space: pre-line; overflow-wrap: anywhere; }
  .up-acts { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding-left: var(--s-4); }

  .stack { display: flex; }
  .stack :global(.av + .av) { margin-left: -8px; }
  .stack :global(.av) { box-shadow: 0 0 0 2px var(--surface-solid); }

  /* the footer: save and share, then the one primary action */
  .actions { display: flex; gap: 8px; align-items: center; }
  .sv.on :global(.btn) { color: var(--warning); }
  .ans { flex: 1; display: flex; gap: 8px; min-width: 0; }
  .yes { flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px; min-width: 0; border-radius: var(--r-full);
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
