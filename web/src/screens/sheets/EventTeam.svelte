<script lang="ts">
  // A team event on its sheet (server evteams.py): the sizes for everyone; once signed up, my team (its people, the
  // captain first) or that I wait to be placed. The captain invites by link (Telegram's share sheet or a copy), asks the
  // app for teammates, renames, removes someone; anyone leaves. Each tap answers at once and goes back if refused.
  import UsersRound from '@lucide/svelte/icons/users-round';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import Copy from '@lucide/svelte/icons/copy';
  import Search from '@lucide/svelte/icons/search';
  import { api, ApiErr, type EventFull, type EventTeam, type EventTeams } from '../../lib/api';
  import { errorText } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  let { detail, going, onchange }: { detail: EventFull; going: boolean; onchange: (d: EventFull) => void } = $props();
  const tm = $derived(detail.teams!);
  const team = $derived(tm.team);
  const me = $derived(session.me?.id);
  const captain = $derived(!!team && team.captain === me);
  const link = $derived(team?.token ? `https://t.me/KBTUappBot?startapp=et_${team.token}` : '');

  const set = (x: Partial<EventTeams>) => onchange({ ...detail, teams: { ...tm, ...x } });
  const setTeam = (x: EventTeam | null) => set({ team: x });
  const fail = (e: unknown) => { haptic.error(); say(e instanceof ApiErr ? errorText(e) : t('common.error'), 'pleading_face_3d'); };
  // optimistic: the change at once, the server's sheet after, the old one back on a no
  async function write(next: EventTeam | null, call: () => Promise<EventFull>, ok?: () => void) {
    const was = detail;
    setTeam(next); haptic.tap();
    try { onchange(await call()); ok?.(); } catch (e) { onchange(was); fail(e); }
  }

  const share = () => { haptic.tap(); openLink(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(t('tm.inviteMsg', { title: detail.title }))}`); };
  async function copy() {
    try { await navigator.clipboard.writeText(link); haptic.ok(); say(t('tm.copied'), 'sparkles_3d'); } catch { fail(null); }
  }
  const setOpen = (on: boolean) => team && write({ ...team, open: on }, () => api.teamEdit(detail.id, { open: on }));
  async function rename() {
    if (!team) return;
    const name = await sheets.askText({ title: t('tm.rename'), ok: t('common.save'), cancel: t('common.cancel'), placeholder: t('tm.name'), max: 40, value: team.name, line: true });
    if (name?.trim() && name.trim() !== team.name) void write({ ...team, name: name.trim() }, () => api.teamEdit(detail.id, { name: name.trim() }));
  }
  async function remove(p: EventTeam['members'][number]) {
    if (!team || !(await sheets.ask({ title: t('tm.removeAsk', { name: p.name }), text: t('tm.removeText'), ok: t('tm.remove'), cancel: t('common.cancel'), danger: true }))) return;
    void write({ ...team, members: team.members.filter((x) => x.id !== p.id) }, () => api.teamRemove(detail.id, p.id));
  }
  async function leave() {
    if (!(await sheets.ask({ title: t('tm.leaveAsk'), text: t('tm.leaveText'), ok: t('tm.leave'), cancel: t('common.cancel'), danger: true }))) return;
    void write(null, () => api.teamLeave(detail.id), () => say(t('tm.left'), 'waving_hand_3d_default'));
  }
  let making = $state(false);
  async function create() {
    const name = await sheets.askText({ title: t('tm.create'), ok: t('tm.create'), cancel: t('common.cancel'), placeholder: t('tm.name'), max: 40, line: true });
    if (!name?.trim() || making) return;
    making = true; haptic.tap();
    try { onchange(await api.teamCreate(detail.id, name.trim())); haptic.ok(); say(t('tm.created'), 'party_popper_3d'); } catch (e) { fail(e); }
    finally { making = false; }
  }
</script>

{#snippet edit()}<Button kind="gray" size="s" onclick={rename}>{t('tm.rename')}</Button>{/snippet}
{#if team}
  <Group caption={t('tm.yours')} footnote={captain && !tm.locked && team.members.length < tm.max ? t('tm.openHint') : undefined}>
    <Row title={team.name} subtitle={tm.locked ? t('tm.locked') : t('tm.of', { n: team.members.length, max: tm.max })} trailing={captain && !tm.locked ? edit : undefined} />
    {#each team.members as p (p.id)}
      {#snippet drop()}<Button kind="gray" size="s" onclick={() => remove(p)}>{t('tm.remove')}</Button>{/snippet}
      <Row dense title={p.id === me ? `${p.name} · ${t('tm.you')}` : p.name} subtitle={p.id === team.captain ? t('tm.captain') : undefined}
        trailing={captain && p.id !== me && !tm.locked ? drop : undefined}>
        {#snippet lead()}<Avatar person={p} size={32} />{/snippet}
      </Row>
    {/each}
    {#if captain && !tm.locked && link && team.members.length < tm.max}<!-- a full team has nobody to invite -->
      <Row icon={UserPlus} tone="action" title={t('tm.invite')} onclick={share} />
      <Row icon={Copy} title={t('tm.copy')} onclick={copy} />
      <Row icon={Search} title={t('tm.open')} accessory="switch" checked={team.open} onchange={setOpen} />
    {/if}
  </Group>
  {#if !tm.locked}<span class="out"><Button kind="plain" size="s" onclick={leave}>{t('tm.leave')}</Button></span>{/if}
{:else if going && !tm.locked}
  <Group footnote={t('tm.waitingSub')}>
    <Row icon={UsersRound} title={t('tm.waiting')} subtitle={t('tm.size', { min: tm.min, max: tm.max })} />
    <Row tone="add" title={t('tm.create')} disabled={making} onclick={create} />
  </Group>
{:else}
  <Group><Row icon={UsersRound} title={t('tm.event')} subtitle={t('tm.size', { min: tm.min, max: tm.max })} /></Group>
{/if}

<style>
  .out { align-self: center; --plain-ink: var(--danger-text); }
</style>
