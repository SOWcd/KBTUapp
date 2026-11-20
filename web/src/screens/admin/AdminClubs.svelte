<script lang="ts">
  // Admin → Clubs and schools: every organization by name, one line each (a clear order, no
  // pile of pills on the card). A to Z, hidden ones last; a row opens the organization's page (AdminOrg). Finding
  // one is the Admin search's job, so no second search here. A new club on top (schools come from KBTU's site);
  // DMP's registry is the third tab.
  import { staffOnly } from '../../lib/state/staffGate.svelte';
  import { api, ApiErr, type AdminOrg } from '../../lib/api';
  import { adminOrgs, loadAdminOrgs, orgLine, putOrg } from '../../lib/state/adminOrgs.svelte';
  import { staffStill } from '../../lib/state/staffAccess.svelte';
  import { loadAfisha } from '../../lib/state/data.svelte';
  import { open, say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { PICK_EMOJI } from '../../lib/emoji';
  import { fold } from '../../ui/fold';
  import { TAB_ICON } from '../../ui/icons';
  import Sheet from '../../ui/Sheet.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import Button from '../../ui/Button.svelte';
  import EmojiPick from '../../ui/EmojiPick.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import OfficialMark from '../../ui/OfficialMark.svelte';
  import OrgLogo, { initials } from '../../ui/OrgLogo.svelte';
  import Registry from '../dmp/Registry.svelte';
  import AdminOrgPane from './AdminOrg.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  staffOnly(() => overlay);
  void loadAdminOrgs(); // again on every opening (another admin's change, a club just approved); the last list shows meanwhile

  // clubs and schools on their own tabs (the admin comes for clubs; the schools are seeded and rarely touched)
  let kind = $state<'club' | 'school' | 'registry'>('club');
  const orgs = $derived(adminOrgs.list);
  const schools = $derived((orgs ?? []).filter((o) => o.kind === 'school').length);
  const shown = $derived((orgs ?? []).filter((o) => (o.kind === 'school') === (kind === 'school'))
    .sort((a, b) => +a.hidden - +b.hidden || a.name.localeCompare(b.name)));
  const page = (o: AdminOrg) => { haptic.tap(); open(AdminOrgPane, { org: o }); };

  // ---- a new club (schools come from KBTU's site, never by hand) ----
  let adding = $state(false), busy = $state(false);
  let nc = $state({ name: '', emoji: PICK_EMOJI[1], official: false });
  async function create(ev: Event) {
    ev.preventDefault();
    busy = true;
    const still = staffStill();
    try {
      const o = await api.adminCreateOrg({ name: nc.name.trim(), short: initials(nc.name), emoji: nc.emoji, official: nc.official });
      if (!still()) return;
      putOrg(o);
      adding = false; nc = { name: '', emoji: PICK_EMOJI[1], official: false };
      haptic.ok(); say(t('adm.created'), 'party_popper_3d');
      void loadAfisha(); // the club shows in Clubs at once
      open(AdminOrgPane, { org: o }); // its President next
    } catch (e) {
      haptic.error();
      say(e instanceof ApiErr && e.message === 'emoji' ? t('nc.emoji') : e instanceof ApiErr && e.code === 'bad_input' ? t('adm.bad') : t('common.error'), 'warning_3d');
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} icon={TAB_ICON.club} full title={t('adm.clubs')}>
  <div class="page">
    <Segmented bind:value={kind} label={t('adm.clubs')} onchange={() => (adding = false)} items={[
      { value: 'club', label: t('clubs.clubs') + (orgs ? ` · ${orgs.length - schools}` : '') },
      ...(schools ? [{ value: 'school' as const, label: `${t('clubs.schools')} · ${schools}` }] : []),
      { value: 'registry', label: t('adm.registry') }]} />
    {#if kind === 'registry'}
      <Registry inSheet />
    {:else if !orgs}
      {#if adminOrgs.failed}<EmptyState inline text={t('common.error')} onretry={loadAdminOrgs} />{:else}<Skeleton n={6} />{/if}
    {:else}
      {#if kind === 'club'}
        <Group><Row tone="add" title={t('adm.newClub')} onclick={() => { haptic.select(); adding = !adding; }} /></Group>
        {#if adding}
          <form class="new" onsubmit={create} transition:fold>
            <Field label={t('adm.name')} bind:value={nc.name} maxlength={60} enterkeyhint="done" />
            <Group><Row title={t('reg.official')} accessory="switch" checked={nc.official} onchange={(on) => (nc.official = on)} /></Group>
            <EmojiPick bind:value={nc.emoji} size={26} />
            <Button kind="filled" full type="submit" loading={busy} disabled={nc.name.trim().length < 2}>{t('adm.create')}</Button>
          </form>
        {/if}
      {/if}
      {#if shown.length}
        <Group>
          {#each shown as o (o.id)}
            <Row dense title={o.name} subtitle={(o.hidden ? t('adm.hiddenTag') + ' · ' : '') + orgLine(o)} accessory="chevron" onclick={() => page(o)}>
              {#snippet lead()}<span class={{ dim: o.hidden }}><OrgLogo org={o} size={36} /></span>{/snippet}
              {#snippet detail()}{#if o.official && o.kind === 'club'}<span class="ok"><OfficialMark size={16} /></span>{/if}{/snippet}
            </Row>
          {/each}
        </Group>
      {:else}<EmptyState inline text={t('adm.noClubs')} />{/if}
    {/if}
  </div>
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-5); }
  .new { display: flex; flex-direction: column; gap: var(--s-3); margin-top: calc(-1 * var(--s-2)); }
  .ok { display: inline-flex; color: var(--accent-text); }
  .dim { display: inline-flex; opacity: 0.45; }
</style>
