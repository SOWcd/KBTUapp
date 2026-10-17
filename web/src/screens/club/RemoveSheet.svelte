<script lang="ts">
  // Removing someone from the club (Team 2.0, SPEC §2b): a Vice+ above them removes at once; a Head's tap goes to the
  // President and Vice as a request with a line why. "Ban" keeps them from joining again (an application, the link)
  // until a Vice+ lifts it.
  import { api, type Id } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, org, user, name, request, ondone }: { overlay: Overlay; org: Id; user: Id; name: string; request: boolean; ondone?: (done: boolean) => void } = $props();

  let ban = $state(false);
  let note = $state('');
  let busy = $state(false);

  async function go() {
    if (busy) return;
    busy = true;
    try {
      const r = await api.removeFromClub(org, user, ban, note.trim());
      haptic.ok(); say(r.done ? t('team.removed', { name }) : t('team.asked'), r.done ? 'waving_hand_3d_default' : 'raising_hands_3d_default');
      ondone?.(r.done);
      close(overlay.id);
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} title={request ? t('team.askRemove') : t('team.remove')}>
  <h2 class="t-h2 hd">{request ? t('rm.askTitle', { name }) : t('rm.title', { name })}</h2>
  <p class="t-foot sub">{request ? t('rm.askText') : t('rm.text')}</p>
  <label class="switch"><span><b>{t('rm.ban')}</b><i class="t-foot">{t('rm.banHint')}</i></span><input type="checkbox" role="switch" bind:checked={ban} /></label>
  {#if request}<textarea bind:value={note} maxlength="140" rows="2" placeholder={t('rm.notePh')}></textarea>{/if}

  {#snippet footer()}
    <Button kind="danger" size="l" full loading={busy} onclick={go}>{request ? t('rm.ask') : t('team.remove')}</Button>
  {/snippet}
</Sheet>

<style>
  .hd { margin: 4px 0 2px; }
  .sub { margin-bottom: 14px; text-wrap: pretty; }
  textarea { width: 100%; margin-top: 12px; padding: 12px 14px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text); resize: none; font: 450 16px/1.4 var(--font-text); }
  textarea::placeholder { color: var(--text-3); }
</style>
