<script lang="ts">
  // The Awards page in a tall sheet, opened from my badge's numbers.
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import Award from '@lucide/svelte/icons/award';
  import Awards from './Awards.svelte';
  let { overlay }: { overlay: Overlay } = $props();
</script>

<Sheet {overlay} icon={Award} title={t('page.awards')} tall><Awards /></Sheet>
