<script lang="ts">
  // The registry in a full sheet: from Studio with DMP picked, and from the Admin panel for the admin. On a wide window
  // (a computer) it takes the whole window: the clubs as a table, the chosen club's roster beside it.
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { MediaQuery } from 'svelte/reactivity';
  import { WIDE } from '../../lib/desk';
  import Sheet from '../../ui/Sheet.svelte';
  import Library from '@lucide/svelte/icons/library';
  import Registry from './Registry.svelte';
  let { overlay }: { overlay: Overlay } = $props();
  const wide = new MediaQuery(WIDE);
  // the app's phone column opens up to the window while this sheet is wide (base.css)
  $effect(() => {
    if (!wide.current) return;
    const d = document.documentElement.dataset;
    d.wide = '';
    return () => { delete d.wide; };
  });
</script>

<Sheet {overlay} icon={Library} full title={t('reg.title')}><Registry inSheet wide={wide.current} /></Sheet>
