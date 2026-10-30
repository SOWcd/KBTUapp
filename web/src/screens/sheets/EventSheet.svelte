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
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Ticket from '@lucide/svelte/icons/ticket';
  import UserCheck from '@lucide/svelte/icons/user-check';
  import Check from '@lucide/svelte/icons/check';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import Pencil from '@lucide/svelte/icons/pencil';
  import BookOpen from '@lucide/svelte/icons/book-open';
  import Eye from '@lucide/svelte/icons/eye';
  import ImagePlus from '@lucide/svelte/icons/image-plus';
  import Camera from '@lucide/svelte/icons/camera';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Link from '@lucide/svelte/icons/link';
  import { shrink } from '../../lib/photo';
  import { FACES } from '../../lib/faces';
  import { burst } from '../../ui/burst';
  import { fly } from '../../ui/fly';
  import { onMount } from 'svelte';
  import AiBadge from '../../ui/AiBadge.svelte';
  import Sheet from '../../ui/Sheet.svelte';
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
  import { data, eventById, eventDetails, toggleGoing, toggleSaved, studioChanged, phrase, declineInvite } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { may, withNick, inner } from '../../lib/perms';
  import { t, tn, money, friendsLine, fmtNum, type Key, placeOf, subjectOf } from '../../lib/i18n/index.svelte';
  import { relDay, time, nowTs, dayMonth, parts, at, duration, ago } from '../../lib/time';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import X from '@lucide/svelte/icons/x';
  import { openLink, haptic, shareCard } from '../../lib/tg';
  import { sheets } from '../../lib/state/sheets';
  import { focusPos } from '../../lib/photo';
  import { nameOf } from '../../lib/short';
  import { grow } from '../../ui/grow';

  // from: the poster that was tapped, which grows into the header as the sheet opens
  let { overlay, id, preview, from }: { overlay: Overlay; id: Id; preview?: EventFull; from?: Element | null } = $props();

  let detail = $state<EventFull | null>(null);
  $effect(() => { if (!preview) eventDetails(id).then((d) => (detail = d)).catch(() => {}); });

  // the shared card is the live source (it changes when you tap Going); details add the text
  const e = $derived(preview ?? eventById(id) ?? detail);
  let pic = $state(0); // which of the header's photos is on screen
  let hero = $state<HTMLDivElement>();
  let land = () => {};
  onMount(() => { if (from && hero) land = fly(from, hero, e?.cover?.focus); return () => land(); });
  let later = $state(false);
  onMount(() => { const f = requestAnimationFrame(() => setTimeout(() => (later = true))); return () => cancelAnimationFrame(f); });
  $effect(() => { if (overlay.closing) land(); });
  const about = $derived(preview ? preview.description : detail?.description);
  let raw = $state(false); // the description as typed, not the AI's translation (PLAN 9)
  const aiAbout = $derived(!preview && !!detail && translated(detail, 'description'));
  const st = $derived(e?.my?.status);
  const route = $derived(t('event.route').split(' ')); // the ↗ sticks to the last word, never wraps alone
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
  const freeMe = $derived(!!e?.price && !!e.freeLeft && session.me?.student?.course === 1);
  const canInvite = $derived(!preview && !!session.me?.student && !!e && e.status === 'published' && !started && (e.visibility ?? 'public') === 'public');
  const over = $derived(!!e && (e.endsAt ?? e.startsAt + 3 * 3600) <= nowTs());
  // the student's classes around the event that day: the last one before, any that overlap, the first one
  // after — so they see at once whether they make it
  const day = $derived.by(() => {
    if (!e || !data.schedule.length) return null;
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
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
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
    } catch (err) { haptic.error(); say(err instanceof ApiErr && err.code === 'rate_limited' ? t('upd.tooMany') : t('common.error'), 'pleading_face_3d'); }
    finally { sending = false; }
  }
  // ---- one tap after the event (checked-in people): a face sends the rating at once; a comment can follow ----
  let rated = $state<number | null>(null);
  $effect(() => { if (detail) rated = detail.myRating; });
  let note = $state('');
  let noted = $state(false);
  async function rateIt(score: number, comment?: string) {
    const was = rated;
    rated = score; haptic.select();
    try {
      detail = await api.rate(id, score, comment);
      if (comment) { noted = true; haptic.ok(); say(t('rate.saved'), 'sparkles_3d'); }
      else say(phrase('say.rated'), FACES[score - 1]);
    } catch { rated = was; haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
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
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); return null; }
  }

  const hidePhoto = (p: AlbumPhoto) => { if (detail) detail = { ...detail, photos: detail.photos.filter((x) => x.id !== p.id) }; }; // reported: gone for me

  async function removeUpdate(u: EventUpdate) {
    if (!(await sheets.ask({ title: t('upd.deleteAsk'), ok: t('upd.delete'), cancel: t('common.cancel'), danger: true }))) return;
    try { await api.deleteUpdate(id, u.id); if (detail) detail = { ...detail, updates: detail.updates.filter((x) => x.id !== u.id) }; haptic.soft(); say(t('say.updDeleted'), 'waving_hand_3d_default'); }
    catch { say(t('common.error'), 'pleading_face_3d'); }
  }

  async function cancelEvent() {
    if (!(await sheets.ask({ title: t('studio.cancelAsk'), text: t('studio.cancelText'), ok: t('studio.cancelGo'), cancel: t('tk.keep'), danger: true }))) return;
    try { await api.cancelEvent(id); studioChanged(); haptic.warn(); say(t('say.eventCancelled'), 'crying_face_3d'); }
    catch { say(t('common.error'), 'pleading_face_3d'); }
  }

  function share() {
    if (!e) return;
    haptic.tap();
    // absolute date: the card is read later, when "tomorrow" is wrong
    shareCard({ kind: 'ev', id: String(id), title: e.title, when: `${dayMonth(e.startsAt)}, ${time(e.startsAt)}`, place: placeOf(e.place), img: e.cover?.url ?? e.video?.poster?.url ?? '' },
      'https://t.me/KBTUappBot?startapp=ev_' + id, e.title).then((sent) => { if (sent) say(phrase('say.shared'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'pleading_face_3d'); });
  }
  // "My link": the same card with my badge code in its button, so who signs up by it counts for me (EventManage's "Who brought")
  const myLink = $derived(!!mem && !!e && e.status === 'published' && !started && !e.guestHost && !e.externalUrl && !inner(e) && !preview);
  function shareMine() {
    if (!e) return;
    haptic.tap();
    shareCard({ kind: 'ev', id: String(id), mine: '1' }, `https://t.me/KBTUappBot?startapp=ev_${id}_${session.me?.qr?.split('_')[1] ?? ''}`, e.title)
      .then((sent) => { if (sent) say(t('event.myLinkSent'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'pleading_face_3d'); });
  }
</script>

<Sheet {overlay} title={preview ? t('ed.preview') : (e?.title ?? '')} tint={e?.tint}>
  {#if e}
    {#if preview}<p class="pv"><Eye size={15} />{t('event.preview')}</p>{/if}
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
      <button class="org" onclick={() => sheets.club(e.org.id)}><OrgTag org={e.org} /></button>
      {#if e.meeting}<span class="tag"><Tag tone="onphoto">{t('event.meeting')}</Tag></span>{:else if e.visibility === 'members'}<span class="tag"><Tag tone="onphoto">{t('event.teamOnly')}</Tag></span>{:else if e.visibility === 'leaders'}<span class="tag"><Tag tone="onphoto">{t('event.leaders')}</Tag></span>{:else if e.firstYear}<span class="tag"><Tag tone="warning">{t('event.firstYear')}</Tag></span>{/if}
    </div>

    <h2 class="t-h2 title" class:strike={cancelled}>{e.title}</h2>
    {#if cancelled}<p class="cancel">{t('event.cancelledLong')}</p>{/if}
    {#if e.guestHost}<p class="t-foot">{t('event.with', { host: e.guestHost })} · {t('event.notKbtu')}</p>{/if}

    {#if detail && (detail.canRate || detail.myRating != null)}
      <section class="rate">
        <b class="rq">{rated ? t('rate.thanks') : t('rate.ask')}</b>
        <div class="faces">
          {#each FACES as f, i (i)}<button class:on={rated === i + 1} class:dim={!!rated && rated !== i + 1} disabled={!detail.canRate} onclick={() => rateIt(i + 1, note.trim() || undefined)} aria-label={String(i + 1)}><Emoji name={f} size={34} /></button>{/each}
        </div>
        {#if rated && detail.canRate && !noted}
          <div class="rnote"><input bind:value={note} maxlength="300" placeholder={t('rate.comment')} enterkeyhint="send" onkeydown={(ev) => { if (ev.key === 'Enter' && note.trim()) void rateIt(rated!, note.trim()); }} />
            <Button kind="secondary" size="s" disabled={!note.trim()} onclick={() => rateIt(rated!, note.trim())}>{t('rate.add')}</Button></div>
        {/if}
        <p class="t-foot">{t('rate.anon')}</p>
      </section>
    {/if}

    {#if detail?.ratings}
      {@const r = detail.ratings}
      <section class="rsum">
        <div class="rs-top">{#if r.avg != null}<span class="avg num">{fmtNum(r.avg)}</span>{/if}<span><b>{t('rate.title')}</b><i class="t-foot">{tn('rate.count', r.count)}{r.avg == null ? ' · ' + t('rate.few') : ''}</i></span></div>
        {#each [...r.dist].reverse() as n, i (i)}
          <div class="rs-row"><span class="rf"><Emoji name={FACES[4 - i]} size={18} /></span><span class="rbar"><span style="width:{r.count ? (n / r.count) * 100 : 0}%"></span></span><span class="rn num">{n}</span></div>
        {/each}
        {#each r.comments.slice(0, 20) as c, i (i)}<p class="rc"><Emoji name={FACES[c.score - 1]} size={18} />{c.body}</p>{/each}
      </section>
    {/if}

    {#if detail && !e.meeting && (photos.length || detail.canAddPhotos)}
      <section class="album">
        <div class="al-h"><b>{t('album.title')}</b>{#if photos.length}<span class="t-foot num">{photos.length}</span>{/if}
          {#if detail.canAddPhotos}<button class="al-add" disabled={adding > 0} onclick={() => picker?.click()}><ImagePlus size={16} />{t('album.add')}</button>{/if}</div>
        {#if shown || adding}
          <div class="mosaic n{Math.min(shown, 3)}">
            {#each photos.slice(0, shown) as p, i (p.id)}
              <button class="ph" style="background-color:{p.color ?? 'var(--surface-2)'}" onclick={() => sheets.photos(photos, i, removePhoto, hidePhoto)}>
                <img src={p.thumb} alt="" loading="lazy" decoding="async" />
                {#if i === shown - 1 && photos.length > shown}<span class="more num">+{photos.length - shown}</span>{/if}
              </button>
            {/each}
            {#each { length: adding } as _, i (i)}<span class="ph wait"></span>{/each}
          </div>
        {:else}
          <p class="t-foot al-empty">{t('album.empty')}</p>
        {/if}
        <input type="file" accept="image/*" multiple hidden bind:this={picker} onchange={addPhotos} />
      </section>
    {/if}

    {#if e.visibility === 'leaders' && head && crew && answers}
      <section class="lead">
        <h3 class="t-cap sec">{t('lead.answers')} · {answers.reduce((n, a) => n + a.people.filter((p) => p.answer === 'yes').length, 0)} / {answers.reduce((n, a) => n + a.people.length, 0)}</h3>
        {#each answers as a (a.org.id)}
          <div class="lc"><span class="ln"><OrgLogo org={a.org} size={20} /><b class="ellipsis">{nameOf(a.org)}</b></span>
            <span class="lp">{#each a.people as p (p.person.id)}<span class="pa {p.answer}">{p.answer === 'yes' ? '✓' : p.answer === 'no' ? '✕' : '…'} {p.fullName}</span>{/each}</span></div>
        {/each}
      </section>
    {/if}

    {#if ups.length || (head && crew)}
      <section class="ups">
        {#each allUps ? ups : ups.slice(0, 1) as u, i (u.id)}
          <div class="up" class:older={i > 0}>
            <span class="up-h"><Megaphone size={14} strokeWidth={2.2} />{t('upd.title')} · {ago(u.at)}
              {#if u.canDelete}<button class="up-x" onclick={() => removeUpdate(u)} aria-label={t('upd.delete')}><X size={14} /></button>{/if}</span>
            <p>{u.body}</p>
          </div>
        {/each}
        {#if ups.length > 1 && !allUps}<button class="up-more" onclick={() => (allUps = true)}>{t('upd.more', { n: ups.length - 1 })}</button>{/if}
        {#if head && crew}
          {#if writing}
            <div class="up-new">
              <textarea bind:value={draft} maxlength="300" rows="2" placeholder={t('upd.placeholder')} use:grow></textarea>
              <div class="up-acts"><span class="t-foot">{t('upd.note')}</span>
                <Button kind="primary" size="s" loading={sending} disabled={draft.trim().length < 2} onclick={sendUpdate}>{t('upd.send')}</Button></div>
            </div>
          {:else}
            <button class="up-add" onclick={() => (writing = true)}><Megaphone size={16} />{t('upd.write')}</button>
          {/if}
        {/if}
      </section>
    {/if}

    <div class="facts">
      <div class="fact"><span class="fi"><CalendarClock size={18} /></span>
        <span><b>{relDay(e.startsAt)}</b><i>{time(e.startsAt)}{e.endsAt ? ' – ' + time(e.endsAt) : ''}</i></span></div>
      {#if e.placeUrl}
        <button class="fact gis" onclick={() => openLink(e.placeUrl!)}><span class="fi"><TwoGisMark size={22} /></span><span><b>{e.place}</b><i class="go">{route.slice(0, -1).join(' ')} <span class="nw">{route.at(-1)}<ArrowUpRight size={14} strokeWidth={2.4} /></span></i></span></button>
      {:else if floorOf(e.place) != null}
        <button class="fact" onclick={() => sheets.map(e.place)}><span class="fi"><MapIcon size={18} /></span><span><b>{e.place}</b><i class="go">{floorOf(e.place) ? t('map.onFloor', { n: floorOf(e.place)! }) : t('map.onBasement')}</i></span></button>
      {:else}
        <div class="fact"><span class="fi"><MapPin size={18} /></span><span><b class:tba={!e.place}>{placeOf(e.place)}</b><i>{e.price ? money(e.price) : e.guestHost ? '' : t('event.free')}</i></span></div>
      {/if}
    </div>

    {#if (e.meeting || e.visibility === 'leaders') && st === 'cancelled' && e.my?.cancelReason === 'self' && !started}
      <p class="rnote">{e.my.note ? t('meet.yourNo', { why: e.my.note }) : t('meet.yourNoBare')}</p>{/if}
    {#if e.my?.status === 'cancelled' && (e.my.cancelReason === 'receipt_rejected' || e.my.cancelReason === 'hold_expired') && !over}
      <p class="paynote">{t(e.my.cancelReason === 'receipt_rejected' ? 'pay.rejected' : 'pay.holdGone')}</p>
    {/if}
    {#if e.seats && !cancelled && !over}
      <div class="seats">
        <div class="bar"><span style="width:{pct}%" class:full={pct >= 100}></span></div>
        <div class="t-foot row"><span>{tn('event.going', e.taken)}</span><span class:red={full}>{full ? t('event.full') : tn('event.seatsLeft', Math.max(0, e.seats - e.taken))}</span></div>
        {#if head && crew && !started && e.taken >= e.seats}
          <div class="addseats"><span class="t-foot">{t('seats.add')}</span>{#each [5, 10, 20] as n (n)}<button disabled={adding2} onclick={() => addSeats(n)}>+{n}</button>{/each}</div>
        {/if}
      </div>
    {/if}

    {#if e.regUntil && !cancelled && !started}
      <p class="rnote" class:shut={e.regUntil <= nowTs()}><Clock size={15} />{e.regUntil <= nowTs() ? t('event.regClosed') : t('event.regUntil', { when: relDay(e.regUntil) + ', ' + time(e.regUntil) })}</p>
    {/if}
    {#if e.price && e.freeFirst && !cancelled && !started}
      <p class="rnote"><GraduationCap size={15} />{e.freeLeft ? t('event.freeFirst', { n: e.freeLeft, of: e.freeFirst }) : t('event.freeFirstGone')}</p>
    {/if}

    <!-- below the first screen: built a frame after the sheet appears, so its rise starts at once -->
    {#if later}
    <!-- volunteers: a student applies with a short "why", the organizers answer; the team sees the count -->
    {#if detail?.volunteers && !preview && !cancelled && !started}
      {@const vo = detail.volunteers}
      <div class="vol surface">
        <div class="vh"><HandHeart size={20} /><span><b>{t('vol.title')}</b><i class="t-foot">{t('vol.left', { n: Math.max(0, vo.need - vo.taken), of: vo.need })}{vo.senior ? ' · ' + t('vol.senior') : ''}</i></span></div>
        {#if head && crew}
          <Button kind="secondary" size="m" full onclick={() => sheets.volunteers(id, vo.need)}>{t('vol.open')}{vo.asked ? ` · ${vo.asked}` : ''}</Button>
        {:else if !crew}
          {#if vo.mine === 'asked'}
            <div class="vs"><span class="t-foot">{t('vol.sent')}</span><button class="vx" onclick={volLeave}>{t('vol.leave')}</button></div>
          {:else if vo.mine === 'yes'}
            <div class="vs"><b class="ok">{t('vol.youAre')}</b><button class="vx" onclick={volLeave}>{t('vol.stepDown')}</button></div>
          {:else if vo.mine === 'no'}
            <p class="t-foot">{t('vol.notThisTime')}</p>
          {:else if vo.taken < vo.need}
            {#if volWriting}
              <label class="field"><textarea bind:value={volNote} rows="2" maxlength="300" placeholder={t('vol.whyPh')}></textarea></label>
              <Button kind="primary" size="m" full onclick={volApply}>{t('vol.send')}</Button>
            {:else}
              <Button kind="primary" size="m" full onclick={() => { haptic.tap(); volWriting = true; }}>{t('vol.want')}</Button>
            {/if}
          {/if}
        {/if}
      </div>
    {/if}

    {#if detail?.chat && !preview && !cancelled && !over}
      <div class="chatrow"><Button kind="secondary" size="m" full onclick={() => openLink(detail!.chat!)}>{#snippet icon()}<MessagesSquare size={18} />{/snippet}{t('chat.open')}</Button></div>
    {/if}

    {#if day && !cancelled && !over}
      <div class="day">
        <span class="t-cap dh"><BookOpen size={14} strokeWidth={2.2} />{t('day.title')}</span>
        {#if day.before}<p>{t('day.before', { subject: subjectOf(day.before.c), end: day.before.c.ends, gap: duration(e.startsAt - day.before.en) })}</p>{/if}
        {#each day.clash as x (x.c.begins + x.c.subject)}<p class="warn">{t('day.clash', { subject: subjectOf(x.c), from: x.c.begins, to: x.c.ends })}</p>{/each}
        {#if day.after}<p>{e.endsAt ? t('day.after', { subject: subjectOf(day.after.c), from: day.after.c.begins, gap: duration(day.after.b - e.endsAt) }) : t('day.afterOpen', { subject: subjectOf(day.after.c), from: day.after.c.begins })}</p>{/if}
      </div>
    {/if}

    {#if crew}
      <div class="tools">
        {#if e.guestHost}{:else if inner(e)}<button onclick={() => sheets.scanner(id, true)}><UserCheck size={18} />{t('studio.marks')}</button>
        {:else}<button onclick={() => sheets.scanner(id)}><ScanLine size={18} />{t('studio.scanner')}</button>{/if}
        {#if head}
          {#if !e.guestHost}<button onclick={() => sheets.attendees(id)}><UsersRound size={18} />{t('studio.attendees')}</button>{/if}
          <button onclick={() => sheets.editor(e.org.id, id)}><Pencil size={18} />{t('studio.edit')}</button>
        {/if}
      </div>
    {/if}
    {#if myLink}<div class="tools"><button onclick={shareMine}><Link size={18} />{t('event.myLink')}</button></div>{/if}

    {#if e.meeting && head && crew && meet}
      <section class="lead">
        <h3 class="t-cap sec">{over ? t('meet.after') : t('meet.answers')} · {meet.filter((a) => (over ? a.came : a.answer === 'yes')).length} / {meet.length}</h3>
        {#each meetGroups as [title, list] (title)}
          <div class="mg"><b class="t-foot">{t(title)} · {list.length}</b>
            {#each list as a (a.person.id)}
              <div class="mp"><span class="mn"><b class="ellipsis">{withNick(a.fullName, a.person)}</b>
                {#if a.answer === 'no'}<i>{a.note ?? t('meet.noWhy')}</i>{/if}</span>
              </div>
            {/each}
          </div>
        {/each}
      </section>
    {/if}

    {#if !cancelled && (e.friends.length || canInvite)}
      <div class="friends">
        {#if e.friends.length}
          <span class="stack">{#each e.friends.slice(0, 4) as f (f.id)}<Avatar person={f} size={28} />{/each}</span>
          <span class="t-callout fl">{friendsLine(e.friends.map((f) => f.name), over)}</span>
        {:else}<span class="t-callout fl dim">{t('inv.nudge')}</span>{/if}
        {#if canInvite}<button class="inv" onclick={() => sheets.invite(id, e.title)}><UserPlus size={16} strokeWidth={2.3} />{t('inv.button')}</button>{/if}
      </div>
    {/if}

    {#if about}
      <h3 class="t-cap sec">{t('event.about')}</h3>
      <p class="t-body desc selectable">{aiAbout && raw ? detail?.orig?.description : about}</p>
      {#if aiAbout}<button class="trn" onclick={() => (raw = !raw)}><AiBadge /> {raw ? t('ai.showTr') : t('ai.showOrig')}</button>{/if}
    {/if}
    {#if detail?.discuss && !preview && !cancelled}
      <!-- the talk lives under the channel post, with Telegram's replies and reactions -->
      <button class="talk" onclick={() => openLink(detail!.discuss!)}>
        <span class="fi"><MessageCircle size={18} /></span>
        <span class="tk"><b>{t('cm.titleEvent')}</b><i>{t('cm.inTelegram')}</i></span>
        <ArrowUpRight size={18} />
      </button>
    {/if}
    <!-- what was asked here before the Telegram talk stays readable -->
    {#if detail && !preview && !cancelled && ((detail.commentsOn && !detail.discuss) || detail.comments)}
      <button class="talk" onclick={() => (session.me?.student ? sheets.comments('event', id, e.title, (n) => { if (detail) detail = { ...detail, comments: n }; }) : sheets.login())}>
        <span class="fi"><MessageCircle size={18} /></span>
        <span class="tk"><b>{t('cm.titleEvent')}</b><i>{detail.comments ? tn('cm.count', detail.comments) : t('cm.askNudge')}</i></span>
        <ChevronRight size={18} />
      </button>
    {/if}
    {#if crew && head && !started}<div class="kill"><Button kind="danger" size="m" full onclick={cancelEvent}>{t('studio.cancelEvent')}</Button></div>{/if}
    <!-- the one report sheet: anyone but the event's own crew -->
    {#if !may(mem, 'door') && !preview && session.me?.student}<button class="rep" onclick={() => sheets.report('event', id, e.title)}>{t('cm.report')}</button>{/if}
    {/if}
  {/if}

  {#snippet footer()}
    {#if e}
      <div class="actions btns" inert={!!preview}>
        <button class="ib" class:on={e.saved} onclick={() => toggleSaved(id)} aria-label={e.saved ? t('event.saved') : t('event.save')}>
          <Bookmark size={20} fill={e.saved ? 'currentColor' : 'none'} />
        </button>
        <button class="ib" onclick={share} aria-label={t('event.share')}><Share size={20} /></button>
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
        {:else if over}
          <Button kind="neutral" size="l" full disabled>{t('event.over')}</Button>
        {:else if e.externalUrl}
          <Button kind="primary" size="l" full onclick={() => openLink(e.externalUrl!)}>{#snippet icon()}<ExternalLink size={18} />{/snippet}{t('event.external')}</Button>
        {:else if going && inner(e)}
          <!-- a club's own event: no ticket, just the answer, changeable until it starts -->
          <div class="ans btns">
            {#if !started}<Button kind="secondary" size="l" full onclick={() => (e.meeting ? cantCome() : e.visibility === 'leaders' ? declineInvite(id) : toggleGoing(id))}>{t('lead.no')}</Button>{/if}
            <span class="yes"><Check size={18} strokeWidth={2.6} />{t('event.youGo')}</span>
          </div>
        {:else if going}
          <Button kind="primary" size="l" full onclick={() => sheets.ticket(id)}>{#snippet icon()}<Ticket size={18} />{/snippet}{t('event.ticket')}</Button>
        {:else if started}
          <Button kind="neutral" size="l" full disabled>{t('event.started')}</Button>
        {:else if st === 'hold'}
          <Button kind="primary" size="l" full onclick={() => sheets.pay(id)}>{t('event.pay', { price: money(e.price ?? 0) })}</Button>
        {:else if st === 'waitlist'}
          <Button kind="neutral" size="l" full onclick={() => toggleGoing(id)}>{t('event.notifyOn')}</Button>
        {:else if regShut}
          <Button kind="neutral" size="l" full disabled>{t('event.regClosed')}</Button>
        {:else if full}
          <Button kind="secondary" size="l" full onclick={() => toggleGoing(id)}>{t('event.notify')}</Button>
        {:else}
          <Button kind="primary" size="l" full onclick={() => toggleGoing(id, () => sheets.pay(id))}>{e.price ? freeMe ? t('event.goFree') : t('event.goPrice', { price: money(e.price) }) : t('event.go')}</Button>
        {/if}
      </div>
    {/if}
  {/snippet}
</Sheet>

<style>
  .trn { align-self: flex-start; margin-top: 6px; padding: 2px 0; font: 600 12.5px/1.2 var(--font-text); color: var(--text-3); }
  .rnote { display: flex; align-items: center; gap: 7px; margin: 10px 2px 0; font: 600 13.5px/1.3 var(--font-text); color: var(--text-2); }
  .mg { display: flex; flex-direction: column; gap: 6px; margin-top: 10px; }
  .mg > b { color: var(--text-2); }
  .mp { display: flex; align-items: center; gap: 10px; padding: 8px 12px; border-radius: var(--r-m); background: var(--surface-2); }
  .mn { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; font: 600 14.5px/1.3 var(--font-text); }
  .mn i { font: 500 13px/1.3 var(--font-text); color: var(--text-2); font-style: normal; }
  .rnote :global(svg) { flex: none; color: var(--text-3); }
  .rnote.shut, .rnote.shut :global(svg) { color: var(--danger-text); }
  .paynote { margin: 12px 0 0; padding: 10px 12px; border-radius: var(--r-m); background: var(--warning-soft); color: var(--warning-text); font: 600 14px/1.35 var(--font-text); }
  .album { margin: 14px 0 4px; }
  .al-h { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
  .al-h b { font: 720 17px/1.2 var(--font-display); letter-spacing: -0.015em; }
  .al-add { margin-left: auto; display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 640 13.5px/1 var(--font-text); }
  .al-add:active { transform: scale(0.96); }
  .al-empty { padding: 4px 2px; }
  /* the mosaic: the first photo big, two beside it, three under (whole blocks only) */
  .mosaic { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; border-radius: 18px; overflow: hidden; }
  .mosaic.n1 { grid-template-columns: 1fr; }
  .mosaic.n2 { grid-template-columns: 1fr 1fr; }
  .ph { position: relative; aspect-ratio: 1; overflow: hidden; display: block; background-size: cover; }
  .mosaic.n1 .ph { aspect-ratio: 16 / 10; }
  .mosaic.n3 .ph:first-child { grid-column: span 2; grid-row: span 2; }
  .ph img { width: 100%; height: 100%; object-fit: cover; display: block; animation: ph-in 420ms ease-out backwards; }
  @keyframes ph-in { from { opacity: 0; } }
  .ph:active img { transform: scale(0.97); transition: transform 120ms; }
  .more { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: #fff; background: rgba(8, 10, 20, 0.5);
    font: 760 22px/1 var(--font-display); }
  .ph.wait { background: var(--surface-2); animation: ph-wait 1.1s ease-in-out infinite; }
  @keyframes ph-wait { 50% { opacity: 0.5; } }
  .pv { display: flex; align-items: center; justify-content: center; gap: 6px; width: fit-content; margin: 0 auto 10px; padding: 6px 12px;
    border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 630 13px/1.2 var(--font-text); }
  .hero { position: relative; height: 210px; margin: 4px 0 16px; border-radius: 22px; overflow: hidden; }
  .wide { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .strip { position: absolute; inset: 0; display: flex; overflow-x: auto; scroll-snap-type: x mandatory; overscroll-behavior-x: contain; scrollbar-width: none; }
  .strip::-webkit-scrollbar { display: none; }
  .pic { flex: 0 0 100%; scroll-snap-align: start; scroll-snap-stop: always; }
  .pic img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .dots { position: absolute; left: 0; right: 0; bottom: 10px; display: flex; justify-content: center; gap: 5px; pointer-events: none; }
  .dots i { width: 6px; height: 6px; border-radius: 50%; background: rgba(255, 255, 255, 0.5); box-shadow: 0 0 4px rgba(0, 0, 0, 0.4); transition: transform var(--t-fast); }
  .dots i.on { background: #fff; transform: scale(1.25); }
  .org { position: absolute; left: 12px; top: 12px; }
  .org :global(.chip) { height: 26px; padding: 0 10px 0 6px; font-size: 12.5px; gap: 6px; -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); }
  .tag { position: absolute; right: 12px; top: 12px; }
  .title { margin-bottom: 6px; }
  .strike { text-decoration: line-through; color: var(--text-2); }
  .cancel { color: var(--danger-text); font-weight: 600; margin-bottom: 8px; }

  .facts { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin: 14px 0; }
  .fact { display: flex; gap: 10px; align-items: flex-start; padding: 12px; border-radius: var(--r-m); background: var(--surface-2); min-width: 0; text-align: left; }
  /* off campus: the place opens in 2GIS, so it wears their mark and green */
  .gis { --gis: #19AA1E; background: linear-gradient(rgba(25, 170, 30, 0.14), rgba(25, 170, 30, 0.14)), var(--surface-2); box-shadow: inset 0 0 0 1px rgba(25, 170, 30, 0.4); transition: transform var(--t-fast) var(--ease); }
  :global(:root[data-theme='light']) .gis { --gis: #0F7A14; }
  .gis:active { transform: scale(0.97); }
  .fact .go { color: var(--gis, var(--accent-text)); font-weight: 650; }
  .go :global(svg) { display: inline; vertical-align: -2px; margin-left: 1px; }
  .nw { white-space: nowrap; }
  .fi { color: var(--accent-text); display: flex; margin-top: 1px; }
  .fact > span:last-child { display: flex; flex-direction: column; min-width: 0; }
  .fact b { font: 640 14px/1.3 var(--font-text); }
  .fact i { font: 500 13px/1.3 var(--font-text); font-style: normal; color: var(--text-2); }

  .seats { margin: 4px 0 14px; }
  .bar { height: 6px; border-radius: 3px; background: var(--surface-2); overflow: hidden; }
  .bar span { display: block; height: 100%; border-radius: 3px; background: var(--accent); transition: width var(--t-slow) var(--ease); }
  .bar span.full { background: var(--danger); }
  .row { display: flex; justify-content: space-between; margin-top: 7px; }
  .red { color: var(--danger-text); }

  .friends { display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: var(--r-m); background: var(--surface-2); margin-bottom: 14px; }
  .stack { display: flex; }
  .addseats { display: flex; align-items: center; gap: 6px; margin-top: 8px; }
  .addseats .t-foot { margin-right: auto; }
  .addseats button { height: 30px; padding: 0 12px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 700 13px/1 var(--font-text); }
  .addseats button:active { transform: scale(0.94); }
  .ans { flex: 1; display: flex; gap: 8px; min-width: 0; }
  .yes { flex: 1; display: flex; align-items: center; justify-content: center; gap: 6px; min-width: 0; border-radius: var(--r-full);
    background: var(--success-soft); color: var(--success-text); font: 650 16px/1 var(--font-text); }
  .lead { margin: 4px 0 12px; }
  .lc { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; margin-bottom: 6px; border-radius: var(--r-m); background: var(--surface-2); }
  .ln { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .ln b { font: 650 14px/1.2 var(--font-text); }
  .lp { display: flex; flex-wrap: wrap; gap: 4px 10px; }
  .pa { font: 550 12.5px/1.3 var(--font-text); color: var(--text-3); }
  .pa.yes { color: var(--success-text); }
  .pa.no { color: var(--danger-text); }
  .talk { display: flex; align-items: center; gap: 12px; width: 100%; margin: 16px 0 4px; padding: 12px 12px 12px 10px; border-radius: var(--r-m); background: var(--surface-2); text-align: left; color: var(--text-3); }
  .talk:active { transform: scale(0.99); }
  .tk { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tk b { font: 650 15px/1.25 var(--font-text); color: var(--text); }
  .tk i { font: 500 13px/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .fl { flex: 1; min-width: 0; }
  .fl.dim { color: var(--text-2); }
  .inv { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px; border-radius: var(--r-full);
    background: var(--accent); color: #fff; font: 650 13.5px/1 var(--font-text); }
  .inv:active { transform: scale(0.95); }
  .stack :global(.av + .av) { margin-left: -8px; }
  .stack :global(.av) { box-shadow: 0 0 0 2px var(--surface-solid); }

  .day { display: flex; flex-direction: column; gap: 5px; padding: 11px 12px; margin: -2px 0 14px; border-radius: var(--r-m); background: var(--surface-2); }
  .day .dh { display: flex; align-items: center; gap: 6px; margin-bottom: 1px; }
  .day p { font: 550 14px/1.35 var(--font-text); }
  .day .warn { color: var(--warning-text); font-weight: 620; }
  .tools { display: flex; gap: 8px; margin: 0 0 14px; }
  .tools button { flex: 1; min-width: 0; height: 40px; display: flex; align-items: center; justify-content: center; gap: 6px; border-radius: 12px;
    background: var(--accent-soft); color: var(--accent-text); font: 630 13.5px/1 var(--font-text); white-space: nowrap; }
  .tools button:active { transform: scale(0.96); }
  .kill { margin: 20px 0 4px; }
  .rep { display: block; margin: 22px auto 4px; padding: 8px 10px; font: 600 13.5px/1 var(--font-text); color: var(--text-3); }
  .sec { margin: 8px 0 8px; }
  .desc { color: var(--text); white-space: pre-line; }

  .actions { display: flex; gap: 8px; align-items: center; }
  .ib { width: var(--ctl-l); height: var(--ctl-l); flex: none; border-radius: 16px; background: var(--surface-2); color: var(--text); display: flex; align-items: center; justify-content: center; transition: transform var(--t-fast) var(--ease), color var(--t-base); }
  .ib:active { transform: scale(0.94); }
  .ib.on { color: var(--warning); }
  /* the organizer's updates: an accent note pinned under the title */
  .ups { display: flex; flex-direction: column; gap: 8px; margin: 10px 0 2px; }
  .up { padding: 10px 12px; border-radius: 16px; background: var(--accent-soft); box-shadow: inset 3px 0 0 var(--accent); animation: upIn 420ms cubic-bezier(.2, .9, .25, 1.05) backwards; }
  .up.older { background: var(--surface-2); box-shadow: none; }
  .up-h { display: flex; align-items: center; gap: 6px; font: 650 12px/1.2 var(--font-text); color: var(--accent-text); }
  .up.older .up-h { color: var(--text-3); }
  .up-x { margin-left: auto; display: flex; padding: 2px; color: var(--text-3); }
  .up p { margin-top: 4px; font: 500 15px/1.4 var(--font-text); white-space: pre-line; overflow-wrap: anywhere; }
  .up-more, .up-add { align-self: flex-start; display: inline-flex; align-items: center; gap: 6px; padding: 4px 2px; font: 640 14px/1 var(--font-text); color: var(--accent-text); }
  .up-new { display: flex; flex-direction: column; gap: 8px; padding: 10px 12px; border-radius: 16px; background: var(--surface-2); }
  .up-new textarea { width: 100%; resize: none; background: none; color: var(--text); font: 500 15px/1.4 var(--font-text); }
  .up-acts { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  @keyframes upIn { from { opacity: 0; transform: translateY(6px); } }
  /* one tap after the event */
  .rate { display: flex; flex-direction: column; gap: 10px; margin: 12px 0 4px; padding: 14px; border-radius: 20px;
    background: radial-gradient(90% 120% at 50% 0%, rgba(124, 77, 255, 0.18), transparent 65%), var(--surface-2); text-align: center; }
  .rq { font: 720 17px/1.2 var(--font-display); letter-spacing: -0.015em; }
  .faces { display: flex; justify-content: space-between; gap: 6px; }
  .faces button { flex: 1; aspect-ratio: 1; max-width: 62px; border-radius: 18px; display: flex; align-items: center; justify-content: center; background: var(--surface);
    font-size: 30px; line-height: 1; transition: transform 260ms cubic-bezier(.2, 1.6, .4, 1), opacity var(--t-base), background-color var(--t-base); }
  .faces button:active { transform: scale(0.9); }
  .faces button.on { transform: scale(1.12); background: var(--accent-soft); box-shadow: inset 0 0 0 2px var(--accent); }
  .faces button.on :global(.emoji) { animation: hop 520ms cubic-bezier(.2, 1.6, .4, 1); }
  @keyframes hop { 30% { transform: translateY(-9px) scale(1.25) rotate(-8deg); } 60% { transform: translateY(0) scale(0.95); } }
  .faces button.dim { opacity: 0.4; }
  .rnote { display: flex; gap: 8px; align-items: center; }
  .rnote input { flex: 1; min-width: 0; height: 40px; padding: 0 12px; border-radius: var(--r-m); background: var(--surface); color: var(--text); font: 500 15px/1 var(--font-text); }
  .rsum { display: flex; flex-direction: column; gap: 6px; margin: 12px 0 4px; padding: 14px; border-radius: 20px; background: var(--surface-2); }
  .rs-top { display: flex; align-items: center; gap: 12px; margin-bottom: 4px; }
  .avg { font: 780 34px/1 var(--font-display); letter-spacing: -0.03em; }
  .rs-top span:last-child { display: flex; flex-direction: column; gap: 2px; }
  .rs-top b { font: 680 15px/1.2 var(--font-text); }
  .rs-row { display: flex; align-items: center; gap: 8px; }
  .rf { width: 22px; display: flex; justify-content: center; }
  .rbar { flex: 1; height: 6px; border-radius: 3px; background: var(--surface-3); overflow: hidden; }
  .rbar > span { display: block; height: 100%; border-radius: 3px; background: var(--grad-accent); }
  .rn { width: 24px; text-align: right; font: 650 12.5px/1 var(--font-text); color: var(--text-2); }
  .rc { display: flex; gap: 8px; padding-top: 8px; margin-top: 2px; border-top: 1px solid var(--line); font: 500 14px/1.4 var(--font-text); }
  .rc :global(.emoji) { flex: none; }
  .chatrow { margin-top: 12px; }
  .vol { display: flex; flex-direction: column; gap: 12px; margin-top: 16px; padding: 14px; }
  .vh { display: flex; align-items: center; gap: 12px; color: var(--accent-text); }
  .vh span { display: flex; flex-direction: column; gap: 2px; }
  .vh b { color: var(--text); font: 650 15.5px/1.25 var(--font-text); }
  .vs { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
  .vs .ok { color: var(--success-text, var(--accent-text)); font: 650 15px/1.2 var(--font-text); }
  .vx { height: 30px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-2); color: var(--text-2); font: 620 13px/1 var(--font-text); }
</style>
