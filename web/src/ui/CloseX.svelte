<script lang="ts">
  // The one way out of a full-screen overlay: a round glass × at the bottom centre, under the thumb,
  // the same on every one (the photo viewer's). The overlay leaves it room: its content scrolls in a box that ends
  // --close-room above the bottom, so nothing ever slides under the × (Share sat on top of it).
  // Every overlay that has it stands on a dark stage in both themes: the × takes the dark glass (as Feed's).
  import X from '@lucide/svelte/icons/x';
  import { t } from '../lib/i18n/index.svelte';
  import IconButton from './IconButton.svelte';

  let { onclick }: { onclick: () => void } = $props();
</script>

<span class="closex theme-dark"><IconButton icon={X} kind="glass" size="l" label={t('common.close')} {onclick} /></span>

<style>
  .closex { position: absolute; left: 50%; bottom: calc(var(--safe-bottom) + 16px); translate: -50% 0; display: flex; pointer-events: auto; }
</style>
