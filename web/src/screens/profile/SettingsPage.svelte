<script lang="ts">
  // Profile's gear: the Settings page full screen (Oct 30: it was the third page beside Friends and Me); Back closes it
  import SettingsIcon from '@lucide/svelte/icons/settings';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import Settings from './Settings.svelte';

  let { overlay }: { overlay: Overlay } = $props();
</script>

<Sheet {overlay} full title={t('me.settings')} icon={SettingsIcon}><Settings /></Sheet>
