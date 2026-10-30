<script lang="ts">
  // Students who say they're the one in DMP's list under another name (PLAN 95): the club's President confirms (DMP for
  // a club without one). The sheet's name beside the KBTU account's: the President knows their people. Confirmed: joined
  // with the row's data; not them: the row stays for the right person.
  import { api, type RosterRequest } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { roleName } from '../../lib/perms';
  import { nameOf } from '../../lib/short';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, ondone }: { overlay: Overlay; ondone?: () => void } = $props();
  let list = $state<RosterRequest[] | null>(null);
  $effect(() => { api.rosterRequests().then((l) => (list = l)).catch(() => (list = [])); });
  async function decide(r: RosterRequest, ok: boolean) {
    try {
      await api.rosterDecide(r.id, ok); haptic.ok(); say(t(ok ? 'ro.confirmed' : 'ro.declined'), ok ? 'party_popper_3d' : 'waving_hand_3d_default');
      list = (list ?? []).filter((x) => x.id !== r.id); ondone?.();
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

<Sheet {overlay} title={t('ro.reqTitle')}>
  <h2 class="t-h2 hd">{t('ro.reqTitle')}</h2>
  <p class="t-foot sub">{t('ro.reqText')}</p>
  {#each list ?? [] as r (r.id)}
    <div class="rq surface">
      <div class="who"><Avatar person={r.person} size={44} />
        <span class="tx"><b class="ellipsis">{r.name}</b><i class="t-foot ellipsis">{t('ro.listed', { name: r.sheetName ?? '—' })}</i>
          <i class="t-foot ellipsis">{nameOf(r.org)} · {r.title || roleName(r.role, null)}{r.dept ? ' · ' + r.dept : ''}</i></span></div>
      <div class="acts btns">
        <Button kind="neutral" size="m" full onclick={() => decide(r, false)}>{t('ro.decline')}</Button>
        <Button kind="primary" size="m" full onclick={() => decide(r, true)}>{t('ro.confirm')}</Button>
      </div>
    </div>
  {/each}
</Sheet>

<style>
  .hd { margin: 4px 0 2px; }
  .sub { margin-bottom: 14px; }
  .rq { display: flex; flex-direction: column; gap: 12px; padding: 14px; border-radius: var(--r-l); margin-bottom: 10px; }
  .who { display: flex; align-items: center; gap: 12px; }
  .tx { min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 650 15.5px/1.25 var(--font-text); }
  .tx i { font-style: normal; }
  .acts { display: flex; gap: 8px; }
</style>
