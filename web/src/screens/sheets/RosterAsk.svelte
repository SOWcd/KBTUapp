<script lang="ts">
  // A row of DMP's list under my Telegram username but another name (PLAN 95): the club and position only (the sheet's
  // name, phone and city may be someone else's). "Yes, it's me" (a typo, a new surname) asks the club's President to
  // confirm; something else wrong goes to support. Closed: asked again next time. No student removes a row.
  import type { Id, RosterSpot } from '../../lib/api';
  import { api } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { roleName } from '../../lib/perms';
  import { nameOf } from '../../lib/short';
  import { haptic } from '../../lib/tg';
  import { writeSupport } from '../../lib/feedback';
  import Sheet from '../../ui/Sheet.svelte';
  import UserRoundCheck from '@lucide/svelte/icons/user-round-check';
  import Button from '../../ui/Button.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';

  let { overlay, row }: { overlay: Overlay; row: RosterSpot & { id: Id; dept: string | null } } = $props();
  let busy = $state(false);
  async function yes() {
    busy = true;
    try { await api.rosterClaim(row.id); haptic.ok(); say(t('ro.asked'), 'raising_hands_3d_default'); close(overlay.id); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={UserRoundCheck} title={t('ro.askTitle')}>
  <div class="top">
    <OrgLogo org={row.org} size={64} />
    <h2 class="t-h2">{t('ro.askTitle')}</h2>
    <p class="t-foot">{nameOf(row.org)} · {row.title || roleName(row.role, null)}{row.dept ? ' · ' + row.dept : ''}</p>
  </div>
  <p class="t-callout text">{t('ro.askText', { org: nameOf(row.org) })}</p>
  <div class="sup"><Button kind="plain" size="s" onclick={() => writeSupport(t('ro.draft', { org: row.org.name }))}>{t('ro.support')}</Button></div>
  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} onclick={yes}>{t('ro.yes')}</Button>
  {/snippet}
</Sheet>

<style>
  .top { display: flex; flex-direction: column; align-items: center; text-align: center; gap: 6px; padding: 6px 0 var(--s-1); }
  .top h2 { margin-top: 6px; }
  .text { margin-top: var(--s-3); color: var(--text-2); text-align: center; }
  .sup { display: flex; justify-content: center; margin-top: var(--s-3); --plain-ink: var(--text-3); }
</style>
