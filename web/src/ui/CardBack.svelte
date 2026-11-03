<script lang="ts">
  // The back of my lanyard card (round 5, owner): the lanyard's own art, a QR on its white plate on the left, my name, role,
  // course line and number beside it, the medallion top right. One look for Hero's back (the badge's u_ code, the plate
  // opens the full-screen one, the medallion turns the card face on) and the invite sheet (RefSheet: the r_ invite link,
  // nothing to tap). The text and the QR are the caller's: this only draws them.
  import type { Snippet } from 'svelte';
  import RefreshCw from '@lucide/svelte/icons/refresh-cw';
  import { banded, clubLook, lookVars, QR_LOOK, SOWER, type Look } from '../lib/awards';
  import LanyardBand from './LanyardBand.svelte';
  import SowerArt from './SowerArt.svelte';
  import OrgMedal from './OrgMedal.svelte';
  import LookMark from './LookMark.svelte';
  import Qr from './Qr.svelte';

  let { look, name, title, line, no, text, logo = null, lazy = false, onplate, plateLabel, onmedal, medalLabel, mark }: {
    look: Look; name: string; title: string; line: string; no: string;
    text: string;          // the QR's
    logo?: string | null;  // the medallion's (OrgMedal)
    lazy?: boolean;        // Qr's: encoded when the page is idle
    onplate?: () => void; plateLabel?: string; // the plate as a button
    onmedal?: () => void; medalLabel?: string; // the medallion as a button (Hero: back to the face)
    mark?: Snippet;        // the QR's middle; the look's mark by default
  } = $props();
</script>

<div class="cb {look} {look === 'sower' ? 'sw-' + SOWER : ''}" class:club={!!clubLook(look)} style={lookVars(look)}>
  <!-- the lanyard's own art on this side too (owner, Nov 3: the back was a bare colour) -->
  {#if look === 'sower'}<SowerArt wide />{/if}
  {#if banded(look)}<LanyardBand {look} wide qr />{/if}
  <!-- no JCC sakura pieces on this side (club, Nov 3): cut by the plate they read as stray bits; their scene has its own -->
  <span class="slot" aria-hidden="true"></span><!-- the clip's hole goes through both sides -->
  {#snippet code()}<Qr {text} tone={QR_LOOK[look]} {lazy}>{#if mark}{@render mark()}{:else}<LookMark {look} />{/if}</Qr>{/snippet}
  {#if onplate}<button class="plate" onclick={onplate} aria-label={plateLabel}>{@render code()}</button>
  {:else}<span class="plate">{@render code()}</span>{/if}
  <span class="bside">
    <b class="bnm">{name}</b>
    <span class="role">{title}</span>
    <span class="meta">{line}</span>
    <span class="bno">№ {no}</span>
  </span>
  <!-- the medallion on the right, where the face has it (owner, Nov 3: QR left, name in the middle, the medallion right) -->
  {#if onmedal}<button class="bmed" onclick={onmedal} aria-label={medalLabel}><OrgMedal {look} {logo} /><span class="qrhint"><RefreshCw size={10} strokeWidth={2.6} /></span></button>
  {:else}<span class="bmed"><OrgMedal {look} {logo} /></span>{/if}
</div>

<style>
  .cb { --kb: linear-gradient(155deg, rgb(42, 79, 214), rgb(18, 26, 61) 72%); position: relative; isolation: isolate; height: 100%; display: flex; align-items: center; gap: 14px;
    padding: 22px 14px 18px 18px; overflow: hidden; border-radius: var(--r-l); color: white;
    background: radial-gradient(90% 90% at 100% 0%, rgba(124, 77, 255, 0.45), transparent 60%), var(--kb);
    box-shadow: 0 30px 50px -26px rgba(0, 0, 0, 0.75), inset 0 1px 0 rgba(255, 255, 255, 0.28); }
  .club { background: radial-gradient(90% 90% at 100% 0%, rgba(255, 255, 255, 0.16), transparent 60%), linear-gradient(155deg, var(--c1), var(--c2) 55%, var(--c3)); color: var(--ink); }
  .faces { background: radial-gradient(90% 120% at 0% 0%, rgb(38, 38, 43), rgb(0, 0, 0) 62%); }
  .sower { background: radial-gradient(80% 110% at 100% 0%, rgba(120, 130, 170, 0.2), transparent 60%), linear-gradient(160deg, rgb(27, 28, 33), rgb(0, 0, 0)); }
  .sw-gold { background: radial-gradient(80% 110% at 100% 0%, rgba(120, 90, 30, 0.26), transparent 60%), linear-gradient(160deg, rgb(21, 18, 12), rgb(0, 0, 0)); }
  .studex { background: linear-gradient(135deg, rgb(15, 35, 80), rgb(29, 59, 122) 55%, rgb(11, 28, 68)); }
  .cheer { background: linear-gradient(180deg, rgb(34, 38, 70), rgb(24, 26, 52)); }
  .knights { background: radial-gradient(90% 90% at 100% 0%, rgba(232, 196, 120, 0.22), transparent 60%), linear-gradient(150deg, rgb(24, 58, 126), rgb(7, 20, 54)); }
  .moments { background: radial-gradient(70% 90% at 100% 100%, rgba(214, 120, 70, 0.4), transparent 70%), linear-gradient(150deg, rgb(74, 42, 30), rgb(20, 11, 8)); }
  /* each look's role colour, as on the face (Hero) */
  .cheer { --role: rgb(255, 200, 61); }
  .knights { --role: rgb(232, 196, 120); }
  .moments { --role: rgb(244, 217, 190); }
  .faces { --role: rgb(255, 155, 214); }
  .studex { --role: rgba(255, 255, 255, 0.92); }
  .sower { --role: rgb(212, 218, 232); }
  .sw-gold { --role: rgb(232, 196, 120); }
  /* no tilt reaches the back (the face's glass writes --gx): its depth layers stand still, so they are painted with the
     side, not each kept as a layer of its own */
  .cb :global(.z) { will-change: auto; }
  .slot { position: absolute; z-index: 1; top: 9px; left: 50%; width: 46px; height: 8px; margin-left: -23px; border-radius: 4px;
    background: rgba(5, 8, 20, 0.55); box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.7), 0 1px 0 rgba(255, 255, 255, 0.16); }
  /* the plate: white, the code's own quiet zone in it; the size a door's scanner reads from a phone */
  .plate { position: relative; z-index: 3; flex: none; display: block; width: 136px; height: 136px; padding: 8px; border-radius: var(--r-m); background: white;
    box-shadow: 0 10px 22px -12px rgba(0, 0, 0, 0.7), inset 0 0 0 1px rgba(0, 0, 0, 0.06); transition: transform var(--t-fast) var(--ease); }
  button.plate:active { transform: scale(0.96); }
  /* the name and the rest under the medallion's corner, down to the number at the foot */
  .bside { position: relative; z-index: 3; display: flex; flex-direction: column; align-items: flex-start; justify-content: flex-end; gap: 5px; min-width: 0; flex: 1;
    align-self: stretch; padding-top: 50px; }
  .bside > * { flex: none; }
  .bmed { position: absolute; z-index: 3; top: 14px; right: 14px; width: 52px; height: 52px; transition: transform var(--t-fast) var(--ease); }
  button.bmed:active { transform: scale(0.92); }
  .qrhint { position: absolute; right: -5px; bottom: -5px; display: grid; place-items: center; width: 18px; height: 18px; border-radius: 50%;
    background: white; color: rgb(14, 20, 48); box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35); }
  .bnm { max-width: 100%; font: 780 18px/1.15 var(--font-display); letter-spacing: -0.02em; overflow-wrap: anywhere;
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; }
  .role { display: -webkit-box; margin-top: 2px; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; overflow-wrap: anywhere;
    font: 760 var(--fs-tab)/1.3 var(--font-text); letter-spacing: 0.12em; text-transform: uppercase; color: var(--role, rgb(169, 192, 255)); }
  .meta { display: block; margin-top: 1px; overflow-wrap: anywhere; font: 550 var(--fs-sub)/1.3 var(--font-text); color: rgba(255, 255, 255, 0.72); }
  .moments .meta { color: rgba(255, 255, 255, 0.84); }
  .studex .meta { color: rgba(255, 255, 255, 0.8); }
  .sower .meta { color: rgba(255, 255, 255, 0.66); }
  .club .meta { color: var(--ink2); }
  .bno { margin-top: 4px; font: 800 var(--fs-micro)/1 var(--font-text); letter-spacing: 0.16em; font-variant-numeric: tabular-nums; opacity: 0.75; }
  /* the anime club's art where this side sets the name (mid-right): its mist moved under it, its swirl's ink haloed */
  .klubanimeshnikov :global(.mist) { background: radial-gradient(34% 52% at 64% 56%, rgba(232, 232, 235, 0.72), transparent 80%); }
  .klubanimeshnikov .bside { text-shadow: 0 0 3px rgba(226, 226, 230, 0.9), 0 0 9px rgba(226, 226, 230, 0.7); }
  /* kbtu.mag: its issues stand where this side sets the name: quieter here, the name haloed in their cream */
  .kbtumag :global(.near) { opacity: 0.45; }
  .kbtumag .bside { text-shadow: 0 0 3px rgba(243, 233, 219, 0.95), 0 0 9px rgba(243, 233, 219, 0.85); }
  .japanesecultureclub .bside { text-shadow: 0 0 3px rgba(227, 176, 194, 0.95), 0 0 9px rgba(227, 176, 194, 0.85); } /* as on the face (Hero) */
  @media (max-width: 359px) { .plate { width: 124px; height: 124px; } }
</style>
