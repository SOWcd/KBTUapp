<script lang="ts">
  // KBTU's anthem, to listen to and learn (Oct 30: the volunteers learn it for the Oct 31 initiation). The words in big
  // type, the Kazakh chorus on a soft band after each verse; the player stays at the bottom while they scroll, as in
  // Apple Music's lyrics. One audio element, made on the first tap (iOS plays only from a tap; nothing loads before it),
  // paused as the sheet leaves.
  // The creator alone also has a timer: the song from 0:00 and a big Tap, each tap the start of the next sung line (it is
  // highlighted and kept in sight), Undo, Copy (the list as JSON, for TIMES in lib/i18n/anthem.ts); nothing goes to the
  // server. Once TIMES holds every line, the words follow the song.
  import { onMount } from 'svelte';
  import Music from '@lucide/svelte/icons/music';
  import Play from '@lucide/svelte/icons/play';
  import Pause from '@lucide/svelte/icons/pause';
  import Repeat from '@lucide/svelte/icons/repeat';
  import Timer from '@lucide/svelte/icons/timer';
  import Undo2 from '@lucide/svelte/icons/undo-2';
  import Copy from '@lucide/svelte/icons/copy';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { t, LANG_FULL } from '../../lib/i18n/index.svelte';
  import { ANTHEM, SUNG, TIMED } from '../../lib/i18n/anthem';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let audio: HTMLAudioElement | null = null;
  let on = $state(false), waiting = $state(false), repeat = $state(false), held = $state(false);
  let cur = $state(0), dur = $state(211); // the file's length: the time left shows before it loads
  let track: HTMLSpanElement, words: HTMLDivElement;
  const ms = 'mediaSession' in navigator ? navigator.mediaSession : null;
  const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

  function make(): HTMLAudioElement {
    const a = new Audio();
    a.preload = 'none';
    a.loop = repeat;
    a.src = 'anthem/kbtu-anthem.m4a';
    const from = cur; // scrubbed before the first play: it starts there
    if (from) a.addEventListener('loadedmetadata', () => (a.currentTime = from), { once: true });
    a.onplay = () => { on = true; if (ms) ms.playbackState = 'playing'; };
    a.onpause = () => { on = waiting = false; if (ms) ms.playbackState = 'paused'; };
    a.onwaiting = () => (waiting = true);
    a.onplaying = () => (waiting = false);
    a.ontimeupdate = () => { if (!held) cur = a.currentTime; };
    a.ondurationchange = () => { if (isFinite(a.duration)) dur = a.duration; };
    a.onended = () => { a.currentTime = cur = 0; }; // repeat off (on, `loop` starts it over by itself)
    a.onerror = () => { on = waiting = false; say(t('common.offline'), 'pleading_face_3d'); };
    if (ms) {
      try { // the lock screen and the headphones' buttons
        ms.metadata = new MediaMetadata({ title: t('anthem.title'), artist: 'KBTU', artwork: [{ src: 'apple-touch-icon.png', sizes: '180x180', type: 'image/png' }] });
        ms.setActionHandler('play', () => void a.play().catch(() => {}));
        ms.setActionHandler('pause', () => a.pause());
      } catch { /* an old WebView without it */ }
    }
    return a;
  }

  function toggle() {
    const a = (audio ??= make());
    if (!a.paused) { a.pause(); return; }
    if (a.error) a.load(); // a failed load (offline) tries again
    on = true; waiting = a.readyState < 3; // the tap answers at once; a ring while it buffers
    a.play().catch((e) => { if (e?.name !== 'AbortError') on = waiting = false; });
  }
  function loop() { repeat = !repeat; if (audio) audio.loop = repeat; }

  // the scrubber: a finger anywhere on it (iOS's own range input moves by its thumb only), the arrows ±5 s
  function scrub(e: PointerEvent) {
    const r = track.getBoundingClientRect();
    cur = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * dur;
  }
  function seek(s: number) { cur = Math.min(dur, Math.max(0, s)); if (audio) audio.currentTime = cur; }
  const letGo = () => { if (held) { held = false; seek(cur); } };
  const STEP: Record<string, number> = { ArrowRight: 5, ArrowUp: 5, ArrowLeft: -5, ArrowDown: -5 };

  // the creator's timer: a close while it runs only stops it (the stamps stay, Copy too)
  const founder = $derived(!!session.me?.founder);
  let timing = $state(false), stamps = $state<number[]>([]), raw = $state('');
  // the line the next tap stamps; once every line is timed, the one being sung
  const at = $derived(timing ? stamps.length : TIMED ? SUNG.filter((l) => l.t! <= cur).length - 1 : -1);
  function timer() {
    if (timing) { timing = false; return; }
    timing = true; stamps = []; raw = ''; cur = 0;
    const a = (audio ??= make());
    a.currentTime = 0;
    if (a.paused) toggle();
  }
  // on the finger's touch, not its lift: the stamp lands when the line is heard
  function stamp() {
    if (!timing || !audio || stamps.length >= SUNG.length) return;
    stamps.push(Math.round(audio.currentTime * 100) / 100);
    haptic.select();
  }
  async function copy() {
    const text = JSON.stringify(stamps);
    try { await navigator.clipboard.writeText(text); }
    catch { // an older WebView: the old way; failing that, the list shows below to copy by hand
      const ta = Object.assign(document.createElement('textarea'), { value: text });
      ta.style.cssText = 'position:fixed;top:0;opacity:0';
      document.body.append(ta); ta.select();
      let ok = false;
      try { ok = document.execCommand('copy'); } catch { /* none at all */ }
      ta.remove();
      if (!ok) { raw = text; haptic.error(); return; }
    }
    haptic.ok(); say(t('anthem.copied'), 'sparkles_3d');
  }
  $effect(() => {
    if (!timing || at < 0) return;
    const smooth = !matchMedia('(prefers-reduced-motion: reduce)').matches;
    words.querySelector(`[data-i="${at}"]`)?.scrollIntoView({ block: 'center', behavior: smooth ? 'smooth' : 'auto' });
  });

  $effect(() => { if (overlay.closing) audio?.pause(); });
  onMount(() => () => {
    if (!audio) return;
    audio.onerror = null;
    audio.pause(); audio.removeAttribute('src'); audio.load(); // its download stops too
    if (ms) { try { ms.metadata = null; ms.setActionHandler('play', null); ms.setActionHandler('pause', null); } catch { /* as above */ } }
  });
</script>

<Sheet {overlay} tall title={t('anthem.title')} icon={Music} hold={() => timing} onhold={() => (timing = false)}>
  <header class="hd">
    <span class="art"><KbtuMark size={30} /></span>
    <h2 class="t-h2">{t('anthem.title')}</h2>
  </header>
  <div class="words" bind:this={words}>
    {#each ANTHEM as part, i (i)}
      <section class="part" class:chorus={part.kind === 'chorus'} lang={part.lang}>
        <h3 class="t-cap">{part.n ? `${part.n} · ${LANG_FULL[part.lang]}` : t('anthem.chorus')}</h3>
        {#each part.lines as line, j (j)}{#if line.i >= 0}<p data-i={line.i} class:now={line.i === at}>{line.text}</p>{:else}<i class="gap"></i>{/if}{/each}
      </section>
    {/each}
  </div>
  {#snippet footer()}
    <div class="player">
      <button class="play" class:off={!on} class:busy={on && waiting} onclick={toggle} aria-label={on ? t('anthem.pause') : t('anthem.play')} aria-busy={on && waiting}>
        {#if on}<Pause size={24} fill="currentColor" />{:else}<Play size={24} fill="currentColor" />{/if}
      </button>
      <div class="seek" class:held role="slider" tabindex="0" aria-label={t('anthem.title')} aria-valuemin={0} aria-valuemax={Math.floor(dur)}
           aria-valuenow={Math.floor(cur)} aria-valuetext="{clock(cur)} / {clock(dur)}"
           onpointerdown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); held = true; scrub(e); }}
           onpointermove={(e) => { if (held) scrub(e); }} onpointerup={letGo} onpointercancel={letGo}
           onkeydown={(e) => { const d = STEP[e.key]; if (d) { e.preventDefault(); seek(cur + d); } }}>
        <span class="track" bind:this={track}><i style="width:{(cur / dur) * 100}%"></i></span>
        <span class="times num"><span>{clock(cur)}</span><span>−{clock(Math.floor(dur) - Math.floor(cur))}</span></span>
      </div>
      <button class="rnd" class:on={repeat} onclick={loop} aria-pressed={repeat} aria-label={t('anthem.repeat')}><Repeat size={20} /></button>
      {#if founder}<button class="rnd" class:on={timing} onclick={timer} aria-pressed={timing} aria-label={t('anthem.timing')}><Timer size={20} /></button>{/if}
    </div>
    {#if founder && (timing || stamps.length)}
      <div class="tim">
        <button class="rnd" onclick={() => stamps.pop()} disabled={!stamps.length} aria-label={t('anthem.undo')}><Undo2 size={20} /></button>
        <button class="tap" data-nohaptic disabled={!timing || stamps.length >= SUNG.length} onpointerdown={stamp} onclick={(e) => { if (!e.detail) stamp(); }}>
          {t('anthem.tap')}<small class="num">{stamps.length}/{SUNG.length}</small></button>
        <button class="rnd" onclick={copy} disabled={!stamps.length} aria-label={t('anthem.copy')}><Copy size={20} /></button>
      </div>
      {#if raw}<textarea class="raw selectable" readonly value={raw}></textarea>{/if}
    {/if}
  {/snippet}
</Sheet>

<style>
  .hd { display: flex; flex-direction: column; align-items: center; gap: 12px; margin: 8px 0 28px; text-align: center; }
  .art { display: grid; place-items: center; width: 60px; height: 60px; border-radius: 17px; background: var(--accent); color: #fff; }

  .part { margin-bottom: 26px; }
  .part h3 { margin-bottom: 10px; }
  /* big enough to sing from (20 px from a 400-px phone, 17 at 320); a line too long for the phone goes on under
     itself, indented, the two halves even */
  .part p { padding-left: 0.8em; text-indent: -0.8em; font: 650 clamp(17px, 5vw, 20px)/1.4 var(--font-text); letter-spacing: -0.012em; text-wrap: balance;
    transition: color var(--t-base); }
  .part p.now { color: var(--accent-text); }
  .gap { display: block; height: 14px; }
  /* the chorus, the same words three times: set apart on a soft band the sheet's width (a card's padding broke its
     lines on a phone), its label in the accent */
  .chorus { margin-left: calc(-1 * var(--gutter)); margin-right: calc(-1 * var(--gutter)); padding: 16px var(--gutter) 18px; background: var(--surface); }
  .chorus h3 { color: var(--accent-text); }

  .player { display: flex; align-items: center; gap: 14px; }
  .play { position: relative; flex: none; width: 56px; height: 56px; border-radius: 50%; display: grid; place-items: center; background: var(--accent); color: #fff; }
  .off :global(svg) { translate: 2px 0; } /* the triangle's weight sits left of its box */
  /* buffering: a thin ring around the button, no layout change */
  .play::after { content: ''; position: absolute; inset: -5px; border-radius: 50%; border: 2px solid transparent; border-top-color: var(--accent); opacity: 0; transition: opacity var(--t-base); }
  .play.busy::after { opacity: 1; animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .play.busy::after { animation: none; } }

  .seek { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; padding: 12px 0 4px; touch-action: none; cursor: pointer; outline: none; }
  .track { position: relative; height: 5px; border-radius: 3px; background: var(--line-2); overflow: hidden; transition: transform var(--t-fast) var(--ease); }
  .held .track { transform: scaleY(1.6); }
  .seek:focus-visible .track { box-shadow: 0 0 0 3px var(--accent-soft); }
  .track i { position: absolute; inset: 0 auto 0 0; border-radius: inherit; background: var(--text); }
  .times { display: flex; justify-content: space-between; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }

  /* a round icon button: repeat, the creator's timer, Undo, Copy */
  .rnd { flex: none; width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; color: var(--text-3);
    transition: transform 450ms var(--ease-bounce), background-color var(--t-base), color var(--t-base), opacity var(--t-base); }
  .rnd.on { background: var(--accent-soft); color: var(--accent-text); }
  .rnd:disabled { opacity: 0.35; }

  .tim { display: flex; align-items: center; gap: 10px; margin-top: 12px; }
  .tap { flex: 1; min-width: 0; display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 50px; border-radius: var(--r-full);
    background: var(--accent); color: #fff; font: 700 18px/1 var(--font-text); }
  .tap small { font: 600 var(--fs-sub)/1 var(--font-text); opacity: 0.75; }
  .tap:disabled { opacity: 0.4; }
  .raw { display: block; width: 100%; height: 64px; margin-top: 10px; padding: 8px 10px; border-radius: 12px; background: var(--surface-2); font: 500 12px/1.35 ui-monospace, monospace; resize: none; }
</style>
