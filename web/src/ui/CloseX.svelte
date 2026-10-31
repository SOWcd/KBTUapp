<script lang="ts">
  // The one way out of a full-screen overlay (owner, Oct 31): a round glass × at the bottom centre, under the thumb,
  // the same on every one (the photo viewer's). The overlay leaves it room: its bottom padding is --close-room.
  import X from '@lucide/svelte/icons/x';
  import { t } from '../lib/i18n/index.svelte';
  import { glass } from './glass';

  let { onclick }: { onclick: () => void } = $props();
</script>

<button class="closex glass glass-pill" use:glass {onclick} aria-label={t('common.close')}><X size={22} strokeWidth={2.4} /></button>

<style>
  .closex {
    position: absolute; left: 50%; bottom: calc(var(--safe-bottom) + 16px); translate: -50% 0; width: 52px; height: 52px;
    display: grid; place-items: center; border-radius: var(--r-full); color: rgba(255, 255, 255, 1); background-color: rgba(255, 255, 255, 0.12); pointer-events: auto;
  }
  .closex > :global(svg) { position: relative; }
  .closex:active { transform: scale(0.94); }
</style>
