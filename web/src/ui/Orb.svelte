<script lang="ts">
  // The orb: a frosted glass ball with a light and grains inside, floating over its own shadow and breathing.
  // KRI's light on its welcome and an empty state's picture. Gradients and two small SVGs of grains
  // (tools/orb-dots.mjs); only transform and opacity move, each on its own layer: no blur, no filter, no canvas.
  //   size       the ball's diameter, px
  //   tone       the light's colour: the accent, or a state's (EmptyState)
  //   children   a glyph held inside the glass, under the grains and the window light
  import type { Snippet } from 'svelte';

  type Props = { size?: number; tone?: 'neutral' | 'success' | 'danger'; children?: Snippet };
  let { size = 168, tone = 'neutral', children }: Props = $props();
</script>

<i class="orb {tone}" style:--d="{size}px" aria-hidden="true">
  <i class="halo"></i>
  <i class="ball"><i class="core"></i>{#if children}<i class="in">{@render children()}</i>{/if}<i class="dots near"></i><i class="dots far"></i></i>
  <i class="floor"></i>
</i>

<style>
  .orb { position: relative; flex: none; display: block; width: var(--d); height: var(--d);
    animation: breathe 6s ease-in-out infinite alternate; animation-play-state: var(--sheet-loop, running); }
  .success { --orb-core-a: var(--success); --orb-core-b: var(--tile-teal); --orb-halo: var(--success-soft); --orb-halo-2: transparent; }
  .danger { --orb-core-a: var(--danger); --orb-core-b: var(--warning); --orb-halo: var(--danger-soft); --orb-halo-2: transparent; }
  .orb > i, .ball > i { position: absolute; display: block; pointer-events: none; }
  /* the light it throws on the ground behind it */
  .halo { inset: -42%; border-radius: 50%; background: radial-gradient(closest-side, var(--orb-halo), var(--orb-halo-2) 58%, transparent);
    animation: glow 6s ease-in-out infinite alternate; animation-play-state: var(--sheet-loop, running); }
  .ball { inset: 0; border-radius: 50%; overflow: hidden; background: var(--orb-shell); }
  /* the light inside: two colours a little apart, a soft bloom between them */
  .core { inset: 0;
    background: radial-gradient(circle at 50% 56%, var(--orb-hot), transparent 30%), radial-gradient(circle at 41% 49%, var(--orb-core-a), transparent 42%),
      radial-gradient(circle at 60% 62%, var(--orb-core-b), transparent 48%);
    animation: core 6s ease-in-out infinite alternate; animation-play-state: var(--sheet-loop, running); }
  .ball > .in { inset: 0; display: grid; place-items: center; color: var(--text); }
  .dots { inset: 0; border-radius: 50%; background: center / 100% 100% no-repeat; animation: turn 90s linear infinite; animation-play-state: var(--sheet-loop, running); }
  .near { background-image: url('../assets/orb/near.svg'); }
  .far { background-image: url('../assets/orb/far.svg'); animation-duration: 140s; animation-direction: reverse; }
  /* the glass: a soft window light up left, the rim, the fringes of the app's own glass */
  .ball::after { content: ''; position: absolute; inset: 0; border-radius: 50%; pointer-events: none;
    background: radial-gradient(ellipse 46% 30% at 36% 15%, var(--orb-gloss), transparent 70%); box-shadow: var(--orb-rim); }
  /* it floats: its shadow (in the dark, its glow) on the ground under it */
  .floor { left: 12%; right: 12%; top: calc(100% + var(--d) * 0.13); height: calc(var(--d) * 0.1); background: radial-gradient(closest-side, var(--orb-floor), transparent);
    animation: floor 6s ease-in-out infinite alternate; animation-play-state: var(--sheet-loop, running); }
  @keyframes breathe { from { transform: translateY(2px) scale(0.985); } to { transform: translateY(-3px) scale(1.02); } }
  @keyframes glow { from { opacity: 0.7; } to { opacity: 1; } }
  @keyframes core { from { opacity: 0.78; transform: scale(0.94); } to { opacity: 1; transform: scale(1.05); } }
  @keyframes turn { to { transform: rotate(360deg); } }
  @keyframes floor { from { opacity: 1; transform: scaleX(1); } to { opacity: 0.7; transform: scaleX(0.9); } }
  /* power saving: nothing moves without end; less motion asked: nothing moves at all */
  :global(html.lowfx) .orb, :global(html.lowfx) .orb i { animation: none; }
  @media (prefers-reduced-motion: reduce) { .orb, .orb i { animation: none; } }
</style>
