<script lang="ts">
  // Removing someone from the club (Team 2.0, SPEC §2b): a Vice+ above them removes at once; a Head's tap goes to the
  // President and Vice as a request with a line why. "Ban" keeps them from joining again (an application, the link)
  // until a Vice+ lifts it.
  import { api, type Id } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import UserMinus from '@lucide/svelte/icons/user-minus';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';

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
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={UserMinus} title={request ? t('team.askRemove') : t('team.remove')}>
  <h2 class="t-h2 hd">{request ? t('rm.askTitle', { name }) : t('rm.title', { name })}</h2>
  <p class="t-foot sub">{request ? t('rm.askText') : t('rm.text')}</p>
  <div class="body">
    <Group footnote={t('rm.banHint')}>
      <Row title={t('rm.ban')} accessory="switch" checked={ban} onchange={(on) => (ban = on)} />
    </Group>
    {#if request}<Field label={t('rm.notePh')} bind:value={note} multiline rows={2} maxlength={140} />{/if}
  </div>

  {#snippet footer()}
    <Button kind="danger" size="l" full loading={busy} onclick={go}>{request ? t('rm.ask') : t('team.remove')}</Button>
  {/snippet}
</Sheet>

<style>
  .hd { margin: var(--s-1) 0 2px; }
  .sub { margin-bottom: var(--s-4); text-wrap: pretty; }
  .body { display: flex; flex-direction: column; gap: var(--s-5); }
</style>
