<script lang="ts">
  // KBTU's anthem, to listen to and learn (Oct 30: the volunteers learn it for the Oct 31 initiation). The words in big
  // type, the Kazakh chorus on a soft band after each verse; the player stays at the bottom while they scroll, as in
  // Apple Music's lyrics. One audio element, made on the first tap (iOS plays only from a tap; nothing loads before it),
  // paused as the sheet leaves.
  // Playing, the words follow the song (lib/lyrics.ts): the line being sung bright and a little larger, the rest dimmed,
  // a pause as three dots filling before the next line; the page keeps that line in its upper third (a hand scrolling it
  // wins for 3 s); a tap on any line plays from there.
  // The creator alone has an editor (the timer): each line's time; a tap picks a line and plays it from a second before;
  // ±0.1 / ±0.5 s nudge it; "re-tap from this line" stamps it and the lines after it as they are sung; a line's end can
  // be marked where a pause follows it; Undo; Copy (TIMES for lib/i18n/anthem.ts, as JSON). His fixes stay on his phone
  // (a draft over the shipped TIMES) until they ship; nothing goes to the server.
  import { onMount, untrack } from 'svelte';
  import { fade } from 'svelte/transition';
  import Music from '@lucide/svelte/icons/music';
  import Play from '@lucide/svelte/icons/play';
  import Pause from '@lucide/svelte/icons/pause';
  import Repeat from '@lucide/svelte/icons/repeat';
  import Timer from '@lucide/svelte/icons/timer';
  import Undo2 from '@lucide/svelte/icons/undo-2';
  import Copy from '@lucide/svelte/icons/copy';
  import Check from '@lucide/svelte/icons/check';
  import ArrowRightToLine from '@lucide/svelte/icons/arrow-right-to-line';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { t, LANG_FULL } from '../../lib/i18n/index.svelte';
  import { ANTHEM, SUNG, TIMED, TIMES } from '../../lib/i18n/anthem';
  import { lineLen, lyricAt } from '../../lib/lyrics';
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
  const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  function make(): HTMLAudioElement {
    const a = new Audio();
    a.preload = 'none';
    a.loop = repeat;
    a.src = 'anthem/kbtu-anthem.m4a';
    const from = cur; // scrubbed or a line tapped before the first play: it starts there
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
  const playFrom = (s: number) => { seek(s); if (!audio || audio.paused) toggle(); };

  // the timings: the shipped ones, or the creator's draft of his fixes (while it was made from those same ones)
  const N = SUNG.length, founder = !!session.me?.founder, DRAFT = 'kb-anthem-draft', BASE = JSON.stringify(TIMES);
  type Times = { s: number[]; e: (number | null)[] };
  function load(): Times | null {
    try { const d = JSON.parse(localStorage.getItem(DRAFT) ?? 'null'); return d?.base === BASE && d.s?.length === N ? d : null; } catch { return null; }
  }
  const draft = founder ? load() : null;
  let starts = $state(draft?.s ?? SUNG.map((l) => l.t ?? 0)), ends = $state(draft?.e ?? SUNG.map((l) => l.end));

  // the editor: the line picked; while re-tapping, the line the next tap stamps
  let edit = $state(false), sel = $state(-1), cursor = $state(-1), raw = $state('');
  let past = $state.raw<(Times & { c: number })[]>([]);

  // where the song is: the line lit, or a pause (dots before line `gapAt`, filled to `gapP`). timeupdate comes ~4 times
  // a second and a tap lands a little after the voice, so the words run LEAD ahead of the clock
  const LEAD = 0.25;
  const synced = $derived(TIMED && (cursor >= 0 || on || cur > 0));
  const len = $derived(lineLen(starts));
  const pos = $derived(synced && cursor < 0 ? lyricAt(starts, ends, cur + LEAD, dur, len) : null);
  const lit = $derived(cursor >= 0 ? cursor : (pos?.line ?? -1));
  const gapAt = $derived(pos?.next ?? -1), gapP = $derived(pos?.p ?? 0);
  const dot = (k: number) => 0.25 + 0.75 * Math.min(1, Math.max(0, gapP * 3 - k));

  // the line (or the dots before the next one) stays in the page's upper third while the song plays; a hand scrolling
  // the page wins for 3 s, then it comes back
  let userAt = 0, back = 0;
  const focus = $derived(lit >= 0 ? lit : gapAt);
  function follow(i: number) {
    const el = words.querySelector(`[data-i="${i}"]`), box = words.parentElement;
    if (!el || !box || performance.now() - userAt < 3000) return;
    const top = box.scrollTop + el.getBoundingClientRect().top - box.getBoundingClientRect().top - box.clientHeight * 0.3;
    box.scrollTo({ top: Math.max(0, top), behavior: still() ? 'auto' : 'smooth' });
  }
  $effect(() => { const f = focus; if (f >= 0 && (on || cursor >= 0)) untrack(() => follow(f)); });

  // a tap on a line plays from it (the creator's editor: picks it and plays it from a second before)
  function jump(i: number) {
    userAt = 0;
    if (edit) { cursor = -1; sel = i; }
    playFrom(starts[i] - (edit ? 1 : LEAD));
  }

  const r2 = (x: number) => Math.round(x * 100) / 100;
  const fine = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(2).padStart(5, '0')}`;
  const now = () => (audio ? audio.currentTime : cur);
  function save() {
    try { localStorage.setItem(DRAFT, JSON.stringify({ base: BASE, s: starts, e: ends })); } catch { /* storage off: the fixes last while the sheet is open */ }
  }
  function change(fn: () => void) { past = [...past, { s: [...starts], e: [...ends], c: cursor }]; fn(); save(); }
  function undo() {
    const p = past[past.length - 1];
    if (!p) return;
    past = past.slice(0, -1); starts = p.s; ends = p.e; cursor = p.c; save();
  }
  function editor() { edit = !edit; cursor = -1; raw = ''; if (edit && sel < 0) sel = Math.max(0, lit); }
  function nudge(d: number) {
    if (sel < 0) return;
    change(() => (starts[sel] = Math.max(0, r2(starts[sel] + d))));
    playFrom(starts[sel] - 1);
  }
  // from the line before it, so the tap comes when the picked line is heard
  function retap() { if (sel < 0) return; cursor = sel; userAt = 0; playFrom(sel ? starts[sel - 1] - 0.5 : 0); }
  // on the finger's touch, not its lift: the stamp lands when the line is heard
  function stamp() {
    if (cursor < 0) return;
    const i = cursor;
    change(() => { starts[i] = r2(now()); ends[i] = null; });
    sel = i; cursor = i + 1 < N ? i + 1 : -1;
    haptic.select();
  }
  // a line's end, where a pause follows it: re-tapping, the line just stamped; else the one picked (again: no end)
  function endHere() {
    const i = cursor >= 0 ? cursor - 1 : sel;
    if (i < 0) return;
    change(() => (ends[i] = cursor < 0 && ends[i] != null ? null : r2(now())));
  }
  async function copy() {
    const text = JSON.stringify(starts.map((s, i) => (ends[i] != null ? [s, ends[i]] : s)));
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

  $effect(() => { if (overlay.closing) audio?.pause(); });
  onMount(() => {
    const box = words.parentElement!;
    const hand = () => { userAt = performance.now(); clearTimeout(back); back = window.setTimeout(() => { if (on || cursor >= 0) follow(focus); }, 3100); };
    box.addEventListener('touchmove', hand, { passive: true });
    box.addEventListener('wheel', hand, { passive: true });
    return () => {
      clearTimeout(back); box.removeEventListener('touchmove', hand); box.removeEventListener('wheel', hand);
      if (!audio) return;
      audio.onerror = null;
      audio.pause(); audio.removeAttribute('src'); audio.load(); // its download stops too
      if (ms) { try { ms.metadata = null; ms.setActionHandler('play', null); ms.setActionHandler('pause', null); } catch { /* as above */ } }
    };
  });
</script>

<Sheet {overlay} tall title={t('anthem.title')} icon={Music} hold={() => edit} onhold={() => { edit = false; cursor = -1; }}>
  <header class="hd">
    <span class="art"><KbtuMark size={30} /></span>
    <h2 class="t-h2">{t('anthem.title')}</h2>
  </header>
  <div class="words" class:synced class:edit bind:this={words}>
    {#each ANTHEM as part, i (i)}
      <section class="part" class:chorus={part.kind === 'chorus'} lang={part.lang}>
        <h3 class="t-cap" class:hush={gapAt === part.lines[0].i}>{part.n ? `${part.n} · ${LANG_FULL[part.lang]}` : t('anthem.chorus')}</h3>
        {#each part.lines as line, j (j)}
          {#if line.i < 0}<i class="gap"></i>
          {:else}
            {#if line.i === gapAt}<span class="dots" class:up={j === 0} aria-hidden="true" transition:fade={{ duration: 300 }}><i style:opacity={dot(0)}></i><i style:opacity={dot(1)}></i><i style:opacity={dot(2)}></i></span>{/if}
            <button class="ln" class:now={line.i === lit} class:sel={edit && line.i === sel} data-i={line.i} aria-current={line.i === lit || undefined}
                    onclick={() => jump(line.i)}>{line.text}{#if edit}<span class="tm num">{fine(starts[line.i])}{#if ends[line.i] != null}<br />⇥ {fine(ends[line.i]!)}{/if}</span>{/if}</button>
          {/if}
        {/each}
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
      {#if founder}<button class="rnd" class:on={edit} onclick={editor} aria-pressed={edit} aria-label={t('anthem.timing')}><Timer size={20} /></button>{/if}
    </div>
    {#if edit}
      {#if cursor >= 0}
        <div class="ed">
          <button class="rnd" onclick={undo} disabled={!past.length} aria-label={t('anthem.undo')}><Undo2 size={20} /></button>
          <button class="tap" data-nohaptic onpointerdown={stamp} onclick={(e) => { if (!e.detail) stamp(); }}>{t('anthem.tap')}<small class="num">{cursor + 1}/{N}</small></button>
          <button class="rnd" onclick={endHere} disabled={cursor < 1} aria-label={t('anthem.endHere')}><ArrowRightToLine size={20} /></button>
          <button class="rnd" onclick={() => (cursor = -1)} aria-label={t('anthem.stop')}><Check size={20} /></button>
        </div>
      {:else}
        <div class="ed">
          {#each [-0.5, -0.1] as d (d)}<button class="nud num" onclick={() => nudge(d)} disabled={sel < 0}>−{-d}</button>{/each}
          <span class="at num">{sel >= 0 ? fine(starts[sel]) : '–'}</span>
          {#each [0.1, 0.5] as d (d)}<button class="nud num" onclick={() => nudge(d)} disabled={sel < 0}>+{d}</button>{/each}
        </div>
        <div class="ed">
          <button class="rnd" class:on={sel >= 0 && ends[sel] != null} onclick={endHere} disabled={sel < 0}
                  aria-label={sel >= 0 && ends[sel] != null ? t('anthem.endClear') : t('anthem.endHere')}><ArrowRightToLine size={20} /></button>
          <button class="re" onclick={retap} disabled={sel < 0}>{t('anthem.restamp')}</button>
          <button class="rnd" onclick={undo} disabled={!past.length} aria-label={t('anthem.undo')}><Undo2 size={20} /></button>
          <button class="rnd" onclick={copy} aria-label={t('anthem.copy')}><Copy size={20} /></button>
        </div>
      {/if}
      {#if raw}<textarea class="raw selectable" readonly value={raw}></textarea>{/if}
    {/if}
  {/snippet}
</Sheet>

<style>
  .hd { display: flex; flex-direction: column; align-items: center; gap: 12px; margin: 8px 0 28px; text-align: center; }
  .art { display: grid; place-items: center; width: 60px; height: 60px; border-radius: var(--r-m); background: var(--accent); color: var(--on-accent); }

  .part { margin-bottom: 26px; }
  .part h3 { margin-bottom: 10px; transition: opacity 300ms var(--ease); }
  .part h3.hush { opacity: 0; } /* the dots take the label's place while a pause leads into its section */
  /* big enough to sing from (20 px from a 400-px phone, 17 at 320); a line too long for the phone goes on under
     itself, indented, the two halves even. Each line is a button: a tap plays from it */
  .ln { position: relative; display: block; width: 100%; padding-left: 0.8em; text-indent: -0.8em; text-align: left;
    font: 650 clamp(var(--fs-card), 5vw, calc(var(--fs-card) * 1.18))/1.4 var(--font-text); letter-spacing: -0.012em; text-wrap: balance;
    transform-origin: 0 50%; transition: opacity 400ms var(--ease), transform 400ms var(--ease); }
  /* playing, as Apple Music: the line being sung bright and a little larger, the rest dimmed (opacity and transform only);
     room below the last chorus, so its lines too can come up to the page's upper third */
  .words.synced { padding-bottom: 40vh; }
  .synced .ln { opacity: 0.32; }
  .synced .ln.now { opacity: 1; transform: scale(1.04); }
  .gap { display: block; height: 14px; }
  /* the chorus, the same words three times: set apart on a soft band the sheet's width (a card's padding broke its
     lines on a phone), its label in the accent */
  .chorus { margin-left: calc(-1 * var(--gutter)); margin-right: calc(-1 * var(--gutter)); padding: 16px var(--gutter) 18px; background: var(--surface); }
  .chorus h3 { color: var(--accent-text); }
  /* a pause (the intro, the breaks after the choruses): three dots where the next line starts, one lighting up after
     another as it goes, breathing; no height of their own, nothing below moves */
  .dots { position: relative; top: 0; display: flex; align-items: flex-end; gap: 7px; height: 0; padding-left: 2px; }
  .dots.up { top: -12px; } /* a section's first line: on its label's row */
  .dots i { width: 8px; height: 8px; border-radius: 50%; background: var(--text); transition: opacity 250ms linear; animation: breathe 2.4s ease-in-out infinite; }
  @keyframes breathe { 50% { transform: scale(1.15); } }
  :global(html.lowfx) .dots i { animation: none; }
  @media (prefers-reduced-motion: reduce) { .synced .ln.now { transform: none; } .dots i { animation: none; } }

  /* the creator's editor: each line's time at its end, the picked line on an accent wash */
  .edit .ln { padding-right: 76px; }
  .edit .ln.now { transform: none; } /* the times stay put */
  .tm { position: absolute; top: 0.45em; right: 0; text-indent: 0; text-align: right; font: 600 var(--fs-cap)/1.3 var(--font-text); color: var(--text-3); }
  .ln.sel { opacity: 1; background: var(--accent-soft); box-shadow: 0 0 0 6px var(--accent-soft); border-radius: var(--r-xs); }
  .ln.sel .tm { color: var(--accent-text); }

  .player { display: flex; align-items: center; gap: 14px; }
  .play { position: relative; flex: none; width: 56px; height: 56px; border-radius: 50%; display: grid; place-items: center; background: var(--accent); color: var(--on-accent); }
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
  .track i { position: absolute; inset: 0 auto 0 0; border-radius: inherit; background: var(--text); }
  .times { display: flex; justify-content: space-between; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-3); }

  /* a round icon button: repeat, the creator's timer, Undo, Copy, the line's end, done */
  .rnd { flex: none; width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; color: var(--text-3);
    transition: transform 450ms var(--ease-bounce), background-color var(--t-base), color var(--t-base), opacity var(--t-base); }
  .rnd.on { background: var(--accent-soft); color: var(--accent-text); }
  .rnd:disabled, .nud:disabled, .re:disabled { opacity: 0.35; }

  .ed { display: flex; align-items: center; gap: 8px; margin-top: 10px; }
  .tap { flex: 1; min-width: 0; display: inline-flex; align-items: center; justify-content: center; gap: 8px; height: 50px; border-radius: var(--r-full);
    background: var(--accent); color: var(--on-accent); font: 700 var(--fs-card)/1 var(--font-text); }
  .tap small { font: 600 var(--fs-sub)/1 var(--font-text); opacity: 0.75; }
  .nud { flex: 1 1 0; min-width: 0; height: 40px; border-radius: var(--r-full); background: var(--surface-2); text-align: center; font: 650 var(--fs-sub)/1 var(--font-text); }
  .at { flex: none; min-width: 72px; text-align: center; font: 700 var(--fs-body)/1 var(--font-text); }
  .re { flex: 1; min-width: 0; min-height: 44px; padding: 4px 12px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text);
    font: 650 var(--fs-sub)/1.15 var(--font-text); }
  .raw { display: block; width: 100%; height: 64px; margin-top: 10px; padding: 8px 10px; border-radius: var(--r-s); background: var(--surface-2); font: 500 var(--fs-cap)/1.35 ui-monospace, monospace; resize: none; }
</style>
