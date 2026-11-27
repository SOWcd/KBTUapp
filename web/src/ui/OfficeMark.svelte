<script lang="ts">
  // KBTU's own official service beside its name (lib/clubs service): a calm landmark, not a club's verified seal (a
  // service is the university itself, not a club DMP registered); the words stay as its label and tooltip
  import Landmark from '@lucide/svelte/icons/landmark';
  import { t } from '../lib/i18n/index.svelte';
  let { size = 15 }: { size?: number } = $props();
</script>

<span class="svc" title={t('clubs.office')} role="img" aria-label={t('clubs.office')}><Landmark {size} strokeWidth={2.2} /></span>

<style>
  .svc { display: inline-flex; flex: none; color: var(--accent-text); }
</style>
