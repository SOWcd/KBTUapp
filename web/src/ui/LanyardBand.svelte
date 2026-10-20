<script lang="ts">
  // The top of a lanyard's card (owner, Oct 20, two drafts in KBTUapp-OLD/design/lanyards): each club's own art in full
  // colour, not a faint watermark. `wide`: the profile's horizontal card (art right, wordmark left, the photo overlaps
  // its bottom-left corner); else the full-screen badge's (art in the middle, the strip below names it).
  // Art: the panther and the Knights emblem cut from the clubs' logos, StudEx's official logo, the app's colonnade.
  import type { Look } from '../lib/awards';
  import KbtuMark from './KbtuMark.svelte';
  import panther from '../assets/lanyards/panther.webp';
  import knights from '../assets/lanyards/knights.webp';
  import studex from '../assets/lanyards/studex.webp';
  import cheerWide from '../assets/lanyards/cheer-wide.svg?url';
  import cheerTall from '../assets/lanyards/cheer-tall.svg?url';
  import confetti from '../assets/lanyards/studex-confetti.svg?url';
  import sparks from '../assets/lanyards/sparks.svg?url';

  let { look, wide = false }: { look: Look; wide?: boolean } = $props();
</script>

<div class="band {look}" class:wide aria-hidden="true">
  {#if look === 'cheer'}
    <img class="dec" src={wide ? cheerWide : cheerTall} alt="" /><img class="art" src={panther} alt="" />
    {#if wide}<span class="wm ch">CHEERLEADING<small>KBTU</small></span>{/if}
  {:else if look === 'knights'}
    <svg class="dec" viewBox="0 0 340 112" preserveAspectRatio="xMidYMid slice"><g fill="none" stroke="#fff" stroke-opacity=".16" stroke-width="2">
      <path d="M-10 8H350" /><circle cx="170" cy="8" r="34" /><path d="M120 112V64H220V112" /><path d="M150 64A20 20 0 0 1 190 64" /><path d="M40 112A130 130 0 0 1 300 112" /></g></svg>
    <img class="art" src={knights} alt="" />
    {#if wide}<span class="wm kn">KNIGHTS<small>KBTU SPORT CLUB</small></span>{/if}
  {:else if look === 'studex'}
    <img class="dec" src={confetti} alt="" /><span class="sign"><img src={studex} alt="" /></span>
  {:else if look === 'sower'}
    <span class="wm sw">SOWER</span>
  {:else}
    <span class="glow"></span><img class="dec" src={sparks} alt="" /><span class="mark"><KbtuMark size={wide ? 88 : 100} /></span>
    {#if wide}<span class="wm kb">KBTU<small>STUDENT APP</small></span>{/if}
  {/if}
</div>

<style>
  .band { position: relative; overflow: hidden; height: 124px; color: #fff; }
  .band.wide { height: 112px; }
  img { position: absolute; pointer-events: none; user-select: none; -webkit-user-drag: none; }
  .dec { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; pointer-events: none; }
  .wm { position: absolute; left: 18px; top: 24px; display: flex; flex-direction: column; gap: 5px; white-space: nowrap; text-shadow: 0 2px 10px rgba(0, 0, 0, 0.35); }
  .wm small { font: 800 8.5px/1 var(--font-text); letter-spacing: 0.24em; opacity: 0.92; }

  /* Cheerleading: rays behind the panther, gold and pink pom-poms, confetti */
  .cheer { background: repeating-conic-gradient(from 0deg at var(--c, 50% 78%), rgba(255, 255, 255, 0.06) 0 5deg, transparent 5deg 13deg),
    radial-gradient(circle at var(--c, 50% 78%), #5560C2, #2E3258 48%, #14162E); }
  .cheer.wide { --c: 72% 70%; }
  .cheer .art { left: 50%; bottom: -12px; height: 128px; transform: translateX(-50%); }
  .cheer.wide .art { left: auto; right: 46px; bottom: -10px; height: 118px; transform: none; }
  .ch { font: 700 17px/1 Georgia, 'Times New Roman', serif; letter-spacing: 0.14em; }
  .ch small { color: #FFC83D; }

  /* Knights: royal blue, speed stripes, the court's lines, the emblem */
  .knights { background: repeating-linear-gradient(115deg, rgba(255, 255, 255, 0.05) 0 10px, transparent 10px 26px), linear-gradient(150deg, #3A7BEA, #1C4C94 55%, #0D2A63); }
  .knights .art { left: 50%; top: 10px; height: 112px; transform: translateX(-50%); }
  .knights.wide .art { left: auto; right: 58px; top: 8px; height: 98px; transform: none; }
  .kn { font: italic 900 30px/0.9 var(--font-display); letter-spacing: 0.01em; }
  .kn small { color: #9CC2FF; }

  /* StudEx: its red, a white cut and navy (the badge it had since Oct 13), its own logo on a white sign */
  .studex { background: linear-gradient(104deg, #E2402F, #C12E22 52%, #fff 52%, #fff 54%, #1D3B7A 54%, #0F2350); }
  .sign { position: absolute; left: 50%; top: 34px; display: flex; padding: 11px 14px; border-radius: 14px; background: #fff; transform: translateX(-50%) rotate(-4deg);
    box-shadow: 0 14px 26px -10px rgba(0, 0, 0, 0.5); }
  .sign img { position: static; width: 200px; }
  .studex.wide .sign { left: auto; right: 22px; top: 22px; transform: rotate(-4deg); }
  .studex.wide .sign img { width: 168px; }

  /* SOWER, the creator's alone: black, rings spreading from the corner */
  .sower { background: radial-gradient(90% 120% at 0% 0%, #26262B, #000 62%); }
  .sower::before { content: ''; position: absolute; right: -120px; top: -150px; width: 300px; height: 300px; border-radius: 50%;
    background: repeating-radial-gradient(circle, transparent 0 17px, rgba(255, 255, 255, 0.12) 17px 18.5px); }
  .sw { left: 0; right: 0; top: 50%; align-items: center; transform: translateY(-50%); font: 900 26px/1 var(--font-display); letter-spacing: 0.34em; }
  .sower.wide .sw { left: 18px; right: auto; top: 26px; align-items: flex-start; transform: none; }

  /* KBTU's own: the app's colonnade on an iridescent glow */
  .kbtu { background: radial-gradient(60% 120% at 85% 0%, rgba(134, 227, 255, 0.55), transparent 60%), radial-gradient(70% 120% at 0% 100%, rgba(255, 166, 218, 0.55), transparent 60%),
    linear-gradient(140deg, #7C4DFF, #2A4FD6 55%, #1B2A8A); }
  .glow { position: absolute; left: 50%; top: 50%; width: 200px; height: 200px; margin: -100px 0 0 -100px; border-radius: 50%; opacity: 0.55; filter: blur(28px);
    background: conic-gradient(#FFA6DA, #B9A3FF, #86E3FF, #A6FFD6, #FFE69A, #FFA6DA); }
  .wide .glow { left: auto; right: -40px; top: -50px; margin: 0; }
  .mark { position: absolute; left: 50%; top: 22px; display: flex; transform: translateX(-50%); filter: drop-shadow(0 8px 16px rgba(0, 0, 0, 0.35)); }
  .wide .mark { left: auto; right: 30px; top: 20px; transform: none; }
  .kb { font: 900 32px/0.9 var(--font-display); letter-spacing: -0.02em; }
</style>
