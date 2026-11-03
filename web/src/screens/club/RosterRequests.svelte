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
  import ListChecks from '@lucide/svelte/icons/list-checks';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  // org: one club's (its Studio); none: every claim I confirm (DMP's Studio, the Admin sheet, the bot's link)
  let { overlay, ondone, org }: { overlay: Overlay; ondone?: () => void; org?: number } = $props();
  let list = $state<RosterRequest[] | null>(null);
  $effect(() => { api.rosterRequests(org).then((l) => (list = l)).catch(() => (list = [])); });
  async function decide(r: RosterRequest, ok: boolean) {
    try {
      await api.rosterDecide(r.id, ok); haptic.ok(); say(t(ok ? 'ro.confirmed' : 'ro.declined'), ok ? 'party_popper_3d' : 'waving_hand_3d_default');
      list = (list ?? []).filter((x) => x.id !== r.id); ondone?.();
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
</script>

<Sheet {overlay} icon={ListChecks} title={t('ro.reqTitle')}>
  <p class="t-foot sub">{t('ro.reqText')}</p>
  <div class="list">
    {#each list ?? [] as r (r.id)}
      <Group>
        <Row dense title={r.name} subtitle={`${t('ro.listed', { name: r.sheetName ?? '—' })} · ${nameOf(r.org)} · ${r.title || roleName(r.role, null)}${r.dept ? ' · ' + r.dept : ''}`}>
          {#snippet lead()}<Avatar person={r.person} size={36} />{/snippet}
        </Row>
        <!-- engine: Row needs content under it (a request's actions) -->
        <div class="acts btns">
          <Button kind="secondary" size="m" full onclick={() => decide(r, false)}>{t('ro.decline')}</Button>
          <Button kind="primary" size="m" full onclick={() => decide(r, true)}>{t('ro.confirm')}</Button>
        </div>
      </Group>
    {/each}
  </div>
</Sheet>

<style>
  .sub { margin-bottom: var(--s-4); }
  .list { display: flex; flex-direction: column; gap: var(--s-3); }
  .acts { display: flex; gap: var(--s-2); padding: 0 var(--s-4) var(--s-4); }
</style>
