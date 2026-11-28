<script lang="ts">
  // My club → Team, a sheet from its row: the club's roster for its own team, highest role first (full names inside the team),
  // each with the club's own role name and its tags. A tap opens the person's card; for someone below me it opens their
  // own sheet instead (MemberSheet, the card is its first row): Vice+ give a role (a level or one of the club's own) and remove;
  // Head+ put on probation and ask the President and Vice to remove someone. On top for Vice+: the
  // removal requests. Tags (and probation) filter the list; "Roles and tags" makes the club's own. The club is the one
  // picked in My club (ui.club). Vice+ also get the club's invite link: the link icon opens two cards, the
  // team's link for everyone (7 days, one per club, shared again until turned off) and a one-time one. Anyone but the
  // President can leave.
  import { api, ApiErr, type RemovalRequest, type TeamMember, type TeamSetup } from '../../lib/api';
  import Sheet from '../../ui/Sheet.svelte';
  import Users from '@lucide/svelte/icons/users';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { say, ui, close } from '../../lib/state/ui.svelte';
  import { data, loadTeam, studioChanged } from '../../lib/state/data.svelte';
  import { untrack } from 'svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { byRank, isAbove, may, RANK, roleLabel, ROLE_NAME, withNick } from '../../lib/perms';
  import { haptic } from '../../lib/tg';
  import { shareInvite } from '../../lib/invite';
  import { fold } from '../../ui/fold';
  import { dayMonth } from '../../lib/time';
  import LinkIcon from '@lucide/svelte/icons/link';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import Tags from '@lucide/svelte/icons/tags';
  import Crown from '@lucide/svelte/icons/crown';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import FileDown from '@lucide/svelte/icons/file-down';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Card from '../../ui/Card.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Chip from '../../ui/Chip.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import { hit } from '../../lib/search';
  import Skeleton from '../../ui/Skeleton.svelte';
  import { menu } from '../../ui/menu';
  import SortChip from '../../ui/SortChip.svelte';
  import { sorted, byName, newest, usual, type Order } from '../../lib/sort.svelte';

  // at: that person's sheet opens (Studio → Chats → Roles and admins), once
  let { overlay, at }: { overlay: Overlay; at?: number } = $props();
  let first = untrack(() => at);
  const mine = $derived([...(session.me?.memberships ?? [])].sort(byRank));
  const m = $derived(mine.find((x) => x.org.id === ui.club) ?? mine[0]);
  // kept per club (and for the next launch), so Team opens with the people already there; a visit refreshes it quietly
  const list = $derived(m ? (data.team[m.org.id] ?? null) : null);
  let setup = $state<TeamSetup | null>(null);
  const loadSetup = (org: number) => api.teamSetup(org).then((x) => { if (m?.org.id === org) setup = x; }).catch(() => {});
  const orgId = $derived(m?.org.id); // the same club with a fresh membership (a return refresh) keeps the filter
  $effect(() => { const org = orgId; untrack(() => { filter = null; q = ''; setup = null; off = false; if (org) { void loadTeam(org); void loadSetup(org); if (first != null) sheets.member(org, first, () => setup, deptChoices, refresh); } first = undefined; }); });
  let linkOpen = $state(false); // the link icon's two cards
  let off = $state(false); // the open link turned off here, ahead of the server (and of a setup fetched before it)
  const link = $derived(off ? null : (setup?.teamLink ?? null));
  async function shareLink(many: boolean) {
    if (!m) return;
    const org = m.org.id;
    // the open link shows at once, "On" and its day on the card: set when it is made, not after the
    // picker (Android's may never answer), and the cards stay open to show it
    const ok = await shareInvite(m.org, undefined, many, (until) => { if (setup && m?.org.id === org) { setup.teamLink = { expiresAt: until }; off = false; } });
    if (ok && !many) linkOpen = false;
    if (many) void loadSetup(org);
  }
  // off at once after the confirm; the toast's Undo brings the link back (it waits for the "off" to land first)
  async function linkOff() {
    if (!m || !link) return;
    const org = m.org.id;
    if (!(await sheets.ask({ title: t('team.linkOffAsk'), text: t('team.linkOffText'), ok: t('team.linkOff'), cancel: t('common.cancel'), danger: true }))) return;
    off = true; haptic.ok();
    const gone = api.teamLinkOff(org).then(() => true, () => false);
    say(t('team.linkOffDone'), 'raising_hands_3d_default', async () => {
      if (m?.org.id === org) off = false;
      if (!(await gone)) return; // it never went off: the link is as it was
      try {
        const { expiresAt } = await api.teamLinkBack(org);
        if (setup && m?.org.id === org) setup.teamLink = { expiresAt };
      } catch { if (m?.org.id === org) off = true; haptic.error(); say(t('common.error'), 'warning_3d'); }
    });
    if (!(await gone)) { if (m?.org.id === org) off = false; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  let busy = $state(false);
  let filter = $state<number | 'probation' | null>(null); // a tag's id, or those on probation
  let q = $state(''); // a name or @username (a Head of HR's ask): the box shows once the list is long
  const me = $derived(session.me?.id);
  const vice = $derived(may(m, 'team'));  // roles, removing at once, probation off
  const tagOf = $derived(new Map((setup?.tags ?? []).map((g) => [g.id, g])));
  const onProbation = $derived((list ?? []).filter((x) => x.probation).length);
  const ORDERS: Order<TeamMember>[] = [usual('sort.role'), byName((x) => x.fullName), newest((x) => x.joinedAt)]; // the server's: highest role first
  const shown = $derived(sorted('team', ORDERS, (list ?? []).filter((x) => (filter == null || (filter === 'probation' ? x.probation : x.tags?.includes(filter))) && (!q.trim() || hit(q, [x.fullName, x.person.nick, x.username])))));
  // one list, highest role first (the server's order); departments are their own chips (grouped, the
  // President would sit last under "no department" and the heads would scatter)
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

  // a role of my own level on myself, a name only; tags are picked in the tag (TeamSetupSheet)
  const ownLevel = $derived((setup?.roles ?? []).filter((r) => r.level === m?.role && r.rights.every((k) => may(m, k))));
  // the avatar is the profile; the row opens what I can do with them, or the profile when there's nothing (no
  // "Profile" button, no tags on the fly here: who has a tag is picked in the tag, in "Roles and tags")
  function tap(x: TeamMember) {
    if (!hasActs(x)) { sheets.person(x.person.id); return; }
    if (m) sheets.member(m.org.id, x.person.id, () => setup, deptChoices, refresh);
  }
  // what can be done with them: the row opens their sheet, else the profile
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
  async function decide(q: RemovalRequest, approve: boolean) {
    if (approve && !(await sheets.ask({ title: t('team.removeAsk', { name: q.person.name }), text: q.ban ? t('rm.banHint') : t('team.removeText'), ok: t('team.remove'),
      cancel: t('common.cancel'), danger: true }))) return;
    await run(() => api.decideRemoval(q.id, approve), approve ? t('team.removed', { name: q.person.name }) : t('team.kept', { name: q.person.name }),
      approve ? 'waving_hand_3d_default' : 'raising_hands_3d_default');
    refresh();
  }
  async function leave() {
    if (!m) return;
    if (!(await sheets.ask({ title: t('team.leaveAsk', { club: m.org.name }), text: t('team.leaveText'), ok: t('team.leave'), cancel: t('common.cancel'), danger: true }))) return;
    if (!(await run(() => api.removeMember(m.org.id, me!), t('team.left'), 'waving_hand_3d_default'))) return;
    close(overlay.id); // not my team any more: the sheet would show the next club's
    void loadMe();
  }
  // the roster as a file, from the bot (Medina): Vice+, like the attendees' list
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
      <!-- two cards, one action each: the team's open link (its state, "turn off" only while it is on) and a one-time one -->
      <div class="links" transition:fold>
        <Card>
          <div class="lk">
            <div class="top">
              <span class="ic"><Users size={20} strokeWidth={1.8} /></span>
              <span class="tx"><b>{t('team.linkAll')}</b>
                <span class="sb">{link ? t('team.linkAllSubOn', { date: dayMonth(link.expiresAt) }) : t('team.linkAllSub')}</span></span>
            </div>
            <div class="ft">
              <span class="state" class:live={!!link}><i class="pip"></i>{link ? t('team.linkOnState') : t('team.linkOffState')}</span>
              <span class="acts">
                {#if link}<Button kind="plain" size="s" onclick={linkOff}>{t('team.linkOff')}</Button>{/if}
                <Button size="s" onclick={() => shareLink(true)}>{t('team.linkShare')}</Button>
              </span>
            </div>
          </div>
        </Card>
        <Card>
          <div class="lk">
            <div class="top">
              <span class="ic"><UserPlus size={20} strokeWidth={1.8} /></span>
              <span class="tx"><b>{t('team.linkOnce')}</b><span class="sb">{t('team.linkOnceSub')}</span></span>
            </div>
            <div class="ft">
              <span class="state">{t('team.linkFresh')}</span>
              <span class="acts"><Button kind="tinted" size="s" onclick={() => shareLink(false)}>{t('team.linkShare')}</Button></span>
            </div>
          </div>
        </Card>
      </div>
    {/if}

    {#if setup?.removals?.length}
      <!-- a Head's request; the President or a Vice above them decides -->
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
      {#if list.length > 8 || q}<SearchField bind:value={q} placeholder={t('door.search')} />{/if}
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
        {#if setup?.tags.length || onProbation || list.length > 1}<div class="chips last">
          {#if !depts.length && (setup?.tags.length || onProbation)}<Chip selected={filter == null} onclick={() => (filter = null)}>{t('common.all')}<span class="n num">{list.length}</span></Chip>{/if}
          {#if otherTags.length}
            {@const g = typeof filter === 'number' && !dept ? tagOf.get(filter) : null}
            <Chip selected={!!g} onclick={tagMenu}>
              {#if g}{@render dot(g.color)}<span class="ellipsis">{g.name}</span><span class="n num">{list.filter((x) => x.tags?.includes(g.id)).length}</span>
              {:else}{t('team.tagsLabel')}{/if}<ChevronDown size={16} />
            </Chip>
          {/if}
          {#if onProbation}<Chip selected={filter === 'probation'} onclick={() => (filter = filter === 'probation' ? null : 'probation')}>{t('team.probation')}<span class="n num">{onProbation}</span></Chip>{/if}
          <!-- the filters' row ends with the order (alone in it when the club has no tags) -->
          {#if list.length > 1}<SortChip list="team" orders={ORDERS} />{/if}
        </div>{/if}
      {#if dept && vice}<span class="deptinv"><Button kind="tinted" size="s" onclick={() => shareInvite(m.org, { id: dept.id, name: dept.name })}>{#snippet icon()}<LinkIcon size={16} />{/snippet}{t('team.inviteDept', { dept: dept.name })}</Button></span>{/if}
      <Group>
        {#each shown as x (x.person.id)}
          <Row dense title={x.fullName} subtitle={sub(x)} value={roleLabel(x)} accessory="chevron"
            onclick={() => tap(x)}>
            <!-- the avatar is the profile (its own tap); the club's President: a crown on it -->
            {#snippet lead()}<span class="av"><Avatar person={x.person} size={36} />{#if x.role === 'president'}<span class="crown" title={ROLE_NAME.president}><Crown size={11} strokeWidth={2.6} /></span>{/if}</span>{/snippet}
          </Row>
        {/each}
        {#if !shown.length}<EmptyState inline text={t('clubs.nothing')} />{/if}
      </Group>
      <!-- the President hands the club over first: no Leave that only says no -->
      {#if m.role !== 'president'}<Group><Row tone="destructive" title={t('team.leave')} onclick={leave} /></Group>{/if}
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
  /* the invite links: two cards (ActionCard's tile and padding), the words on top, the state and the action under them */
  .links { --card-pad: var(--s-3); display: flex; flex-direction: column; gap: var(--s-3); }
  .lk { display: flex; flex-direction: column; gap: var(--s-3); }
  .top { display: flex; align-items: center; gap: var(--s-3); }
  .ic { flex: none; display: grid; place-items: center; width: var(--ctl-s); height: var(--ctl-s); border-radius: var(--r-s); background: var(--fill); color: var(--text-2); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 600 var(--fs-body)/1.25 var(--font-text); letter-spacing: -0.01em; overflow-wrap: break-word; }
  .sb { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); overflow-wrap: break-word; }
  /* wraps instead of cutting a label, should a language run long at 320 */
  .ft { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: var(--s-2); }
  .state { display: inline-flex; align-items: center; gap: 6px; padding-left: var(--s-1); font: 600 var(--fs-cap)/1.2 var(--font-text); color: var(--text-3); }
  .state.live { color: var(--success-text); }
  .pip { flex: none; width: var(--s-2); height: var(--s-2); border-radius: var(--r-full); background: var(--fill-2); }
  .live .pip { background: var(--success); box-shadow: 0 0 0 3px var(--success-soft); }
  .acts { --plain-ink: var(--text-3); display: flex; align-items: center; gap: var(--s-1); margin-left: auto; }
  /* the club's President: a crown on the avatar */
  .av { position: relative; display: inline-flex; }
  .crown { position: absolute; right: -4px; top: -4px; width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: var(--gold); color: var(--ink); box-shadow: 0 0 0 2px var(--surface-solid); }
  .chips { display: flex; gap: var(--s-2); overflow-x: auto; scrollbar-width: none; margin: 0 calc(-1 * var(--gutter)); padding: 4px var(--gutter); }
  .chips::-webkit-scrollbar { display: none; }
  .chips :global(.fc) { max-width: 75vw; }
  .chips.last { align-items: center; }
  .chips.last :global(.sort) { padding-left: var(--s-2); }
  .n { flex: none; font-weight: 700; opacity: 0.6; }
  .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--c); }
  .deptinv { align-self: flex-start; }
  .ar { display: flex; flex-wrap: wrap; gap: 6px; }
  .ar.under { padding: 0 var(--s-4) var(--s-3) 64px; }
</style>
