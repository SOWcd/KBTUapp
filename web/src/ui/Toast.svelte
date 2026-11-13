<script lang="ts">
  // Live phrase: a 3D emoji and a short line, floats over the nav for ~2.5 s (state/ui.svelte.ts say()).
  // One pill while phrases keep coming (A1): a new phrase doesn't replay the entrance, the pill MORPHS
  // into it, its width springs to the new line while the old line and emoji fade out in place. The entrance: the glass
  // rises on a spring and grows out of its emoji, the emoji bounces in a beat later, the line comes into focus.
  // Transforms, opacity, clip-path and one width tween per phrase: nothing runs while it just sits there.
  // Reduced motion and power saving: plain fades. A swipe throws it away; a finger on it holds it.
  import { holdToast, toast } from '../lib/state/ui.svelte';
  import { power } from '../lib/state/power.svelte';
  import Emoji from './Emoji.svelte';
  import { glass } from './glass';
  import { untrack } from 'svelte';
  import { t } from '../lib/i18n/index.svelte';

  // every timing of the toast, ms; the auto-hide lives with say() (state/ui.svelte.ts)
  const T = {
    pop: 450, grow: 480,          // the glass rises on a spring and grows out of its emoji
    bounceAt: 90, bounce: 540,    // the emoji lands a beat after the glass
    lineAt: 130, line: 300,       // then the line comes into focus
    morph: 420, swapOut: 160, swapAt: 60, swapIn: 280, // one phrase into the next: the width springs, lines cross
    exit: 380,                    // the line folds into the emoji, the circle lifts and pops away: quicker than the entrance
    fling: 280, snap: 420,        // a swipe throws it on with its speed; a short one springs back
    fade: 180,                    // reduced motion and power saving: a plain fade, nothing moves or resizes
    flipAt: 520, flip: 280,       // a toggle toast's switch flips once its line is in
  };
  // a damped spring (8% overshoot, settled at the end); no linear() (iOS < 17.2, old Android WebViews): a close bezier
  const SPRING = CSS.supports?.('animation-timing-function', 'linear(0, 1)')
    ? 'linear(0, .093, .299, .531, .739, .898, 1.003, 1.061, 1.082, 1.08, 1.065, 1.046, 1.028, 1.013, 1.002, .996, .993, .993, .994, .996, .997, .999, 1)'
    : 'cubic-bezier(.32, 1.25, .4, 1)';
  const vars = `--spring:${SPRING};--t-pop:${T.pop}ms;--t-bounce:${T.bounce}ms;--at-bounce:${T.bounceAt}ms;--at-flip:${T.flipAt}ms;--t-flip:${T.flip}ms`;
  const out3 = (k: number) => 1 - Math.pow(1 - k, 3);
  // read once per showing, not live: a sheet closing right after say() must not move the toast mid-way;
  // the map's bottom holds its place card, so there it drops under the floors (it covered the card)
  const atTop = () => { const d = document.documentElement.dataset; return 'sheet' in d || 'map' in d; };
  const calm = () => power.lite || matchMedia('(prefers-reduced-motion: reduce)').matches;
  const fade = (ms: number) => ({ duration: ms, css: (k: number) => `opacity:${k}` });

  let pill = $state<HTMLElement>();
  let from = [0, 0];
  const at = new WeakMap<Element, [number, number, number]>();
  let top = $state(false);
  let fresh = $state(true); // nothing on screen yet: the entrance, not a morph
  // per phrase only: the pill binding a frame later re-ran this and turned `fresh` off, so the emoji never bounced in
  $effect.pre(() => {
    void toast.id;
    untrack(() => {
      fresh = !pill;
      // a phrase arriving during the exit revives the same pill: tappable again, nothing of a swipe left on it
      if (pill?.classList.contains('going')) { pill.classList.remove('going'); unshift(pill); fling = null; }
      if (fresh) top = atTop();
      from = [pill?.offsetWidth ?? 0, pill?.offsetHeight ?? 0];
      // where the leaving line and emoji stand, read before either leaves: the emoji going out of the flow first moved
      // the line onto it, and a theme switch froze that in its snapshot
      for (const c of pill?.children ?? []) { const e = c as HTMLElement; at.set(c, [e.offsetLeft, e.offsetTop, e.offsetWidth]); }
    });
  });
  $effect(() => {
    void toast.id;
    const el = pill;
    if (!el || !from[0] || calm()) return;
    const to = [el.offsetWidth, el.offsetHeight];
    if (Math.abs(to[0] - from[0]) < 2 && Math.abs(to[1] - from[1]) < 2) return;
    // the new line is laid out at its final width while the pill springs to it (owner's video, Oct 24: the narrow start
    // wrapped the new line, the pill grew a line taller and jumped up); the pill's edge uncovers it, the height (one
    // line or two) moves with the width, nothing reflows and nothing is cut at the end
    const tx = [...el.querySelectorAll<HTMLElement>('.tx')].find((n) => !n.style.position);
    if (tx) tx.style.flex = `0 0 ${tx.offsetWidth + 1}px`; // a pixel more: offsetWidth rounds, a line that just fitted broke at its soft hyphen
    el.animate({ width: [`${from[0]}px`, `${to[0]}px`], height: [`${from[1]}px`, `${to[1]}px`] }, { duration: T.morph, easing: SPRING }).finished
      .catch(() => {}).finally(() => tx?.style.removeProperty('flex'));
  });

  // the old line leaves where it stood, as it stood (its width, so its lines don't reflow): out of the flow at once,
  // so the pill measures the new one
  function leave(node: HTMLElement) {
    const [l, t, w] = at.get(node) ?? [node.offsetLeft, node.offsetTop, node.offsetWidth];
    // a pixel more: offsetWidth rounds, and a line that just fitted broke at its soft hyphen as it left
    node.style.cssText += `position:absolute;left:${l}px;top:${t}px;width:${w + 1}px;`;
    if (calm()) return fade(T.fade);
    return { duration: T.swapOut, css: (k: number) => `opacity:${k};filter:blur(${(1 - k) * 4}px)` };
  }
  function come(_node: HTMLElement, { at }: { at: number }) {
    if (calm()) return fade(T.fade);
    return { delay: at, duration: fresh ? T.line : T.swapIn, easing: out3,
      css: (k: number) => `opacity:${k};filter:blur(${(1 - k) * 5}px);transform:translateX(${(1 - k) * 6}px)` };
  }
  // the whole pill: grows from the emoji's circle at its left
  function grow(node: HTMLElement) {
    if (calm()) return fade(T.fade);
    const r = node.offsetWidth - node.offsetHeight;
    return { duration: T.grow, easing: out3,
      css: (k: number) => `clip-path:inset(0 ${(1 - k) * r}px 0 0 round 999px);opacity:${Math.min(1, k * 3)}` };
  }
  // the exit mirrors it: the line is wiped back into the emoji, blurring as it goes, then that circle lifts and pops away
  function shrink(node: HTMLElement) {
    node.classList.add('going');
    if (fling) { // thrown: it keeps the finger's speed (out3 starts at 3x, so a third of the time carries it on) and fades
      const [x, y, vx, vy] = fling, d = T.fling / 3;
      fling = null;
      return { duration: T.fling, easing: out3, css: (k: number) => { const u = 1 - k;
        return `${at2(x + vx * d * u, y + vy * d * u)};opacity:${k * k};--xb:${u * 4}px;--eb:${u * 4}px`; } };
    }
    if (calm()) return fade(T.fade);
    const r = node.offsetWidth - node.offsetHeight, h = node.offsetHeight / 2;
    return { duration: T.exit, css: (k: number) => {
      const u = 1 - k, c = Math.min(1, u / 0.6), q = Math.max(0, (u - 0.5) / 0.5);
      const s = c * c * (3 - 2 * c); // smoothstep: the wipe eases in and settles on the circle
      return `clip-path:inset(0 ${s * r}px 0 0 round 999px);opacity:${1 - q * q};transform-origin:${h}px 50%;--xb:${c * 3}px;--eb:${q * 3}px;`
        + `transform:translate(-50%, ${-q * 6}px) scale(${1 - 0.6 * q * q}) rotate(${q * 14}deg)`;
    } };
  }

  // Swipe it away: sideways, or toward the edge it came from (down at the bottom, up at the top); the other way it
  // resists. A finger on it holds the auto-hide. Taps still reach Undo (the pointer is captured only once it moves).
  let drag: { id: number; x: number; y: number; dx: number; dy: number; t: number; vx: number; vy: number; on: boolean } | null = null;
  let fling: number[] | null = null; // where the finger let go and its speed (px, px/ms), for the exit
  const free = (dy: number) => (top ? dy <= 0 : dy >= 0);
  const rubber = (d: number) => (d * 40) / (40 + Math.abs(d));
  // the finger's offset: the `translate` property where there is one (Chrome 104+, iOS 14.1+), else composed into transform
  const TR = CSS.supports?.('translate', '1px') ?? false;
  const at2 = (x: number, y: number) => (TR ? `translate:${x}px ${y}px` : `transform:translate(calc(-50% + ${x}px), ${y}px)`);
  const shift = (x: number, y: number): Record<string, string> => (TR ? { translate: `${x}px ${y}px` } : { transform: `translate(calc(-50% + ${x}px), ${y}px)` });
  function unshift(el: HTMLElement) { for (const k of ['translate', 'transform', 'opacity']) el.style.removeProperty(k); }
  // a finger lost (released outside before the capture, the app hidden, the window blurred) never leaves the hold on
  function reset() {
    if (!drag) return;
    if (drag.on && pill) unshift(pill);
    drag = null;
    holdToast(false);
  }
  function down(e: PointerEvent) {
    if (drag || !e.isPrimary || pill?.classList.contains('going')) return;
    drag = { id: e.pointerId, x: e.clientX, y: e.clientY, dx: 0, dy: 0, t: e.timeStamp, vx: 0, vy: 0, on: false };
    holdToast(true);
  }
  function move(e: PointerEvent) {
    if (!drag || e.pointerId !== drag.id || !pill) return;
    const dx = e.clientX - drag.x, raw = e.clientY - drag.y, dy = free(raw) ? raw : rubber(raw);
    if (!drag.on) { if (Math.hypot(dx, raw) < 6) return; drag.on = true; pill.setPointerCapture(e.pointerId); }
    const dt = Math.max(1, e.timeStamp - drag.t); // the speed, smoothed over the last few moves
    drag.vx = 0.6 * ((dx - drag.dx) / dt) + 0.4 * drag.vx;
    drag.vy = 0.6 * ((dy - drag.dy) / dt) + 0.4 * drag.vy;
    Object.assign(drag, { dx, dy, t: e.timeStamp });
    Object.assign(pill.style, shift(dx, dy));
    pill.style.opacity = `${1 - Math.min(0.5, Math.hypot(dx, free(dy) ? dy : 0) / 240)}`;
  }
  function up(e: PointerEvent) {
    if (!drag || e.pointerId !== drag.id) return;
    const d = drag;
    drag = null;
    holdToast(false);
    if (!d.on || !pill) return;
    const live = e.type === 'pointerup' && e.timeStamp - d.t < 90; // a finger that stopped before letting go threw nothing
    const vx = live ? d.vx : 0, vy = live && free(d.vy) ? d.vy : 0;
    // where a flick would carry it in 150 ms: far enough, it goes
    const px = d.dx + vx * 150, py = free(d.dy) ? d.dy + vy * 150 : 0;
    if (e.type === 'pointerup' && (Math.abs(px) > 90 || Math.abs(py) > 44)) {
      const n = Math.hypot(px, py), v = Math.max(1.2, Math.hypot(vx, vy)); // at least a brisk throw
      fling = [d.dx, d.dy, (px / n) * v, (py / n) * v];
      toast.text = '';
      return;
    }
    const o = pill.style.opacity || '1';
    unshift(pill);
    const a = shift(d.dx, d.dy), b = shift(0, 0);
    pill.animate(Object.fromEntries([...Object.keys(a).map((k) => [k, [a[k], b[k]]]), ['opacity', [o, '1']]]), { duration: calm() ? T.fade : T.snap, easing: SPRING });
  }
</script>

<svelte:window onpointermove={move} onpointerup={up} onpointercancel={up} onblur={reset} />
<svelte:document onvisibilitychange={() => document.hidden && reset()} />

{#if toast.text}
  <div class="toast glass glass-pill" class:top role="status" style={vars} use:glass bind:this={pill} in:grow out:shrink
    onpointerdown={down}>
    {#key toast.id}
      <span class="em" in:come|global={{ at: fresh ? T.bounceAt : T.swapAt }} out:leave><span class:bounce={fresh}><Emoji name={toast.emoji} size={26} /></span></span>
      <span class="tx" in:come|global={{ at: fresh ? T.lineAt : T.swapAt }} out:leave>{toast.text}</span>
      {#if toast.toggle != null}<span class="sw" class:on={toast.toggle} in:come|global={{ at: fresh ? T.lineAt : T.swapAt }} out:leave></span>{/if}
      {#if toast.undo}{@const undo = toast.undo}<button class="undo" in:come|global={{ at: fresh ? T.lineAt : T.swapAt }} out:leave onclick={() => { toast.text = ''; undo(); }}>{t('fc.undo')}</button>{/if}
    {/key}
  </div>
{/if}

<style>
  /* width: max-content — with left: 50% the shrink-to-fit width stopped at half the screen and short phrases wrapped */
  .toast {
    position: absolute; left: 50%; bottom: calc(var(--safe-bottom) + 82px); z-index: var(--z-toast);
    display: flex; align-items: center; gap: 10px; width: max-content; max-width: calc(100% - 40px); padding: 9px 16px 9px 10px;
    border-radius: var(--r-full); font: 600 14px/1.25 var(--font-text); letter-spacing: -0.01em; overflow: hidden;
    transform: translateX(-50%); touch-action: none; user-select: none; -webkit-user-select: none;
    animation: pop var(--t-pop) var(--spring) backwards; /* backwards: once done, a swipe's translate moves it freely */
  }
  .toast:global(.going) { pointer-events: none; }
  /* the exit's blur rides on the line and the emoji, never on the glass (a filter there flattens its backdrop) */
  .toast:global(.going) .tx, .toast:global(.going) .undo { filter: blur(var(--xb, 0px)); }
  .toast:global(.going) .em { filter: blur(var(--eb, 0px)); }
  /* a sheet's footer holds its buttons: there the toast drops from the top, under Telegram's header, like an iOS push */
  .toast.top { bottom: auto; top: calc(var(--safe-top) + max(var(--tg-head), 46px) + 8px); animation-name: drop; }
  :global(html[data-map]) .toast.top { top: calc(max(48px, var(--top)) + 70px); } /* under the map's floor row */
  .em { display: flex; flex: none; }
  /* the one tap a toast takes: Undo, the accent's ink, its own 44 px of height to hit */
  .undo { flex: none; align-self: stretch; margin: -9px -8px -9px 2px; padding: 0 var(--s-2); color: var(--accent); font: inherit; font-weight: 700; }
  /* a long line wraps between words, two lines at most (a name never cut in the middle; a third line ends in …) */
  .tx { min-width: 0; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; }
  /* a toggle toast's switch (power saving), Settings' switch made small: it flips once the line is in, from where it was */
  .sw { flex: none; position: relative; width: 34px; height: 20px; margin-right: -4px; border-radius: var(--r-full); background: var(--line-2);
    animation: sw-off var(--t-flip) var(--ease) var(--at-flip) backwards; }
  .sw::after { content: ''; position: absolute; left: 2px; top: 2px; width: 16px; height: 16px; border-radius: 50%; background: var(--on-accent);
    box-shadow: 0 1px 3px rgba(0, 0, 0, 0.25); animation: knob-off var(--t-flip) var(--ease) var(--at-flip) backwards; }
  .sw.on { background: var(--switch-on); animation-name: sw-on; }
  .sw.on::after { transform: translateX(14px); background: var(--switch-knob); animation-name: knob-on; }
  @keyframes sw-on { from { background: var(--line-2); } }
  @keyframes sw-off { from { background: var(--switch-on); } }
  @keyframes knob-on { from { transform: none; background: var(--on-accent); } }
  @keyframes knob-off { from { transform: translateX(14px); background: var(--switch-knob); } }
  .bounce { display: flex; animation: bounce var(--t-bounce) cubic-bezier(.3, 1.6, .5, 1) var(--at-bounce) both; }
  @keyframes pop { from { transform: translate(-50%, 14px) scale(0.92); } }
  @keyframes drop { from { transform: translate(-50%, -14px) scale(0.92); } }
  @keyframes bounce { from { transform: scale(0.3) rotate(-18deg); } }
  :global(html.lowfx) .toast, :global(html.lowfx) .bounce { animation: none; }
  @media (prefers-reduced-motion: reduce) { .toast, .bounce, .sw, .sw::after { animation: none; } }
</style>
