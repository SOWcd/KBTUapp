<script lang="ts">
  // Live phrase: a 3D emoji and a short line, floats over the nav for ~2.5 s (state/ui.svelte.ts say()).
  // One pill while phrases keep coming (A1): a new phrase doesn't replay the entrance, the pill MORPHS
  // into it, its width springs to the new line while the old line and emoji fade out in place. The entrance: the pill
  // grows out of its emoji, the emoji bounces in, the line comes into focus. Transforms, opacity, clip-path and one
  // width tween per phrase: nothing runs while it just sits there.
  import { toast } from '../lib/state/ui.svelte';
  import Emoji from './Emoji.svelte';
  import { glass } from './glass';
  // read once per showing, not live: a sheet closing right after say() must not move the toast mid-way;
  // the map's bottom holds its place card, so there it drops under the floors (it covered the card)
  const atTop = () => { const d = document.documentElement.dataset; return 'sheet' in d || 'map' in d; };
  const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  let pill = $state<HTMLElement>();
  let from = [0, 0];
  const at = new WeakMap<Element, [number, number, number]>();
  let top = $state(false);
  let fresh = $state(true); // nothing on screen yet: the entrance, not a morph
  $effect.pre(() => {
    void toast.id;
    fresh = !pill;
    if (fresh) top = atTop();
    from = [pill?.offsetWidth ?? 0, pill?.offsetHeight ?? 0];
    // where the leaving line and emoji stand, read before either leaves: the emoji going out of the flow first moved
    // the line onto it, and a theme switch froze that in its snapshot
    for (const c of pill?.children ?? []) { const e = c as HTMLElement; at.set(c, [e.offsetLeft, e.offsetTop, e.offsetWidth]); }
  });
  $effect(() => {
    void toast.id;
    const el = pill;
    if (!el || !from[0] || still()) return;
    const to = [el.offsetWidth, el.offsetHeight];
    if (Math.abs(to[0] - from[0]) < 2 && Math.abs(to[1] - from[1]) < 2) return;
    // the new line is laid out at its final width while the pill springs to it (owner's video, Oct 24: the narrow start
    // wrapped the new line, the pill grew a line taller and jumped up); the pill's edge uncovers it, the height (one
    // line or two) moves with the width, nothing reflows and nothing is cut at the end
    const tx = [...el.querySelectorAll<HTMLElement>('.tx')].find((n) => !n.style.position);
    if (tx) tx.style.flex = `0 0 ${tx.offsetWidth}px`;
    el.animate({ width: [`${from[0]}px`, `${to[0]}px`], height: [`${from[1]}px`, `${to[1]}px`] }, { duration: 420, easing: 'cubic-bezier(.32, 1.25, .4, 1)' }).finished
      .catch(() => {}).finally(() => tx?.style.removeProperty('flex'));
  });

  // the old line leaves where it stood, as it stood (its width, so its lines don't reflow): out of the flow at once,
  // so the pill measures the new one
  function leave(node: HTMLElement) {
    const [l, t, w] = at.get(node) ?? [node.offsetLeft, node.offsetTop, node.offsetWidth];
    node.style.cssText += `position:absolute;left:${l}px;top:${t}px;width:${w}px;`;
    return { duration: still() ? 0 : 160, css: (k: number) => `opacity:${k};filter:blur(${(1 - k) * 4}px)` };
  }
  function come(_node: HTMLElement, { first }: { first: boolean }) {
    return { delay: first ? 120 : 60, duration: still() ? 0 : 300, css: (k: number) => `opacity:${k};filter:blur(${(1 - k) * 5}px);transform:translateX(${(1 - k) * 6}px)` };
  }
  // the whole pill: grows from the emoji's circle at its left
  function grow(node: HTMLElement) {
    const r = node.offsetWidth - node.offsetHeight;
    return { duration: still() ? 0 : 520, easing: (k: number) => 1 - Math.pow(1 - k, 3),
      css: (k: number) => `clip-path:inset(0 ${(1 - k) * r}px 0 0 round 999px);opacity:${Math.min(1, k * 3)}` };
  }
  // the exit mirrors it: the line is wiped back into the emoji, then that circle pops away
  function shrink(node: HTMLElement, { top }: { top: boolean }) {
    const r = node.offsetWidth - node.offsetHeight, h = node.offsetHeight / 2;
    return { duration: still() ? 0 : 480, css: (k: number) => {
      const u = 1 - k, c = Math.min(1, u / 0.6), q = Math.max(0, (u - 0.5) / 0.5);
      const s = c * c * (3 - 2 * c); // smoothstep: the wipe eases in and settles on the circle
      return `clip-path:inset(0 ${s * r}px 0 0 round 999px);opacity:${1 - q * q};transform-origin:${h}px 50%;`
        + `transform:translate(-50%, ${q * (top ? -6 : 6)}px) scale(${1 - 0.6 * q * q}) rotate(${q * 14}deg)`;
    } };
  }
</script>

{#if toast.text}
  <div class="toast glass glass-pill" class:top role="status" use:glass bind:this={pill} in:grow out:shrink={{ top }}>
    {#key toast.id}
      <span class="em" in:come={{ first: fresh }} out:leave><span class:bounce={fresh}><Emoji name={toast.emoji} size={26} /></span></span>
      <span class="tx" in:come={{ first: fresh }} out:leave>{toast.text}</span>
    {/key}
  </div>
{/if}

<style>
  /* width: max-content — with left: 50% the shrink-to-fit width stopped at half the screen and short phrases wrapped */
  .toast {
    position: absolute; left: 50%; bottom: calc(var(--safe-bottom) + 82px); z-index: var(--z-toast);
    display: flex; align-items: center; gap: 10px; width: max-content; max-width: calc(100% - 40px); padding: 9px 16px 9px 10px;
    border-radius: var(--r-full); font: 600 14px/1.25 var(--font-text); letter-spacing: -0.01em; overflow: hidden;
    transform: translateX(-50%); pointer-events: none;
    animation: pop 420ms var(--ease-spring) both;
  }
  /* a sheet's footer holds its buttons: there the toast drops from the top, under Telegram's header, like an iOS push */
  .toast.top { bottom: auto; top: calc(var(--safe-top) + max(var(--tg-head), 46px) + 8px); animation-name: drop; }
  :global(html[data-map]) .toast.top { top: calc(max(48px, var(--top)) + 70px); } /* under the map's floor row */
  .em { display: flex; flex: none; }
  /* a long line wraps between words, two lines at most (a name never cut in the middle; a third line ends in …) */
  .tx { min-width: 0; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; }
  .bounce { display: flex; animation: bounce 560ms cubic-bezier(.3, 1.6, .5, 1) 60ms both; }
  @keyframes pop { from { transform: translate(-50%, 14px) scale(0.92); } }
  @keyframes drop { from { transform: translate(-50%, -14px) scale(0.92); } }
  @keyframes bounce { from { transform: scale(0.3) rotate(-18deg); } }
  @media (prefers-reduced-motion: reduce) { .toast, .bounce { animation: none; } }
</style>
