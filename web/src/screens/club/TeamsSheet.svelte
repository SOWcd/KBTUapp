<script lang="ts">
  // A team event's teams, the organizers' (the "events" right; server evteams.py): every team with its people (the
  // captain first), then those with no team yet; "Form teams" fills the teams looking for people and makes new ones of
  // the rest; a person's ⌃⌄ moves them to another team or to none, after a confirm. All fixed once the event starts.
  // Someone without the teams' own consent waits alone, marked at the row's end, never placed (server evteams.py).
  import { onMount } from 'svelte';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import { api, ApiErr, type Id, type PersonRef, type TeamsBoard } from '../../lib/api';
  import { errorText } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import type { MenuItem } from '../../ui/menu';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();
  let b = $state<TeamsBoard | null>(null);
  onMount(() => { api.teams(id).then((x) => (b = x)).catch(() => {}); });
  const fail = (e: unknown) => { haptic.error(); say(e instanceof ApiErr ? errorText(e) : t('common.error'), 'pleading_face_3d'); };

  // the move at once (the same rules as the server's: a team that empties goes), the server's list after
  function moved(x: TeamsBoard, p: PersonRef, to: Id | null): TeamsBoard {
    const teams = x.teams.map((tm) => ({ ...tm, members: tm.members.filter((m) => m.id !== p.id) }))
      .map((tm) => (tm.id === to ? { ...tm, members: [...tm.members, p] } : tm))
      .filter((tm) => tm.members.length)
      .map((tm) => ({ ...tm, captain: tm.members[0].id }));
    return { ...x, teams, solo: to === null ? [...x.solo.filter((m) => m.id !== p.id), { ...p, consent: true }] : x.solo.filter((m) => m.id !== p.id) };
  }
  async function move(p: PersonRef, to: Id | null, name: string) {
    if (!b || !(await sheets.ask({ title: to === null ? t('tm.toSoloAsk', { name: p.name }) : t('tm.moveAsk', { name: p.name, team: name }),
      text: to === null ? undefined : t('tm.moveText'), ok: t('tm.move'), cancel: t('common.cancel') }))) return;
    const was = b;
    b = moved(b, p, to); haptic.tap();
    try { b = await api.teamsMove(id, p.id, to); haptic.ok(); } catch (e) { b = was; fail(e); }
  }
  const menuOf = (p: PersonRef, from: Id | null): MenuItem[] => !b || b.locked ? [] : [
    ...b.teams.filter((tm) => tm.id !== from).map((tm) => ({ label: `${tm.name} · ${tm.members.length}/${b!.max}`, disabled: tm.members.length >= b!.max, onselect: () => move(p, tm.id, tm.name) })),
    ...(from !== null ? [{ label: t('tm.solo'), onselect: () => move(p, null, '') }] : []),
  ];

  let forming = $state(false);
  async function form() {
    if (!b || forming || !(await sheets.ask({ title: t('tm.formAsk'), text: t('tm.formText'), ok: t('tm.form'), cancel: t('common.cancel') }))) return;
    forming = true; haptic.tap();
    try {
      b = await api.teamsForm(id);
      const skipped = b.noConsent ? ' · ' + t('tm.skipped', { n: b.noConsent }) : ''; // no consent yet: not placed
      if (!b.placed) { haptic.soft(); say(t('tm.nothing') + skipped, 'thinking_face_3d'); }
      else { haptic.ok(); say((b.left ? t('tm.formedLeft', { n: b.placed, left: b.left }) : t('tm.formed', { n: b.placed })) + skipped, 'party_popper_3d'); }
    } catch (e) { fail(e); }
    finally { forming = false; }
  }
</script>

<Sheet {overlay} icon={UsersRound} full title={t('tm.board')}>
  {#if b}
    <p class="t-foot sub">{t('tm.size', { min: b.min, max: b.max })}{b.locked ? ' · ' + t('tm.locked') : ''}</p>
    {#if !b.teams.length && !b.solo.length}
      <EmptyState inline text={t('tm.none')} />
    {:else}
      <div class="list">
        {#each b.teams as tm (tm.id)}
          <Group caption="{tm.name} · {tm.members.length}/{b.max}{tm.open && tm.members.length < b.max ? ' · ' + t('tm.looking') : ''}">
            {#each tm.members as p (p.id)}
              <Row dense title={p.name} subtitle={p.id === tm.captain ? t('tm.captain') : undefined} menu={b.locked ? undefined : menuOf(p, tm.id)}>
                {#snippet lead()}<Avatar person={p} size={32} />{/snippet}
              </Row>
            {/each}
          </Group>
        {/each}
        {#if b.solo.length}
          <Group caption="{t('tm.solo')} · {b.solo.length}">
            {#each b.solo as p (p.id)}
              <Row dense title={p.name} value={p.consent ? undefined : t('tm.noConsent')} menu={b.locked || !b.teams.length || !p.consent ? undefined : menuOf(p, null)}>
                {#snippet lead()}<Avatar person={p} size={32} />{/snippet}
              </Row>
            {/each}
          </Group>
        {/if}
      </div>
    {/if}
  {/if}
  {#snippet footer()}
    {#if b && !b.locked}<Button kind="primary" size="l" full loading={forming} disabled={!b.solo.length} onclick={form}>{t('tm.form')}</Button>{/if}
  {/snippet}
</Sheet>

<style>
  .sub { margin: 2px var(--s-1) 0; }
  .list { display: flex; flex-direction: column; gap: var(--s-5); margin-top: var(--s-4); }
</style>
