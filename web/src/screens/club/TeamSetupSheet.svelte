<script lang="ts">
  // Team 2.0 (SPEC §2b), from Team: the club's own roles — a name, a colour and toggles of rights, as admin rights in
  // Telegram, made by whoever runs the team, only with rights they
  // have and below their own level — and its tags, groups of people ("people"). The team runner also sees who is banned
  // and can lift it. Who has a tag is set here too, in the tag (owner, Oct 14: not on the fly in a person's card, where
  // a stray tap tagged someone).
  import { api, ApiErr, type ClubLevel, type ClubRole, type ClubTag, type Id, type Right, type TeamMember, type TeamSetup } from '../../lib/api';
  import { data, loadTeam } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { phrase } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { hit } from '../../lib/search';
  import { haptic } from '../../lib/tg';
  import { inLang, isAbove, may, RANK, RIGHTS, ROLE_NAME, TEAM_COLORS, withNick } from '../../lib/perms';
  import Sheet from '../../ui/Sheet.svelte';
  import UserCog from '@lucide/svelte/icons/user-cog';
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Field from '../../ui/Field.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import SearchField from '../../ui/SearchField.svelte';

  let { overlay, org, onchange }: { overlay: Overlay; org: Id; onchange?: () => void } = $props();

  const m = $derived(session.me?.memberships.find((x) => x.org.id === org) ?? null);
  const mine = $derived(m?.role ?? null);
  const vice = $derived(may(m, 'team'));
  const head = $derived(may(m, 'people'));
  // a right I can put in a role: one I have, below my own level (a role level with mine would outrank no one I can manage)
  const givable = (r: { key: Right; level: ClubLevel }) => !!mine && may(m, r.key) && RANK[r.level] < RANK[mine] && (!ffixed || RANK[r.level] <= RANK[ffixed]);

  let setup = $state<TeamSetup | null>(null);
  const load = () => api.teamSetup(org).then((x) => (setup = x)).catch(() => say(t('common.error'), 'warning_3d'));
  $effect(() => { void load(); });

  // one form open at a time: a role or a tag, new (id null) or an edit
  let kind = $state<'role' | 'tag' | 'assign' | null>(null);
  let fid = $state<Id | null>(null);
  let fname = $state('');
  // a role's title is typed once in any language; the AI fills the other two ("Translations"), never one corrected by hand
  type Lang = 'ru' | 'kk' | 'en';
  const LANGS: Lang[] = ['ru', 'kk', 'en'];
  // the server's ai.lang_of: Kazakh's own letters, else Cyrillic is Russian, else English
  const langOf = (x: string): Lang => (/[\u04d9\u0493\u049b\u04a3\u04e9\u04b1\u04af\u04bb\u0456\u04d8\u0492\u049a\u04a2\u04e8\u04b0\u04ae\u04ba\u0406]/.test(x) ? 'kk' : /[\u0400-\u04ff]/.test(x) ? 'ru' : 'en');
  let ftr = $state<Record<Lang, string>>({ ru: '', kk: '', en: '' });
  let fwas: Record<Lang, string> = { ru: '', kk: '', en: '' }; // as opened: a changed one counts as corrected
  let fhand = $state<Lang[]>([]);
  let trOpen = $state(false);
  const fsrc = $derived(langOf(fname));
  const others = $derived(LANGS.filter((k) => k !== fsrc));
  let fcolor = $state(TEAM_COLORS[0]);
  let frights = $state<Right[]>([]);
  let ffixed = $state<ClubLevel | null>(null); // an official role: its name and level stay, rights up to the level
  let fdept = $state(false); // a tag that is a department (PLAN 47)
  let busy = $state(false);
  function edit(k: 'role' | 'tag', x?: ClubRole | ClubTag) {
    const r = x && 'rights' in x ? x : null;
    const slots: Record<Lang, string> = { ru: r?.name ?? '', kk: r?.nameKk ?? '', en: r?.nameEn ?? '' };
    kind = k; fid = x?.id ?? null; fname = r ? slots[r.src ?? 'ru'] || r.name : x?.name ?? '';
    // still translating: the Russian slot holds the typed text, not a translation
    const shown = (l: Lang) => (r?.hand?.includes(l) || !r?.translating ? slots[l] : '');
    ftr = { ru: shown('ru'), kk: shown('kk'), en: shown('en') }; fwas = { ...ftr }; fhand = (r?.hand ?? []) as Lang[]; trOpen = false;
    fcolor = x?.color ?? TEAM_COLORS[(setup?.[k === 'role' ? 'roles' : 'tags'].length ?? 0) % TEAM_COLORS.length];
    frights = x && 'rights' in x ? [...x.rights] : ['door'];
    ffixed = x && 'fixed' in x && x.fixed ? x.level : null;
    fdept = !!(x && 'department' in x && x.department);
    haptic.select();
  }
  const done = (x: TeamSetup) => { setup = x; kind = null; haptic.ok(); onchange?.(); };
  const oops = (e: unknown) => {
    haptic.error();
    say(e instanceof ApiErr && e.message === 'taken' ? t('ts.taken') : e instanceof ApiErr && e.message === 'many' ? t('ts.many') : t('common.error'), 'warning_3d');
  };
  // every correction kept: one corrected before or changed now, not emptied (empty: the AI's again)
  const corrected = () => Object.fromEntries(others.filter((l) => ftr[l].trim() && (fhand.includes(l) || ftr[l] !== fwas[l])).map((l) => [l, ftr[l]]));
  async function save() {
    if (!kind || busy || !fname.trim()) return;
    busy = true;
    try { done(kind === 'role' ? await api.saveRole(org, { name: fname, tr: corrected(), color: fcolor, rights: frights }, fid ?? undefined) : await api.saveTag(org, { name: fname, color: fcolor, department: fdept }, fid ?? undefined)); say(phrase('say.tsSaved'), 'sparkles_3d'); }
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
  // a department: a person may be in several, ticking adds or takes this one (a Head does their own in Team's card)
  const mayDept = $derived(head && RANK[mine ?? 'member'] >= RANK.vice);
  async function tagPerson(x: TeamMember, tag: Id, on: boolean) {
    tagging = x.person.id; haptic.select();
    try {
      const saved = !!setup?.tags.find((g) => g.id === tag)?.department; // as the server has it, not the unsaved switch
      data.team[org] = await api.updateMember(org, x.person.id, saved ? (on ? { addDept: tag } : { dropDept: tag })
        : { tags: on ? [...(x.tags ?? []), tag] : (x.tags ?? []).filter((g) => g !== tag) });
      void load(); onchange?.();
    } catch (e) { oops(e); } finally { tagging = null; }
  }
  // one role to many at once (a president, Nov 6): tick who holds it, Save sends them all; those I may not change stay as they are
  let picked = $state<Id[]>([]);
  let q = $state('');
  const mayAssign = (x: TeamMember) => vice && !!mine && x.person.id !== session.me?.id && RANK[mine] > RANK[x.role];
  const found = $derived(q.trim() ? team.filter((x) => hit(q, [withNick(x.fullName, x.person)])) : team);
  async function assign() {
    haptic.select(); q = '';
    if (!data.team[org]) await loadTeam(org); // Team loads it with the app; this is the rare cold path
    picked = team.filter((x) => x.roleId === fid).map((x) => x.person.id); kind = 'assign';
  }
  // the preview (Astra): who gets it and who loses it on Save, by name; nothing changing, nothing to save
  const names = (xs: TeamMember[]) => xs.map((x) => withNick(x.fullName, x.person)).join(', ');
  const gain = $derived(team.filter((x) => mayAssign(x) && x.roleId !== fid && picked.includes(x.person.id)));
  const lose = $derived(team.filter((x) => mayAssign(x) && x.roleId === fid && !picked.includes(x.person.id)));
  const preview = $derived([gain.length ? t('ts.assignGain', { names: names(gain) }) : '', lose.length ? t('ts.assignLose', { names: names(lose) }) : '']
    .filter(Boolean).join('. ') || t('ts.assignNone'));
  const pick = (x: TeamMember) => { haptic.tap(); picked = picked.includes(x.person.id) ? picked.filter((i) => i !== x.person.id) : [...picked, x.person.id]; };
  async function saveAssign() {
    if (fid == null || busy) return;
    busy = true;
    try {
      const r = await api.assignRole(org, fid, picked);
      data.team[org] = r.team; done(r.setup);
      if (r.skipped) say(t('ts.assignSkipped', { n: r.skipped }), 'warning_3d'); else say(phrase('say.tsSaved'), 'sparkles_3d');
    } catch (e) { oops(e); } finally { busy = false; }
  }
  const toggle = (k: Right, on: boolean) => { haptic.tap(); frights = on ? [...frights, k] : frights.filter((x) => x !== k); };
  const rightName = (k: Right) => t(`right.${k}` as 'right.door');
  // the door is every member's, not a toggle; event reports only while the server has them on (REPORTS)
  const listed = (k: Right) => k !== 'door' && (k !== 'reports' || !!session.me?.reports);
  const TOGGLES = $derived(RIGHTS.filter((x) => listed(x.key)));
  const summary = (r: ClubRole) => { const on = r.rights.filter(listed); return on.length ? on.map(rightName).join(', ') : t('ts.noRights'); };
</script>

{#snippet dot(c: string)}<span class="dot" style="--c:{c}"></span>{/snippet}

<!-- the open role or tag, in place of its list -->
{#snippet assigning()}
  <div class="form">
    <Group><Row title={fname}>{#snippet lead()}{@render dot(fcolor)}{/snippet}</Row></Group>
    <SearchField bind:value={q} placeholder={t('ts.assignFind')} />
    <Group footnote={preview}>
      {#each found as x (x.person.id)}
        <Row dense title={withNick(x.fullName, x.person)} accessory="check" checked={picked.includes(x.person.id)} disabled={!mayAssign(x)} onclick={() => pick(x)}>
          {#snippet lead()}<Avatar person={x.person} size={30} tappable={false} />{/snippet}
        </Row>
      {/each}
    </Group>
    <div class="fa">
      <Button kind="primary" size="s" loading={busy} disabled={!gain.length && !lose.length} onclick={saveAssign}>{t('common.save')}</Button>
      <Button kind="secondary" size="s" onclick={() => (kind = 'role')}>{t('common.cancel')}</Button>
    </div>
  </div>
{/snippet}

{#snippet form()}
  <div class="form">
    {#if ffixed}<Group><Row title={fname}>{#snippet lead()}{@render dot(fcolor)}{/snippet}</Row></Group><!-- an official role's name is the app's own -->
    {:else}
      <Field label={kind === 'role' ? t('ts.rolePh') : t('ts.tagPh')} bind:value={fname} maxlength={24} enterkeyhint="done" />
      {#if kind === 'role'}
        <Group footnote={trOpen ? t('ts.trsSub') : undefined}>
          <Row dense title={t('ts.trs')} subtitle={others.map((l) => ftr[l]).filter(Boolean).join(' \u00b7 ') || t('ts.trAuto')} accessory="disclosure" open={trOpen}
            onclick={() => { haptic.select(); trOpen = !trOpen; }} />
        </Group>
        {#if trOpen}
          <!-- engine: Field could pass `lang` to its input -->
          {#each others as l (l)}<Field label={t(`ts.role.${l}`)} bind:value={ftr[l]} placeholder={t('ts.trAuto')} maxlength={24} enterkeyhint="done" />{/each}
        {/if}
      {/if}
    {/if}
    <div class="colors">
      {#each TEAM_COLORS as c (c)}<button class:on={fcolor === c} style="--c:{c}" onclick={() => (fcolor = c)} aria-label={c}></button>{/each}
    </div>
    {#if kind === 'role'}
      <Group caption={t('ts.level')} footnote={TOGGLES.some((r) => !givable(r)) ? t('ts.locked') : undefined}>
        {#each TOGGLES as r (r.key)}
          <Row title={rightName(r.key)} subtitle={t(`right.${r.key}.sub` as 'right.door.sub')} accessory="switch" disabled={!givable(r)}
            checked={frights.includes(r.key)} onchange={(on) => toggle(r.key, on)} />
        {/each}
      </Group>
    {:else}
      <Group footnote={t('ts.isDeptSub')}>
        <Row title={t('ts.isDept')} accessory="switch" checked={fdept} disabled={!mayDept} onchange={(on) => (fdept = on)} />
      </Group>
    {/if}
    {#if kind === 'role' && fid != null && !ffixed}
      <Group><Row title={t('ts.assign')} accessory="chevron" onclick={assign} /></Group>
    {/if}
    {#if kind === 'tag' && fid != null}
      {@const tag = fid}
      <Group caption={t('ts.tagPeople')}>
        {#each team as x (x.person.id)}{@const on = !!x.tags?.includes(tag)}
          <Row dense title={withNick(x.fullName, x.person)} accessory="check" checked={on} onclick={() => tagPerson(x, tag, !on)}
            disabled={fdept !== !!setup?.tags.find((g) => g.id === tag)?.department || !(fdept ? mayDept : mayTag(x)) || tagging === x.person.id}>
            {#snippet lead()}<Avatar person={x.person} size={30} tappable={false} />{/snippet}
          </Row>
        {/each}
      </Group>
    {/if}
    <div class="fa">
      <Button kind="primary" size="s" loading={busy} disabled={!fname.trim()} onclick={save}>{t('common.save')}</Button>
      <Button kind="secondary" size="s" onclick={() => (kind = null)}>{t('common.cancel')}</Button>
      {#if fid != null && !ffixed}<span class="del"><Button kind="destructive" size="s" onclick={drop}>{t('ts.delete')}</Button></span>{/if}
    </div>
  </div>
{/snippet}

<Sheet {overlay} icon={UserCog} full title={t('team.setup')}>
  <div class="page">
    {#if kind === 'role'}<section class="sec"><h3 class="cap">{t('ts.roles')}</h3>{@render form()}</section>
    {:else if kind === 'assign'}<section class="sec"><h3 class="cap">{t('ts.assign')}</h3>{@render assigning()}</section>
    {:else}
      <Group caption={t('ts.roles')} footnote={t('ts.rolesHint')}>
        <!-- the three official roles first: the President, one per club, is the level itself -->
        <Row dense title={ROLE_NAME.president} subtitle={t('ts.president')} value="1">{#snippet lead()}{@render dot('var(--gold)')}{/snippet}</Row>
        {#each setup?.roles ?? [] as r (r.id)}
          <Row dense title={inLang(r.name, r.nameKk, r.nameEn)} subtitle={summary(r)} value={String(r.count)}
            accessory={mayEdit(r) ? 'chevron' : 'disclosure'} open={peek === r.id}
            onclick={() => { if (mayEdit(r)) edit('role', r); else { haptic.select(); peek = peek === r.id ? null : r.id; } }}>
            {#snippet lead()}{@render dot(r.color)}{/snippet}
          </Row>
          {#if peek === r.id}
            <!-- a role I can't edit, open to read: what it may and may not do -->
            {#each TOGGLES as x (x.key)}
              <Row dense title={rightName(x.key)} subtitle={t(`right.${x.key}.sub` as 'right.door.sub')} accessory="check" checked={r.rights.includes(x.key)} />
            {/each}
            <EmptyState inline text={t('ts.readOnly')} />
          {/if}
        {/each}
        {#if vice}<Row tone="add" title={t('ts.newRole')} onclick={() => edit('role')} />
        {:else if !setup?.roles.length}<EmptyState inline text={t('ts.noRoles')} />{/if}
      </Group>
    {/if}

    {#if kind === 'tag'}<section class="sec"><h3 class="cap">{t('ts.tags')}</h3>{@render form()}</section>
    {:else}
      <Group caption={t('ts.tags')} footnote={t('ts.tagsHint')}>
        <!-- departments first: recruitment and meetings look for them here -->
        {#each [...(setup?.tags ?? [])].sort((a, b) => +!!b.department - +!!a.department) as g (g.id)}
          <Row dense title={g.name} subtitle={g.department ? t('ts.deptMark') : undefined} value={String(g.count)} accessory={head ? 'chevron' : 'none'}
            onclick={head ? () => edit('tag', g) : undefined}>
            {#snippet lead()}{@render dot(g.color)}{/snippet}
          </Row>
        {/each}
        {#if head}<Row tone="add" title={t('ts.newTag')} onclick={() => edit('tag')} />
        {:else if !setup?.tags.length}<EmptyState inline text={t('ts.noTags')} />{/if}
      </Group>
    {/if}

    {#if setup?.bans?.length}
      <Group caption={t('ts.bans')}>
        {#each setup.bans as b (b.person.id)}
          <Row dense title={withNick(b.fullName, b.person)}>
            {#snippet lead()}<Avatar person={b.person} size={36} />{/snippet}
            {#snippet trailing()}<Button kind="secondary" size="s" onclick={() => unban(b.person.id)}>{t('ts.unban')}</Button>{/snippet}
          </Row>
        {/each}
      </Group>
    {/if}
  </div>
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-3); }
  .sec { display: flex; flex-direction: column; }
  /* Group's caption, over the open form (engine: Group could take a form, not only Rows) */
  .cap { margin: 0 var(--s-1) 10px; font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; }
  .dot { flex: none; display: block; width: 12px; height: 12px; margin: 0 var(--s-1); border-radius: 50%; background: var(--c); }
  .form { display: flex; flex-direction: column; gap: var(--s-4); }
  .colors { display: flex; flex-wrap: wrap; gap: var(--s-2); padding: 0 var(--s-1); }
  .colors button { width: 30px; height: 30px; border-radius: 50%; background: var(--c); box-shadow: inset 0 0 0 2px rgba(255, 255, 255, 0.25); transition: transform var(--t-fast); }
  .colors button.on { box-shadow: 0 0 0 2px var(--bg), 0 0 0 4px var(--c); }
  .colors button:active { transform: scale(0.9); }
  .fa { display: flex; align-items: center; gap: var(--s-2); }
  .del { margin-left: auto; }
</style>
