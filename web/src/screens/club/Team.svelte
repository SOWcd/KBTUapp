<script lang="ts">
  // Tab 2 → Team (SPEC §2, §2b): the club's roster for its own team, highest role first (full names inside the team, §3),
  // each with the club's own role name and its tags. A tap opens the person's card; for someone below me it opens the
  // actions instead (the card is the first of them): Vice+ give a role (a level or one of the club's own) and remove;
  // Head+ put on probation, give strikes, and ask the President and Vice to remove someone. On top for Vice+: the
  // removal requests. Tags (and probation) filter the list; "Roles and tags" makes the club's own. The club is the one
  // picked in Studio (ui.club). Vice+ also get the club's invite link (§4.5): share it to the club's chat, copy it, or
  // replace it if it went somewhere it shouldn't. Anyone but the President can leave.
  import { api, ApiErr, type ClubRole, type OrgRole, type RemovalRequest, type Strike, type TeamMember, type TeamSetup } from '../../lib/api';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { say, ui } from '../../lib/state/ui.svelte';
  import { data, loadTeam, studioChanged } from '../../lib/state/data.svelte';
  import { untrack } from 'svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago } from '../../lib/time';
  import { byRank, canGive, canManage, isAbove, may, RANK, roleName, ROLE_NAME, withNick } from '../../lib/perms';
  import { haptic } from '../../lib/tg';
  import { shareInvite } from '../../lib/invite';
  import LinkIcon from '@lucide/svelte/icons/link';
  import Tags from '@lucide/svelte/icons/tags';
  import Crown from '@lucide/svelte/icons/crown';
  import ChevronDown from '@lucide/svelte/icons/chevron-down';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';

  const mine = $derived([...(session.me?.memberships ?? [])].sort(byRank));
  const m = $derived(mine.find((x) => x.org.id === ui.club) ?? mine[0]);
  // kept per club (and for the next launch), so Team opens with the people already there; a visit refreshes it quietly
  const list = $derived(m ? (data.team[m.org.id] ?? null) : null);
  let setup = $state<TeamSetup | null>(null);
  const loadSetup = (org: number) => api.teamSetup(org).then((x) => { if (m?.org.id === org) setup = x; }).catch(() => {});
  $effect(() => { const org = m?.org.id; untrack(() => { open = null; filter = null; setup = null; if (org) { void loadTeam(org); void loadSetup(org); } }); });
  let open = $state<number | null>(null); // whose actions are out
  let busy = $state(false);
  let filter = $state<number | 'probation' | null>(null); // a tag's id, or those on probation
  const me = $derived(session.me?.id);
  const vice = $derived(may(m, 'team'));  // roles, removing at once, probation off
  const tagOf = $derived(new Map((setup?.tags ?? []).map((g) => [g.id, g])));
  const onProbation = $derived((list ?? []).filter((x) => x.probation).length);
  const shown = $derived((list ?? []).filter((x) => filter == null || (filter === 'probation' ? x.probation : x.tags?.includes(filter))));
  // departments (PLAN 47, a club president's ask): the whole list grouped by them, highest role first in each, then
  // those in none; filtered, a plain list
  const depts = $derived((setup?.tags ?? []).filter((g) => g.department));
  const groups = $derived(filter == null && depts.length
    ? [...depts.map((g) => ({ id: g.id as number | null, name: g.name, color: g.color, people: shown.filter((x) => x.dept === g.id) })),
       { id: null, name: t('team.noDept'), color: '', people: shown.filter((x) => x.dept == null) }].filter((g) => g.people.length || (vice && g.id != null))
    : [{ id: null, name: '', color: '', people: shown }]);
  // who may put this person in a department: a Vice+ anyone; a Head those below them, in or out of the Head's own
  const myDept = $derived((list ?? []).find((x) => x.person.id === me)?.dept ?? null);
  const deptChoices = (x: TeamMember) => {
    if (!depts.length || !may(m, 'people')) return [];
    if (RANK[m?.role ?? 'member'] >= RANK.vice) return depts;
    if (x.person.id === me || !isAbove(m, x.role) || myDept == null || (x.dept != null && x.dept !== myDept)) return [];
    return depts.filter((g) => g.id === myDept);
  };
  const setDept = (x: TeamMember, d: number | null) =>
    run(() => api.updateMember(org(), x.person.id, { dept: d }),
      d == null ? t('team.deptNone', { name: x.person.name }) : t('team.deptSet', { name: x.person.name, dept: tagOf.get(d)?.name ?? '' }), 'raising_hands_3d_default');

  // the strikes of whoever's actions are out (or mine), fetched when opened
  let strikesOf = $state<{ user: number; items: Strike[] } | null>(null);
  async function loadStrikes(user: number) {
    try { const items = await api.strikes(m!.org.id, user); if (open === user) strikesOf = { user, items }; } catch { /* the count still shows */ }
  }
  // a role of my own level on myself, a name only (owner, Oct 12); tags are picked in the tag (TeamSetupSheet)
  const ownLevel = $derived((setup?.roles ?? []).filter((r) => r.level === m?.role && r.rights.every((k) => may(m, k))));
  // the avatar is the profile; the row opens what I can do with them, or the profile when there's nothing (owner, Oct 14:
  // no "Profile" button, no tags on the fly here: who has a tag is picked in the tag, in "Roles and tags")
  function tap(x: TeamMember, ev: MouseEvent) {
    const self = x.person.id === me;
    if ((ev.target as HTMLElement).closest('.av') || (self ? !x.probation && !ownLevel.length && !deptChoices(x).length : !isAbove(m, x.role) && !deptChoices(x).length)) { sheets.person(x.person.id); return; }
    open = open === x.person.id ? null : x.person.id;
    strikesOf = null;
    if (open != null && x.probation) void loadStrikes(x.person.id);
  }
  function refresh() {
    if (!m) return;
    void loadTeam(m.org.id); void loadSetup(m.org.id);
    studioChanged();
  }

  async function run(job: () => Promise<TeamMember[] | void>, done: string, emoji: string) {
    busy = true;
    try {
      const fresh = await job();
      if (fresh && m) data.team[m.org.id] = fresh;
      if (done) { haptic.ok(); say(done, emoji); } else haptic.select();
      void loadSetup(m!.org.id);
      studioChanged();
    } catch (e) {
      haptic.error(); say(e instanceof ApiErr && e.message === 'president' ? t('team.presLeave') : t('common.error'), 'pleading_face_3d');
    } finally { busy = false; }
  }
  const org = () => m!.org.id;
  const give = (x: TeamMember, role: OrgRole) =>
    run(() => api.updateMember(org(), x.person.id, { role, roleId: null }), t('team.roleSet', { name: x.person.name, role: ROLE_NAME[role] }), 'raising_hands_3d_default');
  const giveOwn = (x: TeamMember, r: ClubRole) =>
    run(() => api.updateMember(org(), x.person.id, { roleId: r.id }), t('team.roleSet', { name: x.person.name, role: r.name }), 'raising_hands_3d_default');
  const probation = (x: TeamMember, on: boolean) =>
    run(() => api.updateMember(org(), x.person.id, { probation: on }), on ? t('team.probationSet', { name: x.person.name }) : t('team.probationPassed', { name: x.person.name }),
      on ? 'sparkles_3d' : 'party_popper_3d');
  const strike = (x: TeamMember) => sheets.strike(org(), x.person.id, x.person.name, () => { refresh(); void loadStrikes(x.person.id); });
  async function clearStrike(s: Strike) {
    try { await api.clearStrike(s.id); haptic.ok(); say(t('team.strikeCleared'), 'sparkles_3d'); refresh(); if (strikesOf) void loadStrikes(strikesOf.user); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
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
    await run(() => api.removeMember(m.org.id, me!), t('team.left'), 'waving_hand_3d_default');
    void loadMe();
  }
</script>

{#snippet deptRow(x: TeamMember)}
  {@const choices = deptChoices(x)}
  {#if choices.length}
    <span class="t-cap">{t('team.dept')}</span>
    <div class="ar">
      {#each choices as g (g.id)}
        <button class="pill" class:on={x.dept === g.id} disabled={busy || x.dept === g.id} onclick={() => setDept(x, g.id)}><span class="dot" style="--c:{g.color}"></span>{g.name}</button>
      {/each}
      <button class="pill" class:on={x.dept == null} disabled={busy || x.dept == null} onclick={() => setDept(x, null)}>{t('team.noDept')}</button>
    </div>
  {/if}
{/snippet}

{#snippet strikeList(x: TeamMember, canClear: boolean)}
  <div class="strikes">
    <b class="sh">{t('team.strikes', { n: x.strikes ?? 0 })}<span class="pips">{#each [0, 1, 2] as i (i)}<span class:hit={i < (x.strikes ?? 0)}></span>{/each}</span></b>
    {#if strikesOf?.user === x.person.id}
      {#each strikesOf.items.filter((s) => !s.clearedAt) as s (s.id)}
        <div class="st">
          <span><b>{s.reason === 'other' ? s.note : t(`strike.${s.reason}`)}</b>{#if s.note && s.reason !== 'other'}{' · ' + s.note}{/if}
            <i class="t-foot">{ago(s.at)}{s.by ? ' · ' + s.by.name : ''}</i></span>
          {#if canClear}<button onclick={() => clearStrike(s)}>{t('team.clearStrike')}</button>{/if}
        </div>
      {/each}
    {/if}
  </div>
{/snippet}

<div class="page scroll">
  {#if m}
    <header class="hd">
      <span class="org"><OrgLogo org={m.org} size={30} /><span><h1 class="t-h2 ellipsis">{t('page.team')}</h1><p class="t-foot ellipsis">{m.org.name}</p></span></span>
      <!-- the list first; invite and roles are icons up here (owner, Oct 15: the invite row was too big, the hint noise) -->
      <span class="icons">
        {#if vice}<button class="ic" onclick={() => shareInvite(m.org)} aria-label={t('team.inviteTitle')}><LinkIcon size={19} /></button>{/if}
        {#if may(m, 'people') || vice || setup?.roles.length || setup?.tags.length}
          <button class="ic" onclick={() => sheets.teamSetup(m.org.id, refresh)} aria-label={t('team.setup')}><Tags size={19} /></button>
        {/if}
      </span>
    </header>

    {#if setup?.removals?.length}
      <!-- §2b: a Head's request, or the third strike; the President or a Vice above them decides -->
      <section class="asks">
        <h2 class="t-cap">{t('team.removals')}</h2>
        {#each setup.removals as q (q.id)}
          <div class="ask">
            <div class="aq"><Avatar person={q.person} size={36} />
              <span class="tx"><b class="ellipsis">{withNick(q.fullName, q.person)}</b>
                <i class="t-foot">{q.by ? t('team.removalBy', { name: q.by.name }) : t('team.removalStrikes')}{q.ban ? ' · ' + t('team.withBan') : ''}{q.note ? ' · «' + q.note + '»' : ''}</i></span></div>
            {#if q.canDecide}
              <div class="ar"><Button kind="secondary" size="s" disabled={busy} onclick={() => decide(q, false)}>{t('team.keep')}</Button>
                <Button kind="danger" size="s" disabled={busy} onclick={() => decide(q, true)}>{t('team.remove')}</Button></div>
            {:else}<p class="t-foot">{t('team.onlyHigher')}</p>{/if}
          </div>
        {/each}
      </section>
    {/if}

    {#if list}
      {#if setup?.tags.length || onProbation}
        <!-- one row whatever the count: the tags sit behind one chip that opens the phone's own list, and the chosen
             one shows on it (owner, Oct 13: long department names in a scrolling row hid the chosen one; wrapped,
             six of them took half the screen and stood ragged) -->
        <div class="filters">
          <button class:on={filter == null} onclick={() => (filter = null)}>{t('common.all')}<span class="num">{list.length}</span></button>
          {#if setup?.tags.length}
            {@const g = typeof filter === 'number' ? tagOf.get(filter) : null}
            <label class="pick" class:on={!!g}>
              {#if g}<span class="dot" style="--c:{g.color}"></span><span class="ellipsis">{g.name}</span><span class="num">{list.filter((x) => x.tags?.includes(g.id)).length}</span>
              {:else}<span>{t('team.tagsLabel')}</span>{/if}
              <ChevronDown size={16} />
              <select value={g ? String(g.id) : ''} onchange={(e) => { const v = e.currentTarget.value; filter = v ? Number(v) : null; }} aria-label={t('team.tagsLabel')}>
                <option value="">{t('common.all')} · {list.length}</option>
                {#each setup.tags as x (x.id)}<option value={String(x.id)}>{x.name} · {list.filter((y) => y.tags?.includes(x.id)).length}</option>{/each}
              </select>
            </label>
          {/if}
          {#if onProbation}<button class:on={filter === 'probation'} onclick={() => (filter = filter === 'probation' ? null : 'probation')}>{t('team.probation')}<span class="num">{onProbation}</span></button>{/if}
        </div>
      {/if}
      <div class="list">
        {#each groups as grp (grp.id ?? 'none')}
        {#if grp.name}<h2 class="t-cap grp">{#if grp.color}<span class="dot" style="--c:{grp.color}"></span>{/if}{grp.name}<span class="num">{grp.people.length}</span>{#if vice && grp.id != null}<button class="ic sm" onclick={() => shareInvite(m.org, { id: grp.id as number, name: grp.name })} aria-label={t('team.inviteDept', { dept: grp.name })}><LinkIcon size={16} /></button>{/if}</h2>{/if}
        {#each grp.people as x (x.person.id)}
          {@const manage = x.person.id !== me && canManage(m, x.role)}
          <div class="row" class:out={open === x.person.id}>
            <button class="who" onclick={(ev) => tap(x, ev)}>
              <span class="av"><Avatar person={x.person} size={42} />{#if x.role === 'president'}<span class="crown" title={ROLE_NAME.president}><Crown size={12} strokeWidth={2.6} /></span>{/if}</span>
              <span class="tx"><b class="ellipsis">{x.fullName}</b>
                <i class="t-foot ellipsis">{[x.person.nick, x.username && '@' + x.username].filter(Boolean).join(' · ') || x.person.name}{#if x.quiet}<span class="quiet">{t('reg.quiet')}</span>{/if}</i>
                {#if x.tags?.length || x.probation}
                  <span class="marks">
                    {#if x.probation}<span class="prob">{t('team.probation')}<span class="pips">{#each [0, 1, 2] as i (i)}<span class:hit={i < (x.strikes ?? 0)}></span>{/each}</span></span>{/if}
                    {#each x.tags ?? [] as id (id)}{@const g = tagOf.get(id)}{#if g}<span class="tag"><span class="dot" style="--c:{g.color}"></span>{g.name}</span>{/if}{/each}
                  </span>
                {/if}
              </span>
              <span class="rl" class:top={x.role !== 'member' && !x.title} class:own={!!x.title} style={x.titleColor ? `--c:${x.titleColor}` : undefined}>{roleName(x.role, x.title)}</span>
            </button>
            {#if open === x.person.id}
              <div class="acts">
                {#if x.person.id === me}
                  {@render deptRow(x)}
                  {@render strikeList(x, false)}
                  {#if ownLevel.length}
                    <span class="t-cap">{t('team.roleLabel')}</span>
                    <div class="ar">{#each ownLevel as r (r.id)}<button class="pill" class:on={x.roleId === r.id} disabled={busy || x.roleId === r.id} onclick={() => giveOwn(x, r)}><span class="dot" style="--c:{r.color}"></span>{r.name}</button>{/each}</div>
                  {/if}
                {:else}
                  {@render deptRow(x)}
                  {#if isAbove(m, x.role)}
                  {#if manage}
                    <span class="t-cap">{t('team.roleLabel')}</span>
                    <div class="ar">
                      <!-- Member, or one of the club's roles, each its toggles (owner, Oct 7: no levels by name); only rights I have -->
                      <button class="pill" class:on={x.role === 'member' && !x.title} disabled={busy || (x.role === 'member' && !x.title)} onclick={() => give(x, 'member')}>{ROLE_NAME.member}</button>
                      {#each (setup?.roles ?? []).filter((r) => canGive(m.role).includes(r.level) && r.rights.every((k) => may(m, k))) as r (r.id)}
                        <button class="pill" class:on={x.roleId === r.id} disabled={busy || x.roleId === r.id} onclick={() => giveOwn(x, r)}><span class="dot" style="--c:{r.color}"></span>{r.name}</button>
                      {/each}
                      <button class="pill add" onclick={() => sheets.teamSetup(m.org.id, refresh)}>{t('ts.newRole')}</button>
                    </div>
                  {/if}
                  <span class="t-cap">{t('team.probation')}</span>
                  {#if x.probation}
                    {@render strikeList(x, vice)}
                    <div class="ar">
                      <Button kind="danger" size="s" disabled={busy || (x.strikes ?? 0) >= 3} onclick={() => strike(x)}>{t('team.strike')}</Button>
                      {#if vice}<Button kind="secondary" size="s" disabled={busy} onclick={() => probation(x, false)}>{t('team.probationOff')}</Button>{/if}
                    </div>
                  {:else}
                    <div class="ar"><Button kind="secondary" size="s" disabled={busy} onclick={() => probation(x, true)}>{t('team.probationOn')}</Button></div>
                  {/if}
                  <div class="ar end">
                    {#if m.role === 'president'}<Button kind="secondary" size="s" disabled={busy} onclick={() => handOver(x)}>{t('team.transfer')}</Button>{/if}
                    <Button kind="danger" size="s" disabled={busy} onclick={() => removeOrAsk(x)}>{manage ? t('team.remove') : t('team.askRemove')}</Button>
                  </div>
                  {/if}
                {/if}
              </div>
            {/if}
          </div>
        {/each}
        {/each}
        {#if !shown.length}<p class="t-foot empty">{t('clubs.nothing')}</p>{/if}
      </div>
      <button class="leave" onclick={leave}>{t('team.leave')}</button>
    {:else}
      <div class="skel"><span></span><span></span><span></span></div>
    {/if}
  {/if}
  <div class="tail"></div>
</div>

<style>
  .quiet { margin-left: 6px; padding: 1px 6px; border-radius: var(--r-full); background: var(--warning-soft); color: var(--warning-text); font-weight: 650; font-style: normal; }
  .page { position: absolute; inset: 0; padding: calc(var(--top) + 56px) var(--gutter) 0; background: var(--glow), var(--bg); display: flex; flex-direction: column; gap: 10px; }
  .page > :global(*) { flex-shrink: 0; }
  /* the club's President: a crown on the avatar (owner, Oct 15) */
  .av { position: relative; }
  .crown { position: absolute; right: -3px; top: -4px; width: 20px; height: 20px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: #FFB23D; color: #3A2400; box-shadow: 0 0 0 2px var(--surface); }
  .icons { display: flex; gap: 8px; flex: none; }
  .ic { width: 38px; height: 38px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent-text); transition: transform var(--t-fast) var(--ease); }
  .ic:active { transform: scale(0.9); box-shadow: 0 0 0 4px var(--accent-soft), 0 0 22px rgba(59, 107, 255, 0.55); } /* a press glows (owner, Oct 17) */
  .hd { margin-bottom: 4px; display: flex; align-items: center; justify-content: space-between; gap: 10px; }
  .org { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .org > span { min-width: 0; }

  .asks { display: flex; flex-direction: column; gap: 8px; padding: 12px; border-radius: var(--r-l); background: var(--danger-soft); }
  .asks h2 { color: var(--danger-text); }
  .ask { display: flex; flex-direction: column; gap: 8px; padding: 10px; border-radius: var(--r-m); background: var(--surface); }
  .aq { display: flex; align-items: center; gap: 10px; min-width: 0; }

  .filters { display: flex; gap: 6px; }
  .filters button, .pick { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface); color: var(--text-2);
    box-shadow: inset 0 0 0 1px var(--line); font: 620 13.5px/1 var(--font-text); }
  .pick { position: relative; flex: 0 1 auto; min-width: 0; }
  .pick :global(svg) { flex: none; opacity: 0.6; }
  .pick select { position: absolute; inset: 0; opacity: 0; font-size: 16px; }
  .filters button.on, .pick.on { background: var(--text); color: var(--bg); box-shadow: none; }
  .filters .num { flex: none; font-weight: 700; opacity: 0.6; }

  .list { display: flex; flex-direction: column; gap: 8px; }
  .grp { display: flex; align-items: center; gap: 7px; margin: 8px 2px 0; color: var(--text-2); }
  .grp .num { margin-left: auto; opacity: 0.6; }
  .grp .ic.sm { width: 28px; height: 28px; margin: -6px -4px -6px 0; }
  .row { border-radius: var(--r-l); background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); overflow: hidden; }
  .who { display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px 12px; text-align: left; }
  .who:active { background: var(--surface-2); }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 640 15px/1.25 var(--font-text); }
  .tx i { font-style: normal; }
  .marks { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 3px; }
  .tag, .prob { display: inline-flex; align-items: center; gap: 5px; height: 20px; padding: 0 7px; border-radius: var(--r-full); background: var(--surface-2); color: var(--text-2);
    font: 620 11.5px/1 var(--font-text); }
  .prob { background: var(--warning-soft); color: var(--warning-text); }
  .dot { flex: none; width: 8px; height: 8px; border-radius: 50%; background: var(--c); }
  .pips { display: inline-flex; gap: 3px; margin-left: 2px; }
  .pips span { width: 6px; height: 6px; border-radius: 50%; box-shadow: inset 0 0 0 1.5px currentColor; opacity: 0.6; }
  .pips span.hit { background: var(--danger); box-shadow: none; opacity: 1; }
  .rl { flex: none; max-width: 40%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; padding: 5px 9px; border-radius: var(--r-full); background: var(--surface-2); color: var(--text-2);
    font: 700 11px/1 var(--font-text); letter-spacing: 0.04em; text-transform: uppercase; }
  .rl.top { background: var(--accent-soft); color: var(--accent-text); }
  .rl.own { background: color-mix(in srgb, var(--c) 18%, transparent); color: var(--text); box-shadow: inset 0 0 0 1px color-mix(in srgb, var(--c) 45%, transparent); }

  .acts { display: flex; flex-direction: column; gap: 8px; padding: 0 12px 12px 66px; }
  .acts .t-cap { margin-top: 4px; }
  .ar { display: flex; flex-wrap: wrap; gap: 6px; }
  .ar.end { margin-top: 6px; }
  .pill { display: inline-flex; align-items: center; gap: 6px; height: 32px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-2); color: var(--text);
    font: 620 13px/1 var(--font-text); box-shadow: inset 0 0 0 1.5px transparent; }
  .pill.on { background: var(--accent-soft); color: var(--accent-text); box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--accent) 50%, transparent); }
  .pill:disabled:not(.on) { opacity: 0.5; }
  .strikes { display: flex; flex-direction: column; gap: 6px; padding: 10px 12px; border-radius: var(--r-m); background: var(--surface-2); }
  .sh { display: flex; align-items: center; gap: 8px; font: 650 14px/1.2 var(--font-text); color: var(--warning-text); }
  .st { display: flex; align-items: center; gap: 8px; }
  .st > span { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; font: 500 14px/1.3 var(--font-text); }
  .st b { font-weight: 650; }
  .st i { font-style: normal; }
  .st button { flex: none; height: 28px; padding: 0 10px; border-radius: var(--r-full); background: var(--surface); color: var(--accent-text); font: 650 12.5px/1 var(--font-text); }
  .empty { padding: 14px 4px; text-align: center; }
  .leave { align-self: center; margin-top: 10px; padding: 10px 14px; font: 620 14px/1 var(--font-text); color: var(--danger-text); }
  .skel { display: flex; flex-direction: column; gap: 8px; }
  .skel span { height: 62px; border-radius: var(--r-l); background: var(--surface-2); animation: pulse 1.2s ease-in-out infinite; }
  @keyframes pulse { 50% { opacity: 0.5; } }
  .tail { flex: none; height: calc(var(--bottom) + 12px); }
</style>
