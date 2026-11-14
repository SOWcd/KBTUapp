<script lang="ts">
  // The Mark screen's «People» (owner, Nov 14, after the Talent Show: the Senate wanted its whole roster by department,
  // came / not came, many without the app): one list of everyone this event's door records, the team by department
  // (server checkin.team: members, roster rows with no account) and the guests going (the door list), each group with
  // its own «12 of 18». «Mark» answers at once with an Undo in the toast; a hand mark says so. A tap on a hand mark takes
  // it back (a scan stays: it proves they came). Lists stay fixable until the midnight after the event.
  import UsersRound from '@lucide/svelte/icons/users-round';
  import { api, ApiErr, type DoorPerson, type Id, type TeamList } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { hit } from '../../lib/search';
  import { time, nowTs } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Button from '../../ui/Button.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay, id, onchange }: { overlay: Overlay; id: Id; onchange?: () => void } = $props();

  let team = $state<TeamList | null>(null);
  let guests = $state<DoorPerson[] | null>(null);
  const load = () => {
    api.teamList(id).then((l) => (team = l)).catch(() => {});
    api.door(id).then((l) => (guests = l)).catch(() => {});
  };
  $effect(load);
  const aud = $derived(team?.audience ?? 'both');

  // one shape for both lists: a team row (key) or a guest going (uid)
  type Item = { key: string; uid?: Id; name: string; group: string; at: number | null; manual: boolean; app: boolean };
  const items = $derived.by<Item[]>(() => [
    ...(aud !== 'guests' ? (team?.rows ?? []).map((r) => ({ ...r, group: r.group ?? t('mk.noGroup') })) : []),
    ...(aud !== 'team' ? (guests ?? []).map((d) => ({ key: `g${d.person.id}`, uid: d.person.id, name: d.person.realName, group: t('mk.guestsGroup'),
      at: d.checkedInAt, manual: d.manual, app: true })) : []),
  ]);
  let tab = $state<'not' | 'came' | 'other'>('not');
  let q = $state('');
  const want = (x: { name: string }) => !q.trim() || hit(q, [x.name]);
  // the groups in the list's order, each counted over all its people (search and tab only pick the rows shown)
  const groups = $derived.by(() => {
    const by = new Map<string, { all: number; came: number; rows: Item[] }>();
    for (const x of items) {
      const g = by.get(x.group) ?? by.set(x.group, { all: 0, came: 0, rows: [] }).get(x.group)!;
      g.all++;
      if (x.at) g.came++;
      if ((tab === 'came') === !!x.at && want(x)) g.rows.push(x);
    }
    return [...by].filter(([, g]) => g.rows.length);
  });
  const others = $derived((aud !== 'guests' ? team?.other ?? [] : []).filter(want));

  const err = (e: unknown) => { haptic.error(); say(t(e instanceof ApiErr && e.code === 'closed' ? 'mk.closed' : 'common.error'), 'warning_3d'); };
  async function mark(x: Item, admit = false) {
    haptic.ok();
    const was = { at: x.at, manual: x.manual };
    set(x, nowTs(), true); // at once; back if the server says no
    say(t('mk.marked', { name: x.name }), 'sparkles_3d', () => void unmark(x));
    try {
      if (x.uid == null) team = await api.teamMark(id, x.key, true);
      else {
        const r = await api.checkinPerson(id, x.uid, admit);
        if (r.result === 'flagged') {
          set(x, was.at, was.manual);
          if (await sheets.ask({ title: t('mk.admitAsk'), ok: t('mk.admit'), cancel: t('common.cancel') })) void mark(x, true);
          return;
        }
        if (r.result !== 'ok' && r.result !== 'already') { set(x, was.at, was.manual); haptic.error(); say(t(r.result === 'closed' ? 'scan.closed' : r.result === 'not_open' ? 'scan.notOpen' : 'common.error'), 'warning_3d'); return; }
        set(x, r.at, r.result === 'ok');
      }
      onchange?.();
    } catch (e) { set(x, was.at, was.manual); err(e); }
  }
  async function unmark(x: Item) {
    const was = { at: x.at, manual: x.manual };
    set(x, null, false);
    try {
      if (x.uid == null) team = await api.teamMark(id, x.key, false);
      else await api.undoCheckin(id, x.uid);
      haptic.soft(); say(t('door.undone'), 'waving_hand_3d_default'); onchange?.();
    } catch (e) { set(x, was.at, was.manual); err(e); }
  }
  // the list a row came from, changed in place (the derived items follow)
  function set(x: Item, at: number | null, manual: boolean) {
    if (x.uid == null) { const r = team?.rows.find((y) => y.key === x.key); if (r) { r.at = at; r.manual = manual; } }
    else { const d = guests?.find((y) => y.person.id === x.uid); if (d) { d.checkedInAt = at; d.manual = manual; } }
  }
  const sub = (x: Item) => (x.at ? [time(x.at), x.manual && t('mk.byHand')] : [!x.app && t('mk.noApp')]).filter(Boolean).join(' · ') || undefined;
</script>

<Sheet {overlay} icon={UsersRound} full title={t('mk.people')}>
  <div class="col">
    <SearchField bind:value={q} placeholder={t('door.search')} />
    <Segmented items={[{ value: 'not', label: t('mk.notCame') }, { value: 'came', label: t('mk.came') }, ...(aud !== 'guests' ? [{ value: 'other' as const, label: t('mk.other') }] : [])]}
      bind:value={tab} onchange={() => haptic.tap()} />
    {#if tab === 'other'}
      {#if others.length}
        <Group>{#each others as o, i (i)}<Row dense title={o.name} value={time(o.at)} />{/each}</Group>
      {:else}<EmptyState inline text={t('mk.none')} />{/if}
    {:else if groups.length}
      {#each groups as [name, g] (name)}
        <Group caption={name} note={t('mk.ofN', { n: g.came, m: g.all })}>
          {#each g.rows as x (x.key)}
            {#if x.at}
              <Row dense title={x.name} subtitle={sub(x)} menu={x.manual ? [{ label: t('mk.unmark'), destructive: true, onselect: () => void unmark(x) }] : undefined} />
            {:else}
              <Row dense title={x.name} subtitle={sub(x)}>
                {#snippet trailing()}<Button kind="secondary" size="s" disabled={team ? !team.open && x.uid == null : false} onclick={() => mark(x)}>{t('door.mark')}</Button>{/snippet}
              </Row>
            {/if}
          {/each}
        </Group>
      {/each}
    {:else if team || guests}<EmptyState inline text={t('mk.none')} />{/if}
  </div>
</Sheet>

<style>
  .col { display: flex; flex-direction: column; gap: var(--s-3); margin-top: var(--s-1); }
</style>
