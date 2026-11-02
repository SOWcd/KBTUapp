<script lang="ts">
  // My invite (referrals), the right square beside Friends (owner, Nov 1): how many came, big in the corner (owner, Nov 2), and a bar to the next
  // "Recruiter" level; the tile opens RefSheet (my profile QR with my photo, Share). A student it brings
  // counts once they sign in with KBTU.
  // The art is my Recruiter medal at its level (owner, Nov 2), with the Awards row's "N more to level X" under the name.
  import type { Achievement, Me } from '../../lib/api';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { sheets } from '../../lib/state/sheets';
  import { leftLine, nextOf } from '../../lib/awards';
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

  function open() { haptic.tap(); sheets.referral(r.code); }
</script>

<div class="sq inv surface" role="button" tabindex="0" onclick={open} onkeydown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } }}>
  <span class="top">
    <span class="art"><Medal {a} size={56} /></span>
    <span class="cnt"><b class="num">{r.count}</b><i>{tn('ref.came', r.count)}</i></span>
  </span>
  <span class="tx">
    <b>{t('ref.title')}</b>
    {#if next}<i class="left ellipsis">{leftLine(a)}</i><span class="bar" aria-hidden="true"><span style="width:{((r.count - from) / (next - from)) * 100}%"></span></span>{/if}
  </span>
</div>

<style>
  .sq { position: relative; overflow: hidden; aspect-ratio: 1; display: flex; flex-direction: column; justify-content: space-between; padding: 14px; border-radius: var(--r-l); text-align: left; cursor: pointer; }
  .sq:active { transform: scale(0.97); }
  /* a warm glow behind the medal, the tile's one colour */
  .inv { background: radial-gradient(90% 70% at 15% 0%, rgba(255, 178, 61, 0.22), transparent 70%), var(--surface); }
  .top { display: flex; align-items: flex-start; justify-content: space-between; gap: 8px; }
  /* a medal's small turn now and then */
  .art { display: flex; margin: -2px 0 0 -2px; animation: nudge 4.8s ease-in-out 900ms infinite; }
  :global(html.lowfx) .art { animation: none; }
  /* under a sheet (the award's full-screen blur) it would make the backdrop re-blur every frame: it waits */
  :global(html[data-sheet]) .art { animation-play-state: paused; }
  @keyframes nudge { 0%, 78%, 100% { transform: none; } 84% { transform: rotate(-6deg) scale(1.04); } 90% { transform: rotate(3deg); } }
  .tx { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .tx b { font: 700 var(--fs-body)/1.2 var(--font-text); }
  .left { font: 500 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  /* how far to the next Recruiter level, from the level I have */
  .bar { display: block; height: 4px; margin-top: 6px; border-radius: var(--r-full); background: var(--fill); overflow: hidden; }
  .bar span { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, rgba(255, 178, 61, 0.7), rgba(255, 178, 61, 1)); transition: width 600ms var(--ease-out, ease); }
  .cnt { display: flex; flex-direction: column; align-items: flex-end; }
  .cnt b { font: 800 var(--fs-title)/1 var(--font-display, var(--font-text)); letter-spacing: -0.02em; }
  .cnt i { font: 500 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
</style>
