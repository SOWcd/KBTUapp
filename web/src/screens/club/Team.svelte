<script lang="ts">
  // My club → Team, a sheet from its row (SPEC §2, §2b): the club's roster for its own team, highest role first (full names inside the team, §3),
  // each with the club's own role name and its tags. A tap opens the person's card; for someone below me it opens the
  // actions instead (the card is the first of them): Vice+ give a role (a level or one of the club's own) and remove;
  // Head+ put on probation and ask the President and Vice to remove someone. On top for Vice+: the
  // removal requests. Tags (and probation) filter the list; "Roles and tags" makes the club's own. The club is the one
  // picked in My club (ui.club). Vice+ also get the club's invite link (§4.5): the link icon opens a small choice, the
  // team's link for everyone (7 days, one per club, shared again until turned off) or a one-time one. Anyone but the
  // President can leave.
  import { api, ApiErr, type ClubRole, type OrgRole, type RemovalRequest, type TeamMember, type TeamSetup } from '../../lib/api';
  import Sheet from '../../ui/Sheet.svelte';
  import Users from '@lucide/svelte/icons/users';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { say, ui, close } from '../../lib/state/ui.svelte';
  import { data, loadTeam, studioChanged } from '../../lib/state/data.svelte';
  import { untrack } from 'svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { byRank, canGive, canManage, isAbove, may, RANK, inLang, roleName, ROLE_NAME, titleOf, withNick } from '../../lib/perms';
  import { haptic } from '../../lib/tg';
  import { shareInvite } from '../../lib/invite';
  import { fold } from '../../ui/fold';
  import { dayMonth } from '../../lib/time';
  import LinkIcon from '@lucide/svelte/icons/link';
  import Tags from '@lucide/svelte/icons/tags';
  import Crown from '@lucide/svelte/icons/crown';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import Plus from '@lucide/svelte/icons/plus';
  import FileDown from '@lucide/svelte/icons/file-down';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Chip from '../../ui/Chip.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import { menu } from '../../ui/menu';

  // at: that person's actions open (Studio → Chats → Roles and admins), once
  let { overlay, at }: { overlay: Overlay; at?: number } = $props();
  let first = untrack(() => at);
  const mine = $derived([...(session.me?.memberships ?? [])].sort(byRank));
  const m = $derived(mine.find((x) => x.org.id === ui.club) ?? mine[0]);
  // kept per club (and for the next launch), so Team opens with the people already there; a visit refreshes it quietly
  const list = $derived(m ? (data.team[m.org.id] ?? null) : null);
  let setup = $state<TeamSetup | null>(null);
  const loadSetup = (org: number) => api.teamSetup(org).then((x) => { if (m?.org.id === org) setup = x; }).catch(() => {});
  const orgId = $derived(m?.org.id); // the same club with a fresh membership (a return refresh) keeps the filter and the open member
  $effect(() => { const org = orgId; untrack(() => { open = first ?? null; first = undefined; filter = null; setup = null; if (org) { void loadTeam(org); void loadSetup(org); } }); });
  let open = $state<number | null>(null); // whose actions are out
  let linkOpen = $state(false); // the link icon's choice
  async function shareLink(many: boolean) {
    if (!m) return;
    const org = m.org.id;
    // the open link shows at once, its day on the row and "turn off" under it: set when it is made, not after the
    // picker (Android's may never answer), and the choice stays open to show it
    const ok = await shareInvite(m.org, undefined, many, (until) => { if (setup && m?.org.id === org) setup.teamLink = { expiresAt: until }; });
    if (ok && !many) linkOpen = false;
    if (many) void loadSetup(org);
  }
  async function linkOff() {
    if (!m || !(await sheets.ask({ title: t('team.linkOffAsk'), text: t('team.linkOffText'), ok: t('team.linkOff'), cancel: t('common.cancel'), danger: true }))) return;
    if (await run(() => api.teamLinkOff(m.org.id), t('team.linkOffDone'), 'raising_hands_3d_default')) linkOpen = false;
  }
  let busy = $state(false);
  let filter = $state<number | 'probation' | null>(null); // a tag's id, or those on probation
  const me = $derived(session.me?.id);
  const vice = $derived(may(m, 'team'));  // roles, removing at once, probation off
  const tagOf = $derived(new Map((setup?.tags ?? []).map((g) => [g.id, g])));
  const onProbation = $derived((list ?? []).filter((x) => x.probation).length);
  const shown = $derived((list ?? []).filter((x) => filter == null || (filter === 'probation' ? x.probation : x.tags?.includes(filter))));
  // one list, highest role first (the server's order); departments are their own chips (owner, Oct 20: grouped, the
  // President sat last under "no department" and the heads were scattered)
  const depts = $derived((setup?.tags ?? []).filter((g) => g.department));
  const otherTags = $derived((setup?.tags ?? []).filter((g) => !g.department));
  const dept = $derived(typeof filter === 'number' ? depts.find((g) => g.id === filter) ?? null : null);
  // a person may be in several departments, each a toggle: a Vice+ any of them on anyone; a Head those below them, only
  // the departments the Head was given by hand (the server's myDepts: one the chat sync gave adds no powers)
  const myDepts = $derived(setup?.myDepts ?? []);
  const deptChoices = (x: TeamMember) => {
    if (!depts.length || !may(m, 'people')) return [];
    if (RANK[m?.role ?? 'member'] >= RANK.vice) return depts;
    if (x.person.id === me || !isAbove(m, x.role)) return [];
    return depts.filter((g) => myDepts.includes(g.id));
  };
  const setDept = (x: TeamMember, d: number, on: boolean) =>
    run(() => api.updateMember(org(), x.person.id, on ? { addDept: d } : { dropDept: d }),
      t(on ? 'team.deptSet' : 'team.deptOff', { name: x.person.name, dept: tagOf.get(d)?.name ?? '' }), 'raising_hands_3d_default');

  // a role of my own level on myself, a name only; tags are picked in the tag (TeamSetupSheet)
  const ownLevel = $derived((setup?.roles ?? []).filter((r) => r.level === m?.role && r.rights.every((k) => may(m, k))));
  // the avatar is the profile; the row opens what I can do with them, or the profile when there's nothing (owner, Oct 14:
  // no "Profile" button, no tags on the fly here: who has a tag is picked in the tag, in "Roles and tags")
  function tap(x: TeamMember) {
    if (!hasActs(x)) { sheets.person(x.person.id); return; }
    open = open === x.person.id ? null : x.person.id;
  }
  // what can be done with them: the row unfolds the actions, else it opens the profile
  const hasActs = (x: TeamMember) => (x.person.id === me ? ownLevel.length > 0 : isAbove(m, x.role)) || deptChoices(x).length > 0;
  // the line under the name: the nick or @username, then the marks in words (statuses first, then tags)
  const sub = (x: TeamMember) => [[x.person.nick, x.username && '@' + x.username].filter(Boolean).join(' · ') || x.person.name,
    x.probation && t('team.probation'), x.quiet && t('reg.quiet'), x.brought && t('team.brought', { n: x.brought }),
    ...(x.tags ?? []).map((id) => tagOf.get(id)?.name)].filter(Boolean).join(' · ');
  // the tags' chip: a menu of every tag with its count
  function tagMenu(e: MouseEvent) {
    const all = list ?? [];
    menu(e.currentTarget as Element, [{ label: `${t('common.all')} · ${all.length}`, checked: filter == null || filter === 'probation' || !!dept, onselect: () => (filter = null) },
      ...otherTags.map((g) => ({ label: `${g.name} · ${all.filter((y) => y.tags?.includes(g.id)).length}`, checked: filter === g.id, onselect: () => (filter = g.id) }))]);
  }
  function refresh() {
    if (!m) return;
    void loadTeam(m.org.id); void loadSetup(m.org.id);
    studioChanged();
  }

  /** true when the job went through (a failure says so itself) */
  async function run(job: () => Promise<TeamMember[] | void>, done: string, emoji: string): Promise<boolean> {
    busy = true;
    try {
      const fresh = await job();
      if (fresh && m) data.team[m.org.id] = fresh;
      if (done) { haptic.ok(); say(done, emoji); } else haptic.select();
      void loadSetup(m!.org.id);
      studioChanged();
      return true;
    } catch (e) {
      haptic.error(); say(e instanceof ApiErr && e.message === 'president' ? t('team.presLeave') : e instanceof ApiErr && e.message === 'president_elsewhere' ? t('team.presElsewhere') : t('common.error'), 'warning_3d');
      return false;
    } finally { busy = false; }
  }
  const org = () => m!.org.id;
  const give = (x: TeamMember, role: OrgRole) =>
    run(() => api.updateMember(org(), x.person.id, { role, roleId: null }), t('team.roleSet', { name: x.person.name, role: ROLE_NAME[role] }), 'raising_hands_3d_default');
  const giveOwn = (x: TeamMember, r: ClubRole) =>
    run(() => api.updateMember(org(), x.person.id, { roleId: r.id }), t('team.roleSet', { name: x.person.name, role: inLang(r.name, r.nameKk, r.nameEn) }), 'raising_hands_3d_default');
  const probation = (x: TeamMember, on: boolean) =>
    run(() => api.updateMember(org(), x.person.id, { probation: on }), on ? t('team.probationSet', { name: x.person.name }) : t('team.probationPassed', { name: x.person.name }),
      on ? 'sparkles_3d' : 'party_popper_3d');
  // a Vice+ removes at once; a Head's goes to the President and Vice (§2b)
  const removeOrAsk = (x: TeamMember) => sheets.removeMember(org(), x.person.id, x.person.name, !vice, (gone) => {
    open = null;
    if (gone) data.team[org()] = (data.team[org()] ?? []).filter((y) => y.person.id !== x.person.id);
    refresh();
  });
  async function decide(q: RemovalRequest, approve: boolean) {
    if (approve && !(await sheets.ask({ title: t('team.removeAsk', { name: q.person.name }), text: q.ban ? t('rm.banHint') : t('team.removeText'), ok: t('team.remove'),
      cancel: t('common.cancel'), danger: true }))) return;
    await run(() => api.decideRemoval(q.id, approve), approve ? t('team.removed', { name: q.person.name }) : t('team.kept', { name: q.person.name }),
      approve ? 'waving_hand_3d_default' : 'raising_hands_3d_default');
    refresh();
  }
  async function handOver(x: TeamMember) {
    if (!(await sheets.ask({ title: t('team.transferAsk', { name: x.person.name }), text: t('team.transferText', { name: x.person.name }), ok: t('team.transfer'), cancel: t('common.cancel'), danger: true }))) return;
    await run(() => api.transfer(m!.org.id, x.person.id), t('team.transferred', { name: x.person.name }), 'party_popper_3d');
    void loadMe(); // my role changed
  }
  async function leave() {
    if (!m) return;
    if (m.role === 'president') { haptic.error(); say(t('team.presLeave'), 'pleading_face_3d'); return; }
    if (!(await sheets.ask({ title: t('team.leaveAsk', { club: m.org.name }), text: t('team.leaveText'), ok: t('team.leave'), cancel: t('common.cancel'), danger: true }))) return;
    if (!(await run(() => api.removeMember(m.org.id, me!), t('team.left'), 'waving_hand_3d_default'))) return;
    close(overlay.id); // not my team any more: the sheet would show the next club's
    void loadMe();
  }
  // the roster as a file, from the bot (Medina, Nov 5): Vice+, like the attendees' list
  let sending = $state(false);
  async function exportRoster() {
    if (!m || sending) return;
    sending = true;
    try { await api.exportMembers(m.org.id); haptic.ok(); say(t('att.sent'), 'party_popper_3d'); }
    catch (e) { haptic.error(); say(e instanceof ApiErr && e.message === 'no_dm' ? t('att.noDm') : t('common.error'), 'warning_3d'); }
    finally { sending = false; }
  }
</script>

{#snippet dot(c: string)}<span class="dot" style="--c:{c}"></span>{/snippet}

{#snippet deptRow(x: TeamMember)}
  {@const choices = deptChoices(x)}
  {#if choices.length}
    <span class="t-cap">{t('team.dept')}</span>
    <div class="ar">
      {#each choices as g (g.id)}
        {@const on = !!x.depts?.includes(g.id)}
        <Chip selected={on} onclick={() => !busy && setDept(x, g.id, !on)}>{@render dot(g.color)}{g.name}</Chip>
      {/each}
    </div>
  {/if}
{/snippet}

<Sheet {overlay} tall title={t('page.team')} icon={Users}>
<div class="team">
  {#if m}
    <header class="hd">
      <span class="org"><OrgLogo org={m.org} size={30} /><b class="nm ellipsis">{m.org.name}</b></span>
      <!-- the list first; invite and roles are icons up here (the invite row was too big, the hint noise) -->
      <span class="icons">
        {#if vice}<IconButton icon={FileDown} size="s" label={t('team.export')} loading={sending} onclick={exportRoster} />{/if}
        {#if vice}<IconButton icon={LinkIcon} size="s" label={t('team.inviteTitle')} on={linkOpen} onclick={() => { haptic.select(); linkOpen = !linkOpen; }} />{/if}
        {#if may(m, 'people') || vice || setup?.roles.length || setup?.tags.length}
          <IconButton icon={Tags} size="s" label={t('team.setup')} onclick={() => sheets.teamSetup(m.org.id, refresh)} />
        {/if}
      </span>
    </header>
    {#if vice && linkOpen}
      <div class="linkpick" transition:fold>
        <Group footnote={t('team.linkHint')}>
          <Row tone="action" title={setup?.teamLink ? t('team.linkAllUntil', { date: dayMonth(setup.teamLink.expiresAt) }) : t('team.linkAll')} onclick={() => shareLink(true)} />
          <Row tone="action" title={t('team.linkOnce')} onclick={() => shareLink(false)} />
        </Group>
        {#if setup?.teamLink}<Group><Row tone="destructive" title={t('team.linkOff')} disabled={busy} onclick={linkOff} /></Group>{/if}
      </div>
    {/if}

    {#if setup?.removals?.length}
      <!-- §2b: a Head's request; the President or a Vice above them decides -->
      <Group caption={t('team.removals')}>
        {#each setup.removals as q (q.id)}
          <Row dense title={withNick(q.fullName, q.person)}
            subtitle={[q.by && t('team.removalBy', { name: q.by.name }), q.ban && t('team.withBan'), q.note && '«' + q.note + '»', !q.canDecide && t('team.onlyHigher')].filter(Boolean).join(' · ')}>
            {#snippet lead()}<Avatar person={q.person} size={36} />{/snippet}
          </Row>
          {#if q.canDecide}
            <!-- engine: Row needs content under it (a request's actions) -->
            <div class="ar under"><Button kind="secondary" size="s" disabled={busy} onclick={() => decide(q, false)}>{t('team.keep')}</Button>
              <Button kind="destructive" size="s" disabled={busy} onclick={() => decide(q, true)}>{t('team.remove')}</Button></div>
          {/if}
        {/each}
      </Group>
    {/if}

    {#if list}
      {#if setup?.tags.length || onProbation}
        {#if depts.length}
          <div class="chips">
            <Chip selected={filter == null} onclick={() => (filter = null)}>{t('common.all')}<span class="n num">{list.length}</span></Chip>
            {#each depts as g (g.id)}
              <Chip selected={filter === g.id} onclick={() => (filter = filter === g.id ? null : g.id)}>{@render dot(g.color)}{g.name}<span class="n num">{list.filter((x) => x.depts?.includes(g.id)).length}</span></Chip>
            {/each}
          </div>
        {/if}
        <!-- one row whatever the count: the tags sit behind one chip that opens a menu, and the chosen one shows on it
             (long department names in a scrolling row hid the chosen one; wrapped, six of them took half the screen) -->
        <div class="chips">
          {#if !depts.length}<Chip selected={filter == null} onclick={() => (filter = null)}>{t('common.all')}<span class="n num">{list.length}</span></Chip>{/if}
          {#if otherTags.length}
            {@const g = typeof filter === 'number' && !dept ? tagOf.get(filter) : null}
            <Chip selected={!!g} onclick={tagMenu}>
              {#if g}{@render dot(g.color)}<span class="ellipsis">{g.name}</span><span class="n num">{list.filter((x) => x.tags?.includes(g.id)).length}</span>
              {:else}{t('team.tagsLabel')}{/if}<ChevronDown size={16} />
            </Chip>
          {/if}
          {#if onProbation}<Chip selected={filter === 'probation'} onclick={() => (filter = filter === 'probation' ? null : 'probation')}>{t('team.probation')}<span class="n num">{onProbation}</span></Chip>{/if}
        </div>
      {/if}
      {#if dept && vice}<span class="deptinv"><Button kind="tinted" size="s" onclick={() => shareInvite(m.org, { id: dept.id, name: dept.name })}>{#snippet icon()}<LinkIcon size={16} />{/snippet}{t('team.inviteDept', { dept: dept.name })}</Button></span>{/if}
      <Group>
        {#each shown as x (x.person.id)}
          {@const manage = x.person.id !== me && canManage(m, x.role)}
          <Row dense title={x.fullName} subtitle={sub(x)} value={roleName(x.role, titleOf(x))} accessory={hasActs(x) ? 'disclosure' : 'chevron'} open={open === x.person.id}
            onclick={() => tap(x)}>
            <!-- the avatar is the profile (its own tap); the club's President: a crown on it -->
            {#snippet lead()}<span class="av"><Avatar person={x.person} size={36} />{#if x.role === 'president'}<span class="crown" title={ROLE_NAME.president}><Crown size={11} strokeWidth={2.6} /></span>{/if}</span>{/snippet}
          </Row>
          {#if open === x.person.id}
            <!-- engine: Row needs content under it (the person's actions, unfolded) -->
            <div class="acts" transition:fold>
              {#if x.person.id === me}
                {@render deptRow(x)}
                {#if ownLevel.length}
                  <span class="t-cap">{t('team.roleLabel')}</span>
                  <div class="ar">{#each ownLevel as r (r.id)}<Chip selected={x.roleId === r.id} onclick={() => !busy && x.roleId !== r.id && giveOwn(x, r)}>{@render dot(r.color)}{inLang(r.name, r.nameKk, r.nameEn)}</Chip>{/each}</div>
                {/if}
              {:else}
                {@render deptRow(x)}
                {#if isAbove(m, x.role)}
                {#if manage}
                  <span class="t-cap">{t('team.roleLabel')}</span>
                  <div class="ar">
                    <!-- Member, or one of the club's roles, each its toggles (no levels by name); only rights I have -->
                    <Chip selected={x.role === 'member' && !x.title} onclick={() => !busy && !(x.role === 'member' && !x.title) && give(x, 'member')}>{ROLE_NAME.member}</Chip>
                    {#each (setup?.roles ?? []).filter((r) => canGive(m.role).includes(r.level) && r.rights.every((k) => may(m, k))) as r (r.id)}
                      <Chip selected={x.roleId === r.id} onclick={() => !busy && x.roleId !== r.id && giveOwn(x, r)}>{@render dot(r.color)}{inLang(r.name, r.nameKk, r.nameEn)}</Chip>
                    {/each}
                    <Chip selected={false} icon={Plus} onclick={() => sheets.teamSetup(m.org.id, refresh)}>{t('ts.newRole')}</Chip>
                  </div>
                {/if}
                {#if !x.probation || vice}
                  <span class="t-cap">{t('team.probation')}</span>
                  <div class="ar">{#if x.probation}<Button kind="secondary" size="s" disabled={busy} onclick={() => probation(x, false)}>{t('team.probationOff')}</Button>
                    {:else}<Button kind="secondary" size="s" disabled={busy} onclick={() => probation(x, true)}>{t('team.probationOn')}</Button>{/if}</div>
                {/if}
                <div class="ar end">
                  {#if m.role === 'president'}<Button kind="secondary" size="s" disabled={busy} onclick={() => handOver(x)}>{t('team.transfer')}</Button>{/if}
                  <Button kind="destructive" size="s" disabled={busy} onclick={() => removeOrAsk(x)}>{manage ? t('team.remove') : t('team.askRemove')}</Button>
                </div>
                {/if}
              {/if}
            </div>
          {/if}
        {/each}
        {#if !shown.length}<EmptyState inline text={t('clubs.nothing')} />{/if}
      </Group>
      <Group><Row tone="destructive" title={t('team.leave')} onclick={leave} /></Group>
    {:else}
      <Skeleton n={4} />
    {/if}
  {/if}
</div>
</Sheet>

<style>
  .team { display: flex; flex-direction: column; gap: var(--s-4); }
  .team > :global(*) { flex-shrink: 0; }
  .hd { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); }
  .org { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .nm { min-width: 0; font: 600 var(--fs-body)/1.2 var(--font-text); }
  .icons { display: flex; gap: var(--s-2); flex: none; }
  .linkpick { display: flex; flex-direction: column; gap: var(--s-4); }
  /* the club's President: a crown on the avatar */
  .av { position: relative; display: inline-flex; }
  .crown { position: absolute; right: -4px; top: -4px; width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--gold); color: var(--ink); box-shadow: 0 0 0 2px var(--surface-solid); }
  .chips { display: flex; gap: var(--s-2); overflow-x: auto; scrollbar-width: none; margin: 0 calc(-1 * var(--gutter)); padding: 4px var(--gutter); }
  .chips::-webkit-scrollbar { display: none; }
  .chips :global(.fc) { max-width: 75vw; }
  .n { flex: none; font-weight: 700; opacity: 0.6; }
  .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--c); }
  .deptinv { align-self: flex-start; }
  /* a row's unfolded actions, from where its title starts */
  .acts { display: flex; flex-direction: column; gap: var(--s-2); padding: 0 var(--s-4) var(--s-4) 64px; }
  .acts .t-cap { margin-top: var(--s-1); }
  .ar { display: flex; flex-wrap: wrap; gap: 6px; }
  .ar.end { margin-top: 6px; }
  .ar.under { padding: 0 var(--s-4) var(--s-3) 64px; }
</style>
