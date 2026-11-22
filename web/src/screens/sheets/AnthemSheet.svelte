<script lang="ts">
  // KBTU's anthem as a music player: a slow soft light behind, the emblem, the
  // title and its three languages, then the words centred, one flow without stanza labels; the controls at the bottom.
  // The audio and the award's rule live outside the sheet (lib/state/anthem.svelte.ts): the song stops as the sheet
  // leaves, unless it is sent to the background (the small button right of the play: the sheet closes, the song goes on
  // and the capsule shows it; a tap there opens the sheet again).
  // After the last line (the instrumental tail, ~15 s) the words give way to the award itself: its coin, grey at first and
  // taking its colours as the end comes, and the time left to it; no award to wait for (it is mine already, or this
  // play skipped something): the coin as it stands and what it is for.
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
  import PictureInPicture2 from '@lucide/svelte/icons/picture-in-picture-2';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { anthem, anthemLoop, anthemOwned, anthemPause, anthemSeek, anthemStop, anthemTime, anthemToggle } from '../../lib/state/anthem.svelte';
  import { coinOf } from '../../lib/awards';
  import { t, LANG_FULL } from '../../lib/i18n/index.svelte';
  import { ANTHEM, SUNG } from '../../lib/i18n/anthem';
  import { GAP, lineLen, lyricAt, wordAt } from '../../lib/lyrics';
  import Sheet from '../../ui/Sheet.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { glass } from '../../ui/glass';

  let { overlay }: { overlay: Overlay } = $props();
  let held = $state(false), drag = $state(0); // the scrubber under a finger shows the finger's place, not the song's
  const on = $derived(anthem.on), dur = $derived(anthem.dur), cur = $derived(held ? drag : anthem.cur);
  let track: HTMLSpanElement, fill: HTMLElement, words: HTMLDivElement, fin = $state<HTMLDivElement>();
  const clock = (s: number) => `${Math.floor(s / 60)}:${String(Math.floor(s % 60)).padStart(2, '0')}`;

  // while it plays the clock is read each frame (timeupdate comes ~4 times a second: a word would fill in steps), and
  // the frame touches no state: sync() writes CSS variables and a word's class straight to the page (a Svelte state
  // per frame re-ran the whole sheet's template every frame); reduced motion: words light whole, timeupdate is enough
  let raf = 0;
  function tick() {
    if (!anthem.on) { raf = 0; return; }
    if (!held) { const t = anthemTime(); sync(t); fill.style.setProperty('--p', String(t / dur)); }
    raf = requestAnimationFrame(tick);
  }
  $effect(() => { if (on && !raf && !calm()) raf = requestAnimationFrame(tick); });
  // paused, sought, or reduced motion: the song's own events move the words
  $effect(() => { const c = cur; untrack(() => { if (!raf) sync(c); }); });

  const toggle = anthemToggle;
  // the scrubber: a finger anywhere on it (iOS's own range input moves by its thumb only), the arrows ±5 s
  function scrub(e: PointerEvent) {
    const r = track.getBoundingClientRect();
    drag = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)) * dur;
    sync(drag);
  }
  function seek(s: number) { anthemSeek(s); sync(anthem.cur); }
  const letGo = () => { if (held) { held = false; seek(drag); } };
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
  // the tail: from a moment after the last line's end to the song's; `left`: whole seconds to the end (a state: it
  // changes once a second); how far through it, --c on the coin, each frame
  const TAIL = (ends[ends.length - 1] ?? starts[starts.length - 1] + len) + 0.8;
  let tail = $state(false), left = $state(0);
  const COIN = coinOf({ code: 'anthem', emoji: '', level: 1, levels: [] });
  // count: an award is coming (a student's fair play, not his yet); has: it is his
  const has = $derived(anthemOwned()), count = $derived(!has && anthem.fair && !!session.me?.student);

  // where the song is at t: the line lit, or a pause before line `gapAt`; in the lit line the word being sung (.on, --f
  // its fill) and the ones before it (.sung). Each frame while it plays, so: no state but the two lines (they change
  // once a line), the words' classes and fills written straight to the page
  let shown: HTMLElement[] = [], shownLine = -1, shownWord = -1;
  function sync(t = cur) {
    const p = synced ? lyricAt(starts, ends, t + LEAD, dur, len) : { line: -1, next: -1, p: 0 };
    const end = synced && t >= TAIL;
    if (end !== tail) tail = end;
    if (end) {
      const s = Math.max(0, Math.ceil(dur - t));
      if (s !== left) left = s;
      fin?.style.setProperty('--c', Math.min(1, (t - TAIL) / Math.max(1, dur - TAIL)).toFixed(3));
    }
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
  $effect(() => { void [synced, dur, fin]; untrack(() => sync(held ? drag : anthemTime())); });
  // the award given: its coin settles, a soft light crossing it once (its own moment comes over the sheet right after)
  $effect(() => {
    if (!anthem.won || !fin || calm()) return;
    fin.querySelector('.coin')?.animate([{ transform: 'scale(1)' }, { transform: 'scale(1.07)', offset: 0.35 }, { transform: 'scale(1)' }], { duration: 900, easing: 'cubic-bezier(.3, 0, .15, 1)' });
    fin.querySelector('.glint')?.animate([{ transform: 'translateX(-130%) skewX(-18deg)', opacity: 0 }, { opacity: 1, offset: 0.4 }, { transform: 'translateX(130%) skewX(-18deg)', opacity: 0 }], { duration: 1100, easing: 'ease-in-out' });
  });

  // the line being sung (or, in a pause, the next one) stays in the middle of the page while the song plays; a hand
  // scrolling the page wins for 3 s, then it comes back.
  // The glide (FLIP): the page jumps to its new place at once and every line in sight starts back where it was, then
  // slides home with one CSS transition of `translate` (the compositor's, one per line, the lines after the sung one a
  // beat later, as Apple Music's); scrollTo's own smooth scroll ran on the main thread and stuttered on iPhone.
  // A line still gliding starts from where it is (its live translate added), so a quick change never snaps
  let userAt = 0, back = 0, free = $state(false);
  const focus = $derived(aim);
  const lang = $derived(focus >= 0 ? langOf[focus] : null);
  // the chip names the verse's language alone (the capsule above already says whose anthem); leaving, it keeps its word
  let lastLang = langOf[0];
  const chipLang = $derived(lang ? (lastLang = lang) : lastLang);
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
    if (!anthem.on) toggle();
  }

  // to the background: the sheet goes, the song stays (the capsule's live status, App.svelte)
  let kept = false;
  function away() { kept = anthem.bg = true; close(overlay.id); }
  $effect(() => { if (overlay.closing && !kept) anthemPause(); });
  onMount(() => {
    anthem.bg = false; // opened again from the capsule: the sheet has it now
    const box = words.parentElement!;
    // while a hand scrolls, every line is sharp and readable (the words stayed blurred, so why scroll);
    // 3 s after it lets go, the song takes the page back and the soft lines with it
    const hand = () => { userAt = performance.now(); free = true; clearTimeout(back); back = window.setTimeout(() => { free = false; if (on) follow(focus); }, 3100); };
    box.addEventListener('touchmove', hand, { passive: true });
    box.addEventListener('wheel', hand, { passive: true });
    return () => {
      clearTimeout(back); cancelAnimationFrame(raf); box.removeEventListener('touchmove', hand); box.removeEventListener('wheel', hand);
      if (!kept) anthemStop();
    };
  });
</script>

<Sheet {overlay} tall title={t('anthem.title')} icon={Music}>
  <div class="words" class:synced class:free class:tail bind:this={words}>
    <!-- playing: the emblem shrinks into this chip, the verse's language beside it -->
    <div class="chiprow" aria-hidden="true"><span class="chip" class:shown={synced && !!lang}><span class="mini"><KbtuMark size={13} /></span><b>{LANG_FULL[chipLang]}</b></span></div>
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
    <!-- both in the footer, not the words: the page's scroll fade (a mask) would clip them to the words' box.
         The tail: the award's coin (grey under, its colours and their light coming up with --c), the time left to it -->
    <div class="fin" class:shown={tail} class:count class:has bind:this={fin} aria-hidden={!tail}>
      <span class="coin"><i class="halo"></i><img class="grey" src={`emoji/${COIN}.webp`} alt="" draggable="false" /><img class="col" src={`emoji/${COIN}.webp`} alt="" draggable="false" /><span class="clip"><i class="glint"></i></span></span>
      {#if count}
        <p class="cap">{t('anthem.in')}</p>
        <p class="big num" aria-live="off">{clock(left)}</p>
      {:else}
        <p class="name">{t('ach.anthem.name')}</p>
        {#if !has}<p class="cap how">{t('ach.anthem.how')}</p>{/if}
      {/if}
    </div>
    <div class="aura" class:en={lang === 'en'} class:ru={lang === 'ru'} style:--prog={cur / dur} aria-hidden="true"><i></i><i></i><i></i><i></i></div>
    <!-- the scrubber across, then repeat · play, the play in the middle -->
    <div class="player">
      <div class="seek" class:held role="slider" tabindex="0" aria-label={t('anthem.title')} aria-valuemin={0} aria-valuemax={Math.floor(dur)}
           aria-valuenow={Math.floor(cur)} aria-valuetext="{clock(cur)} / {clock(dur)}"
           onpointerdown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); scrub(e); held = true; }}
           onpointermove={(e) => { if (held) scrub(e); }} onpointerup={letGo} onpointercancel={letGo}
           onkeydown={(e) => { const d = STEP[e.key]; if (d) { e.preventDefault(); seek(cur + d); } }}>
        <span class="bar"><span class="track" bind:this={track}><i bind:this={fill} style:--p={cur / dur}></i></span>{#if held}<b class="knob" style:left="{(cur / dur) * 100}%"></b>{/if}</span>
        <span class="times num"><span>{clock(cur)}</span><span>−{clock(Math.floor(dur) - Math.floor(cur))}</span></span>
      </div>
      <div class="ctl">
        <button class="rnd glass glass-pill" use:glass class:on={anthem.repeat} onclick={anthemLoop} aria-pressed={anthem.repeat} aria-label={t('anthem.repeat')}><Repeat size={20} /></button>
        <button class="play glass glass-pill" use:glass class:off={!on} class:busy={on && anthem.waiting} onclick={toggle} aria-label={on ? t('anthem.pause') : t('anthem.play')} aria-busy={on && anthem.waiting}>
          {#if on}<Pause size={30} fill="currentColor" />{:else}<Play size={30} fill="currentColor" />{/if}
        </button>
        <button class="rnd glass glass-pill" use:glass disabled={!on} onclick={away} aria-label={t('anthem.bg')}><PictureInPicture2 size={20} /></button>
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
  /* light: the lights a little stronger than in the dark (white swallows them: 0.3 read as plain white) */
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
  /* only what the compositor moves (the glide felt laggy): a blur or a colour in a transition
     repainted every soft line each frame on the main thread, so a line's blur and colour change at once, under the glide */
  .fl { transition: opacity 650ms var(--glide), transform 800ms var(--glide), translate 800ms var(--glide) var(--lag, 0ms); }
  .words:global(.snap) .fl { transition-property: opacity, transform; }

  /* the chip: where the emblem goes while it plays; at the top of the page, over the words */
  .chiprow { position: sticky; top: 10px; z-index: 2; height: 0; display: flex; justify-content: center; }
  .chip { display: inline-flex; align-items: center; gap: 7px; height: 30px; padding: 0 12px 0 4px; border-radius: var(--r-full); background: var(--glass-pill-bg);
    box-shadow: 0 6px 18px -8px var(--accent); opacity: 0; transform: translateY(-8px) scale(0.86); transition: opacity 450ms var(--ease), transform 550ms var(--ease); }
  .chip.shown { opacity: 1; transform: none; }
  .mini { display: grid; place-items: center; width: 22px; height: 22px; border-radius: 50%; background: var(--grad-accent); color: var(--on-accent); }
  .chip b { font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-2); }

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

  /* repeat and "in the background", round, either side of the play; the second only while it plays */
  .rnd { flex: none; width: 48px; height: 48px; border-radius: 50%; display: grid; place-items: center; color: var(--text-2);
    transition: transform 450ms var(--ease-bounce), background-color var(--t-base), color var(--t-base); }
  .rnd.on { background: var(--accent-soft); color: var(--accent-text); }
  .rnd:disabled { opacity: 0.38; }

  /* the tail: the words fade and can't be tapped (a tap on a line unseen would seek, and lose the award); the coin
     and the time come up in their place, over the page and above the controls (in the footer for the aura's reason).
     The coin: its grey self under (one still filter, drawn once), its colours over it by opacity alone (--c, 0..1, each
     frame: the compositor's), growing a little as they come; reduced motion: the colours still come, nothing moves */
  .tail .ln, .tail .dots { opacity: 0; pointer-events: none; }
  .fin { position: fixed; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: var(--s-2);
    padding: 56px var(--gutter) calc(176px + var(--safe-bottom)); text-align: center; pointer-events: none;
    opacity: 0; transform: translateY(12px) scale(0.96); transition: opacity 500ms var(--ease), transform 700ms var(--ease); }
  .fin.shown { opacity: 1; transform: none; transition-delay: 260ms; }
  .coin { position: relative; width: 168px; height: 168px; margin-bottom: var(--s-4); border-radius: 50%; }
  .coin img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: contain; }
  /* its light, behind it, coming with the colours: a soft gradient of its own (no blur filter), opacity only */
  .halo { position: absolute; inset: -42%; border-radius: 50%; background: radial-gradient(closest-side, var(--accent-2), transparent); opacity: 0; }
  .count .halo { opacity: calc(0.5 * var(--c, 0)); }
  .has .halo { opacity: 0.5; }
  .grey { filter: grayscale(1) brightness(0.8); opacity: 0.5; }
  .col { opacity: 0; }
  .count .coin { transform: scale(calc(0.94 + 0.06 * var(--c, 0))); }
  .count .col { opacity: var(--c, 0); }
  .has .col { opacity: 1; }
  .clip { position: absolute; inset: 0; border-radius: 50%; overflow: hidden; } /* the settling light stays on the coin */
  .glint { position: absolute; inset: 0; opacity: 0; background: linear-gradient(90deg, transparent 30%, var(--glass-hi, rgba(255, 255, 255, 0.5)) 50%, transparent 70%); }
  .cap { font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .big { font: 800 calc(var(--fs-title) * 1.9)/1 var(--font-display); letter-spacing: -0.03em; color: var(--text); }
  .name { font: 700 var(--fs-t3)/1.2 var(--font-display); color: var(--text); }
  .how { max-width: 260px; text-wrap: balance; }
  @media (max-height: 620px) { .coin { width: 128px; height: 128px; } }
  @media (prefers-reduced-motion: reduce) { .fin, .count .coin { transform: none; } }
  :global(html.lowfx) .count .coin { transform: none; }
</style>
