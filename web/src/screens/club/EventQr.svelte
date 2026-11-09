<script lang="ts">
  // An event's rotating check-in QR on the organizer's own phone, for a hall with no big screen (admin/BadgeQr.svelte's
  // look). Opening starts the event's session if it isn't running; closing leaves it running and keeps every mark.
  // The code is the server's, and each poll renews its 15 s lease: nothing showing it, it stops (server checkin.py).
  import { onMount } from 'svelte';
  import { api, ApiErr, type Id, type ScreenSession } from '../../lib/api';
  import { QR_TONE } from '../../lib/awards';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Qr from '../../ui/Qr.svelte';
  import '../../lib/qrnow'; // its code in the first frame (lib/qr.svelte.ts)
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import CloseX from '../../ui/CloseX.svelte';
  import QrCode from '@lucide/svelte/icons/qr-code';

  let { overlay, event }: { overlay: Overlay; event: Id } = $props();
  $effect(() => { overlay.title = t('aw.show'); overlay.icon = QrCode; overlay.theme = 'dark'; });

  let q = $state<ScreenSession | null>(null), failed = $state(false);
  let sid: Id, timer: ReturnType<typeof setTimeout> | undefined, gone = false;
  const out = $derived(q?.phase === 'out');
  const poll = () => void api.screenAct(sid, 'show').then(got).catch(stop);
  function got(r: ScreenSession) {
    if (gone) return;
    if (q && r.done > q.done) haptic.soft();
    q = r;
    if (!r.ended) timer = setTimeout(poll, Math.min(r.next, 3) * 1000 + 300); // the next code as the slot turns, the count meanwhile
  }
  function stop(e: unknown) {
    if (gone) return;
    if (!q || (e instanceof ApiErr && e.code === 'forbidden')) { q = null; failed = true; return; }
    timer = setTimeout(poll, 3000); // a blip of the network: try again
  }
  async function open() {
    const s = await api.eventScreen(event);
    sid = s.session;
    if (!s.started) await api.screenAct(sid, 'start');
    got(await api.screenAct(sid, 'show'));
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
        {#key q.param}<Qr text={`https://t.me/KBTUappBot?startapp=${q.param}`} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr>{/key}
      {:else if q?.ended || failed}
        <p class="note">{failed ? t('common.error') : t('scr.closed')}</p>
      {/if}
    </div>
    {#if q}
      {#if q.param}<p class="hint">{t(out ? 'scr.outScan' : 'scr.scan')}</p>{/if}
      <p class="got"><b>{out ? q.departed : q.done}</b>{#if out} / {q.done}{:else if q.expected} / {q.expected}{/if} {t(out ? 'scr.outDone' : 'scr.done')}</p>
      {#if q.pending}<p class="hint">{t('scr.joining', { n: q.pending })}</p>{/if}
    {/if}
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
