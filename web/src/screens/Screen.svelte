<script lang="ts">
  // The organizer's big screen at /screen (server checkin.py), opened on a laptop in any browser, no Telegram: the
  // session's PIN, then Start: a full-screen QR that changes every 10 s, the count going up live, Finish and the list.
  // The session's key stays in this tab (sessionStorage) so a reload doesn't ask the PIN again.
  import { onMount } from 'svelte';
  import { fade, scale } from 'svelte/transition';
  import Qr from '../ui/Qr.svelte';
  import { QR_TONE } from '../lib/awards';
  import { t } from '../lib/i18n/index.svelte';

  type State = { title: string; started: number | null; ended: number | null; done: number; pending: number; expected: number; param: string | null };
  const KEEP = 'kb-screen';
  let auth = $state<{ session: number; key: string } | null>(null);
  let st = $state<State | null>(null);
  let pin = $state(''), busy = $state(false), error = $state('');

  try { auth = JSON.parse(sessionStorage.getItem(KEEP) ?? 'null'); } catch { /* no storage: the PIN each time */ }

  async function call<T>(method: string, path: string, body?: object): Promise<T> {
    const r = await fetch(`/api/screen${path}`, { method, headers: body ? { 'Content-Type': 'application/json' } : {}, body: body && JSON.stringify(body) });
    if (!r.ok) throw new Error(String(r.status));
    return r.json();
  }
  async function open(ev: Event) {
    ev.preventDefault();
    if (busy || pin.length !== 6) return;
    busy = true; error = '';
    try {
      auth = await call('POST', '/open', { pin });
      try { sessionStorage.setItem(KEEP, JSON.stringify(auth)); } catch { /* fine */ }
      await poll();
    } catch (e) { error = (e as Error).message === '429' ? t('common.error') : t('scr.badPin'); pin = ''; }
    busy = false;
  }
  async function poll() {
    if (!auth) return;
    try { st = await call('GET', `/${auth.session}?k=${auth.key}`); }
    catch (e) { if ((e as Error).message === '403') { auth = null; try { sessionStorage.removeItem(KEEP); } catch { /* fine */ } } }
  }
  async function act(a: 'start' | 'finish') {
    if (!auth || busy) return;
    busy = true;
    try { st = await call('POST', `/${auth.session}/${a}`, { k: auth.key }); } catch { /* the next poll shows it */ }
    busy = false;
  }
  onMount(() => {
    void poll();
    const id = setInterval(poll, 2000); // the count and the QR: the code turns every 10 s, the screen catches it within 2
    return () => clearInterval(id);
  });

  const link = $derived(st?.param ? `https://t.me/KBTUappBot?startapp=${st.param}` : '');
  const csv = $derived(auth ? `/api/screen/${auth.session}/csv?k=${auth.key}` : '');
</script>

<div class="screen">
  <div class="glow" aria-hidden="true"></div>
  {#if !auth || !st}
    <form class="pin" onsubmit={open} in:fade>
      <h1>{t('scr.title')}</h1>
      <input bind:value={pin} inputmode="numeric" maxlength="6" autocomplete="off" placeholder="••••••" aria-label={t('scr.pin')}
        oninput={() => (pin = pin.replace(/\D/g, ''))} />
      <button class="btn" disabled={busy || pin.length !== 6}>{t('scr.open')}</button>
      {#if error}<p class="err">{error}</p>{/if}
    </form>
  {:else}
    <header><h1>{st.title}</h1></header>
    {#if st.param}
      <section class="live">
        {#key link}<div class="code" in:fade={{ duration: 400 }}><Qr text={link} tone={QR_TONE} /></div>{/key}
        <aside>
          <p class="hint">{t('scr.scan')}</p>
          <p class="count"><b>{st.done}</b>{#if st.expected}<span> / {st.expected}</span>{/if}</p>
          <p class="sub">{t('scr.done')}</p>
          {#if st.pending}<p class="sub" transition:fade>{t('scr.joining', { n: st.pending })}</p>{/if}
          <button class="btn ghost" onclick={() => act('finish')} disabled={busy}>{t('scr.finish')}</button>
        </aside>
      </section>
    {:else}
      <section class="idle" in:scale={{ start: 0.96 }}>
        {#if st.ended}
          <p class="count"><b>{st.done}</b>{#if st.expected}<span> / {st.expected}</span>{/if}</p>
          <p class="sub">{t('scr.closed')}</p>
          <div class="row">
            <a class="btn" href={csv} download>{t('scr.csv')}</a>
            <button class="btn ghost" onclick={() => act('start')} disabled={busy}>{t('scr.again')}</button>
          </div>
        {:else}
          <button class="btn big" onclick={() => act('start')} disabled={busy}>{t('scr.start')}</button>
        {/if}
      </section>
    {/if}
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
  .pin { display: flex; flex-direction: column; align-items: center; gap: 20px; }
  .pin input { width: 280px; font-size: 44px; letter-spacing: 0.3em; text-align: center; padding: 14px; border-radius: 18px;
    border: 1px solid color-mix(in srgb, var(--text) 18%, transparent); background: color-mix(in srgb, var(--text) 6%, transparent); color: var(--text); }
  .err { color: #FF6B6B; margin: 0; }
  .btn { appearance: none; border: 0; cursor: pointer; text-decoration: none; font: inherit; font-weight: 650; font-size: 18px; padding: 14px 28px;
    border-radius: 999px; color: #fff; background: linear-gradient(135deg, var(--accent), var(--accent-2)); transition: transform 0.15s, opacity 0.2s; }
  .btn:hover { transform: scale(1.03); }
  .btn:disabled { opacity: 0.45; cursor: default; transform: none; }
  .btn.ghost { background: color-mix(in srgb, var(--text) 10%, transparent); color: var(--text); }
  .btn.big { font-size: clamp(22px, 3.4vh, 34px); padding: 3vh 6vh; box-shadow: 0 0 60px color-mix(in srgb, var(--accent) 45%, transparent); }
  .live { display: flex; align-items: center; gap: 5vw; }
  .code { width: min(68vh, 50vw); padding: 2.4vh; border-radius: 4vh; background: #fff;
    box-shadow: 0 0 80px color-mix(in srgb, var(--accent) 40%, transparent); }
  aside { display: flex; flex-direction: column; align-items: flex-start; gap: 1.2vh; max-width: 30vw; min-width: 0; }
  .hint { margin: 0; font-size: clamp(18px, 2.6vh, 28px); color: var(--text-2); }
  .count { margin: 0; line-height: 1; font-variant-numeric: tabular-nums; }
  .count b { font-size: clamp(48px, 12vh, 160px); font-weight: 800; }
  .count span { font-size: clamp(28px, 5vh, 56px); color: var(--text-2); }
  .sub { margin: 0; font-size: clamp(16px, 2.2vh, 24px); color: var(--text-2); }
  aside .btn { margin-top: 3vh; }
  .idle { display: flex; flex-direction: column; align-items: center; gap: 2vh; }
  .row { display: flex; gap: 14px; margin-top: 2vh; }
  @media (max-aspect-ratio: 1/1) { .live { flex-direction: column; } .code { width: min(86vw, 60vh); } aside { align-items: center; max-width: none; } }
  @media (prefers-reduced-motion: reduce) { .glow { animation: none; } }
</style>
