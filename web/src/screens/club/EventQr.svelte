<script lang="ts">
  // An event's rotating check-in QR on the organizer's own phone, for a hall with no big screen (admin/BadgeQr.svelte's
  // look). Opening starts the event's session if it isn't running; closing leaves it running and keeps every mark.
  // The code is the server's, and each poll renews its 15 s lease: nothing showing it, it stops (server checkin.py).
  // `sess`: a session someone was let help (the same QR, a running session only); with `hand`, the QR that lets them in.
  import { onMount } from 'svelte';
  import { api, ApiErr, type Id, type ScreenSession } from '../../lib/api';
  import { QR_TONE } from '../../lib/awards';
  import { close, removeOverlay, hideChrome, say, overlays, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets, doorMode } from '../../lib/state/sheets';
  import { loadMe, session } from '../../lib/state/session.svelte';
  import { eventById } from '../../lib/state/data.svelte';
  import { time } from '../../lib/time';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Qr from '../../ui/Qr.svelte';
  import '../../lib/qrnow'; // its code in the first frame (lib/qr.svelte.ts)
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import CloseX from '../../ui/CloseX.svelte';
  import Button from '../../ui/Button.svelte';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import UserPlus from '@lucide/svelte/icons/user-plus';

  // `door`: the registration mode's QR half (Scanner.svelte's switch): its scanner button swaps back in place
  let { overlay, event, sess, hand = false, scanner = false, door = false }: { overlay: Overlay; event?: Id | null; sess?: Id; hand?: boolean; scanner?: boolean; door?: boolean } = $props();
  $effect(() => { overlay.title = t(hand ? 'scr.hand' : 'aw.show'); overlay.icon = QrCode; overlay.theme = 'dark'; });

  let q = $state<ScreenSession | null>(null), note = $state('');
  let sid: Id, timer: ReturnType<typeof setTimeout> | undefined, gone = false;
  let off = $state(false), epoch = 0, waited = false; // epoch: a poll started before a pause or "remove all" has nothing to say after it
  const covered = $derived([...overlays].reverse().find((o) => !o.closing)?.id !== overlay.id);
  const halt = () => { epoch++; clearTimeout(timer); };
  const out = $derived(q?.phase === 'out');
  const fetchQr = () => (hand ? api.screenHand(sid) : api.screenAct(sid, 'show'));
  const poll = () => { if (covered || off) return; const at = epoch; void fetchQr().then((r) => { if (at === epoch) got(r); }, (e) => { if (at === epoch) stop(e); }); };
  // Under the scanner nothing shows this code, so nothing renews its lease; back on top, a fresh one at once
  $effect(() => { if (covered) { waited = true; halt(); } else if (waited) { waited = false; poll(); } });
  function got(r: ScreenSession) {
    if (gone) return;
    if (q && (hand ? (r.helpers ?? 0) > (q.helpers ?? 0) : r.done > q.done)) haptic.soft();
    q = r;
    if (!r.ended) timer = setTimeout(poll, Math.min(r.next, 3) * 1000 + 300); // the next code as the slot turns, the count meanwhile
  }
  // why the server refused (checkin._door): not open yet (when), closed, an organizers' QR; else as before
  function why(e: unknown): string {
    if (!(e instanceof ApiErr)) return t('common.error');
    if (e.message === 'not_open' && typeof e.data.at === 'number') return t('scr.doorAt', { time: time(e.data.at) });
    if (e.code === 'closed') return t('scr.closed');
    if (e.message === 'door_staff') return t('scr.staffOnly');
    return t(sess && e.code === 'forbidden' ? 'scr.helpEnded' : 'common.error');
  }
  function stop(e: unknown) {
    if (gone) return;
    const no = e instanceof ApiErr && (e.code === 'forbidden' || e.code === 'closed');
    if (!q || no) { q = null; note = why(e); if (e instanceof ApiErr && e.code === 'forbidden') void loadMe(true); return; } // (the capsule goes too)
    timer = setTimeout(poll, 3000); // a blip of the network: try again
  }
  async function open() {
    if (sess) { sid = sess; got(await fetchQr()); return; }
    const s = await api.eventScreen(event!);
    sid = s.session;
    if (!s.started) { await api.screenAct(sid, 'start'); void loadMe(true); } // the capsule
    got(await api.screenAct(sid, 'show'));
  }

  const toScanner = () => { haptic.tap(); if (door) { doorMode('scan'); close(overlay.id); sheets.scanner(event!, false, true); } else sheets.scannerOnly(event!); };
  // who may let a helper in: the club's President or Vice, or the app's admin (server checkin._hands_over), here at the event's QR
  const board = $derived(!sess && !hand && !!event && (session.me?.role === 'admin' || !!session.me?.memberships.some((m) => m.org.id === eventById(event)?.org.id && (m.role === 'president' || m.role === 'vice'))));

  async function handsOff() {
    if (!(await sheets.ask({ title: t('scr.handOffAsk'), text: t('scr.handOffText'), ok: t('scr.handOff'), cancel: t('scr.keep') }))) return;
    off = true; halt();
    let r: ScreenSession | undefined;
    try { r = await api.screenHandsOff(sid); haptic.ok(); } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    off = false;
    if (r) got(r); else poll();
  }

  let wrap: HTMLDivElement, scrim: HTMLDivElement;
  onMount(() => {
    haptic.soft();
    open().catch(stop);
    wrap.animate([{ opacity: 0, transform: 'translate3d(0,50px,0) scale(0.94)' }, { opacity: 1, transform: 'none' }], { duration: 420, easing: 'cubic-bezier(.2,.9,.25,1.1)' });
    scrim.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 240, easing: 'ease-out' });
    const chrome = hideChrome();
    return () => { chrome(); clearTimeout(timer); };
  });

  function leave() {
    if (gone) return;
    gone = true;
    clearTimeout(timer);
    wrap.animate([{ opacity: 1 }, { opacity: 0, transform: 'translate3d(0,40px,0) scale(0.96)' }], { duration: 220, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
    scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 220, easing: 'ease-in', fill: 'forwards' }).onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });
</script>

<div class="scrim" bind:this={scrim} role="presentation"></div>
<div class="wrap" bind:this={wrap}>
  <div class="page">
    {#if q}<b class="head">{q.title}</b>{/if}
    <div class="plate" class:off={!q?.param}>
      {#if q?.param}
        <Qr text={`https://t.me/KBTUappBot?startapp=${q.param}`} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr><!-- a new code redraws in place: no blank frame -->
      {:else if q?.ended || note}
        <p class="note">{note || t('scr.closed')}</p>
      {/if}
    </div>
    {#if q && hand}
      {#if q.param}<p class="hint">{t('scr.handHint')}</p>{/if}
      <p class="got">{t('scr.helpersN', { n: q.helpers ?? 0 })}</p>
      {#if q.helpers}<Button kind="secondary" size="m" loading={off} onclick={handsOff}>{t('scr.handOff')}</Button>{/if}
    {:else if q}
      {#if q.param}<p class="hint">{t(out ? 'scr.outScan' : 'scr.scan')}</p>{/if}
      <p class="got"><b>{out ? q.departed : q.done}</b>{#if out} / {q.done}{:else if q.expected} / {q.expected}{/if} {t(out ? 'scr.outDone' : 'scr.done')}</p>
      {#if q.last && !out}<p class="hint">{t(q.last.team ? 'scr.lastTeam' : 'scr.lastIn', { name: q.last.name, time: time(q.last.at) })}</p>{/if}
      {#if q.pending}<p class="hint">{t('scr.joining', { n: q.pending })}</p>{/if}
      {#if event && !door && sess && scanner && q.param}<Button kind="secondary" size="m" onclick={toScanner}>{#snippet icon()}<ScanLine size={17} />{/snippet}{t('studio.scanner')}</Button>{/if}
      {#if board && q.param}<Button kind="secondary" size="m" onclick={() => { haptic.tap(); sheets.handQr(sid); }}>{#snippet icon()}<UserPlus size={17} />{/snippet}{t('scr.hand')}</Button>{/if}
    {/if}
    {#if door && event}<Button kind="secondary" size="m" onclick={toScanner}>{#snippet icon()}<ScanLine size={17} />{/snippet}{t('studio.scanner')}</Button>{/if}
  </div>
  <CloseX onclick={() => close(overlay.id)} />
</div>

<style>
  .scrim { position: absolute; inset: 0; z-index: var(--z-sheet); background: rgba(3, 4, 10, 0.94); }
  .wrap { position: absolute; inset: 0; z-index: var(--z-sheet); display: flex; flex-direction: column; padding-bottom: var(--close-room); pointer-events: none; }
  .page { flex: 1; min-height: 0; overflow-y: auto; scrollbar-width: none; display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: var(--s-4); padding: calc(max(var(--top), var(--head-bottom)) + 8px) var(--s-4) var(--s-4); pointer-events: auto; }
  .page::-webkit-scrollbar { display: none; }
  .head { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: white; font: 700 var(--fs-card)/1.2 var(--font-display); }
  /* as big as the phone allows: the whole width, or the height left by the lines around it */
  .plate { width: min(100%, 420px, calc(100dvh - 300px)); min-width: 200px; aspect-ratio: 1; padding: var(--s-4); border-radius: var(--r-l); background: white;
    box-shadow: 0 0 60px rgba(255, 255, 255, 0.18); }
  .plate.off { display: grid; place-items: center; background: rgba(255, 255, 255, 0.08); box-shadow: none; }
  .note { text-align: center; color: rgba(255, 255, 255, 0.8); font: 600 var(--fs-body)/1.3 var(--font-text); }
  .hint { max-width: 300px; text-align: center; color: rgba(255, 255, 255, 0.7); font: 500 var(--fs-sub)/1.35 var(--font-text); }
  .got { color: white; font: 700 var(--fs-body)/1.2 var(--font-text); font-variant-numeric: tabular-nums; }
</style>
