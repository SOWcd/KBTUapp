<script lang="ts">
  // My invite link (referrals): shared as our bot's card, my badge's code in it (never my ID); a student
  // it brings counts once they sign in with KBTU, toward "Recruiter" (3, 10, 25, 50).
  import type { Me } from '../../lib/api';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { haptic, shareCard } from '../../lib/tg';
  import { say } from '../../lib/state/ui.svelte';
  import Emoji from '../../ui/Emoji.svelte';

  let { r }: { r: NonNullable<Me['referrals']> } = $props();
  const LEVELS = [3, 10, 25, 50];
  const next = $derived(LEVELS.find((n) => n > r.count));
  let busy = $state(false);
  async function invite() {
    haptic.tap(); busy = true;
    try { await shareCard({ kind: 'rf', id: '0' }, `https://t.me/KBTUappBot?startapp=r_${r.code}`, t('ref.text'), () => (busy = false)); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }
</script>

<div class="inv surface">
  <Emoji name="megaphone_3d" size={44} />
  <span class="tx"><b>{t('ref.title')}</b><i>{tn('ref.count', r.count)}{next ? ` · ${t('ref.next', { n: next })}` : ''}</i></span>
  <button class="go" disabled={busy} onclick={invite}>{t('ref.invite')}</button>
</div>

<style>
  .inv { display: flex; align-items: center; gap: 12px; margin-top: 12px; padding: 12px 14px; border-radius: var(--r-l); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 3px; }
  .tx b { font: 680 var(--fs-body)/1.2 var(--font-text); }
  .tx i { font: 500 var(--fs-sub)/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .go { flex: none; height: 36px; padding: 0 16px; border-radius: var(--r-full); background: var(--accent); color: #fff; font: 650 14px/1 var(--font-text); }
  .go:disabled { opacity: 0.6; }
</style>
