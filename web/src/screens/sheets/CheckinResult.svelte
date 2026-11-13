<script lang="ts" module>
  /** What a scan of the big screen's QR came to (App.svelte's checkIn): counted, counted before, leaving, waiting for
   *  the sign-in, or one of the refusals */
  export type CiKind = 'done' | 'again' | 'left' | 'wait' | 'no' | 'old' | 'closed' | 'notIn' | 'error';
</script>

<script lang="ts">
  // A scan of the event's check-in QR answered in the middle of the screen (owner, Nov 10: guests at the door couldn't
  // tell from a toast whether they were in). The event's own picture with a check drawn onto it, one line, the event's
  // name and the minute; a counted one settles into the event's sheet by itself. Calm: no confetti, one success haptic.
  import { onMount } from 'svelte';
  import type { Id } from '../../lib/api';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { eventById, eventDetails } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { time, nowTs } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import { calm } from '../../ui/fold';
  import Poster from '../../ui/Poster.svelte';
  import Button from '../../ui/Button.svelte';
  import CloseX from '../../ui/CloseX.svelte';
  import ScanQrCode from '@lucide/svelte/icons/scan-qr-code';

  let { overlay, kind, title, event = null, onsign, text }: { overlay: Overlay; kind: CiKind; title: string; event?: Id | null; onsign?: () => void; text?: string } = $props(); // text: why not, said exactly (a used ticket, a receipt to check)

  const ok = $derived(kind === 'done' || kind === 'again' || kind === 'left');
  const e = $derived(event ? eventById(event) : undefined); // the store holds today's events; none: the check alone
  const at = time(nowTs());
  const HEAD = { done: 'ci.hDone', again: 'ci.hAgain', left: 'ci.hLeft', wait: 'ci.hWait', no: 'ci.hNo', old: 'ci.hOld', closed: 'ci.closed', notIn: 'ci.hNotIn', error: 'common.error' } as const;
  const head = $derived(t(HEAD[kind]));
  // the line under the name: the minute it counted (a second scan: that it isn't needed, never "now" as if it counted again); a refusal says what to do
  const sub = $derived(text ? text : kind === 'again' ? t('ci.againText') : ok ? at : kind === 'wait' ? t('ci.waitText') : kind === 'old' ? t('ci.oldText')
    : kind === 'no' || kind === 'notIn' ? t('ci.askOrg') : '');
  const named = $derived(kind !== 'old' && kind !== 'closed' && kind !== 'error' && !!title);

  $effect(() => { overlay.title = t('cap.checkin'); overlay.icon = ScanQrCode; overlay.theme = 'dark'; });

  let wrap: HTMLDivElement;
  let scrim: HTMLDivElement;
  let gone = false;
  // a counted scan of an event: the event's sheet after a moment to read it (a tap: at once)
  const settles = $derived((kind === 'done' || kind === 'again') && !!event);

  onMount(() => {
    if (event && !eventById(event)) void eventDetails(event).catch(() => {}); // its picture a moment later
    const still = calm();
    scrim.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 220, easing: 'ease-out' });
    wrap.animate(still ? [{ opacity: 0 }, { opacity: 1 }] : [{ opacity: 0, transform: 'scale(0.9)' }, { opacity: 1, transform: 'none' }],
      { duration: still ? 160 : 420, easing: 'cubic-bezier(.2,.9,.3,1.15)' });
    // the haptic with the check's stroke (it draws from 180 ms)
    const buzz = setTimeout(() => (ok ? haptic.ok() : kind === 'wait' ? haptic.soft() : haptic.error()), still ? 0 : 260);
    const auto = settles ? setTimeout(open, 2600) : 0;
    const chrome = hideChrome();
    return () => { clearTimeout(buzz); clearTimeout(auto); chrome(); };
  });

  function open() {
    if (gone || !event) return;
    close(overlay.id);
    sheets.event(event);
  }
  function leave() {
    if (gone) return;
    gone = true;
    wrap.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: calm() ? 'none' : 'scale(0.96)' }], { duration: 200, easing: 'ease-in', fill: 'forwards' });
    scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 220, easing: 'ease-in', fill: 'forwards' }).onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });
</script>

<div class="scrim" bind:this={scrim} style:--c={e?.color ?? (ok ? 'var(--success)' : kind === 'wait' ? 'var(--accent)' : 'var(--warning)')} onclick={() => (settles ? open() : close(overlay.id))} role="presentation"></div>
<div class="wrap" bind:this={wrap}>
  <div class="page">
    <div class="card" role="status" aria-live="polite" class:still={calm()}>
      <div class="mark" class:pic={!!e}>
        {#if e}<Poster item={e} size={104} radius={28} />{/if}
        <span class="disc {ok ? 'ok' : kind === 'wait' ? 'wait' : 'bad'}" aria-hidden="true">
          <svg viewBox="0 0 52 52">
            {#if ok}<path d="M15 27 l7.5 7.5 L37.5 19" />
            {:else if kind === 'wait'}<path d="M26 15 v12 l7 5" />
            {:else}<path d="M26 15 v14 M26 36.5 v.5" />{/if}
          </svg>
        </span>
      </div>
      <h2 class="head">{head}</h2>
      {#if named}<p class="name clamp-2">{title}</p>{/if}
      {#if sub}<p class="sub">{sub}</p>{/if}
      {#if kind === 'wait' && onsign}
        <div class="act"><Button kind="primary" size="l" full lit onclick={() => { close(overlay.id); onsign(); }}>{t('ci.signIn')}</Button></div>
      {/if}
    </div>
  </div>
  <CloseX onclick={() => close(overlay.id)} />
</div>

<style>
  .scrim {
    position: absolute; inset: 0; z-index: var(--z-sheet);
    /* the event's colour as a soft light behind the mark, on the dark scrim of the app's full-screen overlays (MyQr) */
    background: rgba(3, 4, 10, 0.82);
    -webkit-backdrop-filter: blur(20px) saturate(120%); backdrop-filter: blur(20px) saturate(120%);
  }
  .scrim::before { content: ''; position: absolute; inset: 0; opacity: 0.34; background: radial-gradient(60% 38% at 50% 44%, var(--c), transparent 72%); }
  :global(html.lowfx) .scrim { background: rgba(3, 4, 10, 0.94); -webkit-backdrop-filter: none; backdrop-filter: none; }
  .wrap { position: absolute; inset: 0; z-index: var(--z-sheet); pointer-events: none; display: flex; flex-direction: column; padding-bottom: var(--close-room); }
  .page { flex: 1; min-height: 0; overflow-y: auto; scrollbar-width: none; display: flex; flex-direction: column; align-items: center; justify-content: center;
    padding: calc(max(var(--top), var(--head-bottom)) + 8px) 24px 20px; }
  .page::-webkit-scrollbar { display: none; }
  .card { pointer-events: auto; width: 100%; max-width: 340px; display: flex; flex-direction: column; align-items: center; text-align: center; color: var(--on-accent); }

  .mark { position: relative; width: 104px; height: 104px; margin-bottom: 26px; display: grid; place-items: center; }
  .mark :global(.poster) { box-shadow: 0 24px 50px -18px rgba(0, 0, 0, 0.8), inset 0 0 0 1px rgba(255, 255, 255, 0.1); }
  /* alone: the disc is the mark; on a picture: a badge on its corner, ringed by the scrim's dark */
  .disc { width: 88px; height: 88px; border-radius: 50%; display: grid; place-items: center; color: var(--on-accent); }
  .pic .disc { position: absolute; right: -14px; bottom: -14px; width: 46px; height: 46px; box-shadow: 0 0 0 4px rgb(10, 11, 18); }
  .ok { background: var(--success); }
  .wait { background: var(--accent); }
  .bad { background: var(--warning); color: rgb(40, 26, 0); }
  .disc svg { width: 100%; height: 100%; fill: none; stroke: currentColor; stroke-width: 4.4; stroke-linecap: round; stroke-linejoin: round; }
  .pic .disc svg { stroke-width: 5; }
  .disc path { stroke-dasharray: 40; stroke-dashoffset: 40; animation: draw 380ms cubic-bezier(.65, 0, .35, 1) 240ms forwards; }
  .disc { animation: pop 460ms cubic-bezier(.2, .9, .3, 1.25) 120ms both; }
  .still .disc, .still .disc path { animation: none; stroke-dashoffset: 0; }

  .head { margin: 0; font: 700 var(--fs-t1)/1.15 var(--font-display); letter-spacing: -0.025em; text-wrap: balance; }
  .name { margin: 10px 0 0; font: 600 var(--fs-card)/1.3 var(--font-text); color: rgba(255, 255, 255, 0.86); }
  .sub { margin: 6px 0 0; font: 500 var(--fs-body)/1.35 var(--font-text); color: rgba(255, 255, 255, 0.58); text-wrap: balance; }
  .act { width: 100%; margin-top: 26px; }

  @keyframes pop { from { transform: scale(0.4); opacity: 0; } to { transform: none; opacity: 1; } }
  @keyframes draw { to { stroke-dashoffset: 0; } }
  @media (prefers-reduced-motion: reduce) { .disc, .disc path { animation: none; stroke-dashoffset: 0; } }
</style>
