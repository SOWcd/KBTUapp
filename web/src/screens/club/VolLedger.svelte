<script lang="ts">
  // The club's volunteers ledger (server logic/vol.py), its spreadsheet as a screen: everyone with their hours and
  // misses, a row opens the person. Its sessions (a teambuilding counts misses) and who else may read it: the President's.
  // Loaded with the app (data.vol), refreshed as it opens.
  import { api, type Id, type VolLedger } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, loadVol } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { hit } from '../../lib/search';
  import { haptic } from '../../lib/tg';
  import { dayMonth, duration } from '../../lib/time';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  let { overlay }: { overlay: Overlay; vol?: boolean /* App: closes with the ledger */ } = $props();
  $effect(() => { void loadVol(); }); // no longer mine: it closes (volGone)
  const v = $derived(data.vol);
  let q = $state('');
  const people = $derived((v?.people ?? []).filter((p) => !q.trim() || hit(q, [p.name, p.tg ?? '', p.person?.name ?? ''])));
  const org = $derived(session.me?.vol?.org ?? 0);
  // members she may grant: the club's team, not her, not granted already
  const grantable = $derived.by(() => {
    const have = new Set<Id>([session.me?.id ?? 0, ...(v?.access ?? []).map((p) => p.id)]);
    return (data.team[org] ?? []).map((r) => r.person).filter((p) => !have.has(p.id));
  });
  let granting = $state(false);

  async function write(f: () => Promise<VolLedger>, next: VolLedger) {
    const was = data.vol;
    data.vol = next; // at once; back if the server says no
    haptic.tap();
    try { data.vol = await f(); }
    catch { data.vol = was; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  const team = (session: Id, on: boolean) => v && write(() => api.volTeam(session, on), { ...v, meets: v.meets.map((m) => (m.session === session ? { ...m, team: on } : m)) });
  const access = (id: Id, on: boolean) => {
    if (!v) return;
    const p = grantable.find((x) => x.id === id);
    granting = false;
    void write(() => api.volAccess(id, on), { ...v, access: on ? (p ? [...v.access, p] : v.access) : v.access.filter((x) => x.id !== id) });
  };
</script>

<Sheet {overlay} icon={HandHeart} full title={t('ledg.title')}>
  {#if v}
    <div class="list">
      {#if v.people.length > 8 || q}<SearchField bind:value={q} placeholder={t('door.search')} />{/if}
      <Group caption={tn('ledg.count', v.people.length)}>
        {#each people as p (p.id)}
          <Row dense title={p.name || (p.tg ? '@' + p.tg : '—')} subtitle={[p.person ? null : t('ledg.noAccount'), p.misses ? tn('ledg.misses', p.misses) : null, p.unmarked ? t('ledg.unmarkedN', { n: p.unmarked }) : null].filter(Boolean).join(' · ') || undefined}
            value={duration(p.minutes * 60)} whole accessory="chevron" onclick={() => sheets.volPerson(p.id)}>
            {#snippet lead()}{#if p.person}<Avatar person={p.person} size={32} tappable={false} />{:else}<span class="blank" aria-hidden="true"></span>{/if}{/snippet}
          </Row>
        {:else}
          <EmptyState inline text={t('ledg.empty')} />
        {/each}
      </Group>

      {#if v.meets.length}
        <Group caption={t('ledg.meets')} footnote={v.edit ? t('ledg.teamNote') : undefined}>
          {#each v.meets as m (m.session)}
            <Row dense title={m.title} subtitle={[dayMonth(m.at), t('ledg.marked', { m: m.marked, n: m.expected }), m.team ? t('ledg.team') : null, m.held ? t('ledg.held') : null].filter(Boolean).join(' · ')}
              accessory={v.edit ? 'switch' : 'none'} checked={m.team} onchange={(on) => team(m.session, on)} />
            <!-- who left without checking out waits for the President's or Vice's answer: the session's door -->
            {#if v.edit && m.unresolved}<Row dense tone="action" title={t('ledg.unresolvedN', { n: m.unresolved })} accessory="chevron" onclick={() => sheets.volDoor(m.session, m.title)} />{/if}
          {/each}
        </Group>
      {/if}

      {#if v.edit}
        <Group caption={t('ledg.access')} footnote={t('ledg.accessNote')}>
          {#each v.access as p (p.id)}
            {#snippet off()}<Button kind="secondary" size="s" onclick={() => access(p.id, false)}>{t('crew.remove')}</Button>{/snippet}
            <Row dense title={p.name} trailing={off}>
              {#snippet lead()}<Avatar person={p} size={32} tappable={false} />{/snippet}
            </Row>
          {/each}
          <Row tone="add" title={t('ledg.grant')} accessory="disclosure" open={granting} onclick={() => (granting = !granting)} />
          {#if granting}
            {#each grantable as p (p.id)}
              <Row dense title={p.name} onclick={() => access(p.id, true)}>
                {#snippet lead()}<Avatar person={p} size={32} tappable={false} />{/snippet}
              </Row>
            {/each}
          {/if}
        </Group>
      {/if}
    </div>
  {/if}
</Sheet>

<style>
  .list { display: flex; flex-direction: column; gap: var(--s-4); margin-top: var(--s-2); }
  .blank { display: block; width: 32px; height: 32px; border-radius: 50%; background: var(--fill); }
</style>
