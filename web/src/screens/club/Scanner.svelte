<script lang="ts">
  import { withNick } from '../../lib/perms';
  // The door scanner (Member+, full screen): our own camera on top (so the screen around it
  // is ours: the result, the count, haptics, without a popup closing after each scan), Telegram's QR popup when the
  // camera is refused or missing, the typed code anywhere. It takes a
  // ticket or a badge QR (§4.4): a badge registers a person who didn't sign up, on a free event, at the door.
  // Each answer shows big — a name and avatar to compare with the face at the door. After a good scan the
  // camera comes back by itself so a queue moves fast; an error waits for a tap. A club's own event has no tickets
  // (`names`): it opens on the people expected, marked by name ("Who came").
  import { onMount, untrack } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import UserSearch from '@lucide/svelte/icons/user-search';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import Plus from '@lucide/svelte/icons/plus';
  import Qr from '../../ui/Qr.svelte';
  import { QR_TONE } from '../../lib/awards';
  import Minus from '@lucide/svelte/icons/minus';
  import { api, ApiErr, type CheckinResult, type DoorPerson, type EventFull, type Id, type TeamList } from '../../lib/api';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { eventById } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { t, tn, placeOf } from '../../lib/i18n/index.svelte';
  import { hit } from '../../lib/search';
  import { relDay, time } from '../../lib/time';
  import { haptic, inTelegram, scanQr, closeScanner, tg } from '../../lib/tg';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import QrCam from '../../ui/QrCam.svelte';
  import Field from '../../ui/Field.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import EventQr from './EventQr.svelte';

  // only: a scanner-only door helper (server crew.py): tickets and badges of people going, no list by name
  // qr: the Mark screen: the rotating QR first («QR | Scanner»: the camera for tickets and
  // badges, a ticket's code typed there too), one line of counts (only whom this door records), then «People» (the
  // lists by department, marked by hand: People.svelte) and «Helper» (President/Vice). sess: a helper's session (the
  // QR they were let show, server checkin.qr_helping)
  let { overlay, id, names = false, only = false, qr = false, sess, ondone }: { overlay: Overlay; id: Id; names?: boolean; only?: boolean; qr?: boolean; sess?: Id; ondone?: () => void } = $props();
  let mode = $state<'scan' | 'qr' | 'entry'>(untrack(() => (qr ? 'qr' : 'scan')));

  let detail = $state<EventFull | null>(null);
  // the Mark screen's counts once the event says who I am at its door (a scanner-only helper reads no lists: no 403s)
  $effect(() => { api.event(id).then((d) => { detail = d; if (qr) recount(); }).catch(() => {}); });
  const e = $derived(eventById(id) ?? detail);
  const camera = inTelegram && /^(ios|android)$/.test(tg.platform) && tg.can('6.4');
  // our camera (ui/QrCam) until it fails (refused, none), then Telegram's popup takes over
  let live = $state<'off' | 'on' | 'failed'>('mediaDevices' in navigator ? 'off' : 'failed');

  let res = $state<CheckinResult | null>(null);
  let seq = $state(0);
  let count = $state<{ came: number; going: number } | null>(null);
  let code = $state('');
  let busy = $state(false);
  let panel: HTMLDivElement;
  let gone = false;
  let cam = $state(untrack(() => !names));  // off when leaving: the light goes out with the fade, not after it

  // the door's count from its list (who's going, who came) and the team's list (server checkin.team), read as the screen
  // opens, as the QR counts someone and after a hand mark; a scan's answer brings the guests' count itself. Either list
  // refused (a scanner-only helper): no count of it, and no «People»
  let team = $state<TeamList | null>(null);
  const aud = $derived(team?.audience ?? detail?.audience ?? 'both');
  const teamCame = $derived(team ? team.rows.filter((r) => r.at).length : 0);
  // let in by the helper's QR, or named for the scanner only: the QR and the camera, said so plainly (no lists)
  const scanOnly = $derived(qr && detail?.myCrew === 'scan');
  // 18+ at the door (age_check): no self check-in by the rotating QR, it would skip the ID; the entrance QR opens
  // the ticket, the scanner reads it and asks 18+ (owner, Nov 21)
  const aged18 = $derived(!!e?.ageCheck);
  $effect(() => { if (aged18 && mode === 'qr') untrack(() => { mode = 'entry'; closeScanner(); }); });
  // list buyers not in the app yet (guest list): the student ID and surname from their ID card let them in by hand
  let pend = $state<{ pending: number; pendingCame: number } | null>(null);
  let pid = $state(''), psur = $state(''), pbusy = $state(false);
  let plet = $state<{ sid: string; sur: string; adult: boolean | null } | null>(null);
  $effect(() => { if (qr && !only && e?.guestList) api.doorPending(id).then((x) => (pend = x)).catch(() => {}); });
  async function letIn(adult?: boolean) {
    const sid = plet && adult !== undefined ? plet.sid : pid.trim().toUpperCase(), sur = plet && adult !== undefined ? plet.sur : psur.trim();
    if (!sid || !sur) return;
    pbusy = true;
    try {
      const r = await api.letIn(id, sid, sur, adult);
      pend = { pending: r.pending, pendingCame: r.pendingCame }; plet = { sid, sur, adult: r.adult }; pid = ''; psur = ''; haptic.ok();
    } catch (x) { say(x instanceof ApiErr && x.code === 'not_found' ? t('mk.letInNo') : t('common.error'), 'warning_3d'); }
    pbusy = false;
  }
  // outsiders let in without the app (ID checked by eye): one anonymous count, +1/-1 at once, the server's word after
  let extra = $state<number | null>(null);
  $effect(() => { if (qr && !only) api.doorExtra(id).then((x) => (extra = x.extra)).catch(() => {}); });
  function stepExtra(step: 1 | -1) {
    if (extra == null || (step < 0 && extra === 0)) return;
    haptic.tap(); extra += step;
    api.doorExtra(id, step).then((x) => (extra = x.extra)).catch(() => { extra = Math.max(0, (extra ?? 0) - step); say(t('common.error'), 'warning_3d'); });
  }
  function recount() {
    if (detail?.myCrew === 'scan') return;
    api.door(id).then((l) => { people = l; count = { came: l.filter((d) => d.checkedInAt).length, going: l.length }; }).catch(() => {});
    api.teamList(id).then((x) => (team = x)).catch(() => {});
  }
  function toMode(m: 'scan' | 'qr' | 'entry') { haptic.tap(); if (m !== 'scan') closeScanner(); else if (live === 'failed' && camera) scan(); }
  function openPeople() { haptic.tap(); sheets.doorPeople(id, recount); }
  // who may let a helper in: the club's President or Vice, or the app's admin (server checkin._hands_over)
  const board = $derived(session.me?.role === 'admin' || !!session.me?.memberships.some((m) => m.org.id === e?.org.id && (m.role === 'president' || m.role === 'vice')));
  // one place for helpers (CrewSheet): the helper's QR and the people named, with what each may do
  function addHelper() { haptic.tap(); sheets.crew(id); }
  // the capsule's title, live as the door fills up: "Scanner · 12 of 44" (SPEC §8.2)
  $effect(() => { overlay.title = qr ? t('mk.title') : names ? (count ? t('cap.marks', count) : t('door.title')) : count ? t('cap.scanner', count) : t('studio.scanner'); overlay.icon = ScanLine; });

  const MSG = { cancelled: 'scan.cancelled', not_found: 'scan.notFound', not_open: 'scan.notOpen', closed: 'scan.closed', paid: 'scan.paid' } as const;

  // one of our own QRs (the door's own check-in QR, a club's link...) read by this scanner: opened as if tapped, so a
  // team member scanning the door's QR here is marked himself (people scanned it with this scanner)
  const ours = (raw: string) => raw.trim().match(/^(?:https?:\/\/)?t\.me\/KBTUappBot(?:\/\w+)?\?startapp=([\w-]{1,64})$/i)?.[1];
  let last = ''; // the code just read: a flagged receipt is let in by it after a look (admit)
  async function check(raw: string, admit = false) {
    const p = ours(raw);
    if (p) { haptic.tap(); leave(); sheets.deepLink(p); return; }
    if (busy || !raw.trim()) return;
    busy = true; last = raw;
    try {
      const r = await api.checkin(id, raw, admit);
      res = r; seq++; aged = false;
      if (r.result === 'ok' || r.result === 'already') count = { came: r.came, going: r.going };
      if (r.result === 'ok') {
        haptic.ok();
        code = '';
        if (camera && live === 'failed') setTimeout(() => { if (!gone) scan(); }, 1100); // the popup: the next one in the queue
      } else haptic.error(); // "already" too: a ticket used twice is a problem at the door
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); } finally { busy = false; }
  }
  const scan = () => scanQr(t('scan.prompt'), (text) => { void check(text); return true; });

  // ---- no QR (a dead phone): find them among the people going and check in by hand (§4.4) ----
  let byName = $state(untrack(() => names));
  let people = $state<DoorPerson[] | null>(null);
  const lists = $derived(!!team || (aud !== 'team' && !!people));
  let who = $state('');
  let undoFor = $state<number | null>(null); // just checked in by hand: "Undo" on the result for a few seconds
  let undoTimer: ReturnType<typeof setTimeout> | undefined;
  const found = $derived((people ?? []).filter((d) => !who.trim() || hit(who, [withNick(d.person.realName, d.person)])).slice(0, 40));
  async function openByName() {
    byName = true;
    try { people = await api.door(id); } catch { people = []; }
  }
  let pendingAdmit = $state<DoorPerson | null>(null); // a flagged receipt by name: let in by it after a look
  async function mark(d: DoorPerson, admit = false) {
    if (busy) return;
    busy = true;
    try {
      const r = await api.checkinPerson(id, d.person.id, admit);
      res = r; seq++; aged = false; pendingAdmit = r.result === 'flagged' ? d : null;
      if (r.result === 'ok' || r.result === 'already') count = { came: r.came, going: r.going };
      if (r.result === 'ok') {
        haptic.ok(); who = '';
        undoFor = d.person.id; clearTimeout(undoTimer); undoTimer = setTimeout(() => (undoFor = null), 8000);
      } else haptic.error();
      people = await api.door(id);
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); } finally { busy = false; }
  }
  async function undo() {
    const uid = undoFor;
    if (uid == null) return;
    try {
      await api.undoCheckin(id, uid);
      undoFor = null; res = null;
      if (count) count = { ...count, came: count.came - 1 };
      haptic.soft(); say(t('door.undone'), 'waving_hand_3d_default');
      people = await api.door(id);
    } catch { say(t('common.error'), 'warning_3d'); }
  }

  // ---- an age_check event (server organizing.mark_age): the ID looked at, one tap marks 18+ or not; the queue never waits ----
  let aged = $state(false); // marked by a tap on this result (else a mark shown came from the imported list)
  async function setAge(adult: boolean) {
    const r = res;
    if (!r || !('person' in r) || r.adult === adult) return;
    const was = r.adult ?? null, uid = r.person.id, d = people?.find((x) => x.person.id === uid);
    r.adult = adult; aged = true; if (d) d.adult = adult; // at once; back if the server says no
    haptic.select();
    try { await api.markAge(id, uid, adult); } catch {
      r.adult = was; if (d) d.adult = was;
      haptic.error(); say(t('common.error'), 'warning_3d');
    }
  }
  let notifying = $state(false);
  async function notifyMinors() {
    if (!(await sheets.ask({ title: t('age.notifyAsk'), text: t('age.notifyText'), ok: t('age.notifyOk'), cancel: t('common.cancel') }))) return;
    notifying = true;
    try {
      const { count: n } = await api.notifyMinors(id);
      haptic.ok(); say(n ? t('age.sent', { n }) : t('age.nobody'), 'speech_balloon_3d');
    } catch (x) {
      haptic.error(); say(t(x instanceof ApiErr && x.code === 'rate_limited' ? 'age.tooOften' : 'common.error'), 'warning_3d');
    } finally { notifying = false; }
  }

  onMount(() => {
    panel.animate([{ opacity: 0, transform: 'translate3d(0,40px,0)' }, { opacity: 1, transform: 'none' }], { duration: 320, easing: 'cubic-bezier(.2,.9,.25,1)' });
    if (names) void openByName();
    else if (live === 'failed' && camera && mode === 'scan') scan();
    const show = hideChrome();
    return () => { show?.(); ondone?.(); };
  });

  function leave() {
    if (gone) return;
    gone = true;
    closeScanner(); cam = false;
    const a = panel.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 200, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });
</script>

<div class="panel" bind:this={panel}>
  <header class="bar">
    {#if !inTelegram}<button class="x" onclick={() => close(overlay.id)} aria-label={t('common.close')}><X size={22} /></button>{/if}
  </header>

  <div class="body scroll">
    {#if qr}
      <div class="sw"><Segmented items={[...(aged18 ? [] : [{ value: 'qr' as const, label: 'QR' }]), { value: 'scan' as const, label: t('studio.scanner') }, ...(aud !== 'team' ? [{ value: 'entry' as const, label: t('mk.entry') }] : [])]} bind:value={mode} onchange={toMode} /></div>
      {#if mode === 'entry'}
        <!-- the entrance's QR (owner, Nov 21): a guest's own camera opens the app on their ticket (tk_: no ticket -> the event, its sign-in) -->
        <div class="entry"><div class="plate"><Qr text={`https://t.me/KBTUappBot?startapp=tk_${id}`} tone={QR_TONE} /></div><p class="t-foot">{t('mk.entryHint')}</p></div>
      {/if}
      {#if mode === 'qr'}<button class="qr" aria-label={t('studio.scanner')} onclick={() => { mode = 'scan'; toMode('scan'); }}><EventQr {overlay} event={id} {sess} embed onlast={recount} /></button>{/if}
    {:else if e}
      <h2 class="t-h3 clamp-2">{e.title}</h2>
      <p class="t-foot">{relDay(e.startsAt)}, {time(e.startsAt)} · {placeOf(e.place, e.online)}</p>
      <p class="count">{count ? t('scan.came', count) : tn('event.going', e.taken)}</p>
    {/if}

    {#if !names && live !== 'failed' && mode === 'scan'}
      <!-- the camera stays outside {#key}: a new <video> per scan had no stream (black after the first scan) -->
      <div class="cam" class:good={res?.result === 'ok'} class:warn={res?.result === 'already' || res?.result === 'flagged' || res?.result === 'ask_org'} class:bad={!!res && !['ok', 'already', 'flagged', 'ask_org'].includes(res.result)}>
        {#if cam}<QrCam bind:live paused={busy} onscan={(v) => void check(v)} />{/if}
        {#if live === 'off'}<span class="wait"><ScanLine size={36} /></span>{/if}
        {#key seq}<span class="aim" class:flash={seq > 0}></span>{/key}
      </div>
    {/if}

    {#key seq}
      {#if res && mode === 'scan'}
        {#if res.result === 'flagged' || res.result === 'ask_org'}
          <!-- a receipt nobody checked: nothing recorded yet (server organizing._held); its organizer lets them in after a
               look, anyone else is only told to call one (never why) -->
          <div class="res warn">
            <Avatar person={res.person} size={84} />
            <b class="nm">{withNick(res.person.realName, res.person)}</b>
            {#if res.result === 'ask_org'}<span class="flag"><TriangleAlert size={16} />{t('mk.askOrg')}</span>
            {:else}<span class="flag"><TriangleAlert size={16} />{t('mk.flagged')}</span>
              <Button kind="secondary" size="s" disabled={busy} onclick={() => (byName && pendingAdmit != null ? mark(pendingAdmit, true) : check(last, true))}>{t('mk.admit')}</Button>{/if}
          </div>
        {:else if res.result === 'ok' || res.result === 'already'}
          <div class="res" class:good={res.result === 'ok'} class:warn={res.result === 'already'}>
            <Avatar person={res.person} size={84} />
            <b class="nm">{withNick(res.person.realName, res.person)}</b>
            <span>{res.result === 'ok' ? t('scan.ok') : t('scan.already', { time: time(res.at) })}</span>
            {#if res.walkIn || res.late >= 5 || undoFor === res.person.id}<span class="more">{[undoFor === res.person.id && t('door.byHand'), res.walkIn && t('scan.walkIn'), res.late >= 5 && t('scan.late', { n: res.late })].filter(Boolean).join(' · ')}</span>{/if}
            {#if res.flagged}<span class="flag"><TriangleAlert size={16} />{t('scan.flagged')}</span>{/if}
            {#if undoFor === res.person.id}<Button kind="secondary" size="s" onclick={undo}>{t('door.undo')}</Button>{/if}
            {#if e?.ageCheck}
              <span class="more">{t(res.adult != null && !aged ? 'age.listed' : 'age.look')}</span>
              <div class="age">
                <Button kind={res.adult === true ? 'primary' : 'secondary'} size="l" full onclick={() => setAge(true)}>{t('age.adult')}</Button>
                <Button kind={res.adult === false ? 'primary' : 'secondary'} destructive={res.adult === false} size="l" full onclick={() => setAge(false)}>{t('age.minor')}</Button>
              </div>
            {/if}
          </div>
        {:else}
          <div class="res bad"><span class="ic"><TriangleAlert size={44} /></span><b class="nm">{t(MSG[res.result])}</b></div>
        {/if}
      {/if}
    {/key}

    {#if !names && mode === 'scan'}
      {#if live === 'failed' && camera}
        <Button kind="primary" size="l" full onclick={scan}>{#snippet icon()}<ScanLine size={20} />{/snippet}{t('scan.open')}</Button>
      {:else if live === 'failed'}
        <p class="t-callout hint">{t('scan.noCamera')}</p>
      {/if}
    {/if}

    {#if qr}
      <!-- one line: only whom this door records (the event's audience); a tap opens the lists -->
      {#if (aud !== 'guests' && team) || (aud !== 'team' && count)}
        <button class="tally" disabled={!lists} onclick={openPeople}>{[aud !== 'guests' && team && t('mk.team', { n: teamCame, m: team.rows.length }), aud !== 'team' && count && t('mk.guests', { n: count.came })].filter(Boolean).join(' · ')}</button>
      {/if}
      {#if pend && pend.pending}
        <section class="pend">
          <p class="t-foot">{t('mk.pending', { n: pend.pendingCame, m: pend.pending })}</p>
          <Field label={t('mk.letInId')} bind:value={pid} autocomplete="off" placeholder="24B030001" />
          <Field label={t('mk.letInSurname')} bind:value={psur} autocomplete="off" />
          <Button kind="secondary" size="m" full loading={pbusy} disabled={!pid.trim() || !psur.trim()} onclick={() => letIn()}>{t('mk.letIn')}</Button>
          {#if plet}
            <p class="ok">{t('mk.letInOk', { id: plet.sid })}{plet.adult === true ? ' · 18+' : plet.adult === false ? ' · ' + t('age.minor') : ''}</p>
            {#if e?.ageCheck}<div class="ages"><Button kind={plet.adult === true ? 'primary' : 'secondary'} size="m" onclick={() => letIn(true)}>{t('age.adult')}</Button>
              <Button kind={plet.adult === false ? 'primary' : 'secondary'} destructive={plet.adult === false} size="m" onclick={() => letIn(false)}>{t('age.minor')}</Button></div>{/if}
          {/if}
        </section>
      {/if}
      {#if extra != null && aud !== 'team'}
        <div class="extra">
          <span>{t('mk.extra')} · <b>{extra}</b></span>
          <Button kind="secondary" size="s" round label="−1" disabled={!extra} onclick={() => stepExtra(-1)}>{#snippet icon()}<Minus size={18} />{/snippet}</Button>
          <Button kind="secondary" size="s" round label="+1" onclick={() => stepExtra(1)}>{#snippet icon()}<Plus size={18} />{/snippet}</Button>
        </div>
      {/if}
      {#if scanOnly}<p class="t-foot only">{t('mk.scanOnly')}</p>{/if}
      <div class="quiet">
        {#if lists}<Button kind="secondary" size="m" onclick={openPeople}>{#snippet icon()}<UsersRound size={18} />{/snippet}{t('mk.people')}</Button>{/if}
        {#if board && !sess}<Button kind="secondary" size="m" onclick={addHelper}>{#snippet icon()}<UserPlus size={18} />{/snippet}{t('mk.helper')}</Button>{/if}
      </div>
    {/if}

    {#if e?.ageCheck && aud !== 'team' && !only && !scanOnly && !sess}
      <Button kind="secondary" size="m" full loading={notifying} onclick={notifyMinors}>{#snippet icon()}<MessageCircle size={18} />{/snippet}{t('age.notify')}</Button>
    {/if}

    {#if names || (qr && (mode !== 'scan' || aud === 'team'))}{:else}<!-- a team-only door has no tickets -->
      <!-- engine: Field should pass autocapitalize and spellcheck (a ticket code: capitals, no spelling); set here on its input until then -->
      <form class="manual" onsubmit={(ev) => { ev.preventDefault(); void check(code); }}
        {@attach (f) => { const i = f.querySelector('input'); i?.setAttribute('autocapitalize', 'characters'); i?.setAttribute('spellcheck', 'false'); }}>
        <Field label={t('scan.code')} bind:value={code} autocomplete="off" enterkeyhint="done" placeholder="K7 M2" />
        <Button kind="secondary" size="l" type="submit" loading={busy} disabled={!code.trim()}>{t('scan.mark')}</Button>
      </form>
    {/if}

    {#if only || qr}{:else if !byName}
      <Button kind="secondary" size="l" full onclick={openByName}>{#snippet icon()}<UserSearch size={18} />{/snippet}{t('door.byName')}</Button>
    {:else}
      <section class="door">
        <SearchField bind:value={who} placeholder={t('door.search')} />
        {#if people}
          {#if found.length}
            <Group>
              {#each found as d (d.person.id)}
                {#snippet end()}
                  {#if d.adult != null}<Tag tone={d.adult ? 'neutral' : 'warning'}>{t(d.adult ? 'age.adult' : 'age.u18')}</Tag>{/if}
                  {#if d.checkedInAt}<Tag tone="success">{t('door.came', { time: time(d.checkedInAt) })}</Tag>
                  {:else}<Button kind="secondary" size="s" disabled={busy} onclick={() => mark(d)}>{t('door.mark')}</Button>{/if}
                {/snippet}
                <Row dense title={withNick(d.person.realName, d.person)} trailing={end} disabled={!!d.checkedInAt}>
                  {#snippet lead()}<Avatar person={d.person} size={36} tappable={false} />{/snippet}
                </Row>
              {/each}
            </Group>
          {:else}
            <EmptyState inline text={t('door.none')} />
          {/if}
        {/if}
      </section>
    {/if}
  </div>
</div>

<style>
  .flag { display: inline-flex; align-items: center; gap: 6px; padding: 6px 12px; border-radius: var(--r-full); background: var(--warning-soft); color: var(--warning-text); font: 650 13.5px/1.2 var(--font-text); }
  .panel { position: absolute; inset: 0; z-index: var(--z-sheet); background: var(--glow), var(--bg); }
  .bar { position: absolute; left: 0; right: 0; top: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2)); height: 38px; z-index: 1;
    display: flex; align-items: center; justify-content: center; pointer-events: none; }
  .x { position: absolute; left: 12px; width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--surface); color: var(--text); pointer-events: auto; }

  .body { position: absolute; inset: max(48px, var(--top)) 0 0; display: flex; flex-direction: column; gap: 12px; padding: 6px var(--gutter) calc(var(--safe-bottom) + 20px); }
  .body > p.t-foot { margin-top: -8px; }
  .count { font: 760 28px/1.1 var(--font-display); letter-spacing: -0.02em; margin: 6px 0 2px; }
  .sw, .qr { flex: none; }
  .qr { display: flex; justify-content: center; }
  .qr { padding: 0; border: 0; background: none; }
  .tally { align-self: center; padding: var(--s-1) var(--s-3); border: 0; background: none; color: var(--text); font: 700 var(--fs-t3)/1.25 var(--font-display);
    letter-spacing: -0.01em; text-align: center; font-variant-numeric: tabular-nums; }
  .quiet { display: flex; gap: var(--s-2); }
  .only { margin: 0; text-align: center; color: var(--text-2); }
  .quiet > :global(*) { flex: 1 1 0; min-width: 0; }

  .res { display: flex; flex-direction: column; align-items: center; gap: 8px; padding: 22px 16px; border-radius: var(--r-l); text-align: center;
    animation: pop 360ms cubic-bezier(.2, .9, .25, 1.2); }
  .good { background: var(--success-soft); color: var(--success-text); }
  .warn { background: var(--warning-soft); color: var(--warning-text); }
  .bad { background: var(--danger-soft); color: var(--danger-text); }
  .nm { font: 720 22px/1.2 var(--font-display); color: var(--text); }
  .bad .nm { font-size: 18px; }
  .more { font: 650 14px/1.3 var(--font-text); color: var(--text-2); }
  .ic { display: flex; }
  .age { align-self: stretch; display: flex; gap: var(--s-2); margin-top: 4px; }
  .age > :global(*) { flex: 1 1 0; min-width: 0; }
  @keyframes pop { from { opacity: 0; transform: scale(0.92); } }

  .hint { color: var(--text-2); }
  .cam { position: relative; flex: none; width: min(100%, 56vh); margin-inline: auto; aspect-ratio: 1; border-radius: var(--r-l); overflow: hidden; background: #000; }
  .wait { position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; color: rgba(255, 255, 255, 0.5); }
  .aim { position: absolute; inset: 18%; border-radius: 22px; box-shadow: 0 0 0 2px rgba(255, 255, 255, 0.75), 0 0 0 999px rgba(0, 0, 0, 0.28); pointer-events: none; }
  .cam.good .aim { box-shadow: 0 0 0 4px var(--success), 0 0 0 999px rgba(0, 0, 0, 0.28); }
  .cam.warn .aim { box-shadow: 0 0 0 4px var(--warning), 0 0 0 999px rgba(0, 0, 0, 0.28); }
  .cam.bad .aim { box-shadow: 0 0 0 4px var(--danger), 0 0 0 999px rgba(0, 0, 0, 0.28); }
  .aim.flash { animation: pulse 420ms cubic-bezier(.2, .9, .25, 1.2); }
  @keyframes pulse { from { transform: scale(1.08); } }
  .door { display: flex; flex-direction: column; gap: var(--s-3); }
  .manual { display: flex; gap: var(--s-2); align-items: flex-end; }
  .manual > :global(:first-child) { flex: 1; min-width: 0; }
  .manual :global(input) { letter-spacing: 0.06em; text-transform: uppercase; }
  .entry { display: grid; justify-items: center; gap: 10px; }
  .entry .plate { width: min(78vw, 300px); aspect-ratio: 1; padding: 14px; border-radius: var(--r-l); background: white; }
  .entry p { text-align: center; }
  .pend { display: grid; gap: 8px; }
  .pend .ok { color: var(--success-text); text-align: center; }
  .pend .ages { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
  .extra { display: flex; align-items: center; gap: 8px; justify-content: center; }
  .extra span { flex: 1; color: var(--text-2); }
</style>
