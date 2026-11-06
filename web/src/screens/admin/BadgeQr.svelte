<script lang="ts">
  // Admin → Awards → Show QR (owner, Nov 6): the award's code full screen on the giver's phone, big and bright on a
  // white plate, for the hall's cameras: a scan opens the app straight onto the award (App.svelte, bq_…). The code is
  // the server's, a new one every 20 s (a photo of it goes stale within a minute, logic/profiles.py claim_qr); the
  // screen closing closes it on the server too, and its polls hold a 15 s lease (a killed screen's code stops by
  // itself). Under it: how many got it here.
  import { onMount } from 'svelte';
  import { api, ApiErr, type BadgeQr, type GrantItem } from '../../lib/api';
  import { manualMedal, manualName, QR_TONE, type Manual } from '../../lib/awards';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Qr from '../../ui/Qr.svelte';
  import '../../lib/qrnow'; // its code in the first frame (lib/qr.svelte.ts)
  import Medal from '../../ui/Medal.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import CloseX from '../../ui/CloseX.svelte';
  import QrCode from '@lucide/svelte/icons/qr-code';

  let { overlay, award, code }: { overlay: Overlay; award: Manual; code: GrantItem['code'] } = $props();
  $effect(() => { overlay.title = manualName(code); overlay.icon = QrCode; overlay.theme = 'dark'; });
  const art = $derived(award.variants?.find((v) => v.code === code)?.emoji ?? award.emoji);

  let q = $state<BadgeQr | null>(null), ended = $state(false), failed = $state(false);
  let timer: ReturnType<typeof setTimeout> | undefined, gone = false;
  // the next code as the slot turns, and the count every few seconds meanwhile
  function got(r: BadgeQr) {
    if (gone) return;
    if (q && r.got > q.got) haptic.soft();
    q = r;
    timer = setTimeout(() => void api.badgeQr(r.token).then(got).catch(stop), Math.min(r.next, 5) * 1000 + 300);
  }
  function stop(e: unknown) {
    if (gone) return;
    if (e instanceof ApiErr && e.code === 'closed') { ended = true; q = null; return; }
    if (!q) { failed = true; return; }
    timer = setTimeout(() => void api.badgeQr(q!.token).then(got).catch(stop), 3000); // a blip of the network: try again
  }

  let wrap: HTMLDivElement, scrim: HTMLDivElement;
  onMount(() => {
    haptic.soft();
    api.openBadgeQr(code).then(got).catch(stop);
    wrap.animate([{ opacity: 0, transform: 'translate3d(0,50px,0) scale(0.94)' }, { opacity: 1, transform: 'none' }], { duration: 420, easing: 'cubic-bezier(.2,.9,.25,1.1)' });
    scrim.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 240, easing: 'ease-out' });
    const chrome = hideChrome();
    return () => { chrome(); clearTimeout(timer); };
  });

  function leave() {
    if (gone) return;
    gone = true;
    clearTimeout(timer);
    // closed with the screen, tried twice; failing both, the server's lease ends it within 15 s anyway
    if (q) { const tok = q.token; api.revokeLink(tok).catch(() => setTimeout(() => void api.revokeLink(tok).catch(() => {}), 2000)); }
    wrap.animate([{ opacity: 1 }, { opacity: 0, transform: 'translate3d(0,40px,0) scale(0.96)' }], { duration: 220, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
    scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 220, easing: 'ease-in', fill: 'forwards' }).onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });
</script>

<div class="scrim" bind:this={scrim} role="presentation"></div>
<div class="wrap" bind:this={wrap}>
  <div class="page">
    <div class="head"><Medal a={manualMedal(award.code, art)} size={56} /><b>{manualName(code)}</b></div>
    <div class="plate" class:off={!q}>
      {#if q}
        {#key q.param}<Qr text={`https://t.me/KBTUappBot?startapp=${q.param}`} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr>{/key}
      {:else if ended || failed}
        <p class="note">{ended ? t('aw.showEnded') : t('common.error')}</p>
      {/if}
    </div>
    {#if q}
      <p class="hint">{t('aw.showHint')}</p>
      <p class="got">{t('aw.showGot', { n: q.got })}</p>
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
  .head { display: flex; align-items: center; gap: var(--s-3); max-width: 100%; color: white; font: 700 var(--fs-card)/1.2 var(--font-display); }
  .head b { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  /* as big as the phone allows: the whole width, or the height left by the medal and the lines under it */
  .plate { width: min(100%, 420px, calc(100dvh - 300px)); min-width: 200px; aspect-ratio: 1; padding: var(--s-4); border-radius: var(--r-l); background: white;
    box-shadow: 0 0 60px rgba(255, 255, 255, 0.18); }
  .plate.off { display: grid; place-items: center; background: rgba(255, 255, 255, 0.08); box-shadow: none; }
  .note { text-align: center; color: rgba(255, 255, 255, 0.8); font: 600 var(--fs-body)/1.3 var(--font-text); }
  .hint { max-width: 300px; text-align: center; color: rgba(255, 255, 255, 0.7); font: 500 var(--fs-sub)/1.35 var(--font-text); }
  .got { color: white; font: 700 var(--fs-body)/1.2 var(--font-text); font-variant-numeric: tabular-nums; }
</style>
