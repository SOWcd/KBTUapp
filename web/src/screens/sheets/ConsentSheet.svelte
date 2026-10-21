<script lang="ts">
  // The privacy policy changed (H2, Oct 22: what a deleted account keeps without the name): every student agrees once
  // more (lib/legal.ts). Closing it asks again at the next open; deleting the account is the other way out.
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import { api } from '../../lib/api';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { CONSENT_VERSION } from '../../lib/legal';

  let { overlay }: { overlay: Overlay } = $props();
  let busy = $state(false);

  async function agree() {
    if (busy) return;
    busy = true;
    try { session.me = await api.consent(CONSENT_VERSION); haptic.ok(); close(overlay.id); }
    catch { haptic.error(); } finally { busy = false; }
  }
</script>

<Sheet {overlay} title={t('consent.title')} icon={ShieldCheck}>
  <div class="wrap">
    <h2 class="t-h2">{t('consent.title')}</h2>
    <p class="t-callout">{t('consent.text')}</p>
    <button class="lnk t-callout" onclick={() => { haptic.tap(); openLink(`${location.origin}/privacy?lang=${i18n.lang}`); }}>{t('login.consentLink')}</button>
  </div>
  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} onclick={agree}>{t('consent.ok')}</Button>
  {/snippet}
</Sheet>

<style>
  .wrap { display: flex; flex-direction: column; gap: 12px; padding-top: 8px; }
  .lnk { align-self: flex-start; color: var(--accent-text); font-weight: 620; }
</style>
