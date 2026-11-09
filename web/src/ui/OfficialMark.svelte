<script lang="ts">
  // An official club's mark beside its name: a filled seal with a tick, as the platforms' verified badges are (owner,
  // Nov 3: the outline tick looked so-so). One shape everywhere: rows, the club's sheet, Admin, the registry
  // explain: a tap says who gives it (the club's sheet; in a list the tap is the row's)
  import { t } from '../lib/i18n/index.svelte';
  import { say } from '../lib/state/ui.svelte';
  let { size = 15, explain = false }: { size?: number; explain?: boolean } = $props();
</script>

{#snippet seal()}
  <svg width={size} height={size} viewBox="0 0 24 24" aria-hidden="true">
    <path class="seal" d="M12.00 0.61L12.49 0.72L12.96 1.04L13.38 1.49L13.77 1.95L14.15 2.32L14.54 2.53L14.98 2.55L15.49 2.41L16.06 2.21L16.65 2.03L17.21 1.99L17.70 2.13L18.07 2.48L18.31 2.99L18.45 3.59L18.56 4.18L18.70 4.69L18.93 5.07L19.31 5.30L19.82 5.44L20.41 5.55L21.01 5.69L21.52 5.93L21.87 6.30L22.01 6.79L21.97 7.35L21.79 7.94L21.59 8.51L21.45 9.02L21.47 9.46L21.68 9.85L22.05 10.23L22.51 10.62L22.96 11.04L23.28 11.51L23.39 12.00L23.28 12.49L22.96 12.96L22.51 13.38L22.05 13.77L21.68 14.15L21.47 14.54L21.45 14.98L21.59 15.49L21.79 16.06L21.97 16.65L22.01 17.21L21.87 17.70L21.52 18.07L21.01 18.31L20.41 18.45L19.82 18.56L19.31 18.70L18.93 18.93L18.70 19.31L18.56 19.82L18.45 20.41L18.31 21.01L18.07 21.52L17.70 21.87L17.21 22.01L16.65 21.97L16.06 21.79L15.49 21.59L14.98 21.45L14.54 21.47L14.15 21.68L13.77 22.05L13.38 22.51L12.96 22.96L12.49 23.28L12.00 23.39L11.51 23.28L11.04 22.96L10.62 22.51L10.23 22.05L9.85 21.68L9.46 21.47L9.02 21.45L8.51 21.59L7.94 21.79L7.35 21.97L6.79 22.01L6.30 21.87L5.93 21.52L5.69 21.01L5.55 20.41L5.44 19.82L5.30 19.31L5.07 18.93L4.69 18.70L4.18 18.56L3.59 18.45L2.99 18.31L2.48 18.07L2.13 17.70L1.99 17.21L2.03 16.65L2.21 16.06L2.41 15.49L2.55 14.98L2.53 14.54L2.32 14.15L1.95 13.77L1.49 13.38L1.04 12.96L0.72 12.49L0.61 12.00L0.72 11.51L1.04 11.04L1.49 10.62L1.95 10.23L2.32 9.85L2.53 9.46L2.55 9.02L2.41 8.51L2.21 7.94L2.03 7.35L1.99 6.79L2.13 6.30L2.48 5.93L2.99 5.69L3.59 5.55L4.18 5.44L4.69 5.30L5.07 5.07L5.30 4.69L5.44 4.18L5.55 3.59L5.69 2.99L5.93 2.48L6.30 2.13L6.79 1.99L7.35 2.03L7.94 2.21L8.51 2.41L9.02 2.55L9.46 2.53L9.85 2.32L10.23 1.95L10.62 1.49L11.04 1.04L11.51 0.72Z" />
    <path class="tick" d="M7.6 12.4l3 3 5.8-6.4" />
  </svg>
{/snippet}

{#if explain}
  <button class="om tap" aria-label={t('clubs.official')} onclick={() => say(t('clubs.officialWhy'), 'scroll_3d')}>{@render seal()}</button>
{:else}
  <span class="om" title={t('clubs.official')} role="img" aria-label={t('clubs.official')}>{@render seal()}</span>
{/if}

<style>
  .om { display: inline-flex; flex: none; color: var(--accent); }
  .tap { position: relative; }
  .tap::after { content: ''; position: absolute; inset: -12px; } /* 44 to the finger */
  .tap:active { opacity: 0.5; transform: none; }
  .seal { fill: currentColor; }
  .tick { fill: none; stroke: var(--on-accent); stroke-width: 2.4; stroke-linecap: round; stroke-linejoin: round; }
</style>
