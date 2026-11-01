<script lang="ts">
  // The Student Government's seal beside its name, like the verified tick (owner: the Russian "Student Government"
  // chip under the club named "Student Government" said it twice); the words stay as its label and tooltip
  import Vote from '@lucide/svelte/icons/vote';
  import { t } from '../lib/i18n/index.svelte';
  let { size = 15 }: { size?: number } = $props();
</script>

<span class="gov" title={t('clubs.gov')} role="img" aria-label={t('clubs.gov')}><Vote {size} strokeWidth={2.2} /></span>

<style>
  .gov { display: inline-flex; flex: none; color: var(--accent-text); }
</style>
