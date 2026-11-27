<script lang="ts">
  // The organizer's big screen at /show (server checkin.py), opened on a laptop in any browser, no Telegram. It holds
  // no controls (a PIN typed in view of the hall opened Finish and the CSV to anyone): it shows a
  // pairing QR until an organizer scans it in the app, then the session the app runs: the rotating check-in QR, the
  // count going up live. A small QR stays in the corner so another organizer can reach the controls (a flat phone).
  // The screen's secret stays in this tab (sessionStorage): a reload or a dead network keeps the pairing, so the screen
  // can't fall off mid-event; closing the tab ends it, a new tab pairs again.
  import { onMount } from 'svelte';
  import { fade, scale } from 'svelte/transition';
  import Qr from '../ui/Qr.svelte';
  import '../lib/qrnow'; // its code in the first frame (lib/qr.svelte.ts)
  import KbtuMark from '../ui/KbtuMark.svelte';
  import { QR_TONE } from '../lib/awards';
  import { screenPoll, screenView, type ScreenState } from '../lib/screen';
  import { sw } from '../lib/i18n/staff';

  let st = $state<ScreenState | null>(null);
  let now = $state(Date.now());
  let again = $state(() => {});
  onMount(() => {
    let expiry: ReturnType<typeof setTimeout> | undefined;
    const polling = screenPoll((value) => {
      st = value;
      now = Date.now();
      clearTimeout(expiry);
      if (value && value.expires > now) expiry = setTimeout(() => { now = Date.now(); }, value.expires - now);
    });
    again = polling.again;
    return () => { polling.stop(); clearTimeout(expiry); };
  });
  const view = $derived(screenView(st, now));
</script>

<div class="screen">
  <div class="glow" aria-hidden="true"></div>
  {#if !st || !view.fresh}
    <p class="sub">{sw('scr.reconnecting')}</p>
    {#if st?.session != null}<div class="corner"><button class="again" onclick={again}>{sw('scr.again')}</button></div>{/if}
  {:else if st.session == null}
    <section class="pair" in:fade>
      <h1>{sw('scr.pairTitle')}</h1>
      <!-- a new code redraws in place (no key, no fade): the swap is seamless -->
      <div class="code small"><Qr text={view.pair} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr></div>
      <p class="hint">{sw('scr.pairHint')}</p>
      <p class="sub">{sw('scr.pairWho')}</p>
    </section>
  {:else}
    <header><h1>{st.title}</h1></header>
    {#if view.entry}
      <section class="live" class:out={st.phase === 'out'}>
        <div class="code"><Qr text={view.entry} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr></div>
        <aside>
          {#if st.phase === 'out'}
            <!-- the way out: the same QR marks leaving (the organizer switched it in the app) -->
            <p class="hint outh">{sw('scr.outScan')}</p>
            <p class="count"><b>{st.departed}</b><span> / {view.arrivals}</span></p>
            <p class="sub">{sw('scr.outDone')}</p>
          {:else if st.param?.startsWith('tk_')}
            <p class="hint">{sw('scr.ticket')}</p>
          {:else}
            <p class="hint">{sw('scr.scan')}</p>
            <p class="count"><b>{view.arrivals}</b></p>
            <p class="sub">{sw('scr.done')}</p>
          {/if}
          {#if st.pending}<p class="sub" transition:fade>{sw('scr.joining', { n: st.pending })}</p>{/if}
        </aside>
      </section>
    {:else}
      <section class="idle" in:scale={{ start: 0.96 }}>
        {#if st.ended}
          <p class="count"><b>{view.arrivals}</b></p>
          <p class="sub">{sw('scr.closed')}</p>
          <p class="sub">{sw('scr.listInApp')}</p>
        {:else}
          <p class="hint">{sw('scr.pressStart')}</p>
        {/if}
      </section>
    {/if}
    <!-- the same pairing code: another organizer's way to the controls; anyone else's scan changes nothing -->
    <div class="corner"><div class="mini"><Qr text={view.pair} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr></div><span>{sw('scr.organizers')}</span>
      <button class="again" onclick={again}>{sw('scr.again')}</button></div>
  {/if}
</div>

<style>
  .screen { position: fixed; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 3vh;
    background: var(--bg); color: var(--text); overflow: hidden; padding: 4vh 4vw; font-family: inherit; }
  .glow { position: absolute; inset: -30%; z-index: 0; pointer-events: none;
    background: radial-gradient(40% 35% at 30% 30%, color-mix(in srgb, var(--accent) 28%, transparent), transparent 70%),
                radial-gradient(35% 30% at 70% 70%, color-mix(in srgb, var(--accent-2) 24%, transparent), transparent 70%);
    animation: drift 18s ease-in-out infinite alternate; }
  @keyframes drift { to { transform: translate(6%, -4%) rotate(8deg); } }
  .screen > :not(.glow) { position: relative; z-index: 1; }
  h1 { margin: 0; font-size: clamp(24px, 4vh, 44px); font-weight: 700; text-align: center; }
  .pair { display: flex; flex-direction: column; align-items: center; gap: 2.4vh; text-align: center; }
  .code.small { width: min(48vh, 70vw); }
  .screen > .corner { position: absolute; right: 2.4vh; bottom: 2.4vh; display: flex; flex-direction: column; align-items: center; gap: 6px;
    font-size: 12px; color: var(--text-2); opacity: 0.75; }
  .again { margin-top: 2px; padding: 4px 8px; border-radius: 999px; font: inherit; font-size: 11px; color: var(--text-2); background: none; border: 0; cursor: pointer; }
  .again:hover { background: color-mix(in srgb, var(--text) 8%, transparent); }
  .mini { width: 11vh; min-width: 72px; padding: 6px; border-radius: 10px; background: #fff; }
  .live { display: flex; align-items: center; gap: 5vw; }
  .live.out .code { box-shadow: 0 0 80px rgba(255, 159, 10, 0.55); }
  .outh { color: #FF9F0A; font-weight: 700; }
  .code { width: min(68vh, 50vw); padding: 2.4vh; border-radius: 4vh; background: #fff;
    box-shadow: 0 0 80px color-mix(in srgb, var(--accent) 40%, transparent); }
  aside { display: flex; flex-direction: column; align-items: flex-start; gap: 1.2vh; max-width: 30vw; min-width: 0; }
  .hint { margin: 0; font-size: clamp(18px, 2.6vh, 28px); color: var(--text-2); }
  .count { margin: 0; line-height: 1; font-variant-numeric: tabular-nums; }
  .count b { font-size: clamp(48px, 12vh, 160px); font-weight: 800; }
  .count span { font-size: clamp(28px, 5vh, 56px); color: var(--text-2); }
  .sub { margin: 0; font-size: clamp(16px, 2.2vh, 24px); color: var(--text-2); }
  .idle { display: flex; flex-direction: column; align-items: center; gap: 2vh; }
  @media (max-aspect-ratio: 1/1) { .live { flex-direction: column; } .code { width: min(86vw, 60vh); } aside { align-items: center; max-width: none; } }
  @media (prefers-reduced-motion: reduce) { .glow { animation: none; } }
</style>
