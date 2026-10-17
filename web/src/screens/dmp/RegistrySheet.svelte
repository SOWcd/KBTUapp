<script lang="ts">
  // The registry for the admin (who isn't DMP staff): the same page in a tall sheet, opened from the Admin panel.
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import Registry from './Registry.svelte';
  let { overlay }: { overlay: Overlay } = $props();
</script>

<Sheet {overlay} tall title={t('reg.title')}><Registry inSheet /></Sheet>
