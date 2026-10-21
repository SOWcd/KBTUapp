<script module lang="ts">
  import type { Component } from 'svelte';
  export type Live = { kind: 'event' | 'class'; title: string; at: number; until?: number; emoji: string; tint: string; label: string; onopen?: () => void };
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  export type CapPage = { label: string; icon: Component<any>; dot?: boolean };
</script>

<script lang="ts">
  // The capsule (SPEC §8.2): one liquid-glass object at the top, between Telegram's own buttons, that
  // always says where you are and what's happening now. Priority: title of a full-screen view (or of
  // a one-page tab) → live status (event today, class soon) when idle → page switcher (icons). Any
  // touch wakes the switcher for 3 s. The pill follows the pager finger through 'kb:pager' events
  // (no reactive state per frame) and squashes like jelly when it starts to slide.
  //
  // Geometry is the prototype's, approved on an iPhone: a 184 px window whose right edge sits 94 px
  // right of centre. On a phone Telegram's left button first shows the app name, then turns into
  // the narrower «Close» about 2.5 s after the webview opens; until then the window is 32 px
  // narrower on the left, then it grows into the freed space. «Close» is in Telegram's own language, and it is
  // wider in most of them than in English: the Russian one ends ~9 px further right (two iPhones, Oct 4), close
  // enough to touch. So outside English and Kazakh (short words) the window gives up 10 px more on the left.
  import { onMount } from 'svelte';
  import { ui, TABS } from '../lib/state/ui.svelte';
  import { haptic, inTelegram, tg } from '../lib/tg';
  import { t } from '../lib/i18n/index.svelte';
  import { countdown } from '../lib/time';
  import { glass, jelly } from './glass';
  import { chrome } from './chrome';
  import Emoji from './Emoji.svelte';

  type Props = { pages: CapPage[]; index: number; onpick: (i: number) => void; live?: Live | null; title?: string | null; icon?: Component<any> | null };
  let { pages, index, onpick, live = null, title = null, icon = null }: Props = $props();

  const BOOT_MS = 2550; // from the webview opening; matched to Telegram's «KBTU App» → «Close» on iPhone
  const phone = inTelegram && /^(ios|android)$/.test(tg.platform);
  let booting = $state(phone && performance.now() < BOOT_MS);
  const wideClose = phone && !/^(en|kk)\b/i.test(tg.user?.language_code ?? 'en');

  let pill: HTMLSpanElement;
  let blob: HTMLSpanElement;
  let awake = $state(true);
  let now = $state(Date.now() / 1000);
  let sleepTimer: ReturnType<typeof setTimeout> | undefined;

  const heading = $derived(title ?? (pages.length === 1 ? pages[0].label : null));
  const mode = $derived(heading ? 'title' : live && !awake ? 'live' : 'switch');

  function wake() {
    awake = true;
    clearTimeout(sleepTimer);
    sleepTimer = setTimeout(() => (awake = false), 3000);
  }
  // any interaction in the app (page change, tab tap) bumps ui.awake
  $effect(() => { void ui.awake; void index; wake(); });

  let target = -1;
  // the page under the pill right now: follows the finger, so icon colours flip halfway, not after the commit
  let lit = $state(0);
  function move(x: number, ease: string) {
    if (!pill) return;
    const c = Math.max(0, Math.min(pages.length - 1, x));
    lit = Math.round(c);
    pill.style.transition = ease || 'none';
    pill.style.transform = `translate3d(calc(${c.toFixed(3)} * (100% + 2px)),0,0)`;
    // jelly when the pill starts its eased slide to another page, not at the end of it
    if (ease && Math.round(c) !== target) jelly(blob);
    if (ease) target = Math.round(c);
  }
  $effect(() => { move(index, 'transform 450ms cubic-bezier(.3,1.25,.5,1)'); });

  // The pill always answers a tab switch. A different page slides it (above). On the same page it behaves
  // like a drop of liquid that sets off toward the new tab and stays: with room on that side its front
  // edge reaches out, against the capsule's wall its back end presses in. The motion is a damped spring's
  // response to a push (computed, not hand-placed keyframes), so it settles the way the slide does; a rigid
  // there-and-back shift read as the "wrong passcode" shake. The new icons come in by themselves (CSS).
  let seen = { tab: ui.tab, index: -1 }; // filled on the first run
  $effect(() => {
    const tab = ui.tab, i = index;
    if (blob?.animate && tab !== seen.tab && i === seen.index) {
      const dir = TABS.indexOf(tab) > TABS.indexOf(seen.tab) ? 1 : -1;
      const wall = dir > 0 ? i === pages.length - 1 : i === 0;
      const k = (wall ? -8 : 12) / blob.offsetWidth; // reach (or press) at the peak, px → fraction of the width
      const transformOrigin = dir > 0 !== wall ? '0% 50%' : '100% 50%'; // the edge that stays put
      const frames = Array.from({ length: 29 }, (_, f) => {
        const t = f * 0.025, s = f === 28 ? 0 : (Math.exp(-5 * t) * Math.sin(8.66 * t)) / 0.473; // ζ 0.5, peak 1 at 121 ms
        return { transform: `scale(${1 + k * s}, ${1 - 0.3 * k * s})`, transformOrigin };
      });
      blob.animate(frames, { duration: 700 });
    }
    seen = { tab, index: i };
  });

  onMount(() => {
    const onPager = (e: Event) => { const d = (e as CustomEvent).detail as { x: number; ease: string }; move(d.x, d.ease); if (!awake) wake(); };
    window.addEventListener('kb:pager', onPager);
    // any touch elsewhere brings the switcher back for a moment (a tap on the live capsule opens it instead)
    const onTouch = (e: PointerEvent) => { if (!(e.target as HTMLElement).closest?.('.cap .live')) wake(); };
    document.addEventListener('pointerdown', onTouch, true);
    const tick = setInterval(() => { if (live) now = Date.now() / 1000; }, 1000);
    const boot = booting ? setTimeout(() => (booting = false), BOOT_MS - performance.now()) : undefined;
    return () => { window.removeEventListener('kb:pager', onPager); document.removeEventListener('pointerdown', onTouch, true); clearInterval(tick); clearTimeout(boot); };
  });

  const liveTop = $derived.by(() => {
    if (!live) return '';
    const left = live.at - now;
    if (live.kind === 'event') return left > 0 ? countdown(left) : live.label;
    return live.label;
  });
</script>

<div class="cap glass glass-pill" class:wide={wideClose} class:boot={booting} role="navigation" aria-label={t('cap.pages')} use:glass={{ bloom: true }} use:chrome>
  <span class="tone-base" aria-hidden="true"></span><span class="tone-feed" aria-hidden="true"></span>
  <!-- page switcher -->
  <div class="layer sw" class:off={mode !== 'switch'} style="--n:{pages.length}">
    <span class="pill" bind:this={pill} aria-hidden="true"><span class="blob" bind:this={blob}></span></span>
    {#each pages as p, i (p.label)}
      <button class:on={i === lit} aria-label={p.label} aria-pressed={i === index} onclick={() => { haptic.select(); onpick(i); wake(); }}>
        <p.icon size={18} strokeWidth={2} />{#if p.dot}<i class="dot" aria-hidden="true"></i>{/if}
      </button>
    {/each}
  </div>
  <!-- live status -->
  <button class="layer live" class:off={mode !== 'live'} onclick={() => live?.onopen?.()} aria-label={live?.title}>
    {#if live}
      <span class="lv" style="background:{live.tint}"><Emoji name={live.emoji} size={20} /></span>
      <span class="lt"><b class="num">{liveTop}</b><i class="ellipsis">{live.title}</i></span>
    {/if}
  </button>
  <!-- title of a full-screen view or of a one-page tab -->
  <div class="layer ttl" class:off={mode !== 'title'}>{#if icon && title}{@const Icon = icon}<Icon size={16} strokeWidth={2.4} />{/if}<span class="ellipsis">{heading ?? ''}</span></div>
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

  .sw .pill { position: absolute; top: 0; bottom: 0; left: 0; width: calc((100% - (var(--n) - 1) * 2px) / var(--n)); will-change: transform; }
  .blob { position: absolute; inset: 0; border-radius: var(--r-full); background: var(--text); transition: background-color 200ms ease; }
  .sw button {
    position: relative; flex: 1 1 0; min-width: 0; height: 100%; border-radius: var(--r-full);
    display: flex; align-items: center; justify-content: center; color: var(--chrome-ink);
    transition: color 150ms ease, transform 350ms cubic-bezier(.3, 1.6, .5, 1);
  }
  .sw button:active { transform: scale(0.94); transition-duration: 150ms, 80ms; }
  .sw button + button { margin-left: 2px; }
  .sw button.on { color: var(--bg); }
  /* something waits on that page (Friends: a request), as on the bottom bar */
  .sw .dot { position: absolute; top: 6px; left: calc(50% + 4px); width: 8px; height: 8px; border-radius: 50%; background: var(--danger); box-shadow: 0 0 0 2px var(--glass-solid); }
  /* a tab switch brings another set of pages: their icons grow in like an iOS symbol swap */
  .sw button > :global(svg) { animation: symIn 340ms cubic-bezier(.3, 1.35, .5, 1) backwards; }
  @keyframes symIn { from { opacity: 0; transform: scale(0.5); } }

  .live { gap: 8px; padding: 0 12px 0 0; text-align: left; }
  .lv { width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; flex: none; }
  .lt { display: flex; flex-direction: column; min-width: 0; line-height: 1.1; }
  .lt b { font: 700 13px/1.1 var(--font-text); letter-spacing: 0.01em; }
  .lt i { font: 500 11.5px/1.2 var(--font-text); font-style: normal; color: var(--text-2); }

  .ttl { justify-content: center; gap: 7px; font: 650 14px/1 var(--font-text); letter-spacing: -0.01em; padding: 0 14px; }
  .ttl :global(svg) { flex: none; opacity: 0.8; }
</style>
