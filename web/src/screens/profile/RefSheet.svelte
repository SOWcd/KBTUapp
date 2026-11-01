<script lang="ts">
  // My invite as a QR (owner, Oct 31) with my photo in the middle (Nov 1). It is r_<link code>, never the lanyard's
  // u_<id>_<badge code>: this QR is made to be posted and the badge code checks me in at the door (review, Nov 1).
  // A newcomer who scans my lanyard in person still counts for me (server refer).
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { say } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, shareCard } from '../../lib/tg';
  import { QR_TONE } from '../../lib/awards';
  import Sheet from '../../ui/Sheet.svelte';
  import Link from '@lucide/svelte/icons/link';
  import Button from '../../ui/Button.svelte';
  import Qr from '../../ui/Qr.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import { session } from '../../lib/state/session.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';

  let { overlay, code }: { overlay: Overlay; code: string } = $props();
  const link = $derived(`https://t.me/KBTUappBot?startapp=r_${code}`);
  const me = $derived(session.me);
  let busy = $state(false);
  async function send() {
    haptic.tap(); busy = true;
    try { await shareCard({ kind: 'rf', id: '0' }, link, t('ref.text'), () => (busy = false)); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={Link} title={t('ref.title')}>
  <h2 class="t-h2 hd">{t('ref.title')}</h2>
  <div class="pass">
    <div class="plate"><span class="code"><Qr text={link} tone={QR_TONE}>{#if me}<span class="face"><Avatar person={me} size={48} tappable={false} /></span>{/if}</Qr></span></div>
    <p class="cap">{t('ref.qr')}</p>
  </div>
  <div class="acts">
    <Button kind="primary" size="l" full loading={busy} onclick={send}>{#snippet icon()}<TelegramMark size={18} />{/snippet}{t('fr.send')}</Button>
  </div>
</Sheet>

<style>
  .hd { margin: 4px 0 14px; }
  /* the badge's material, as on AddFriend */
  .pass { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 18px 18px 16px; border-radius: var(--r-xl); color: rgb(255, 255, 255);
    background: radial-gradient(110% 70% at 0% 0%, rgba(124, 77, 255, 0.6), transparent 55%), linear-gradient(160deg, rgb(42, 79, 214), rgb(18, 26, 61) 70%);
    box-shadow: 0 26px 46px -26px rgba(18, 26, 61, 0.9), inset 0 1px 0 rgba(255, 255, 255, 0.25); }
  .plate { width: 220px; height: 220px; padding: 12px; border-radius: var(--r-l); background: rgb(255, 255, 255); display: flex; align-items: center; justify-content: center;
    box-shadow: 0 16px 30px -18px rgba(0, 0, 0, 0.6); }
  .code { display: block; width: 100%; }
  /* my photo in the code's middle: a white gap, then the brand's ring, like a story */
  .face { display: flex; width: 100%; height: 100%; padding: 2px; border-radius: 50%; background: var(--grad-accent);
    box-shadow: 0 0 0 2px rgb(255, 255, 255), 0 4px 10px -4px rgba(42, 79, 214, 0.6); }
  .face :global(.av) { width: 100% !important; height: 100% !important; border-radius: 50%; box-shadow: 0 0 0 1.5px rgb(255, 255, 255); overflow: hidden; }
  .face :global(img), .face :global(.ini) { width: 100%; height: 100%; border-radius: 50%; object-fit: cover; }
  .face :global(.seal) { display: none; } /* the founder's seal would cover the code */
  .cap { margin-top: 8px; font: 650 var(--fs-body)/1.3 var(--font-text); text-align: center; text-wrap: balance; }
  .acts { margin-top: 12px; }
</style>
