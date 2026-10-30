<script module lang="ts">
  export type Live = { kind: 'event' | 'class'; title: string; at: number; until?: number; emoji: string; tint: string; label: string; onopen?: () => void };
</script>

<script lang="ts">
  // The capsule (SPEC §8.2): one liquid-glass object at the top, between Telegram's own buttons, that
  // always says where you are and what's happening now: the title of the view on top (a sheet, a full-screen view, else
  // the tab), or the live status (an event today, a class soon) when nothing is on top. It never switches pages
  // (Oct 30: one tab, one screen).
  //
  // Geometry is the prototype's, approved on an iPhone: a 184 px window whose right edge sits 94 px
  // right of centre. On a phone Telegram's left button first shows the app name, then turns into
  // the narrower «Close» about 2.5 s after the webview opens; until then the window is 32 px
  // narrower on the left, then it grows into the freed space. «Close» is in Telegram's own language, and it is
  // wider in most of them than in English: the Russian one ends ~9 px further right (two iPhones), close
  // enough to touch. So outside English and Kazakh (short words) the window gives up 10 px more on the left.
  import { onMount, type Component } from 'svelte';
  import { inTelegram, tg } from '../lib/tg';
  import { countdown } from '../lib/time';
  import { glass } from './glass';
  import { chrome } from './chrome';
  import Emoji from './Emoji.svelte';

  // title: null = the live status speaks
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  type Props = { live?: Live | null; title?: string | null; icon?: Component<any> | null; spin?: boolean };
  let { live = null, title = null, icon = null, spin = false }: Props = $props();

  const BOOT_MS = 2550; // from the webview opening; matched to Telegram's «KBTU App» → «Close» on iPhone
  const phone = inTelegram && /^(ios|android)$/.test(tg.platform);
  let booting = $state(phone && performance.now() < BOOT_MS);
  const wideClose = phone && !/^(en|kk)\b/i.test(tg.user?.language_code ?? 'en');

  let now = $state(Date.now() / 1000);
  const mode = $derived(title || !live ? 'title' : 'live');

  onMount(() => {
    const tick = setInterval(() => { if (live) now = Date.now() / 1000; }, 1000);
    const boot = booting ? setTimeout(() => (booting = false), BOOT_MS - performance.now()) : undefined;
    return () => { clearInterval(tick); clearTimeout(boot); };
  });

  // a title shrinks to fit before it is cut (the award title was cut on a narrow capsule); 11 px is the floor
  function fit(node: HTMLElement) {
    const run = () => { node.style.fontSize = ''; const k = node.clientWidth / node.scrollWidth; if (k < 1) node.style.fontSize = `${Math.max(11, Math.floor(14 * k * 2) / 2)}px`; };
    const ro = new ResizeObserver(run); // the capsule widens after boot, on a narrow phone it starts smaller
    ro.observe(node.parentElement!);
    // a new title (a sheet opening): measured once the browser has laid it out, not at once (that laid out the sheet early)
    const later = () => { const once = new ResizeObserver(() => { once.disconnect(); run(); }); once.observe(node); };
    const mo = new MutationObserver(later);
    mo.observe(node, { childList: true, characterData: true, subtree: true });
    document.fonts?.ready.then(run); // the first measure may be in the fallback font
    return { destroy: () => { ro.disconnect(); mo.disconnect(); } };
  }

  const liveTop = $derived.by(() => {
    if (!live) return '';
    const left = live.at - now;
    if (live.kind === 'event') return left > 0 ? countdown(left) : live.label;
    return live.label;
  });
</script>

<div class="cap glass glass-pill" class:wide={wideClose} class:boot={booting} use:glass={{ bloom: true }} use:chrome>
  <span class="tone-base" aria-hidden="true"></span><span class="tone-feed" aria-hidden="true"></span>
  <!-- live status -->
  <button class="layer live" class:off={mode !== 'live'} onclick={() => live?.onopen?.()} aria-label={live?.title}>
    {#if live}
      <span class="lv" style="background:{live.tint}"><Emoji name={live.emoji} size={20} /></span>
      <span class="lt"><b class="num">{liveTop}</b><i class="ellipsis">{live.title}</i></span>
    {/if}
  </button>
  <!-- the title of the view on top, else the tab's -->
  <div class="layer ttl" class:spin class:off={mode !== 'title'}>{#if icon && title}{@const Icon = icon}<Icon size={16} strokeWidth={2.4} />{/if}<span class="ellipsis" use:fit>{title ?? ''}</span></div>
</div>

<style>
  .cap {
    position: absolute; z-index: var(--z-capsule);
    top: max(8px, calc(var(--safe-top) + (var(--tg-head) - 38px) / 2));
    right: max(calc(50% - 94px), 96px); width: min(184px, calc(100vw - 198px)); height: 38px;
    border-radius: var(--r-full); overflow: hidden;
    background: none;
    transition: width 400ms cubic-bezier(.25, .8, .3, 1), opacity var(--t-base);
    animation: capIn 400ms cubic-bezier(.2, .9, .25, 1.2) backwards;
  }
  .cap.wide { width: min(174px, calc(100vw - 208px)); }
  .cap.boot { width: min(152px, calc(100vw - 230px)); }
  .cap > .tone-base { background: var(--glass-clear); }
  .cap > .tone-feed { background-color: rgb(var(--feed-rgb, 24 28 44) / 0.45); }
  /* over the Feed (chrome.ts): dark glass tinted by the slide, the dark palette past the halfway point */
  .cap:global([data-feed]) { --text: #FFFFFF; --text-2: rgba(255, 255, 255, 0.72); --bg: #0A0F24; --chrome-ink: rgba(255, 255, 255, 0.85); }
  /* never gone (SPEC §8.2): over a sheet or a full-screen view it says that view's title and takes no taps */
  :global(html[data-sheet]) .cap { z-index: calc(var(--z-sheet) + 5); pointer-events: none; }
  @keyframes capIn { from { opacity: 0; transform: translateY(-8px) scale(0.94); } }

  .layer {
    position: absolute; inset: 3px; display: flex; align-items: center;
    transition: opacity 260ms var(--ease), transform 360ms var(--ease-spring), filter 260ms var(--ease);
  }
  .layer.off { opacity: 0; transform: translateY(10px) scale(0.92); filter: blur(4px); pointer-events: none; }
  .live.off { transform: translateY(-10px) scale(0.92); }

  .live { gap: 8px; padding: 0 12px 0 0; text-align: left; }
  .lv { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex: none; }
  .lt { display: flex; flex-direction: column; min-width: 0; line-height: 1.1; }
  .lt b { font: 700 13px/1.1 var(--font-text); letter-spacing: 0.01em; }
  .lt i { font: 500 11.5px/1.2 var(--font-text); font-style: normal; color: var(--text-2); }

  .ttl { justify-content: center; gap: 7px; font: 650 14px/1 var(--font-text); letter-spacing: -0.01em; padding: 0 14px; }
  .ttl :global(svg) { flex: none; opacity: 0.8; }
  .ttl.spin :global(svg) { animation: spin 0.9s linear infinite; }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
