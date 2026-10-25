<script lang="ts">
  // The Student Government's mark (owner, Oct 25): a name, not a right; wherever the club shows
  import Landmark from '@lucide/svelte/icons/landmark';
  import { t } from '../lib/i18n/index.svelte';
</script>

<span class="gov"><Landmark size={11} strokeWidth={2.4} />{t('clubs.gov')}</span>

<style>
  .gov { display: inline-flex; align-items: center; gap: 4px; padding: 2px 7px; border-radius: var(--r-full); background: var(--accent-soft);
    color: var(--accent-text); font: 680 11px/1.35 var(--font-text); }
  .gov :global(svg) { flex: none; }
</style>
