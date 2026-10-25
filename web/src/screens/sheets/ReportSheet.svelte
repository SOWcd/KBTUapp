<script lang="ts">
  // One report sheet for everything (owner, Oct 22): a post, a comment, an event, a profile, a photo. A reason, a few
  // words if they like, Send. The moderators see the reasons and the words, never who sent them.
  import Flag from '@lucide/svelte/icons/flag';
  import Check from '@lucide/svelte/icons/check';
  import { api, ApiErr, type Id, type ReportReason } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  type Target = 'comment' | 'post' | 'event' | 'user' | 'photo' | 'ask';
  let { overlay, target, id, about = '', onsent }: { overlay: Overlay; target: Target; id: Id; about?: string; onsent?: () => void } = $props();

  const REASONS: ReportReason[] = ['spam', 'insult', 'danger', 'other'];
  let reason = $state<ReportReason | null>(null), note = $state(''), busy = $state(false);

  async function send() {
    if (!reason || busy) return;
    busy = true;
    try {
      await api.report(target, id, reason, note.trim() || undefined);
      haptic.ok();
      // a photo goes from my album at once; anything else waits for a moderator
      say(t(target === 'photo' ? 'rep.sentHidden' : 'rep.sent'), 'raising_hands_3d_default');
      onsent?.();
      close(overlay.id);
    } catch (x) {
      haptic.error();
      const code = x instanceof ApiErr ? x.code : '';
      say(t(code === 'rate_limited' ? 'rep.tooMany' : code === 'not_found' ? 'rep.gone' : 'common.error'), 'pleading_face_3d');
      if (code === 'not_found') close(overlay.id);
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} title={t('rep.title')} icon={Flag}>
  {#if about}<p class="t-foot about ellipsis">{about}</p>{/if}
  <h2 class="t-h2 hd">{t(`rep.why.${target}`)}</h2>
  <div class="rows surface" role="radiogroup" aria-label={t('rep.title')}>
    {#each REASONS as r (r)}
      <button class="row" role="radio" aria-checked={reason === r} onclick={() => { haptic.select(); reason = r; }}>
        <span class="tx"><b>{t(`rep.${r}`)}</b><i>{t(`rep.hint.${r}`)}</i></span>
        <span class="mark" class:on={reason === r}>{#if reason === r}<Check size={15} strokeWidth={3} />{/if}</span>
      </button>
    {/each}
  </div>
  <textarea bind:value={note} maxlength="500" rows="3" placeholder={t('rep.notePh')} aria-label={t('rep.notePh')}></textarea>
  <p class="t-foot fine">{t('rep.anon')}</p>

  {#snippet footer()}
    <Button kind="danger" size="l" full loading={busy} disabled={!reason} onclick={send}>{t('rep.send')}</Button>
  {/snippet}
</Sheet>

<style>
  .about { margin: 0 2px 6px; color: var(--text-3); }
  .hd { margin: 2px 2px 12px; }
  .rows { display: flex; flex-direction: column; padding: 4px 0; }
  .row { display: flex; align-items: center; gap: 12px; padding: 12px 14px; text-align: left; }
  .row + .row { border-top: 1px solid var(--line); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 650 15px/1.25 var(--font-text); }
  .tx i { font: 500 13px/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .mark { flex: none; width: 24px; height: 24px; border-radius: 50%; display: grid; place-items: center; border: 2px solid var(--line-strong, var(--text-3));
    color: var(--on-accent); transition: background var(--t-fast) var(--ease), border-color var(--t-fast) var(--ease); }
  .mark.on { background: var(--accent); border-color: var(--accent); }
  textarea { width: 100%; margin-top: 12px; padding: 12px 14px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text); resize: none; border: 0;
    font: 450 16px/1.4 var(--font-text); }
  textarea::placeholder { color: var(--text-3); }
  .fine { margin: 8px 4px 0; }
</style>
