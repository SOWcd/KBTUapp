<script lang="ts">
  // The organizer's big screen at /show (server checkin.py), opened on a laptop in any browser, no Telegram. It holds
  // no controls (owner, Oct 29 night: a PIN typed in view of the hall opened Finish and the CSV to anyone): it shows a
  // pairing QR until an organizer scans it in the app, then the session the app runs: the rotating check-in QR, the
  // count going up live. A small QR stays in the corner so another organizer can reach the controls (a flat phone).
  // The screen's secret stays in this browser (localStorage: a reload or a closed tab keeps the pairing).
  import { onMount } from 'svelte';
  import { fade, scale } from 'svelte/transition';
  import Qr from '../ui/Qr.svelte';
  import KbtuMark from '../ui/KbtuMark.svelte';
  import { QR_TONE } from '../lib/awards';
  import { t } from '../lib/i18n/index.svelte';

  type State = { code: string; left?: number; session?: number; title?: string; started?: number | null; ended?: number | null;
    done?: number; pending?: number; expected?: number; param?: string | null };
  const KEEP = 'kb-show';
  let secret = '';
  let st = $state<State | null>(null);
  let pairing = false;

  try { secret = localStorage.getItem(KEEP) ?? ''; } catch { /* no storage: a new pairing after a reload */ }

  async function pair() {
    if (pairing) return;
    pairing = true;
    try {
      const r = await fetch('/api/screen/pair', { method: 'POST' });
      if (r.ok) {
        const p = await r.json();
        secret = p.secret;
        try { localStorage.setItem(KEEP, secret); } catch { /* fine */ }
        st = { code: p.code, left: p.ttl };
      }
    } finally { pairing = false; }
  }
  async function poll() {
    if (!secret) { await pair(); return; }
    try {
      const r = await fetch('/api/screen', { headers: { 'X-Screen': secret } });
      if (r.status === 403) { secret = ''; await pair(); return; } // unpaired from the app, or long gone
      if (!r.ok) return;
      st = await r.json();
      if (st && st.session == null && !st.left) await pair(); // nobody scanned it in time: a fresh code
    } catch { /* offline: the next poll */ }
  }
  onMount(() => {
    void poll();
    const id = setInterval(poll, 2000); // the count and the QR: the code turns every 10 s, the screen catches it within 2
    return () => clearInterval(id);
  });

  const bot = 'https://t.me/KBTUappBot?startapp=';
  const link = $derived(st?.param ? bot + st.param : '');
  const pairLink = $derived(st ? bot + 'sh_' + st.code : '');
</script>

<div class="screen">
  <div class="glow" aria-hidden="true"></div>
  {#if !st}
    <p class="sub">…</p>
  {:else if st.session == null}
    <section class="pair" in:fade>
      <h1>{t('scr.pairTitle')}</h1>
      {#key pairLink}<div class="code small" in:fade={{ duration: 300 }}><Qr text={pairLink} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr></div>{/key}
      <p class="hint">{t('scr.pairHint')}</p>
      <p class="sub">{t('scr.pairWho')}</p>
    </section>
  {:else}
    <header><h1>{st.title}</h1></header>
    {#if st.param}
      <section class="live">
        {#key link}<div class="code" in:fade={{ duration: 400 }}><Qr text={link} tone={QR_TONE}><span class="appmark"><KbtuMark /></span></Qr></div>{/key}
        <aside>
          <p class="hint">{t('scr.scan')}</p>
          <p class="count"><b>{st.done}</b>{#if st.expected}<span> / {st.expected}</span>{/if}</p>
          <p class="sub">{t('scr.done')}</p>
          {#if st.pending}<p class="sub" transition:fade>{t('scr.joining', { n: st.pending })}</p>{/if}
        </aside>
      </section>
    {:else}
      <section class="idle" in:scale={{ start: 0.96 }}>
        {#if st.ended}
          <p class="count"><b>{st.done}</b>{#if st.expected}<span> / {st.expected}</span>{/if}</p>
          <p class="sub">{t('scr.closed')}</p>
          <p class="sub">{t('scr.listInApp')}</p>
        {:else}
          <p class="hint">{t('scr.pressStart')}</p>
        {/if}
      </section>
    {/if}
    <!-- the same pairing code: another organizer's way to the controls; anyone else's scan changes nothing -->
    <div class="corner"><div class="mini"><Qr text={pairLink} tone={QR_TONE} /></div><span>{t('scr.organizers')}</span></div>
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
  .mini { width: 11vh; min-width: 72px; padding: 6px; border-radius: 10px; background: #fff; }
  .live { display: flex; align-items: center; gap: 5vw; }
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
