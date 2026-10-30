<script lang="ts">
  // A member's Clubs tab: My club | All clubs, on top of the content, tap only (Oct 30: no page swipe, no hidden switcher)
  import { ui } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';

  const pick = (all: boolean) => { if (ui.allClubs !== all) { haptic.select(); ui.allClubs = all; } };
</script>

<div class="seg sw" role="tablist" aria-label={t('page.clubs')}>
  <button role="tab" class:on={!ui.allClubs} aria-selected={!ui.allClubs} onclick={() => pick(false)}>{t('clubs.myClub')}</button>
  <button role="tab" class:on={ui.allClubs} aria-selected={ui.allClubs} onclick={() => pick(true)}>{t('clubs.allTitle')}</button>
</div>

<style>
  .sw { display: flex; width: 100%; margin-bottom: 16px; }
  .sw button { flex: 1; min-width: 0; }
</style>
