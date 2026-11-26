<script lang="ts">
  // "What's wrong?": anyone tells the creator what they dislike, two ways. Anonymously here (the server keeps the
  // words and the day, never who: logic/helpus.py), or signed in his Telegram with a one-line draft (lib/feedback).
  import MessageCircleWarning from '@lucide/svelte/icons/message-circle-warning';
  import { api, ApiErr } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { count } from '../../lib/stats';
  import { writeSupport } from '../../lib/feedback';
  import Sheet from '../../ui/Sheet.svelte';
  import Field from '../../ui/Field.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let text = $state('');
  let busy = $state(false);
  async function send() {
    if (busy || text.trim().length < 2) return;
    busy = true;
    try {
      await api.helpAnon(text.trim());
      haptic.ok(); count('do.anon'); say(t('fb.sent'), 'blue_heart_3d'); close(overlay.id);
    } catch (e) {
      haptic.error(); say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'fb.many' : 'common.error'), 'warning_3d');
    }
    busy = false;
  }
</script>

<Sheet {overlay} icon={MessageCircleWarning} title={t('fb.title')}>
  <div class="fb">
    <p class="t-body dim">{t('fb.text')}</p>
    <Field label={t('fb.label')} placeholder={t('fb.ph')} bind:value={text} multiline rows={4} maxlength={1000} />
    <p class="t-foot dim">{t('fb.note')}</p>
  </div>

  {#snippet footer()}
    <div class="acts">
      <Button kind="primary" size="l" full disabled={text.trim().length < 2} loading={busy} onclick={send}>{t('fb.send')}</Button>
      <Button kind="plain" size="m" full onclick={() => { haptic.tap(); writeSupport(t('fb.draft')); }}>{t('fb.tg')}</Button>
    </div>
  {/snippet}
</Sheet>

<style>
  .fb { display: flex; flex-direction: column; gap: var(--s-4); padding: var(--s-2) 0; }
  .dim { margin: 0; color: var(--text-2); text-wrap: pretty; }
  .acts { display: flex; flex-direction: column; gap: var(--s-1); }
</style>
