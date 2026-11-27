<script lang="ts">
  // The registry in a full sheet: from Studio with DMP picked, and from the Admin panel for the admin. On a wide window
  // (a computer) it takes the whole window: the clubs as a table, the chosen club's roster beside it.
  import { overlays, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { MediaQuery } from 'svelte/reactivity';
  import { WIDE } from '../../lib/desk';
  import Sheet from '../../ui/Sheet.svelte';
  import Ask from '../../ui/Ask.svelte';
  import Library from '@lucide/svelte/icons/library';
  import Registry from './Registry.svelte';
  let { overlay, focus }: { overlay: Overlay; focus?: 'memos' } = $props();
  const mq = new MediaQuery(WIDE);
  const above = $derived(overlays.filter((o) => o.id > overlay.id && !o.closing));
  // wide while nothing but a question (the short name, taking the check back) stands over it: another screen opened from
  // here (a memo's event, then the map) gets the app's own column, and the registry under it its phone layout
  const wide = $derived(mq.current && above.every((o) => o.component === Ask));
  // the app's phone column opens up to the window while this sheet is wide (base.css)
  $effect(() => {
    if (!wide) return;
    const d = document.documentElement.dataset;
    d.wide = '';
    return () => { delete d.wide; };
  });
</script>

<Sheet {overlay} icon={Library} full title={t('reg.title')}><Registry inSheet {wide} {focus} top={!above.length} /></Sheet>
