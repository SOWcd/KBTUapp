<script lang="ts">
  // An event's door helpers (server logic/crew.py), for a running club's President or Vice: a friend or someone from
  // the team helps at this one event's door until it ends. 🎫 the scanner by default; 🚪 the whole door (the list of
  // names) after a confirm. Three at most. Each tap answers at once; back if the server says no.
  import { api, ApiErr, staffEvents, type CrewKind, type CrewMember, type Id, type PersonRef } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, eventById } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { hit } from '../../lib/search';
  import { haptic } from '../../lib/tg';
  import { RANK } from '../../lib/perms';
  import Sheet from '../../ui/Sheet.svelte';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay, id, onchange }: { overlay: Overlay; id: Id; onchange?: (n: number) => void } = $props();
  let list = $state<CrewMember[] | null>(null);
  $effect(() => { api.event(id).then((d) => (list = d.crew ?? [])).catch(() => (list = [])); });
  $effect(() => { if (list) onchange?.(list.length); });

  const e = $derived(eventById(id));
  // the club I give helpers for: the host first, else the co-host (as the server's _lead); the creator from Admin: the
  // host, as its President (server app.viewer)
  const mine = $derived(staffEvents.has(id) && session.me?.founder ? e?.org ?? null : [e?.org, e?.coHost].find((o) => o && RANK[session.me?.memberships.find((m) => m.org.id === o.id)?.role ?? 'member'] >= RANK.vice) ?? null);
  const full = $derived((list?.length ?? 0) >= 3);

  // friends and the teams I lead, once each, not me, not already helping
  let q = $state('');
  const pool = $derived.by(() => {
    const seen = new Set<Id>([session.me?.id ?? 0, ...(list ?? []).map((x) => x.person.id)]);
    const out: PersonRef[] = [];
    for (const p of [...(data.friends?.friends ?? []).map((r) => r.person), ...[e?.org, e?.coHost].flatMap((o) => (o && data.team[o.id]) || []).map((r) => r.person)])
      if (!seen.has(p.id)) { seen.add(p.id); out.push(p); }
    return (q.trim() ? out.filter((p) => hit(q, [p.name, p.realName])) : out).slice(0, 30);
  });

  const KIND = { scan: 'crew.scan', door: 'crew.door' } as const;
  const why = (x: unknown) => say(t(x instanceof ApiErr && x.code === 'rate_limited' ? 'crew.full' : x instanceof ApiErr && x.message === 'banned' ? 'crew.banned' : 'common.error'), 'pleading_face_3d');

  async function put(p: PersonRef, kind: CrewKind) {
    if (!list || !mine) return;
    if (kind === 'door' && !(await sheets.ask({ title: t('crew.doorAsk'), text: t('crew.doorText'), ok: t('crew.doorOk'), cancel: t('common.cancel') }))) return;
    haptic.tap();
    const was = list;
    list = [...list.filter((x) => x.person.id !== p.id), { person: p, kind, org: mine.id }];
    try { list = await api.crewPut(id, p.id, kind); haptic.ok(); if (!was.some((x) => x.person.id === p.id)) say(t('crew.added'), 'raising_hands_3d_default'); }
    catch (x) { list = was; haptic.error(); why(x); }
  }
  async function drop(p: PersonRef) {
    if (!list) return;
    haptic.tap();
    const was = list;
    list = list.filter((x) => x.person.id !== p.id);
    try { list = await api.crewDrop(id, p.id); say(t('crew.removed'), 'waving_hand_3d_default'); }
    catch (x) { list = was; haptic.error(); why(x); }
  }
  const kindMenu = (x: CrewMember) => [
    ...(['scan', 'door'] as const).map((k) => ({ label: t(KIND[k]), checked: x.kind === k, onselect: () => { if (x.kind !== k) void put(x.person, k); } })),
    { label: t('crew.remove'), destructive: true, onselect: () => void drop(x.person) },
  ];
</script>

<Sheet {overlay} icon={ScanLine} full title={t('crew.title')}>
  <p class="t-foot sub">{t('crew.hint')}</p>
  {#if list}
    <div class="list">
      <Group>
        {#each list as x (x.person.id)}
          {#snippet off()}<Button kind="secondary" size="s" onclick={() => drop(x.person)}>{t('crew.remove')}</Button>{/snippet}
          {#if x.org === mine?.id}
            <Row dense title={x.person.name} value={t(KIND[x.kind])} menu={kindMenu(x)}>
              {#snippet lead()}<Avatar person={x.person} size={36} tappable={false} />{/snippet}
            </Row>
          {:else}
            <Row dense title={x.person.name} subtitle={`${t(KIND[x.kind])} · ${t('crew.theirs')}`} trailing={e && mine?.id === e.org.id ? off : undefined}>
              {#snippet lead()}<Avatar person={x.person} size={36} tappable={false} />{/snippet}
            </Row>
          {/if}
        {:else}
          <Row dense title={t('crew.none')} />
        {/each}
      </Group>
      {#if !full}
        {#if pool.length > 6 || q}<SearchField bind:value={q} placeholder={t('door.search')} />{/if}
        <Group caption={t('crew.pick')}>
          {#each pool as p (p.id)}
            {#snippet add()}<Button kind="tinted" size="s" onclick={() => put(p, 'scan')}>{t('crew.add')}</Button>{/snippet}
            <Row dense title={p.name} trailing={add}>
              {#snippet lead()}<Avatar person={p} size={36} tappable={false} />{/snippet}
            </Row>
          {:else}
            <EmptyState inline text={t('crew.nobody')} />
          {/each}
        </Group>
      {/if}
      <!-- the volunteers who asked, under the one «Helpers» (EventManage) -->
      {#if e?.needsVolunteers}<Group><Row icon={HandHeart} title={t('vol.list')} count={e.volunteersAsked ?? 0} accessory="chevron" onclick={() => sheets.volunteers(id, e.needsVolunteers!)} /></Group>{/if}
    </div>
  {/if}
</Sheet>

<style>
  .sub { margin: 2px var(--s-1) 0; }
  .list { display: flex; flex-direction: column; gap: var(--s-4); margin-top: var(--s-4); }
</style>
