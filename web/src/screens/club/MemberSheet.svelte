<script lang="ts">
  // One person of a club's Team, their own sheet over it (giving roles reworked): who they are, the roles
  // I may give them as rows (what each can do, how many hold it, theirs checked), their departments, probation as a
  // switch, then handing the club over and removing, each its own row at the bottom. Telegram's Back closes it.
  // The rules are Team's (perms.ts, the server's): this sheet only shows what I may do.
  import { api, ApiErr, staffOrg, type ClubRole, type ClubTag, type Id, type OrgRole, type TeamMember, type TeamSetup } from '../../lib/api';
  import Sheet from '../../ui/Sheet.svelte';
  import UserCog from '@lucide/svelte/icons/user-cog';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { data, studioChanged } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { canGive, canManage, isAbove, may, RANK, rightsLine, roleLabel, roleTitle } from '../../lib/perms';
  import { haptic } from '../../lib/tg';
  import Avatar from '../../ui/Avatar.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';

  // setup: Team's (live); depts: the departments I may toggle on them; onchange: Team refreshes
  let { overlay, org, user, setup, depts, onchange }: { overlay: Overlay; org: Id; user: Id; setup: () => TeamSetup | null;
    depts: (x: TeamMember) => ClubTag[]; onchange: () => void } = $props();

  const m = $derived(session.me?.memberships.find((y) => y.org.id === org) ?? null);
  const list = $derived(data.team[org] ?? []);
  const x = $derived(list.find((y) => y.person.id === user) ?? null);
  const me = $derived(user === session.me?.id);
  const vice = $derived(may(m, 'team'));
  const manage = $derived(!!x && !me && canManage(m, x.role));
  const reports = $derived(!!session.me?.reports);
  // the roles I may give them, highest level first (two at one level read as such); on myself, my own level's only
  const roles = $derived([...(setup()?.roles ?? [])].filter((r) => (me ? r.level === m?.role : canGive(m?.role ?? 'member').includes(r.level)) && r.rights.every((k) => may(m, k)))
    .sort((a, b) => RANK[b.level] - RANK[a.level]));
  const holders = (r: ClubRole | null) => list.filter((y) => (r ? y.roleId === r.id : y.role === 'member' && !y.roleId)).length;
  const holds = (r: ClubRole | null) => !!x && (r ? x.roleId === r.id : x.role === 'member' && !x.roleId);
  let busy = $state(false);
  // gone meanwhile (removed by another leader): the roster is here without them, so the sheet closes
  $effect(() => { if (data.team[org] && !x) close(overlay.id); });
  // the creator's borrowed Studio (Admin): a club is never handed over from there (the server refuses)
  const lent = $derived(staffOrg.id === org);

  /** true when the job went through (a failure says so itself) */
  async function run(job: () => Promise<TeamMember[] | void>, done: string, emoji: string): Promise<boolean> {
    busy = true;
    try {
      const fresh = await job();
      if (fresh) data.team[org] = fresh;
      haptic.ok(); say(done, emoji);
      onchange(); studioChanged();
      return true;
    } catch (e) {
      haptic.error(); say(e instanceof ApiErr && e.message === 'president_elsewhere' ? t('team.presElsewhere') : t('common.error'), 'warning_3d');
      return false;
    } finally { busy = false; }
  }
  // a role, or Member (null): the check moves at once and comes back if the server says no; a Vice-level one (almost every
  // right) asks first, saying what it hands over
  async function give(r: ClubRole | null) {
    const p = x;
    if (!p || busy || holds(r)) return;
    if (r?.level === 'vice' && !(await sheets.ask({ title: t('roles.giveAsk', { role: roleTitle(r), name: p.person.name }), text: rightsLine(r.rights, reports),
      ok: t('roles.give'), cancel: t('common.cancel') }))) return;
    const was = { role: p.role, roleId: p.roleId, title: p.title, titleKk: p.titleKk, titleEn: p.titleEn, titleColor: p.titleColor };
    Object.assign(p, r ? { role: r.level, roleId: r.id, title: r.name, titleKk: r.nameKk, titleEn: r.nameEn, titleColor: r.color }
      : { role: 'member', roleId: null, title: null, titleKk: null, titleEn: null, titleColor: null });
    haptic.select();
    const ok = await run(() => api.updateMember(org, p.person.id, r ? { roleId: r.id } : { role: 'member' as OrgRole, roleId: null }),
      t('team.roleSet', { name: p.person.name, role: r ? roleTitle(r) : t('role.member') }), 'raising_hands_3d_default');
    if (!ok) Object.assign(p, was);
    else if (me) void loadMe(); // my own role: my rights follow it
  }
  const setDept = (p: TeamMember, g: ClubTag, on: boolean) => !busy &&
    run(() => api.updateMember(org, p.person.id, on ? { addDept: g.id } : { dropDept: g.id }), t(on ? 'team.deptSet' : 'team.deptOff', { name: p.person.name, dept: g.name }), 'raising_hands_3d_default');
  // the switch moves at once; a refusal puts it back (off first, so the native switch follows)
  async function probation(p: TeamMember, on: boolean) {
    p.probation = on;
    if (!(await run(() => api.updateMember(org, p.person.id, { probation: on }), t(on ? 'team.probationSet' : 'team.probationPassed', { name: p.person.name }), on ? 'sparkles_3d' : 'party_popper_3d')))
      p.probation = !on;
  }
  async function handOver(p: TeamMember) {
    if (!(await sheets.ask({ title: t('team.transferAsk', { name: p.person.name }), text: t('team.transferText', { name: p.person.name }), ok: t('team.transfer'), cancel: t('common.cancel'), danger: true }))) return;
    if (await run(() => api.transfer(org, p.person.id), t('team.transferred', { name: p.person.name }), 'party_popper_3d')) { void loadMe(); close(overlay.id); }
  }
  // a Vice+ removes at once; a Head's goes to the President and Vice
  const remove = (p: TeamMember) => sheets.removeMember(org, p.person.id, p.person.name, !vice, (gone) => {
    if (gone) { data.team[org] = (data.team[org] ?? []).filter((y) => y.person.id !== p.person.id); close(overlay.id); }
    onchange();
  });
</script>

{#snippet dot(c: string)}<span class="dot" style="--c:{c}"></span>{/snippet}

<Sheet {overlay} tall title={x?.person.name ?? ''} icon={UserCog}>
  {#if x}
    {@const p = x}
    {@const choices = depts(p)}
    <div class="page">
      <!-- who: the row is their profile -->
      <Group>
        <Row title={p.fullName} subtitle={roleLabel(p)} accessory="chevron" onclick={() => sheets.person(p.person.id)}>
          {#snippet lead()}<Avatar person={p.person} size={44} tappable={false} />{/snippet}
        </Row>
      </Group>

      {#if manage || (me && roles.length)}
        <Group caption={t('team.roleLabel')}>
          {#each roles as r (r.id)}
            <Row dense title={roleTitle(r)} subtitle={rightsLine(r.rights, reports)} value={String(holders(r))} whole accessory="check" checked={holds(r)} onclick={() => give(r)}>
              {#snippet lead()}{@render dot(r.color)}{/snippet}
            </Row>
          {/each}
          {#if manage}
            <Row dense title={t('role.member')} subtitle={t('right.door')} value={String(holders(null))} whole accessory="check" checked={holds(null)} onclick={() => give(null)}>
              {#snippet lead()}{@render dot('var(--text-3)')}{/snippet}
            </Row>
            <Row dense tone="add" title={t('ts.newRole')} onclick={() => sheets.teamSetup(org, onchange)} />
          {/if}
        </Group>
      {/if}

      {#if choices.length}
        <Group caption={t('team.dept')}>
          {#each choices as g (g.id)}
            {@const on = !!p.depts?.includes(g.id)}
            <Row dense title={g.name} accessory="check" checked={on} onclick={() => setDept(p, g, !on)}>{#snippet lead()}{@render dot(g.color)}{/snippet}</Row>
          {/each}
        </Group>
      {/if}

      {#if !me && isAbove(m, p.role)}
        <!-- on: a Head+; off: a Vice+ -->
        <Group>
          <Row title={t('team.probation')} accessory="switch" checked={!!p.probation} disabled={busy || (!!p.probation && !vice)} onchange={(on) => probation(p, on)} />
        </Group>
        {#if m?.role === 'president' && !lent}<Group><Row tone="action" title={t('team.transfer')} disabled={busy} onclick={() => handOver(p)} /></Group>{/if}
        <Group><Row tone="destructive" title={manage ? t('roles.remove') : t('team.askRemove')} disabled={busy} onclick={() => remove(p)} /></Group>
      {/if}
    </div>
  {:else}
    <Skeleton n={4} />
  {/if}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-3); }
  .dot { flex: none; display: block; width: 10px; height: 10px; margin: 0 var(--s-1); border-radius: 50%; background: var(--c); }
</style>
