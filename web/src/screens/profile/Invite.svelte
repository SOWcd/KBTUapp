<script lang="ts">
  // My invite (referrals), the right square beside Friends (owner, Nov 1): how many came, the next "Recruiter" level
  // (3, 10, 25, 50); a tap opens RefSheet: my profile QR with my photo, or our bot's card. A student it brings counts
  // once they sign in with KBTU.
  import type { Me } from '../../lib/api';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { sheets } from '../../lib/state/sheets';
  import Emoji from '../../ui/Emoji.svelte';

  let { r }: { r: NonNullable<Me['referrals']> } = $props();
  const LEVELS = [3, 10, 25, 50];
  const next = $derived(LEVELS.find((n) => n > r.count));
</script>

<button class="sq inv surface" onclick={() => { haptic.tap(); sheets.referral(r.code); }}>
  <span class="art"><Emoji name="megaphone_3d" size={64} /></span>
  <span class="tx"><b>{t('ref.title')}</b><i>{tn('ref.count', r.count)}{next ? ` · ${t('ref.next', { n: next })}` : ''}</i></span>
</button>

<style>
  .sq { position: relative; overflow: hidden; aspect-ratio: 1; display: flex; flex-direction: column; justify-content: space-between; padding: 14px; border-radius: var(--r-l); text-align: left; }
  .sq:active { transform: scale(0.97); }
  /* a warm glow behind the megaphone, the tile's one colour */
  .inv { background: radial-gradient(90% 70% at 85% 0%, rgba(255, 178, 61, 0.22), transparent 70%), var(--surface); }
  .art { display: flex; margin: -4px 0 0 -4px; transform-origin: 30% 70%; animation: call 3.6s ease-in-out 900ms infinite; }
  :global(html.lowfx) .art { animation: none; }
  @keyframes call { 0%, 70%, 100% { transform: none; } 76% { transform: rotate(-9deg) scale(1.06); } 82% { transform: rotate(5deg) scale(1.03); } 88% { transform: rotate(-3deg); } }
  .tx { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .tx b { font: 700 var(--fs-body)/1.2 var(--font-text); }
  .tx i { font: 500 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
</style>
