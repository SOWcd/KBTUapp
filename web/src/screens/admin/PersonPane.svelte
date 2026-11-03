<script lang="ts">
  // Admin → a person (from the search or the team; review Nov 3): their face (a tap opens the profile), the role from a
  // small menu at its row (the owner gives admin, an admin gives moderator), their awards as chips, the ban last and
  // alone in red with the reason they will read. Nobody touches the owner, himself or (unless the owner) another admin.
  //   row  the person as the list had them;  onchange  the team as it is after a change (the Team page's list)
  import { api, type Staff, type StaffRow, type PlatformRole } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { fold } from '../../ui/fold';
  import Pane from '../../ui/Pane.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Field from '../../ui/Field.svelte';
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import PersonAwards from './PersonAwards.svelte';

  let { overlay, row, onchange }: { overlay: Overlay; row: StaffRow; onchange?: (s: Staff) => void } = $props();
  // svelte-ignore state_referenced_locally
  let p = $state(row); // as it is now, after my changes here
  const iOwn = $derived(!!session.me?.founder);
  const touchable = $derived(!p.owner && p.person.id !== session.me?.id && (p.role !== 'admin' || iOwn));
  const banned = $derived(!!p.banned || !!p.banReason);
  const roles = $derived<PlatformRole[]>(iOwn ? ['user', 'moderator', 'admin'] : ['user', 'moderator']);
  let banning = $state(false), why = $state(''), busy = $state(false);

  async function act(go: () => Promise<Staff>, done: string, emoji: string) {
    busy = true;
    try {
      const s = await go();
      const now = s.team.find((x) => x.person.id === p.person.id), out = s.banned.find((x) => x.person.id === p.person.id);
      p = out ? { ...out, banned: true } : now ? { ...now, banned: false } : { ...p, role: 'user', banned: false, banReason: null };
      banning = false; why = ''; haptic.ok(); say(done, emoji);
      onchange?.(s);
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { busy = false; }
  }
  const setRole = (r: PlatformRole) => p.role !== r && act(() => api.setStaff(p.person.id, r), t('staff.roleSet'), 'sparkles_3d');
</script>

<Pane {overlay} title={p.person.name}>
  <div class="page stagger">
    <div class="hero">
      <Avatar person={p.person} size={64} />
      <span class="who">
        {#if p.username}<span class="nick">@{p.username}</span>{/if}
        {#if p.owner}<Tag tone="accent">{t('staff.owner')}</Tag>{:else if banned}<Tag tone="danger">{t('staff.banned')}</Tag>{/if}
      </span>
    </div>

    <Group footnote={touchable ? undefined : p.owner ? t('staff.ownerNote') : p.person.id === session.me?.id ? t('staff.selfNote') : t('staff.adminNote')}>
      <Row title={t('staff.role')} value={t(`staff.role.${p.role}`)} disabled={!touchable || banned || busy}
        menu={touchable && !banned ? roles.map((r) => ({ label: t(`staff.role.${r}`), checked: p.role === r, onselect: () => setRole(r) })) : undefined} />
    </Group>

    <Group caption={t('adm.awards')}>
      <div class="aw"><PersonAwards person={p.person} /></div>
    </Group>

    {#if touchable}
      <div class="ban">
        <Group footnote={banned && p.banReason ? p.banReason : undefined}>
          {#if banned}
            <Row tone="action" title={t('staff.unban')} disabled={busy}
              onclick={() => act(() => api.ban(p.person.id, false), t('staff.unbannedToast'), 'raising_hands_3d_default')} />
          {:else}
            <Row tone="destructive" title={t('staff.ban') + '…'} accessory="disclosure" open={banning} onclick={() => { haptic.select(); banning = !banning; why = ''; }} />
          {/if}
        </Group>
        {#if banning && !banned}
          <div class="form" transition:fold>
            <Field label={t('staff.reasonPh')} bind:value={why} multiline rows={2} maxlength={300} />
            <Button kind="filled" destructive full loading={busy} disabled={why.trim().length < 3}
              onclick={() => act(() => api.ban(p.person.id, true, why.trim()), t('staff.bannedToast'), 'locked_3d')}>{t('staff.ban')}</Button>
          </div>
        {/if}
      </div>
    {/if}
  </div>
</Pane>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-6); }
  .hero { display: flex; align-items: center; gap: var(--s-4); padding: 0 var(--s-1); }
  .who { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; min-width: 0; }
  .nick { font: 450 var(--fs-row)/1.2 var(--font-text); color: var(--text-3); overflow-wrap: anywhere; }
  .aw { padding: 14px var(--s-4); }
  .ban { display: flex; flex-direction: column; gap: var(--s-4); }
  .form { display: flex; flex-direction: column; gap: var(--s-3); }
</style>
