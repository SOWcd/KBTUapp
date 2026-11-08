<script lang="ts">
  // Settings under my lanyard as an overlay with no element of its own (Me draws it): while it is up Telegram's Back
  // shows, the nav goes and the capsule says "Settings". Back, Escape and Me's check close it; Me runs the way out
  // (onclose) and removes it at its swap. The lanyard's editor in them is a second one over it (title 'look.lanyard'):
  // its Back returns to the list.
  import { onMount, untrack } from 'svelte';
  import SettingsIcon from '@lucide/svelte/icons/settings';
  import { hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { t, type Key } from '../../lib/i18n/index.svelte';

  let { overlay, onclose, title = 'me.settings' }: { overlay: Overlay; onclose: () => void; title?: Key } = $props();
  onMount(hideChrome);
  $effect(() => { overlay.title = t(title); overlay.icon = SettingsIcon; }); // a language picked inside: its word
  $effect(() => { if (overlay.closing) untrack(onclose); });
</script>
