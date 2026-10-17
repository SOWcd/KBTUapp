<script lang="ts">
  // "The app is in development" — warm, so people aren't shy to write (SPEC §4.11b).
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import { t } from '../lib/i18n/index.svelte';
  import { writeOwner } from '../lib/feedback';
  import Emoji from './Emoji.svelte';
</script>

<section class="fb surface">
  <div class="top"><Emoji name="raising_hands_3d_default" size={34} /><b class="t-title">{t('fb.title')}</b></div>
  <p class="t-foot">{t('fb.text')}</p>
  <button class="write" onclick={writeOwner}><MessageCircle size={17} />{t('fb.write')}</button>
</section>

<style>
  .fb { display: flex; flex-direction: column; gap: 8px; padding: 14px; }
  .top { display: flex; align-items: center; gap: 10px; }
  /* one button (owner, Oct 5: "just write to the creator"); the card's text says what to write about */
  .write { display: inline-flex; align-items: center; justify-content: center; gap: 6px; height: 38px; margin-top: 4px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 620 14px/1 var(--font-text); transition: transform var(--t-fast) var(--ease); }
  .write:active { transform: scale(0.97); }
</style>
