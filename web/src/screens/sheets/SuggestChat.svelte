<script lang="ts">
  // Suggest a chat, inside the app (owner, Oct 21: the bot's chat opened behind the app and nothing showed). Any
  // channel or group: @name, its t.me link, or a closed one's invite link; the server looks it up on t.me and it
  // waits for the admins (logic.suggest_chat). Telegram's own picker of my chats is only in the bot: a link below.
  import Plus from '@lucide/svelte/icons/plus';
  import { api } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { pickInTelegram } from '../../lib/chats';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let link = $state(''), busy = $state(false), note = $state('');

  async function send() {
    if (!link.trim() || busy) return;
    busy = true; note = '';
    try {
      const r = await api.suggestChat(link.trim());
      if (r.status === 'sent') { haptic.ok(); say(t('chats.sentSay', { title: r.title }), 'raising_hands_3d_default'); close(overlay.id); return; }
      haptic.error(); note = t(`chats.why.${r.status}`);
    } catch { haptic.error(); note = t('common.error'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} title={t('chats.suggest')} icon={Plus}>
  <p class="t-callout lead">{t('chats.suggestLead')}</p>
  <label class="field" class:bad={!!note}><span class="t-cap">{t('chats.linkLabel')}</span>
    <input bind:value={link} placeholder="@kbtu_chat · t.me/+…" autocomplete="off" autocapitalize="off" spellcheck="false" enterkeyhint="send"
      oninput={() => (note = '')} onkeydown={(e) => e.key === 'Enter' && send()} /></label>
  {#if note}<p class="t-foot note" role="alert">{note}</p>{/if}
  <div class="go"><Button kind="primary" size="l" full loading={busy} disabled={!link.trim()} onclick={send}>{t('chats.send')}</Button></div>
  <button class="tg" onclick={pickInTelegram}><TelegramMark size={16} />{t('chats.pickInTg')}</button>
</Sheet>

<style>
  .lead { color: var(--text-2); margin: 4px 0 14px; }
  .note { margin: 8px 4px 0; color: var(--danger-text); }
  .go { margin-top: 14px; }
  .tg { display: flex; align-items: center; justify-content: center; gap: 6px; width: 100%; margin-top: 12px; padding: 8px; font: 620 var(--fs-sub)/1.2 var(--font-text); color: var(--accent-text); }
</style>
