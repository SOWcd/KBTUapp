<script lang="ts">
  // KBTU's anthem as a music player (owner, Nov 2: "like a real player"): a slow soft light behind, the emblem, the
  // title and its three languages, then the words centred, one flow without stanza labels; the controls at the bottom.
  // One audio element, made on the first tap (iOS plays only from a tap; nothing loads before it), paused as the sheet
  // leaves.
  // Playing, the words follow the song (lib/lyrics.ts, the times in lib/i18n/anthem.ts), as Apple Music's lyrics: the
  // emblem goes, the line being sung stays in the middle of the screen, bright and a little larger, its words lit one by
  // one (the one being sung filling from the left; the clock read each frame while it plays); the lines around it
  // dimmer, smaller and softer the further they are; the page glides to each new line a moment before it is sung (one
  // spring from rest, the lines below a beat later);
  // while only the music plays, three breathing dots where the next line comes. The big emblem gives way to a small chip
  // at the top with the verse's language. A hand scrolling the page wins for 3 s; a tap on any line plays from there.
  import { calm } from '../../ui/fold';
  import { onMount, untrack } from 'svelte';
  import { fade } from 'svelte/transition';
  import Music from '@lucide/svelte/icons/music';
  import Play from '@lucide/svelte/icons/play';
  import Pause from '@lucide/svelte/icons/pause';
  import Repeat from '@lucide/svelte/icons/repeat';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { api } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { data, loadMyCard } from '../../lib/state/data.svelte';
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
    a.onplay = () => { on = true; if (ms) ms.playbackState = 'playing'; if (!raf && !calm()) raf = requestAnimationFrame(tick); };
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
    if (!told && !sent && session.me?.student && !owned()) { told = true; say(t('anthem.skipNote'), 'headphone_3d'); }
  }
  const owned = () => !!data.myCard?.awards.achievements.some((x) => x.code === 'anthem' && x.level > 0); // nothing to lose by skipping
  function award() {
    if (sent || !session.me?.student) return;
    sent = true;
    api.anthemHeard().then((r) => { if (session.me) session.me = { ...session.me, unlocked: r.unlocked }; sheets.celebrate(); void loadMyCard(); }).catch(() => (sent = false));
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
  // the page starts gliding GLIDE ahead of the next line's first word, so the line arrives as it is sung (Apple Music's
  // feel); moving on with the word itself put most of the glide after the word had begun
  const GLIDE = 0.3;
  const starts = SUNG.map((l) => l.t ?? 0), ends = SUNG.map((l) => l.end), len = lineLen(starts);
  const synced = $derived(on || cur > 0);
  const langOf = ANTHEM.flatMap((p) => p.lines.filter((l) => l.i >= 0).map(() => p.lang));
  // the line being sung and, in a pause, the next one: states, so they change only when the song moves on to another
  let lit = $state(-1), gapAt = $state(-1), aim = $state(-1); // aim: the line the page centres (GLIDE ahead)

  // where the song is at t: the line lit, or a pause before line `gapAt`; in the lit line the word being sung (.on, --f
  // its fill) and the ones before it (.sung). Each frame while it plays, so: no state but the two lines (they change
  // once a line), the words' classes and fills written straight to the page
  let shown: HTMLElement[] = [], shownLine = -1, shownWord = -1;
  function sync(t = cur) {
    const p = synced ? lyricAt(starts, ends, t + LEAD, dur, len) : { line: -1, next: -1, p: 0 };
    lit = p.line; gapAt = p.next;
    const q = synced ? lyricAt(starts, ends, t + GLIDE, dur, len) : p;
    aim = q.line >= 0 ? q.line : q.next;
    if (p.next >= 0) words?.querySelector<HTMLElement>('.dots')?.style.setProperty('--g', String(p.p));
    let w = -1, f = 0;
    if (p.line >= 0) {
      const i = p.line, next = (starts[i + 1] ?? dur) - starts[i];
      ({ w, f } = wordAt(SUNG[i].o, t + LEAD - starts[i], Math.min(ends[i] != null ? ends[i]! - starts[i] : next > GAP ? len : next, next)));
    }
    // a word filled to the end is sung: the line's last one too, so the line leaves lit whole (as .on it dropped to the
    // dim under-colour the moment the line moved on, its lit copy gone)
    if (f >= 1) { w++; f = 0; }
    if (p.line !== shownLine || w !== shownWord) {
      for (const el of shown) el.classList.remove('sung', 'on');
      shown = p.line >= 0 ? [...(words?.querySelectorAll<HTMLElement>(`.ln[data-i="${p.line}"] .w`) ?? [])] : [];
      shown.forEach((el, k) => { if (k < w) el.classList.add('sung'); else if (k === w) el.classList.add('on'); });
      shownLine = p.line; shownWord = w;
    }
    shown[w]?.style.setProperty('--f', f.toFixed(3));
  }
  // playing starts or the length comes in: the words catch up at once (not only on the next frame)
  $effect(() => { void [synced, dur]; untrack(() => sync(audio ? audio.currentTime : cur)); });

  // the line being sung (or, in a pause, the next one) stays in the middle of the page while the song plays; a hand
  // scrolling the page wins for 3 s, then it comes back.
  // The glide (FLIP): the page jumps to its new place at once and every line in sight starts back where it was, then
  // slides home with one CSS transition of `translate` (the compositor's, one per line, the lines after the sung one a
  // beat later, as Apple Music's); scrollTo's own smooth scroll ran on the main thread and stuttered on iPhone (Nov 2).
  // A line still gliding starts from where it is (its live translate added), so a quick change never snaps
  let userAt = 0, back = 0, free = $state(false);
  const focus = $derived(aim);
  const lang = $derived(focus >= 0 ? langOf[focus] : null);
  const yOf = (x: HTMLElement) => { const v = getComputedStyle(x).translate; return v === 'none' ? 0 : parseFloat(v.split(' ')[1] ?? '0') || 0; };
  function follow(i: number) {
    const el = words.querySelector(`.ln[data-i="${i}"]`), box = words.parentElement; // the line, not its pause's dots
    if (!el || !box || performance.now() - userAt < 3000) return;
    const r = el.getBoundingClientRect(), b = box.getBoundingClientRect(), was = box.scrollTop;
    const top = Math.max(0, was + r.top - b.top - (box.clientHeight - r.height) * 0.45);
    if (Math.abs(top - was) < 1) return;
    if (calm() || Math.abs(top - was) > box.clientHeight) { box.scrollTop = top; return; } // far (a jump back): no glide
    const near = [...words.querySelectorAll<HTMLElement>('.fl')].filter((x) => { const q = x.getBoundingClientRect(); return q.bottom > b.top - 40 && q.top < b.bottom + 40; });
    const now = near.map(yOf);
    box.scrollTop = top;
    const d = box.scrollTop - was;
    words.classList.add('snap');
    near.forEach((x, n) => {
      const k = Number(x.dataset.i ?? -1) - i;
      x.style.setProperty('--lag', `${Math.min(4, Math.max(0, k)) * 40}ms`);
      x.style.translate = `0 ${d + now[n]}px`;
    });
    void words.offsetHeight; // the start is laid down, then it slides
    words.classList.remove('snap');
    for (const x of near) x.style.translate = '';
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
    // while a hand scrolls, every line is sharp and readable (owner, Nov 3: the words stayed blurred, so why scroll);
    // 3 s after it lets go, the song takes the page back and the soft lines with it
    const hand = () => { userAt = performance.now(); free = true; clearTimeout(back); back = window.setTimeout(() => { free = false; if (on) follow(focus); }, 3100); };
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
  <div class="words" class:synced class:free bind:this={words}>
    <!-- playing: the emblem shrinks into this chip, with the verse's language -->
    <div class="chiprow" aria-hidden="true"><span class="chip" class:shown={synced}><span class="mini"><KbtuMark size={13} /></span><b>{t('anthem.title')}</b>{#if lang}<i>{LANG_FULL[lang]}</i>{/if}</span></div>
    <header class="hd fl" class:gone={synced}>
      <span class="art"><KbtuMark size={52} /></span>
      <h2 class="t-h2">{t('anthem.title')}</h2>
      <p class="sub">{LANG_FULL.kk} · {LANG_FULL.en} · {LANG_FULL.ru}</p>
    </header>
    {#each ANTHEM as part, i (i)}
      <div class="part" lang={part.lang}>
        {#each part.lines as line (line)}
          {#if line.i >= 0}
            {#if line.i === gapAt}<span class="dots fl" data-i={line.i} aria-hidden="true" transition:fade={{ duration: 320 }}><i style:--k={0}></i><i style:--k={1}></i><i style:--k={2}></i></span>{/if}
            {@const d = focus >= 0 ? Math.min(4, Math.abs(line.i - focus)) : 1}
            <button class="ln fl" class:now={line.i === lit} class:by={line.i === lit} data-i={line.i} aria-current={line.i === lit || undefined}
                    style:--d={d} onclick={() => jump(line.i)}
                    >{#each line.w as w, k (k)}{k ? ' ' : ''}<span class="w">{w}<span class="lit" aria-hidden="true">{w}</span></span>{/each}</button>
          {/if}
        {/each}
      </div>
    {/each}
  </div>
  {#snippet footer()}
    <!-- in the footer, not the words: the page's scroll fade (a mask) would clip it to the words' box -->
    <div class="aura" class:en={lang === 'en'} class:ru={lang === 'ru'} style:--prog={cur / dur} aria-hidden="true"><i></i><i></i><i></i><i></i></div>
    <!-- the scrubber across, then repeat · play, the play in the middle -->
    <div class="player">
      <div class="seek" class:held role="slider" tabindex="0" aria-label={t('anthem.title')} aria-valuemin={0} aria-valuemax={Math.floor(dur)}
           aria-valuenow={Math.floor(cur)} aria-valuetext="{clock(cur)} / {clock(dur)}"
           onpointerdown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); held = true; scrub(e); }}
           onpointermove={(e) => { if (held) scrub(e); }} onpointerup={letGo} onpointercancel={letGo}
           onkeydown={(e) => { const d = STEP[e.key]; if (d) { e.preventDefault(); seek(cur + d); } }}>
        <span class="bar"><span class="track" bind:this={track}><i bind:this={fill} style:--p={cur / dur}></i></span>{#if held}<b class="knob" style:left="{(cur / dur) * 100}%"></b>{/if}</span>
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
     holds the fixed layer), three lights drifting; the warm one grows as the song goes on (--prog), a cool one comes up
     in the English verse, the pink one in the Russian; a fine grain over it all, as on a print. Soft by their own
     gradients (a blur filter cost a frame in three: measured), only moved by transforms and faded by opacity, both the
     compositor's; lowfx and reduced motion: still */
  /* the light is opaque: the sheet's own glass blur of the page behind would only be redone every frame for nothing
     (it took 4 frames in 10 to 2 in 10 under a 4x slower CPU: measured) */
  :global(.sheet:has(.aura)) { -webkit-backdrop-filter: none; backdrop-filter: none; }
  .aura { position: fixed; inset: 0; z-index: -1; overflow: hidden; pointer-events: none; background: var(--bg); }
  .aura i { position: absolute; width: 130vw; height: 130vw; max-width: 720px; max-height: 720px; border-radius: 50%; opacity: 0.55; will-change: transform;
    background: radial-gradient(closest-side, var(--c), transparent); animation: drift 26s ease-in-out infinite alternate; transition: opacity 2.4s var(--ease); }
  .aura i:nth-child(1) { left: -55%; top: -25%; --c: var(--accent); }
  .aura i:nth-child(2) { right: -60%; top: 10%; --c: var(--accent-2); animation-duration: 31s; animation-delay: -9s; }
  .aura i:nth-child(3) { left: -35%; bottom: -45%; --c: var(--tile-pink); opacity: calc(0.14 + 0.3 * var(--prog, 0)); animation-duration: 37s; animation-delay: -17s; }
  .aura i:nth-child(4) { right: -45%; bottom: -30%; --c: var(--tile-teal); opacity: 0; animation-duration: 29s; animation-delay: -5s; }
  .aura.en i:nth-child(4) { opacity: 0.32; }
  .aura.ru i:nth-child(3) { opacity: 0.5; }
  .aura::after { content: ''; position: absolute; inset: 0; opacity: 0.07;
    background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='160' height='160'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='100%' height='100%' filter='url(%23n)'/></svg>"); }
  @keyframes drift { 33% { transform: translate(18vw, 10vh) scale(1.15); } 66% { transform: translate(-8vw, 22vh) scale(0.9); } 100% { transform: translate(10vw, -6vh) scale(1.05); } }
  /* light: the lights a little stronger than in the dark (white swallows them: 0.3 read as plain white, owner) */
  :global(html[data-theme='light']) .aura i { opacity: 0.6; }
  :global(html[data-theme='light']) .aura i:nth-child(3) { opacity: calc(0.18 + 0.3 * var(--prog, 0)); }
  :global(html[data-theme='light']) .aura i:nth-child(4) { opacity: 0; }
  :global(html[data-theme='light']) .aura.en i:nth-child(4) { opacity: 0.4; }
  :global(html[data-theme='light']) .aura::after { opacity: 0.05; }
  :global(html.lowfx) .aura i { animation: none; }
  @media (prefers-reduced-motion: reduce) { .aura i { animation: none; } }

  /* the glide (follow): `translate` slides home, the lines after the sung one a beat later (--lag); .snap lays the start
     down without it. The scale, the fade and the blur move with it, on the same curve: a spring from rest (critically
     damped, 1-(1+wt)e^-wt): it eases in and settles long, where the old ease-out started at 4.5x its mean speed and read
     as a kick at every line (measured, Nov 2); old WebViews without linear(): a curve that also starts at rest */
  .words { --glide: cubic-bezier(.3, 0, .15, 1); }
  @supports (transition-timing-function: linear(0, 1)) {
    .words { --glide: linear(0, 0.022 3%, 0.075 6%, 0.173 10%, 0.283 14%, 0.417 19%, 0.559 25%, 0.692 32%, 0.801 40%, 0.888 50%, 0.939 60%, 0.971 72%, 0.987 85%, 1); }
  }
  /* only what the compositor moves (the owner, Nov 2: the glide felt laggy): a blur or a colour in a transition
     repainted every soft line each frame on the main thread, so a line's blur and colour change at once, under the glide */
  .fl { transition: opacity 650ms var(--glide), transform 800ms var(--glide), translate 800ms var(--glide) var(--lag, 0ms); }
  .words:global(.snap) .fl { transition-property: opacity, transform; }

  /* the chip: where the emblem goes while it plays; at the top of the page, over the words */
  .chiprow { position: sticky; top: 10px; z-index: 2; height: 0; display: flex; justify-content: center; }
  .chip { display: inline-flex; align-items: center; gap: 7px; height: 30px; padding: 0 12px 0 4px; border-radius: var(--r-full); background: var(--glass-pill-bg);
    box-shadow: 0 6px 18px -8px var(--accent); opacity: 0; transform: translateY(-8px) scale(0.86); transition: opacity 450ms var(--ease), transform 550ms var(--ease); }
  .chip.shown { opacity: 1; transform: none; }
  .mini { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: var(--grad-accent); color: var(--on-accent); }
  .chip b { font: 700 var(--fs-sub)/1 var(--font-text); }
  .chip i { font: 600 var(--fs-cap)/1 var(--font-text); font-style: normal; color: var(--text-3); }

  /* the emblem, the title, the languages; playing, it shrinks up towards the chip and fades */
  .hd { display: flex; flex-direction: column; align-items: center; gap: 8px; margin: 18px 0 30px; text-align: center; transform-origin: 50% 0; }
  .hd.gone { opacity: 0; transform: translateY(-24px) scale(0.5); }
  .art { display: grid; place-items: center; width: 116px; height: 116px; margin-bottom: 10px; border-radius: var(--r-xl); background: var(--grad-accent); color: var(--on-accent);
    box-shadow: 0 18px 40px -16px var(--accent); }
  .sub { font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }

  /* the words, centred, one flow; a part (a verse, a chorus) a little apart from the next */
  .part { margin-bottom: 22px; }
  .ln { position: relative; display: block; width: 100%; padding: 3px 0; text-align: center; text-wrap: balance;
    font: 700 calc(var(--fs-card) * 1.3)/1.32 var(--font-text); letter-spacing: -0.016em; transform-origin: 50% 50%; }
  /* playing: the line being sung bright and a little larger; the lines around it dimmer, a little smaller and softer the
     further they are (--d, 0..4 lines away): their glyphs drawn as their own shadow, sharp next to the sung line and
     blurring from two away (a filter: blur left hairlines at its edges on iPhone, Nov 2). One formula for every line, so
     a line changing its distance blurs or sharpens through a transition (a class for the far ones popped them at each
     line, Nov 2). Room below, so the last line too comes to the middle */
  .words.synced { padding-bottom: 46vh; }
  .synced .ln { opacity: calc(0.46 - 0.08 * var(--d)); color: transparent; text-shadow: 0 0 calc(max(0, var(--d) - 1) * 1.8px) var(--text);
    transform: scale(calc(1 - 0.014 * var(--d))); }
  .synced .ln.by { text-shadow: 0 0 0 transparent; } /* its words carry their own colours */
  .synced.free .ln { opacity: 0.85; text-shadow: 0 0 0 var(--text); transform: none; }
  .synced.free .ln.by { text-shadow: 0 0 0 transparent; }
  /* the sung line on a layer of its own: its word repainted each frame redraws that line alone, not the soft lines
     around it sharing its tile (they are dear to draw) */
  .synced .ln.now { opacity: 1; transform: scale(1.04); will-change: transform; } /* 1.06 touched the edges at 320 px */
  /* word by word in the line being sung: the words to come dim, the sung ones lit, the one being sung lit from the left
     by a lit copy over it, clipped (--f, 0..1): only glyphs ever show, no box, mask or layer of its own (a masked,
     composited copy left violet seams at its edges on iPhone, Nov 2). At --f 1 the copy covers the word, so it hands
     over to .sung without a step */
  .w { position: relative; display: inline-block; white-space: nowrap; }
  .lit { display: none; }
  .ln.by .w { color: var(--text-3); }
  .ln.by .w:global(.sung) { color: var(--text); }
  /* the dark: the sung words glow a little, as lit (light: a dark halo would read as dirt) */
  :global(html:not([data-theme='light'])) .ln.by .w:global(.sung), :global(html:not([data-theme='light'])) .ln.by .w:global(.on) .lit {
    text-shadow: 0 0 14px rgba(255, 255, 255, 0.28); }
  .ln.by .w:global(.on) .lit { display: block; position: absolute; inset: 0; color: var(--text); text-align: left; pointer-events: none;
    -webkit-clip-path: inset(-0.3em calc((1 - var(--f, 0)) * 100%) -0.3em -0.3em); clip-path: inset(-0.3em calc((1 - var(--f, 0)) * 100%) -0.3em -0.3em); }
  /* while only the music plays: three dots where the next line comes, one lighting after another as the pause goes
     (--g, set by sync), breathing; no height of their own, nothing moves */
  .dots { position: relative; display: flex; justify-content: center; gap: 8px; height: 0; top: -14px; }
  .dots i { width: 9px; height: 9px; border-radius: 50%; background: var(--text); animation: breathe 2.4s ease-in-out infinite;
    opacity: calc(0.25 + 0.75 * clamp(0, var(--g, 0) * 3 - var(--k), 1)); transition: opacity 250ms linear; }
  .dots i:nth-child(2) { animation-delay: 0.2s; } .dots i:nth-child(3) { animation-delay: 0.4s; }
  @keyframes breathe { 50% { transform: scale(1.22); } }
  :global(html.lowfx) .dots i { animation: none; }
  @media (prefers-reduced-motion: reduce) {
    .synced .ln, .synced .ln.now, .hd.gone, .chip { transform: none; } .dots i { animation: none; }
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
  /* the scrubber: held, thicker, with a glow and a knob where the finger is */
  .bar { position: relative; display: block; }
  .track { position: relative; display: block; height: 5px; border-radius: var(--r-full); background: var(--line-2); overflow: hidden; transition: transform var(--t-fast) var(--ease), box-shadow var(--t-base); }
  .held .track { transform: scaleY(1.8); box-shadow: 0 0 16px -2px var(--accent); }
  .knob { position: absolute; top: 50%; width: 16px; height: 16px; margin: -8px 0 0 -8px; border-radius: 50%; background: var(--text); box-shadow: 0 0 0 5px var(--accent-soft), 0 2px 8px -2px var(--accent); }
  .seek:focus-visible .track { box-shadow: 0 0 0 3px var(--accent-soft); }
  .track i { position: absolute; inset: 0; border-radius: inherit; background: var(--text); transform-origin: 0 50%; transform: scaleX(var(--p, 0)); will-change: transform; } /* a transform: set each frame, never laid out */
  .times { display: flex; justify-content: space-between; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }

  /* repeat, round; its twin on the other side is empty, so the play stays in the middle */
  .rnd { flex: none; width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; color: var(--text-2);
    transition: transform 450ms var(--ease-bounce), background-color var(--t-base), color var(--t-base); }
  .rnd.on { background: var(--accent-soft); color: var(--accent-text); }
  .rnd-gap { flex: none; width: 48px; }
</style>
