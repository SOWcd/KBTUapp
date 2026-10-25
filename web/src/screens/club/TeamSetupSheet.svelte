<script lang="ts">
  // Team 2.0 (SPEC §2b), from Team: the club's own roles — a name, a colour and toggles of rights, as admin rights in
  // Telegram, made by whoever runs the team, only with rights they
  // have and below their own level — and its tags, groups of people ("people"). The team runner also sees who is banned
  // and can lift it. Who has a tag is set here too, in the tag (owner, Oct 14: not on the fly in a person's card, where
  // a stray tap tagged someone).
  import Plus from '@lucide/svelte/icons/plus';
  import Check from '@lucide/svelte/icons/check';
  import { fold } from '../../ui/fold';
  import { api, ApiErr, type ClubLevel, type ClubRole, type ClubTag, type Id, type Right, type TeamMember, type TeamSetup } from '../../lib/api';
  import { data, loadTeam } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { phrase } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { isAbove, may, RANK, RIGHTS, ROLE_NAME, TEAM_COLORS, withNick } from '../../lib/perms';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';

  let { overlay, org, onchange }: { overlay: Overlay; org: Id; onchange?: () => void } = $props();

  const m = $derived(session.me?.memberships.find((x) => x.org.id === org) ?? null);
  const mine = $derived(m?.role ?? null);
  const vice = $derived(may(m, 'team'));
  const head = $derived(may(m, 'people'));
  // a right I can put in a role: one I have, below my own level (a role level with mine would outrank no one I can manage)
  const givable = (r: { key: Right; level: ClubLevel }) => !!mine && may(m, r.key) && RANK[r.level] < RANK[mine] && (!ffixed || RANK[r.level] <= RANK[ffixed]);

  let setup = $state<TeamSetup | null>(null);
  const load = () => api.teamSetup(org).then((x) => (setup = x)).catch(() => say(t('common.error'), 'pleading_face_3d'));
  $effect(() => { void load(); });

  // one form open at a time: a role or a tag, new (id null) or an edit
  let kind = $state<'role' | 'tag' | null>(null);
  let fid = $state<Id | null>(null);
  let fname = $state('');
  let fcolor = $state(TEAM_COLORS[0]);
  let frights = $state<Right[]>([]);
  let ffixed = $state<ClubLevel | null>(null); // an official role: its name and level stay, rights up to the level
  let fdept = $state(false); // a tag that is a department (PLAN 47)
  let busy = $state(false);
  function edit(k: 'role' | 'tag', x?: ClubRole | ClubTag) {
    kind = k; fid = x?.id ?? null; fname = x?.name ?? ''; fcolor = x?.color ?? TEAM_COLORS[(setup?.[k === 'role' ? 'roles' : 'tags'].length ?? 0) % TEAM_COLORS.length];
    frights = x && 'rights' in x ? [...x.rights] : ['door'];
    ffixed = x && 'fixed' in x && x.fixed ? x.level : null;
    fdept = !!(x && 'department' in x && x.department);
    haptic.select();
  }
  const done = (x: TeamSetup) => { setup = x; kind = null; haptic.ok(); onchange?.(); };
  const oops = (e: unknown) => {
    haptic.error();
    say(e instanceof ApiErr && e.message === 'taken' ? t('ts.taken') : e instanceof ApiErr && e.message === 'many' ? t('ts.many') : t('common.error'), 'pleading_face_3d');
  };
  async function save() {
    if (!kind || busy || !fname.trim()) return;
    busy = true;
    try { done(kind === 'role' ? await api.saveRole(org, { name: fname, color: fcolor, rights: frights }, fid ?? undefined) : await api.saveTag(org, { name: fname, color: fcolor, department: fdept }, fid ?? undefined)); say(phrase('say.tsSaved'), 'sparkles_3d'); }
    catch (e) { oops(e); } finally { busy = false; }
  }
  async function drop() {
    if (!kind || fid == null || busy) return;
    busy = true;
    try { done(kind === 'role' ? await api.deleteRole(org, fid) : await api.deleteTag(org, fid)); say(t('say.tsDropped'), 'waving_hand_3d_default'); }
    catch (e) { oops(e); } finally { busy = false; }
  }
  async function unban(user: Id) {
    try { await api.unban(org, user); haptic.ok(); await load(); }
    catch (e) { oops(e); }
  }
  // a role I can't edit opens to read: what it may and may not do
  let peek = $state<Id | null>(null);
  // a role I may edit: its level is below mine
  const mayEdit = (r: ClubRole) => vice && !!mine && RANK[r.level] < RANK[mine];
  // a tag's people: tags are labels, no power — a Vice+ tags anyone, a Head those below and themself (as Team did)
  const team = $derived(data.team[org] ?? []);
  $effect(() => { if (kind === 'tag' && fid != null && !data.team[org]) void loadTeam(org); });
  const mayTag = (x: TeamMember) => x.person.id === session.me?.id ? head : head && (RANK[mine ?? 'member'] >= RANK.vice || isAbove(m, x.role));
  let tagging = $state<Id | null>(null);
  // a department: one per person, so ticking moves them here (a Head moves people in their own one, in Team's card)
  const mayDept = $derived(head && RANK[mine ?? 'member'] >= RANK.vice);
  async function tagPerson(x: TeamMember, tag: Id, on: boolean) {
    tagging = x.person.id; haptic.select();
    try {
      const saved = !!setup?.tags.find((g) => g.id === tag)?.department; // as the server has it, not the unsaved switch
      data.team[org] = await api.updateMember(org, x.person.id, saved ? { dept: on ? tag : null }
        : { tags: on ? [...(x.tags ?? []), tag] : (x.tags ?? []).filter((g) => g !== tag) });
      void load(); onchange?.();
    } catch (e) { oops(e); } finally { tagging = null; }
  }
  const toggle = (k: Right, on: boolean) => { haptic.tap(); frights = on ? [...frights, k] : frights.filter((x) => x !== k); };
  const rightName = (k: Right) => t(`right.${k}` as 'right.door');
  // the door is every member's, not a toggle
  const TOGGLES = RIGHTS.filter((x) => x.key !== 'door');
  const summary = (r: ClubRole) => { const on = r.rights.filter((k) => k !== 'door'); return on.length ? on.map(rightName).join(', ') : t('ts.noRights'); };
</script>

{#snippet form()}
  <div class="form">
    <input bind:value={fname} disabled={!!ffixed} maxlength="24" placeholder={kind === 'role' ? t('ts.rolePh') : t('ts.tagPh')} enterkeyhint="done" />
    <div class="colors">
      {#each TEAM_COLORS as c (c)}<button class:on={fcolor === c} style="--c:{c}" onclick={() => (fcolor = c)} aria-label={c}></button>{/each}
    </div>
    {#if kind === 'role'}
      <span class="t-cap">{t('ts.level')}</span>
      <div class="rights">
        {#each TOGGLES as r (r.key)}
          <label class="switch" class:locked={!givable(r)}><span><b>{rightName(r.key)}</b><i class="t-foot">{t(`right.${r.key}.sub` as 'right.door.sub')}</i></span>
            <input type="checkbox" role="switch" disabled={!givable(r)} checked={frights.includes(r.key)} onchange={(e) => toggle(r.key, e.currentTarget.checked)} /></label>
        {/each}
      </div>
      {#if TOGGLES.some((r) => !givable(r))}<p class="t-foot">{t('ts.locked')}</p>{/if}
    {:else}
      <label class="switch"><span><b>{t('ts.isDept')}</b><i class="t-foot">{t('ts.isDeptSub')}</i></span>
        <input type="checkbox" role="switch" bind:checked={fdept} disabled={!mayDept} /></label>
    {/if}
    {#if kind === 'tag' && fid != null}
      {@const tag = fid}
      <span class="t-cap">{t('ts.tagPeople')}</span>
      <div class="ppl">
        {#each team as x (x.person.id)}{@const on = !!x.tags?.includes(tag)}
          <label class="pp" class:locked={!mayTag(x)}><Avatar person={x.person} size={30} /><b class="ellipsis">{withNick(x.fullName, x.person)}</b>
            <input type="checkbox" checked={on} disabled={fdept !== !!setup?.tags.find((g) => g.id === tag)?.department || !(fdept ? mayDept : mayTag(x)) || tagging === x.person.id} onchange={() => tagPerson(x, tag, !on)} /></label>
        {/each}
      </div>
    {/if}
    <div class="fa">
      <Button kind="primary" size="s" loading={busy} disabled={!fname.trim()} onclick={save}>{t('common.save')}</Button>
      <Button kind="secondary" size="s" onclick={() => (kind = null)}>{t('common.cancel')}</Button>
      {#if fid != null && !ffixed}<button class="del" onclick={drop}>{t('ts.delete')}</button>{/if}
    </div>
  </div>
{/snippet}

<Sheet {overlay} full title={t('team.setup')}>
  <h2 class="t-h2 hd">{t('team.setup')}</h2>

  <section>
    <h3 class="t-cap">{t('ts.roles')}</h3>
    <p class="t-foot hint">{t('ts.rolesHint')}</p>
    <div class="items">
      <!-- the three official roles first: the President, one per club, is the level itself -->
      <div class="it"><span class="dot" style="--c:#FFB23D"></span><span class="rn"><b class="ellipsis">{ROLE_NAME.president}</b><i class="ellipsis">{t('ts.president')}</i></span><span class="n num">1</span></div>
      {#each setup?.roles ?? [] as r (r.id)}
        {#if kind === 'role' && fid === r.id}{@render form()}
        {:else}
          <button class="it" aria-expanded={mayEdit(r) ? undefined : peek === r.id} onclick={() => { if (mayEdit(r)) edit('role', r); else { haptic.select(); peek = peek === r.id ? null : r.id; } }}>
            <span class="dot" style="--c:{r.color}"></span><span class="rn"><b class="ellipsis">{r.name}</b><i class="ellipsis">{summary(r)}</i></span><span class="n num">{r.count}</span></button>
          {#if peek === r.id}
            <div class="peek" transition:fold>
              {#each TOGGLES as x (x.key)}{@const on = r.rights.includes(x.key)}
                <div class="pr" class:off={!on}><span class="ck">{#if on}<Check size={15} strokeWidth={3} />{/if}</span><span><b>{rightName(x.key)}</b><i class="t-foot">{t(`right.${x.key}.sub` as 'right.door.sub')}</i></span></div>
              {/each}
              <p class="t-foot">{t('ts.readOnly')}</p>
            </div>
          {/if}
        {/if}
      {/each}
      {#if kind === 'role' && fid === null}{@render form()}
      {:else if vice}<button class="add" onclick={() => edit('role')}><Plus size={17} />{t('ts.newRole')}</button>
      {:else if !setup?.roles.length}<p class="t-foot none">{t('ts.noRoles')}</p>{/if}
    </div>
  </section>

  <section>
    <h3 class="t-cap">{t('ts.tags')}</h3>
    <p class="t-foot hint">{t('ts.tagsHint')}</p>
    <div class="items">
      {#each setup?.tags ?? [] as g (g.id)}
        {#if kind === 'tag' && fid === g.id}{@render form()}
        {:else}
          <button class="it" disabled={!head} onclick={() => edit('tag', g)}><span class="dot" style="--c:{g.color}"></span><b class="ellipsis">{g.name}</b>{#if g.department}<i>{t('ts.deptMark')}</i>{/if}<span class="n num">{g.count}</span></button>
        {/if}
      {/each}
      {#if kind === 'tag' && fid === null}{@render form()}
      {:else if head}<button class="add" onclick={() => edit('tag')}><Plus size={17} />{t('ts.newTag')}</button>
      {:else if !setup?.tags.length}<p class="t-foot none">{t('ts.noTags')}</p>{/if}
    </div>
  </section>

  {#if setup?.bans?.length}
    <section>
      <h3 class="t-cap">{t('ts.bans')}</h3>
      <div class="items">
        {#each setup.bans as b (b.person.id)}
          <div class="it ban"><Avatar person={b.person} size={30} /><b class="ellipsis">{withNick(b.fullName, b.person)}</b>
            <button class="unban" onclick={() => unban(b.person.id)}>{t('ts.unban')}</button></div>
        {/each}
      </div>
    </section>
  {/if}
</Sheet>

<style>
  .rights { display: grid; gap: 6px; }
  .rights .switch, .form > .switch { padding: 10px 12px; background: var(--surface); }
  .rights .switch i { margin-top: 1px; }
  .rights .locked { opacity: 0.45; }
  .rn { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; text-align: left; }
  .hd { margin: 4px 0 8px; }
  section { margin-top: 14px; }
  .hint { margin: 4px 2px 10px; text-wrap: pretty; }
  .items { display: flex; flex-direction: column; gap: 6px; }
  .it { display: flex; align-items: center; gap: 10px; min-height: 48px; padding: 0 14px; border-radius: var(--r-m); background: var(--surface-2); text-align: left; }
  .it:not(:disabled):active { transform: scale(0.99); }
  .it:disabled { cursor: default; }
  .it b { flex: 1; min-width: 0; font: 620 15px/1.2 var(--font-text); }
  .it i { flex: none; font: 550 12.5px/1 var(--font-text); font-style: normal; color: var(--text-3); }
  .n { flex: none; min-width: 26px; height: 22px; padding: 0 7px; border-radius: 11px; background: var(--surface); color: var(--text-2); font: 650 12.5px/22px var(--font-text); text-align: center; }
  .dot { flex: none; width: 12px; height: 12px; border-radius: 50%; background: var(--c); box-shadow: 0 0 0 3px color-mix(in srgb, var(--c) 22%, transparent); }
  .add { display: flex; align-items: center; justify-content: center; gap: 6px; min-height: 44px; border-radius: var(--r-m); border: 1.5px dashed var(--line-2); color: var(--accent-text); font: 620 14.5px/1 var(--font-text); }
  .none { padding: 6px 2px; }
  .form { display: flex; flex-direction: column; gap: 10px; padding: 12px; border-radius: var(--r-m); background: var(--surface-2); box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--accent) 40%, transparent); }
  .form input:not([role="switch"]) { height: 44px; padding: 0 12px; border-radius: var(--r-s, 10px); background: var(--surface); color: var(--text); font: 550 16px/1 var(--font-text); }
  .colors { display: flex; flex-wrap: wrap; gap: 8px; }
  .colors button { width: 30px; height: 30px; border-radius: 50%; background: var(--c); box-shadow: inset 0 0 0 2px rgba(255, 255, 255, 0.25); transition: transform var(--t-fast); }
  .colors button.on { box-shadow: 0 0 0 2px var(--surface-2), 0 0 0 4px var(--c); }
  .colors button:active { transform: scale(0.9); }
  .fa { display: flex; align-items: center; gap: 8px; }
  .del { margin-left: auto; padding: 8px 4px; font: 620 14px/1 var(--font-text); color: var(--danger-text); }
  .peek { display: flex; flex-direction: column; gap: 10px; padding: 12px 14px; border-radius: var(--r-m); background: var(--surface-2); }
  .pr { display: flex; gap: 10px; align-items: flex-start; }
  .pr b { display: block; font: 620 14.5px/1.25 var(--font-text); }
  .pr i { font-style: normal; }
  .pr.off { opacity: 0.4; }
  .ck { flex: none; display: flex; align-items: center; justify-content: center; width: 20px; height: 20px; margin-top: 1px; border-radius: 50%; background: var(--surface); color: var(--accent-text); }
  .pr:not(.off) .ck { background: var(--accent); color: #fff; }
  .ppl { display: flex; flex-direction: column; max-height: 320px; overflow-y: auto; border-radius: var(--r-s, 10px); background: var(--surface); }
  .pp { display: flex; align-items: center; gap: 10px; min-height: 46px; padding: 0 12px; }
  .pp + .pp { box-shadow: inset 0 1px 0 var(--line); }
  .pp b { flex: 1; min-width: 0; font: 600 14.5px/1.2 var(--font-text); }
  .pp input { flex: none; width: 22px; height: 22px; accent-color: var(--accent); }
  .pp.locked { opacity: 0.45; }
  .ban { gap: 10px; }
  .unban { flex: none; height: 30px; padding: 0 12px; border-radius: var(--r-full); background: var(--accent-soft); color: var(--accent-text); font: 650 13px/1 var(--font-text); }
</style>
