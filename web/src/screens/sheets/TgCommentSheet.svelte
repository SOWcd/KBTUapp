<script lang="ts">
  // My own comment the bot deleted in the forum channel's Telegram group (server logic/tgcomments.py), shown to the
  // Telegram account that wrote it and nobody else: a stranger's comment after he signed in, or one removed after
  // reports while the bot couldn't write to me. Its words, Copy, and back to the thread (a student only: for anyone
  // else that button would walk him into the second-comment ban). Telegram's "allow messages" is asked on a tap here,
  // never in front of the text (review 2): a "no" changes nothing.
  import { copyText } from '../../ui/copy';
  import MessageSquareText from '@lucide/svelte/icons/message-square-text';
  import ShieldAlert from '@lucide/svelte/icons/shield-alert';
  import type { TgComment } from '../../lib/api';
  import { close, type Overlay } from '../../lib/state/ui.svelte';
  import { askDm } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, c }: { overlay: Overlay; c: TgComment } = $props();

  async function copy() {
    await copyText(c.body, t('tgc.copied'));
    if (c.student) void askDm(undefined, true);
  }
  function back() {
    haptic.tap();
    if (c.link) openLink(c.link);
    close(overlay.id);
    void askDm(undefined, true);
  }
</script>

<!-- removed after reports: under review, then the moderator's verdict (the rule it broke, or a mistake: post it again) -->
<Sheet {overlay} title={c.verdict === 'restored' ? t('tgc.restoredTitle') : c.removed ? t('tgc.removedTitle') : t('tgc.title')}
  icon={c.removed && c.verdict !== 'restored' ? ShieldAlert : MessageSquareText}>
  <p class="fs-body dim hint">{c.verdict === 'confirmed' ? t('tgc.confirmedText', { rule: t(`tgc.rule.${c.rule ?? 'other'}`) })
    : c.verdict === 'restored' ? t('tgc.restoredText') : c.removed ? t('tgc.removedText') : c.student ? t('tgc.text') : t('tgc.guest')}</p>
  <blockquote class="body surface selectable fs-body">{c.body}</blockquote>
  {#snippet footer()}
    <div class="acts">
      {#if c.link}
        <Button kind="gray" size="l" full onclick={copy}>{t('tgc.copy')}</Button>
        <Button kind="filled" size="l" full onclick={back}>{t('tgc.back')}</Button>
      {:else}
        <Button kind="filled" size="l" full onclick={copy}>{t('tgc.copy')}</Button>
      {/if}
    </div>
  {/snippet}
</Sheet>

<style>
  .hint { margin: 2px var(--s-1) var(--s-3); }
  .body { margin: 0; padding: var(--s-3) var(--s-4); border-radius: var(--r-group); white-space: pre-wrap; overflow-wrap: anywhere; max-height: 40vh; overflow-y: auto; }
  .acts { display: flex; flex-direction: column; gap: var(--s-2); }
</style>
