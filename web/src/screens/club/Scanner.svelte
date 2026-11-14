<script lang="ts">
  import { withNick } from '../../lib/perms';
  // The door scanner (Member+, full screen): our own camera on top (owner, Oct 15: so the screen around it
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
  import { api, type CheckinResult, type DoorPerson, type EventFull, type Id, type TeamList } from '../../lib/api';
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
  // qr: the Mark screen (owner, Nov 14): the rotating QR first («QR | Scanner»: the camera for tickets and
  // badges, a ticket's code typed there too), one line of counts (only whom this door records), then «People» (the
  // lists by department, marked by hand: People.svelte) and «Helper» (President/Vice). sess: a helper's session (the
  // QR they were let show, server checkin.qr_helping)
  let { overlay, id, names = false, only = false, qr = false, sess, ondone }: { overlay: Overlay; id: Id; names?: boolean; only?: boolean; qr?: boolean; sess?: Id; ondone?: () => void } = $props();
  let mode = $state<'scan' | 'qr'>(untrack(() => (qr ? 'qr' : 'scan')));

  let detail = $state<EventFull | null>(null);
  $effect(() => { api.event(id).then((d) => (detail = d)).catch(() => {}); });
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
  function recount() {
    api.door(id).then((l) => { people = l; count = { came: l.filter((d) => d.checkedInAt).length, going: l.length }; }).catch(() => {});
    api.teamList(id).then((x) => (team = x)).catch(() => {});
  }
  function toMode(m: 'scan' | 'qr') { haptic.tap(); if (m === 'qr') closeScanner(); else if (live === 'failed' && camera) scan(); }
  function openPeople() { haptic.tap(); sheets.doorPeople(id, recount); }
  // who may let a helper in: the club's President or Vice, or the app's admin (server checkin._hands_over)
  const board = $derived(session.me?.role === 'admin' || !!session.me?.memberships.some((m) => m.org.id === e?.org.id && (m.role === 'president' || m.role === 'vice')));
  async function addHelper() {
    haptic.tap();
    try { const s = await api.eventScreen(id); if (!s.started) await api.screenAct(s.session, 'start'); sheets.handQr(s.session); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // the capsule's title, live as the door fills up: "Scanner · 12 of 44" (SPEC §8.2)
  $effect(() => { overlay.title = qr ? t('mk.title') : names ? (count ? t('cap.marks', count) : t('door.title')) : count ? t('cap.scanner', count) : t('studio.scanner'); overlay.icon = ScanLine; });

  const MSG = { cancelled: 'scan.cancelled', not_found: 'scan.notFound', not_open: 'scan.notOpen', closed: 'scan.closed', paid: 'scan.paid' } as const;

  // one of our own QRs (the door's own check-in QR, a club's link...) read by this scanner: opened as if tapped, so a
  // team member scanning the door's QR here is marked himself (owner, Nov 14: people scanned it with this scanner)
  const ours = (raw: string) => raw.trim().match(/^(?:https?:\/\/)?t\.me\/KBTUappBot(?:\/\w+)?\?startapp=([\w-]{1,64})$/i)?.[1];
  let last = ''; // the code just read: a flagged receipt is let in by it after a look (admit)
  async function check(raw: string, admit = false) {
    const p = ours(raw);
    if (p) { haptic.tap(); leave(); sheets.deepLink(p); return; }
    if (busy || !raw.trim()) return;
    busy = true; last = raw;
    try {
      const r = await api.checkin(id, raw, admit);
      res = r; seq++;
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
      res = r; seq++; pendingAdmit = r.result === 'flagged' ? d : null;
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

  onMount(() => {
    panel.animate([{ opacity: 0, transform: 'translate3d(0,40px,0)' }, { opacity: 1, transform: 'none' }], { duration: 320, easing: 'cubic-bezier(.2,.9,.25,1)' });
    if (names) void openByName();
    else if (live === 'failed' && camera && mode === 'scan') scan();
    if (qr) recount();
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
      <div class="sw"><Segmented items={[{ value: 'qr', label: 'QR' }, { value: 'scan', label: t('studio.scanner') }]} bind:value={mode} onchange={toMode} /></div>
      {#if mode === 'qr'}<button class="qr" aria-label={t('studio.scanner')} onclick={() => { mode = 'scan'; toMode('scan'); }}><EventQr {overlay} event={id} {sess} embed onlast={recount} /></button>{/if}
    {:else if e}
      <h2 class="t-h3 clamp-2">{e.title}</h2>
      <p class="t-foot">{relDay(e.startsAt)}, {time(e.startsAt)} · {placeOf(e.place)}</p>
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
      <div class="quiet">
        {#if lists}<Button kind="secondary" size="m" onclick={openPeople}>{#snippet icon()}<UsersRound size={18} />{/snippet}{t('mk.people')}</Button>{/if}
        {#if board && !sess}<Button kind="secondary" size="m" onclick={addHelper}>{#snippet icon()}<UserPlus size={18} />{/snippet}{t('mk.helper')}</Button>{/if}
      </div>
    {/if}

    {#if names || (qr && (mode === 'qr' || aud === 'team'))}{:else}<!-- a team-only door has no tickets -->
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
</style>
