<script lang="ts">
  // My invite (referrals), the right square beside Friends (owner, Nov 1), and since Nov 4 my Recruiter's only home on my
  // profile (my own shelf hides it). Its craft is the medal's (owner, Nov 4: the tile looked weak): the medal big and lit,
  // a soft burst of its metal's light behind it, its layers floating with the tilt (glass.ts writes --gx/--gy here);
  // how many came, clean, in the corner; under the title the nine levels as nine small marks in their metals, the next
  // one filling. The medal opens its award view (the levels); the rest of the tile opens RefSheet (my profile QR, Share).
  // A student it brings counts once they sign in with KBTU.
  import type { Achievement, Me } from '../../lib/api';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { sheets } from '../../lib/state/sheets';
  import { achItem, achName, leftLine, metalLetter, metalOf, nextOf } from '../../lib/awards';
  import { glass } from '../../ui/glass';
  import Medal from '../../ui/Medal.svelte';

  let { r, ach }: { r: NonNullable<Me['referrals']>; ach?: Achievement } = $props();
  const LEVELS = [1, 3, 5, 10, 15, 25, 50, 75, 100]; // as the server's ACHIEVEMENTS
  // my card's own Recruiter once it's loaded; until then the same from the count, so the tile never waits
  const a = $derived<Achievement>(ach && ach.count === r.count ? ach : {
    code: 'referral', emoji: 'megaphone_3d', secret: false, count: r.count, rarity: 0,
    level: LEVELS.filter((n) => n <= r.count).length, levels: LEVELS.map((need) => ({ need, reached: r.count >= need, rarity: 0 })),
  });
  const next = $derived(nextOf(a)?.need);
  const from = $derived(a.levels[a.level - 1]?.need ?? 0);
  const part = $derived(next ? Math.max(0.06, (r.count - from) / (next - from)) : 1);
  const metal = $derived(a.level ? metalLetter(a) : 'none');
  // each mark in its own level's metal: I-III bronze, IV-VI silver, VII-VIII gold, IX legend
  const marks = $derived(a.levels.map((l, i) => ({ m: 'bsgl'[metalOf(i + 1, a.levels.length)], fill: l.reached ? 1 : i === a.level ? part : 0 })));

  function open() { haptic.tap(); sheets.referral(r.code); }
</script>

<div class="sq inv surface {metal}" role="button" tabindex="0" onclick={open} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } }}>
  <span class="burst" aria-hidden="true"></span>
  <span class="top">
    <button class="art" use:glass onclick={(e) => { e.stopPropagation(); haptic.tap(); sheets.award(achItem(a), true); }} aria-label={achName(a)}><Medal {a} size={80} /></button>
    <span class="cnt"><b class="num">{r.count}</b><i>{tn('ref.came', r.count)}</i></span>
  </span>
  <span class="tx">
    <b>{t('ref.title')}</b>
    <span class="marks" aria-hidden="true">{#each marks as k, i (i)}<i class={k.m}><s style:transform="scaleX({k.fill})"></s></i>{/each}</span>
    {#if next}<i class="left ellipsis">{leftLine(a)}</i>{/if}
  </span>
</div>

<style>
  .sq { position: relative; overflow: hidden; aspect-ratio: 1; display: flex; flex-direction: column; justify-content: space-between; padding: 12px 14px 13px; border-radius: var(--r-l); text-align: left; cursor: pointer; isolation: isolate; }
  .sq:active { transform: scale(0.97); }
  /* the medal's light: its metal's colour behind it, soft, with faint rays, as the medal's own burst (still: no repaint) */
  .inv { --glow: 255, 178, 61; }
  .inv.b { --glow: 255, 157, 87; }
  .inv.s { --glow: 120, 170, 255; }
  .inv.l { --glow: 200, 140, 255; }
  .inv.none { --glow: 140, 150, 170; }
  .burst { position: absolute; z-index: -1; left: -38px; top: -40px; width: 172px; height: 172px; border-radius: 50%; pointer-events: none;
    background: radial-gradient(closest-side, rgba(var(--glow), 0.42), rgba(var(--glow), 0.12) 55%, transparent),
      repeating-conic-gradient(from 4deg, rgba(var(--glow), 0.16) 0deg 3deg, transparent 3deg 15deg);
    -webkit-mask-image: radial-gradient(closest-side, black 30%, transparent); mask-image: radial-gradient(closest-side, black 30%, transparent); }
  .top { display: flex; align-items: flex-start; justify-content: space-between; gap: 6px; }
  /* the medal: bigger, its shadow of light; a small turn now and then */
  .art { display: flex; margin: -4px 0 0 -4px; border-radius: 50%; box-shadow: 0 6px 22px -4px rgba(var(--glow), 0.55); animation: nudge 4.8s ease-in-out 900ms infinite; }
  :global(html.lowfx) .art { animation: none; }
  @media (prefers-reduced-motion: reduce) { .art { animation: none; } }
  /* under a sheet (the award's full-screen blur) it would make the backdrop re-blur every frame: it waits */
  :global(html[data-sheet]) .art { animation-play-state: paused; }
  @keyframes nudge { 0%, 78%, 100% { transform: none; } 84% { transform: rotate(-6deg) scale(1.04); } 90% { transform: rotate(3deg); } }
  .cnt { display: flex; flex-direction: column; align-items: flex-end; padding-top: 2px; }
  .cnt b { font: 800 var(--fs-title)/1 var(--font-display, var(--font-text)); letter-spacing: -0.03em; }
  .cnt i { font: 500 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .tx { display: flex; flex-direction: column; min-width: 0; }
  .tx b { font: 700 var(--fs-body)/1.2 var(--font-text); }
  .left { margin-top: 5px; font: 500 var(--fs-cap)/1.2 var(--font-text); font-style: normal; color: var(--text-2); }
  /* the nine levels: a mark each, in its metal; the next one fills as friends come */
  .marks { display: flex; gap: 3px; margin-top: 8px; }
  .marks i { flex: 1; height: 4px; border-radius: var(--r-full); background: var(--fill); overflow: hidden; }
  .marks s { display: block; height: 100%; border-radius: inherit; transform-origin: left; transition: transform 600ms var(--ease-out, ease); }
  .marks .b s { background: linear-gradient(90deg, rgb(178, 106, 60), rgb(238, 176, 122)); }
  .marks .s s { background: linear-gradient(90deg, rgb(142, 152, 174), rgb(232, 237, 246)); }
  .marks .g s { background: linear-gradient(90deg, rgb(194, 134, 26), rgb(247, 215, 116)); }
  .marks .l s { background: linear-gradient(90deg, rgb(124, 77, 255), rgb(53, 208, 255), rgb(255, 210, 63)); }
</style>
