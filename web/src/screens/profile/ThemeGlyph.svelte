<script lang="ts" module>
  // engine: Row's `icon` takes a component only; a snippet there would keep this in SettingsList.
  // The theme row's icon (SettingsList): the sun and the moon in one place, SettingsList says which (dark); el: where the
  // new theme grows from
  export const glyph = $state<{ dark: boolean; el: HTMLElement | null }>({ dark: false, el: null });
</script>

<script lang="ts">
  import Sun from '@lucide/svelte/icons/sun';
  import Moon from '@lucide/svelte/icons/moon';
  let { size = 20, strokeWidth = 2 }: { size?: number; strokeWidth?: number } = $props();
  const keep = (node: HTMLElement) => { glyph.el = node; return () => { if (glyph.el === node) glyph.el = null; }; };
</script>

<span class="sm" class:moon={glyph.dark} {@attach keep}><Sun {size} {strokeWidth} /><Moon {size} {strokeWidth} /></span>

<style>
  .sm { display: grid; place-items: center; }
  /* one over the other; the one leaving turns away and shrinks, the other springs in */
  .sm > :global(svg) { grid-area: 1 / 1; transition: transform 300ms var(--ease-bounce), opacity 120ms ease; }
  .sm > :global(svg:last-child), .sm.moon > :global(svg:first-child) { opacity: 0; transform: rotate(-90deg) scale(0.3); }
  .sm.moon > :global(svg:first-child) { transform: rotate(90deg) scale(0.3); }
  .sm.moon > :global(svg:last-child) { opacity: 1; transform: none; }
  /* the sun goes out: its rays draw in one by one round the clock, then the bare disk turns into the moon (it fades a
     beat later so the rays are seen); on the way back they grow out the other way round. Lucide's paths are N, S, NW,
     SE, W, E, SW, NE; --i is each one's place clockwise from the top */
  .sm > :global(svg:first-child path) { transform-origin: 12px 12px; transition: transform 140ms var(--ease-bounce) calc(60ms + (7 - var(--i)) * 14ms); }
  .sm.moon > :global(svg:first-child) { transition: transform 300ms var(--ease-bounce), opacity 120ms ease 90ms; }
  .sm.moon > :global(svg:first-child path) { transform: scale(0); transition: transform 90ms var(--ease-in) calc(var(--i) * 10ms); }
  .sm :global(path:nth-of-type(1)) { --i: 0; }
  .sm :global(path:nth-of-type(8)) { --i: 1; }
  .sm :global(path:nth-of-type(6)) { --i: 2; }
  .sm :global(path:nth-of-type(4)) { --i: 3; }
  .sm :global(path:nth-of-type(2)) { --i: 4; }
  .sm :global(path:nth-of-type(7)) { --i: 5; }
  .sm :global(path:nth-of-type(5)) { --i: 6; }
  .sm :global(path:nth-of-type(3)) { --i: 7; }
  :global(html.lowfx) .sm > :global(svg), :global(html.lowfx) .sm :global(path) { transition: none !important; }
  @media (prefers-reduced-motion: reduce) { .sm > :global(svg), .sm :global(path) { transition: none !important; } }
</style>
