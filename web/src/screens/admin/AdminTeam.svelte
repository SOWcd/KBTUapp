<script lang="ts">
  // Admin → the app's team: the owner gives and takes the admin role, an admin gives the moderator role
  // and bans; nobody touches the owner, himself or (unless the owner) another admin. A ban needs a reason he will
  // read; it takes the role away. Found by @username among everyone who opened the app.
  import UsersRound from '@lucide/svelte/icons/users-round';
  import Search from '@lucide/svelte/icons/search';
  import { api, ApiErr, type Staff, type StaffRow, type PlatformRole } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { fold } from '../../ui/fold';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Avatar from '../../ui/Avatar.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  let staff = $state<Staff | null>(null);
  $effect(() => { api.staff().then((s) => (staff = s)).catch(() => say(t('common.error'), 'pleading_face_3d')); });

  let q = $state(''), found = $state<StaffRow | null>(null), looking = $state(false);
  async function find() {
    const name = q.trim().replace(/^@/, '');
    if (!/^[A-Za-z0-9_]{4,32}$/.test(name)) { haptic.error(); say(t('staff.badName'), 'raising_hands_3d_default'); return; }
    looking = true;
    try {
      const p = await api.staffFind(name);
      // already on a list below: open that row instead of a second one
      found = staff && [...staff.team, ...staff.banned].some((x) => x.person.id === p.person.id) ? null : p;
      open = p.person.id; banning = false; haptic.select();
    }
    catch (x) { found = null; haptic.error(); say(x instanceof ApiErr && x.code === 'not_found' ? t('staff.notFound') : t('common.error'), 'pleading_face_3d'); }
    finally { looking = false; }
  }

  let open = $state<number | null>(null), banning = $state(false), why = $state(''), busy = $state(false);
  const mine = (p: StaffRow) => p.person.id === session.me?.id;
  const touchable = (p: StaffRow) => !!staff && !p.owner && !mine(p) && (p.role !== 'admin' || staff.owner);
  const isBanned = (p: StaffRow) => !!p.banned || !!staff?.banned.some((b) => b.person.id === p.person.id);
  const ROLES: PlatformRole[] = ['user', 'moderator', 'admin'];

  async function act(go: () => Promise<Staff>, done: string, emoji: string) {
    busy = true;
    try {
      staff = await go();
      // once on a list below, the search result goes (one row per person); a plain user again stays found
      if (found && [...staff.team, ...staff.banned].some((x) => x.person.id === found!.person.id)) { found = null; q = ''; }
      else if (found) found = { ...found, role: 'user', banned: false, banReason: null };
      banning = false; why = ''; haptic.ok(); say(done, emoji);
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { busy = false; }
  }
  const setRole = (p: StaffRow, role: PlatformRole) => p.role !== role && act(() => api.setStaff(p.person.id, role), t('staff.roleSet'), 'sparkles_3d');
  const ban = (p: StaffRow) => act(() => api.ban(p.person.id, true, why.trim()), t('staff.bannedToast'), 'locked_3d');
  const unban = (p: StaffRow) => act(() => api.ban(p.person.id, false), t('staff.unbannedToast'), 'raising_hands_3d_default');
</script>

{#snippet row(p: StaffRow)}
  <div class="pr">
    <button class="who" aria-expanded={open === p.person.id} onclick={() => { haptic.select(); open = open === p.person.id ? null : p.person.id; banning = false; }}>
      <Avatar person={p.person} size={40} tappable={false} />
      <span class="tx"><b class="ellipsis">{p.person.name}</b><i class="ellipsis">{p.username ? '@' + p.username : ''}{p.banReason ? ' · ' + p.banReason : ''}</i></span>
      <em class="pill {p.owner ? 'owner' : isBanned(p) ? 'banned' : p.role}">{p.owner ? t('staff.owner') : isBanned(p) ? t('staff.banned') : t(`staff.role.${p.role}`)}</em>
    </button>
    {#if open === p.person.id}
      <div class="acts" transition:fold>
        <button class="lnk" onclick={() => sheets.person(p.person.id)}>{t('staff.profile')}</button>
        {#if !touchable(p)}
          <p class="t-foot">{p.owner ? t('staff.ownerNote') : mine(p) ? t('staff.selfNote') : t('staff.adminNote')}</p>
        {:else if isBanned(p)}
          <Button kind="neutral" size="s" loading={busy} onclick={() => unban(p)}>{t('staff.unban')}</Button>
        {:else}
          <div class="roles">
            {#each ROLES.filter((r) => r !== 'admin' || staff?.owner) as r (r)}
              <button class:on={p.role === r} disabled={busy} onclick={() => setRole(p, r)}>{t(`staff.role.${r}`)}</button>
            {/each}
          </div>
          {#if banning}
            <textarea bind:value={why} rows="2" maxlength="300" placeholder={t('staff.reasonPh')}></textarea>
            <div class="ra"><Button kind="neutral" size="s" onclick={() => (banning = false)}>{t('common.cancel')}</Button>
              <Button kind="danger" size="s" loading={busy} disabled={why.trim().length < 3} onclick={() => ban(p)}>{t('staff.ban')}</Button></div>
          {:else}
            <button class="lnk bad" onclick={() => { banning = true; why = ''; }}>{t('staff.ban')}…</button>
          {/if}
        {/if}
      </div>
    {/if}
  </div>
{/snippet}

<Sheet {overlay} full title={t('staff.title')} icon={UsersRound}>
  <form class="find" onsubmit={(e) => { e.preventDefault(); void find(); }}>
    <label class="srch"><Search size={17} /><input bind:value={q} placeholder="@username" autocapitalize="off" autocorrect="off" spellcheck="false" enterkeyhint="search" /></label>
    <Button kind="secondary" size="m" type="submit" loading={looking}>{t('staff.find')}</Button>
  </form>
  {#if found}<div class="rows surface">{@render row(found)}</div>{/if}

  {#if staff}
    <h3 class="t-cap sh">{t('staff.now')}</h3>
    <div class="rows surface">{#each staff.team as p (p.person.id)}{@render row(p)}{/each}</div>
    <p class="t-foot note">{staff.owner ? t('staff.howOwner') : t('staff.howAdmin')}</p>
    {#if staff.banned.length}
      <h3 class="t-cap sh">{t('staff.bannedList')}</h3>
      <div class="rows surface">{#each staff.banned as p (p.person.id)}{@render row(p)}{/each}</div>
    {/if}
  {/if}
</Sheet>

<style>
  .find { display: flex; gap: 8px; align-items: center; min-width: 0; }
  .find > :global(.btn) { flex: none; }
  .srch { flex: 1; min-width: 0; display: flex; align-items: center; gap: 8px; height: 44px; padding: 0 14px; border-radius: var(--r-full); background: var(--surface-2); color: var(--text-2); }
  .srch input { flex: 1; min-width: 0; background: none; border: 0; outline: 0; font: 550 15px/1 var(--font-text); color: var(--text); }
  .rows { display: flex; flex-direction: column; margin-top: 10px; padding: 4px 0; }
  .pr + .pr { border-top: 1px solid var(--line); }
  .who { width: 100%; display: flex; align-items: center; gap: 12px; padding: 10px 14px; text-align: left; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 650 15px/1.25 var(--font-text); }
  .tx i { font: 500 13px/1.3 var(--font-text); font-style: normal; color: var(--text-2); }
  .pill { flex: none; padding: 4px 10px; border-radius: var(--r-full); background: var(--surface-2); font: 700 12px/1.2 var(--font-text); font-style: normal; color: var(--text-2); }
  .pill.owner { background: var(--accent); color: var(--on-accent); }
  .pill.admin { background: var(--accent-soft); color: var(--accent-text); }
  .pill.moderator { background: color-mix(in srgb, var(--success, #2FBF71) 16%, transparent); color: var(--success, #2FBF71); }
  .pill.banned { background: color-mix(in srgb, var(--danger) 16%, transparent); color: var(--danger-text); }
  .acts { display: flex; flex-direction: column; align-items: flex-start; gap: 10px; padding: 2px 14px 14px 66px; }
  .roles { display: flex; flex-wrap: wrap; gap: 6px; }
  .roles button { height: 36px; padding: 0 14px; border-radius: var(--r-full); background: var(--surface-2); font: 620 14px/1 var(--font-text); color: var(--text-2); }
  .roles button.on { background: var(--text); color: var(--bg); }
  textarea { width: 100%; padding: 10px 12px; border-radius: var(--r-m); background: var(--surface-2); border: 0; font: 500 14.5px/1.35 var(--font-text); color: var(--text); resize: none; }
  .ra { display: flex; gap: 8px; }
  .lnk { padding: 2px 0; font: 620 14px/1.2 var(--font-text); color: var(--accent-text); }
  .lnk.bad { color: var(--danger-text); }
  .sh { margin: 20px 2px 0; }
  .note { margin: 8px 4px 0; }
</style>
