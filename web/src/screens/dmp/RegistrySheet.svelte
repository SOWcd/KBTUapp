<script lang="ts">
  // The registry in a full sheet: from Studio with DMP picked, and from the Admin panel for the admin.
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import Registry from './Registry.svelte';
  let { overlay }: { overlay: Overlay } = $props();
</script>

<Sheet {overlay} full title={t('reg.title')}><Registry inSheet /></Sheet>
