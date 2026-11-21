<script lang="ts">
  // The Mark screen's «People» (a club wants its whole roster by department,
  // came / not came, many without the app): one list of everyone this event's door records, the team by department
  // (server checkin.team: members, roster rows with no account) and the guests going (the door list), each group with
  // its own «12 of 18». The whole row is the tap (not a button on every row): its circle turns into a check
  // at once, the row stays where it is (no jump under the thumb) and moves to «Came» at the next tab switch; an Undo in
  // the toast. A tap on a hand mark offers to take it back (a scan stays: it proves they came). Fixable until the
  // midnight ending the day after the event.
  import UsersRound from '@lucide/svelte/icons/users-round';
  import Circle from '@lucide/svelte/icons/circle';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import { menu } from '../../ui/menu';
  import { api, ApiErr, type DoorPerson, type Id, type TeamList } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { eventById } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { hit } from '../../lib/search';
  import { time, nowTs } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Tag from '../../ui/Tag.svelte';

  let { overlay, id, onchange, guestsOnly = false }: { overlay: Overlay; id: Id; onchange?: () => void; guestsOnly?: boolean } = $props();

  let team = $state<TeamList | null>(null);
  let guests = $state<DoorPerson[] | null>(null);
  // the organizers' list of buyers not in the app (and people with no student ID): ticked by name
  let pend = $state<{ key: string; name: string; adult: boolean | null; came: boolean; at?: number | null; team?: string | null }[]>([]);
  const load = () => {
    if (!guestsOnly) api.teamList(id).then((l) => (team = l)).catch(() => {});
    api.doorPending(id).then((x) => (pend = x.list ?? [])).catch(() => {});
    api.door(id).then((l) => (guests = l)).catch(() => {});
  };
  $effect(load);
  const aud = $derived(team?.audience ?? 'both');

  // one shape for both lists: a team row (key) or a guest going (uid)
  type Item = { key: string; uid?: Id; pend?: string; name: string; group: string; at: number | null; manual: boolean; app: boolean; adult?: boolean | null };
  const items = $derived.by<Item[]>(() => [
    ...pend.map((x) => ({ key: `p:${x.key}`, pend: x.key, name: x.name, group: x.team || t('mk.guestsGroup'), at: x.came ? x.at ?? nowTs() : null, manual: true, app: false, adult: x.adult })),
    ...(aud !== 'guests' && !guestsOnly ? (team?.rows ?? []).map((r) => ({ ...r, group: r.group ?? t('mk.noGroup') })) : []),
    ...(aud !== 'team' ? (guests ?? []).map((d) => ({ key: `g${d.person.id}`, uid: d.person.id, name: d.person.realName, group: d.team || t('mk.guestsGroup'),
      at: d.checkedInAt, manual: d.manual, app: true, adult: d.adult })) : []), // adult: an age_check event's door mark
  ]);
  let tab = $state<'not' | 'came' | 'other'>('not');
  // rows marked or unmarked in this tab stay in it until the next switch
  let stay = $state<string[]>([]);
  let q = $state('');
  const want = (x: { name: string; group?: string }) => !q.trim() || hit(q, [x.name, x.group]); // a department's name finds its people
  // the groups in the list's order, each counted over all its people (search and tab only pick the rows shown)
  const groups = $derived.by(() => {
    const by = new Map<string, { all: number; came: number; rows: Item[] }>();
    for (const x of items) {
      const g = by.get(x.group) ?? by.set(x.group, { all: 0, came: 0, rows: [] }).get(x.group)!;
      g.all++;
      if (x.at) g.came++;
      if (((tab === 'came') === !!x.at || stay.includes(x.key)) && want(x)) g.rows.push(x);
    }
    return [...by].filter(([, g]) => g.rows.length);
  });
  const others = $derived((aud !== 'guests' ? team?.other ?? [] : []).filter(want));

  const err = (e: unknown) => { haptic.error(); say(t(e instanceof ApiErr && e.code === 'closed' ? 'mk.closed' : 'common.error'), 'warning_3d'); };
  const keep = (x: Item) => { if (!stay.includes(x.key)) stay.push(x.key); };
  async function mark(x: Item, admit = false) {
    haptic.ok(); keep(x);
    const was = { at: x.at, manual: x.manual };
    set(x, nowTs(), true); // at once; back if the server says no
    say(t('mk.marked', { name: x.name.split(' ').slice(0, 2).join(' ') }), 'sparkles_3d', () => void unmark(x), undefined, true);
    try {
      if (x.pend) { await api.tickPending(id, x.pend); const p = pend.find((y) => y.key === x.pend); if (p) p.came = true; }
      else if (x.uid == null) team = await api.teamMark(id, x.key, true);
      else {
        const r = await api.checkinPerson(id, x.uid, admit);
        if (r.result === 'flagged' || r.result === 'ask_org') { // a receipt nobody checked: nothing recorded (server organizing._held)
          set(x, was.at, was.manual);
          if (r.result === 'ask_org') { haptic.error(); say(t('mk.askOrg'), 'warning_3d'); }
          else if (!admit && await sheets.ask({ title: t('mk.admitAsk'), ok: t('mk.admit'), cancel: t('common.cancel') })) void mark(x, true);
          return;
        }
        if (r.result !== 'ok' && r.result !== 'already') { set(x, was.at, was.manual); haptic.error(); say(t(r.result === 'closed' ? 'scan.closed' : r.result === 'not_open' ? 'scan.notOpen' : 'common.error'), 'warning_3d'); return; }
        set(x, r.at, r.result === 'ok');
      }
      onchange?.();
    } catch (e) { set(x, was.at, was.manual); err(e); }
  }
  async function unmark(x: Item) {
    keep(x);
    const was = { at: x.at, manual: x.manual };
    set(x, null, false);
    try {
      if (x.pend) { await api.tickPending(id, x.pend, false); onchange?.(); return; }
      if (x.uid == null) team = await api.teamMark(id, x.key, false);
      else await api.undoCheckin(id, x.uid);
      haptic.soft(); say(t('door.undone'), 'waving_hand_3d_default', undefined, undefined, true); onchange?.();
    } catch (e) { set(x, was.at, was.manual); err(e); }
  }
  // the list a row came from, changed in place (the derived items follow)
  function set(x: Item, at: number | null, manual: boolean) {
    if (x.pend) { const p = pend.find((y) => y.key === x.pend); if (p) { p.came = at != null; p.at = at; } return; }
    if (x.uid == null) { const r = team?.rows.find((y) => y.key === x.key); if (r) { r.at = at; r.manual = manual; } }
    else { const d = guests?.find((y) => y.person.id === x.uid); if (d) { d.checkedInAt = at; d.manual = manual; } }
  }
  const shut = (x: Item) => x.uid == null && !!team && !team.open;
  // an 18+ door: the guest's age right where they are ticked (the door saw the ID card)
  const ages = $derived(!!eventById(id)?.ageCheck);
  const ageItems = (x: Item) => (ages && (x.pend || x.uid != null) ? [
    { label: t('age.adult'), checked: x.adult === true, onselect: () => void setAge(x, true) },
    { label: t('age.minor'), checked: x.adult === false, onselect: () => void setAge(x, false) },
  ] : []);
  async function setAge(x: Item, adult: boolean) {
    const was = x.adult;
    const put = (a: boolean | null | undefined) => {
      if (x.pend) { const p = pend.find((y) => y.key === x.pend); if (p) p.adult = a ?? null; }
      else { const d = guests?.find((y) => y.person.id === x.uid); if (d) d.adult = a ?? null; }
    };
    put(adult); haptic.ok();
    try { if (x.pend) await api.tickPending(id, x.pend, true, adult); else await api.markAge(id, x.uid!, adult); }
    catch (e) { put(was); err(e); }
  }
  function tap(x: Item, ev: MouseEvent) {
    const el = ev.currentTarget as Element;
    if (!x.at) { if (!shut(x)) { void mark(x); if (ageItems(x).length) menu(el, ageItems(x)); } return; }
    const items = [...ageItems(x), ...(x.manual ? [{ label: t('mk.unmark'), destructive: true, onselect: () => void unmark(x) }] : [])];
    if (items.length) { haptic.tap(); menu(el, items); }
  }
  const sub = (x: Item) => (x.at ? [time(x.at), x.manual && t('mk.byHand')] : [!x.app && t('mk.noApp')]).filter(Boolean).join(' · ') || undefined;
</script>

<Sheet {overlay} icon={UsersRound} full title={t('mk.people')}>
  <div class="col">
    <SearchField bind:value={q} placeholder={t('door.search')} />
    <Segmented items={[{ value: 'not', label: t('mk.notCame') }, { value: 'came', label: t('mk.came') }, ...(aud !== 'guests' ? [{ value: 'other' as const, label: t('mk.other') }] : [])]}
      bind:value={tab} onchange={() => { haptic.tap(); stay = []; }} />
    {#if tab === 'other'}
      {#if others.length}
        <Group>{#each others as o, i (i)}<Row dense title={o.name} value={time(o.at)} />{/each}</Group>
      {:else}<EmptyState inline text={t('mk.none')} />{/if}
    {:else if groups.length}
      {#each groups as [name, g] (name)}
        <Group caption={name} note={t('mk.ofN', { n: g.came, m: g.all })}>
          {@const rest = g.rows.filter((x) => !x.at && (x.pend || x.uid != null))}
          {#if rest.length > 1 && g.rows.every((x) => x.pend || x.uid != null) && name !== t('mk.guestsGroup')}
            <Row dense title={t('mk.markTeam', { n: rest.length })} accessory="chevron" onclick={() => { for (const x of rest) void mark(x); }} />
          {/if}
          {#each g.rows as x (x.key)}
            <Row dense title={x.name} subtitle={sub(x)} disabled={!x.at && shut(x)} onclick={x.at && !x.manual ? undefined : (ev) => tap(x, ev)}>
              {#snippet detail()}{#if x.adult != null}<span class="tg"><Tag tone={x.adult ? 'neutral' : 'warning'}>{t(x.adult ? 'age.adult' : 'age.u18')}</Tag></span>{/if}<span class="ck" class:on={!!x.at}>{#if x.at}<CircleCheck size={24} />{:else}<Circle size={24} />{/if}</span>{/snippet}
            </Row>
          {/each}
        </Group>
      {/each}
    {:else if team || guests}<EmptyState inline text={t('mk.none')} />{/if}
  </div>
</Sheet>

<style>
  .ck { display: flex; margin-left: auto; color: var(--text-3); }
  .tg { margin-left: auto; }
  .tg + .ck { margin-left: var(--s-2); }
  .ck.on { color: var(--accent); }
  .col { display: flex; flex-direction: column; gap: var(--s-3); margin-top: var(--s-1); }
</style>
