<script lang="ts">
  // KBTU's anthem as a music player (owner, Nov 2: "like a real player"): a slow soft light behind, the emblem, the
  // title and its three languages, then the words centred, one flow without stanza labels; the controls at the bottom.
  // One audio element, made on the first tap (iOS plays only from a tap; nothing loads before it), paused as the sheet
  // leaves.
  // Playing, the words follow the song (lib/lyrics.ts, the times in lib/i18n/anthem.ts), as Apple Music's lyrics: the
  // emblem goes, the line being sung stays in the middle of the screen, bright and a little larger, its words lit one by
  // one (the one being sung filling from the left; the clock read each frame while it plays); the lines around it
  // dimmer and blurred the further they are. A hand scrolling the page wins for 3 s; a tap on any line plays from there.
  import { onMount, untrack } from 'svelte';
  import Music from '@lucide/svelte/icons/music';
  import Play from '@lucide/svelte/icons/play';
  import Pause from '@lucide/svelte/icons/pause';
  import Repeat from '@lucide/svelte/icons/repeat';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { t, LANG_FULL } from '../../lib/i18n/index.svelte';
  import { ANTHEM, SUNG } from '../../lib/i18n/anthem';
  import { GAP, lineLen, lyricAt, wordAt } from '../../lib/lyrics';
  import Sheet from '../../ui/Sheet.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { glass } from '../../ui/glass';

  let { overlay }: { overlay: Overlay } = $props();
  let audio: HTMLAudioElement | null = null;
  let on = $state(false), waiting = $state(false), repeat = $state(false), held = $state(false);
  let cur = $state(0), dur = $state(211); // the file's length: the time left shows before it loads
  let track: HTMLSpanElement, fill: HTMLElement, words: HTMLDivElement;
  const ms = 'mediaSession' in navigator ? navigator.mediaSession : null;
  const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;
  const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  // while it plays the clock is read each frame (timeupdate comes ~4 times a second: a word would fill in steps), and
  // the frame touches no state: sync() writes CSS variables and a word's class straight to the page (a Svelte state
  // per frame re-ran the whole sheet's template every frame, Nov 2); reduced motion: words light whole, timeupdate is enough
  let raf = 0;
  function tick() {
    if (!audio || audio.paused) { raf = 0; return; }
    if (!held) { const t = audio.currentTime; sync(t); fill.style.setProperty('--p', String(t / dur)); }
    raf = requestAnimationFrame(tick);
  }

  function make(): HTMLAudioElement {
    const a = new Audio();
    a.preload = 'none';
    a.loop = repeat;
    a.src = 'anthem/kbtu-anthem.m4a';
    const from = cur; // scrubbed or a line tapped before the first play: it starts there
    if (from) a.addEventListener('loadedmetadata', () => (a.currentTime = from), { once: true });
    a.onplay = () => { on = true; if (ms) ms.playbackState = 'playing'; if (!raf && !still()) raf = requestAnimationFrame(tick); };
    a.onpause = () => { on = waiting = false; if (ms) ms.playbackState = 'paused'; };
    a.onwaiting = () => (waiting = true);
    a.onplaying = () => (waiting = false);
    a.ontimeupdate = () => { heard(a); if (!held) { cur = a.currentTime; if (!raf || a.paused) sync(cur); } };
    a.onseeked = () => { heard(a); if (!held) sync(a.currentTime); };
    a.ondurationchange = () => { if (isFinite(a.duration)) dur = a.duration; };
    a.onended = () => { if (run >= dur - 3) award(); run = -1; a.currentTime = cur = 0; }; // repeat off (on, `loop` starts it over by itself)
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

  // the award for the whole anthem without skipping (owner, Nov 2): a play is followed from its first 2 s; a jump forward
  // past what was heard (the scrubber, the arrows, a line tapped ahead) loses it, once with a word why; back and pause
  // are fine. At the end (or as `loop` wraps it round) the server gives it, once a student, and its moment shows here
  let run = -1, runAt = 0, told = false, sent = false; // run: how far the followed play has got (s), -1: none; runAt: when (ms)
  function heard(a: HTMLAudioElement) {
    // a locked phone sends timeupdate rarely: the time played since the last one counts (paused: none; at most 5 s)
    const at = a.currentTime, gone = a.paused ? 0 : Math.min(5, (performance.now() - runAt) / 1000);
    runAt = performance.now();
    if (run < 0) { if (at < 2 && !a.paused) run = at; return; }
    if (a.loop && at < 1 && run >= dur - 3) { award(); run = at; return; }
    if (at <= run + 2 + gone) { run = Math.max(run, at); return; }
    run = -1;
    if (!told && !sent && session.me?.student) { told = true; say(t('anthem.skipNote'), 'headphone_3d'); }
  }
  function award() {
    if (sent || !session.me?.student) return;
    sent = true;
    api.anthemHeard().then((r) => { if (session.me) session.me = { ...session.me, unlocked: r.unlocked }; sheets.celebrate(); }).catch(() => (sent = false));
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
    sync(cur);
  }
  function seek(s: number) { cur = Math.min(dur, Math.max(0, s)); if (audio) audio.currentTime = cur; sync(cur); }
  const letGo = () => { if (held) { held = false; seek(cur); } };
  const STEP: Record<string, number> = { ArrowRight: 5, ArrowUp: 5, ArrowLeft: -5, ArrowDown: -5 };

  // the times are the voice's own (aligned, lib/i18n/anthem.ts) and the clock is read each frame: the words run only
  // LEAD ahead, as the eye reads
  const LEAD = 0.1;
  const starts = SUNG.map((l) => l.t ?? 0), ends = SUNG.map((l) => l.end), len = lineLen(starts);
  const synced = $derived(on || cur > 0);
  // the line being sung and, in a pause, the next one: states, so they change only when the song moves on to another
  let lit = $state(-1), gapAt = $state(-1);

  // where the song is at t: the line lit, or a pause before line `gapAt`; in the lit line the word being sung (.on, --f
  // its fill) and the ones before it (.sung). Each frame while it plays, so: no state but the two lines (they change
  // once a line), the words' classes and fills written straight to the page
  let shown: HTMLElement[] = [], shownLine = -1, shownWord = -1;
  function sync(t = cur) {
    const p = synced ? lyricAt(starts, ends, t + LEAD, dur, len) : { line: -1, next: -1, p: 0 };
    lit = p.line; gapAt = p.next;
    let w = -1, f = 0;
    if (p.line >= 0) {
      const i = p.line, next = (starts[i + 1] ?? dur) - starts[i];
      ({ w, f } = wordAt(SUNG[i].o, t + LEAD - starts[i], Math.min(ends[i] != null ? ends[i]! - starts[i] : next > GAP ? len : next, next)));
    }
    if (p.line !== shownLine || w !== shownWord) {
      for (const el of shown) el.classList.remove('sung', 'on');
      shown = p.line >= 0 ? [...(words?.querySelectorAll<HTMLElement>(`[data-i="${p.line}"] .w`) ?? [])] : [];
      shown.forEach((el, k) => { if (k < w) el.classList.add('sung'); else if (k === w) el.classList.add('on'); });
      shownLine = p.line; shownWord = w;
    }
    shown[w]?.style.setProperty('--f', f.toFixed(3));
  }
  // playing starts or the length comes in: the words catch up at once (not only on the next frame)
  $effect(() => { void [synced, dur]; untrack(() => sync(audio ? audio.currentTime : cur)); });

  // the line being sung (or, in a pause, the next one) stays in the middle of the page while the song plays; a hand
  // scrolling the page wins for 3 s, then it comes back
  let userAt = 0, back = 0;
  const focus = $derived(lit >= 0 ? lit : gapAt);
  function follow(i: number) {
    const el = words.querySelector(`[data-i="${i}"]`), box = words.parentElement;
    if (!el || !box || performance.now() - userAt < 3000) return;
    const r = el.getBoundingClientRect();
    const top = box.scrollTop + r.top - box.getBoundingClientRect().top - (box.clientHeight - r.height) * 0.45;
    box.scrollTo({ top: Math.max(0, top), behavior: still() ? 'auto' : 'smooth' });
  }
  $effect(() => { const f = focus; if (f >= 0 && on) untrack(() => follow(f)); });

  // a tap on a line plays from it
  function jump(i: number) {
    userAt = 0;
    seek(starts[i] - LEAD);
    if (!audio || audio.paused) toggle();
  }

  $effect(() => { if (overlay.closing) audio?.pause(); });
  onMount(() => {
    const box = words.parentElement!;
    const hand = () => { userAt = performance.now(); clearTimeout(back); back = window.setTimeout(() => { if (on) follow(focus); }, 3100); };
    box.addEventListener('touchmove', hand, { passive: true });
    box.addEventListener('wheel', hand, { passive: true });
    return () => {
      clearTimeout(back); cancelAnimationFrame(raf); box.removeEventListener('touchmove', hand); box.removeEventListener('wheel', hand);
      if (!audio) return;
      audio.onerror = null;
      audio.pause(); audio.removeAttribute('src'); audio.load(); // its download stops too
      if (ms) { try { ms.metadata = null; ms.setActionHandler('play', null); ms.setActionHandler('pause', null); } catch { /* as above */ } }
    };
  });
</script>

<Sheet {overlay} tall title={t('anthem.title')} icon={Music}>
  <header class="hd" class:gone={synced}>
    <span class="art"><KbtuMark size={52} /></span>
    <h2 class="t-h2">{t('anthem.title')}</h2>
    <p class="sub">{LANG_FULL.kk} · {LANG_FULL.en} · {LANG_FULL.ru}</p>
  </header>
  <div class="words" class:synced bind:this={words}>
    {#each ANTHEM as part, i (i)}
      <div class="part" lang={part.lang}>
        {#each part.lines as line (line)}
          {#if line.i >= 0}
            <button class="ln" class:now={line.i === lit} class:by={line.i === lit} data-i={line.i} aria-current={line.i === lit || undefined}
                    style:--d={focus >= 0 ? Math.min(4, Math.abs(line.i - focus)) : null} onclick={() => jump(line.i)}
                    >{#each line.w as w, k (k)}{k ? ' ' : ''}<span class="w">{w}<span class="lit" aria-hidden="true"><span>{w}</span></span></span>{/each}</button>
          {/if}
        {/each}
      </div>
    {/each}
  </div>
  {#snippet footer()}
    <!-- in the footer, not the words: the page's scroll fade (a mask) would clip it to the words' box -->
    <div class="aura" aria-hidden="true"><i></i><i></i><i></i></div>
    <!-- the scrubber across, then repeat · play, the play in the middle -->
    <div class="player">
      <div class="seek" class:held role="slider" tabindex="0" aria-label={t('anthem.title')} aria-valuemin={0} aria-valuemax={Math.floor(dur)}
           aria-valuenow={Math.floor(cur)} aria-valuetext="{clock(cur)} / {clock(dur)}"
           onpointerdown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); held = true; scrub(e); }}
           onpointermove={(e) => { if (held) scrub(e); }} onpointerup={letGo} onpointercancel={letGo}
           onkeydown={(e) => { const d = STEP[e.key]; if (d) { e.preventDefault(); seek(cur + d); } }}>
        <span class="track" bind:this={track}><i bind:this={fill} style:--p={cur / dur}></i></span>
        <span class="times num"><span>{clock(cur)}</span><span>−{clock(Math.floor(dur) - Math.floor(cur))}</span></span>
      </div>
      <div class="ctl">
        <button class="rnd glass glass-pill" use:glass class:on={repeat} onclick={loop} aria-pressed={repeat} aria-label={t('anthem.repeat')}><Repeat size={20} /></button>
        <button class="play glass glass-pill" use:glass class:off={!on} class:busy={on && waiting} onclick={toggle} aria-label={on ? t('anthem.pause') : t('anthem.play')} aria-busy={on && waiting}>
          {#if on}<Pause size={30} fill="currentColor" />{:else}<Play size={30} fill="currentColor" />{/if}
        </button>
        <i class="rnd-gap"></i>
      </div>
    </div>
  {/snippet}
</Sheet>

<style>
  /* the background: slow soft light in the app's colours behind the whole sheet (it doesn't scroll: the sheet's transform
     holds the fixed layer), three lights drifting. Soft by their own gradients (a blur filter cost a frame in three:
     measured), only moved by transforms on composited layers; lowfx and reduced motion: still */
  /* the light is opaque: the sheet's own glass blur of the page behind would only be redone every frame for nothing
     (it took 4 frames in 10 to 2 in 10 under a 4x slower CPU: measured) */
  :global(.sheet:has(.aura)) { -webkit-backdrop-filter: none; backdrop-filter: none; }
  .aura { position: fixed; inset: 0; z-index: -1; overflow: hidden; pointer-events: none; background: var(--bg); }
  .aura i { position: absolute; width: 130vw; height: 130vw; max-width: 720px; max-height: 720px; border-radius: 50%; opacity: 0.55; will-change: transform;
    background: radial-gradient(closest-side, var(--c), transparent); animation: drift 26s ease-in-out infinite alternate; }
  .aura i:nth-child(1) { left: -55%; top: -25%; --c: var(--accent); }
  .aura i:nth-child(2) { right: -60%; top: 10%; --c: var(--accent-2); animation-duration: 31s; animation-delay: -9s; }
  .aura i:nth-child(3) { left: -35%; bottom: -45%; --c: var(--tile-pink); opacity: 0.3; animation-duration: 37s; animation-delay: -17s; }
  @keyframes drift { 33% { transform: translate(18vw, 10vh) scale(1.15); } 66% { transform: translate(-8vw, 22vh) scale(0.9); } 100% { transform: translate(10vw, -6vh) scale(1.05); } }
  /* light: the lights a little stronger than in the dark (white swallows them: 0.3 read as plain white, owner) */
  :global(html[data-theme='light']) .aura i { opacity: 0.6; }
  :global(html[data-theme='light']) .aura i:nth-child(3) { opacity: 0.34; }
  :global(html.lowfx) .aura i { animation: none; }
  @media (prefers-reduced-motion: reduce) { .aura i { animation: none; } }

  /* the emblem, the title, the languages; playing, it fades and the page glides past it to the words */
  .hd { display: flex; flex-direction: column; align-items: center; gap: 8px; margin: 18px 0 30px; text-align: center; transition: opacity 500ms var(--ease), transform 500ms var(--ease); }
  .hd.gone { opacity: 0; transform: scale(0.94); }
  .art { display: grid; place-items: center; width: 116px; height: 116px; margin-bottom: 10px; border-radius: var(--r-xl); background: var(--grad-accent); color: var(--on-accent);
    box-shadow: 0 18px 40px -16px var(--accent); }
  .sub { font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }

  /* the words, centred, one flow; a part (a verse, a chorus) a little apart from the next */
  .part { margin-bottom: 22px; }
  .ln { position: relative; display: block; width: 100%; padding: 3px 0; text-align: center; text-wrap: balance;
    font: 700 calc(var(--fs-card) * 1.3)/1.32 var(--font-text); letter-spacing: -0.016em;
    transform-origin: 50% 50%; transition: opacity 400ms var(--ease), transform 400ms var(--ease), filter 400ms var(--ease); }
  /* playing: the line being sung bright and a little larger; the lines around it fade and blur the further they are
     (--d, 0..4 lines away; set once a line), a few read and the rest is a soft hint. Room below, so the last line too
     comes to the middle */
  .words.synced { padding-bottom: 46vh; }
  .synced .ln { opacity: calc(0.42 - 0.075 * var(--d, 1)); filter: blur(calc(max(0, var(--d, 1) - 1) * 0.8px)); }
  .synced .ln.now { opacity: 1; filter: none; transform: scale(1.05); will-change: transform; } /* its own layer: its words change, the blurred lines aren't repainted */
  /* word by word in the line being sung: the words to come dim, the sung ones lit, the one being sung filling from the
     left with a soft edge. The fill is two transforms (a clipping box slid in by --f, the lit copy slid back by as much):
     each frame moves only composited layers, nothing is laid out or repainted; a fill painted per frame
     (background-clip: text) stuttered and blinked on iPhone (Nov 2). At --f 1 the copy covers the word exactly, so it
     hands over to .sung without a step (no colour transitions on words: one faded a sung word in again) */
  .w { position: relative; display: inline-block; text-indent: 0; white-space: nowrap; }
  .lit { display: none; }
  .ln.by .w { color: var(--text-3); }
  .ln.by .w:global(.sung) { color: var(--text); }
  .ln.by .w:global(.on) .lit { display: block; position: absolute; inset: 0 -0.4em 0 0; overflow: hidden; pointer-events: none;
    transform: translateX(calc((var(--f, 0) - 1) * 100%)); will-change: transform;
    -webkit-mask-image: linear-gradient(90deg, black calc(100% - 0.4em), transparent); mask-image: linear-gradient(90deg, black calc(100% - 0.4em), transparent); }
  .lit > span { display: block; text-align: left; color: var(--text); transform: translateX(calc((1 - var(--f, 0)) * 100%)); will-change: transform; }
  :global(html.lowfx) .synced .ln { filter: none; }
  @media (prefers-reduced-motion: reduce) {
    .synced .ln { filter: none; } .synced .ln.now, .hd.gone { transform: none; }
    .ln.by .w:global(.on) { color: var(--text); } .ln.by .w:global(.on) .lit { display: none; } /* a word lights whole */
  }

  /* the controls float over the background: the sheet's footer without its line */
  :global(.foot:has(> .player)) { border-top-color: transparent; }
  .player { display: flex; flex-direction: column; gap: 10px; }
  .ctl { display: flex; align-items: center; justify-content: center; gap: 28px; padding-bottom: 2px; }
  .play { position: relative; flex: none; width: 76px; height: 76px; border-radius: 50%; display: grid; place-items: center; color: var(--text); }
  .off :global(svg) { translate: 2px 0; } /* the triangle's weight sits left of its box */
  /* buffering: a thin ring around the button, no layout change */
  .play::after { content: ''; position: absolute; inset: -5px; border-radius: 50%; border: 2px solid transparent; border-top-color: var(--accent); opacity: 0; transition: opacity var(--t-base); }
  .play.busy::after { opacity: 1; animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .play.busy::after { animation: none; } }

  .seek { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 8px; padding: 12px 0 4px; touch-action: none; cursor: pointer; outline: none; }
  .track { position: relative; height: 5px; border-radius: var(--r-full); background: var(--line-2); overflow: hidden; transition: transform var(--t-fast) var(--ease); }
  .held .track { transform: scaleY(1.6); }
  .seek:focus-visible .track { box-shadow: 0 0 0 3px var(--accent-soft); }
  .track i { position: absolute; inset: 0; border-radius: inherit; background: var(--text); transform-origin: 0 50%; transform: scaleX(var(--p, 0)); will-change: transform; } /* a transform: set each frame, never laid out */
  .times { display: flex; justify-content: space-between; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }

  /* repeat, round; its twin on the other side is empty, so the play stays in the middle */
  .rnd { flex: none; width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; color: var(--text-2);
    transition: transform 450ms var(--ease-bounce), background-color var(--t-base), color var(--t-base); }
  .rnd.on { background: var(--accent-soft); color: var(--accent-text); }
  .rnd-gap { flex: none; width: 48px; }
</style>
