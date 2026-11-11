<script lang="ts">
  // One volunteer of the club's ledger (server logic/vol.py): hours, shifts, misses, how often they left without
  // checking out. Readers also see the club's own columns and the edits; the President and Vice edit misses and links,
  // each change with a reason; hours come from scans alone. `mine`: my own record, from Studio's "My hours".
  import { api, type Id, type VolPerson, type VolShift } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, loadVol, volGone } from '../../lib/state/data.svelte';
  import { loadMe, session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn, type Key } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { dayMonth, duration, time } from '../../lib/time';
  import type { MenuItem } from '../../ui/menu';
  import Clock from '@lucide/svelte/icons/clock';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  let { overlay, id, mine = false }: { overlay: Overlay; id: Id; mine?: boolean; vol?: boolean /* App: closes with the ledger */ } = $props();
  // the list's row shows at once; the rest (shifts, misses) as it comes
  const seed = data.vol?.people.find((x) => x.id === id);
  let p = $state<VolPerson | null>(seed ? { ...seed, balance: 0, shifts: [], missed: [], manual: [] } : null);
  // no longer mine to see: nothing of it stays on screen
  $effect(() => { (mine ? api.volMine() : api.volPerson(id)).then((x) => (p = x)).catch((e) => { if (volGone(e)) p = null; }); });
  const edit = $derived(!!session.me?.vol?.edit && !mine);

  // the President's and Vice's form: one at a time. Nobody types hours or times (hours come from scans alone, server vol.py)
  type Mode = { k: 'miss'; n: 1 | -1 } | { k: 'link' };
  let mode = $state<Mode | null>(null);
  let reason = $state('');
  function open(m: Mode) { haptic.tap(); mode = m; reason = ''; }
  const okReason = $derived(reason.trim().length >= 2);

  async function done(f: () => Promise<VolPerson>) {
    haptic.tap();
    mode = null;
    try {
      p = await f(); haptic.ok(); say(t('ledg.saved'), 'sparkles_3d');
      void loadVol();
      if (p.person?.id === session.me?.id) void loadMe(true);
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  function save() {
    if (mode?.k !== 'miss' || !p) return;
    const r = reason.trim(), pid = p.id, n = mode.n;
    void done(() => api.volAddMiss(pid, n, r));
  }
  async function gone(s: VolShift, on: boolean) {
    if (!p) return;
    const r = await sheets.askText({ title: t(on ? 'ledg.remove' : 'ledg.restore'), placeholder: t('ledg.reason'), max: 200, ok: t('common.save'), cancel: t('common.cancel') });
    if (!r?.trim() || r.trim().length < 2) return;
    p = { ...p, shifts: p.shifts.map((x) => (x.id === s.id ? { ...x, gone: on } : x)) }; // at once
    void done(() => api.volShiftGone(s.id, on, r.trim()));
  }
  async function dropMiss(mid: Id) {
    const r = await sheets.askText({ title: t('ledg.undoMiss'), placeholder: t('ledg.reason'), max: 200, ok: t('common.save'), cancel: t('common.cancel') });
    if (!r?.trim() || r.trim().length < 2 || !p) return;
    p = { ...p, manual: p.manual.filter((x) => x.id !== mid) };
    void done(() => api.volDropMiss(mid, r.trim()));
  }
  function link(user: Id | null) {
    if (!p) return;
    const pid = p.id;
    void done(() => api.volLink(pid, user));
  }
  async function unlink() {
    if (await sheets.ask({ title: t('ledg.unlink'), ok: t('ledg.unlink'), cancel: t('common.cancel'), danger: true })) link(null);
  }
  const members = $derived((data.team[session.me?.vol?.org ?? 0] ?? []).map((r) => r.person));
  const shiftMenu = (s: VolShift): MenuItem[] => [
    s.gone ? { label: t('ledg.restore'), onselect: () => void gone(s, false) } : { label: t('ledg.remove'), destructive: true, onselect: () => void gone(s, true) },
  ];
  const span = (s: VolShift) => `${dayMonth(s.inAt)}, ${time(s.inAt)}–${s.outAt ? time(s.outAt) : '…'}`;
  const foot = $derived(p ? [p.misses ? tn('ledg.misses', p.misses) : null, p.unmarked ? t('ledg.unmarkedN', { n: p.unmarked }) : null, p.tg && !mine ? '@' + p.tg : null].filter(Boolean).join(' · ') : '');
  const editName = (what: string) => t(('ledg.e.' + what) as Key);
</script>

<Sheet {overlay} icon={Clock} full title={mine ? t('ledg.mine') : (p?.name || t('ledg.title'))}>
  {#if p}
    <div class="body">
      <div class="hero">
        {#if p.person && !mine}<Avatar person={p.person} size={44} tappable={false} />{/if}
        <span class="txt"><b class="num">{duration(p.minutes * 60)}</b>
          {#if foot}<span class="t-foot">{foot}</span>{/if}</span>
      </div>

      {#if edit}
        <Group>
          <Row tone="action" title={t('ledg.addMiss')} onclick={() => open({ k: 'miss', n: 1 })} />
          <Row tone="action" title={t('ledg.excuse')} onclick={() => open({ k: 'miss', n: -1 })} />
          {#if p.balance}<Row title={t('ledg.balance')} value={duration(p.balance * 60)} />{/if}
          {#if p.person}<Row tone="action" title={t('ledg.unlink')} value={p.person.name} onclick={unlink} />
          {:else}<Row tone="action" title={t('ledg.link')} onclick={() => open({ k: 'link' })} />{/if}
        </Group>
      {/if}

      {#if mode?.k === 'link'}
        <Group caption={t('ledg.link')}>
          {#each members as m (m.id)}
            <Row dense title={m.name} onclick={() => link(m.id)}>
              {#snippet lead()}<Avatar person={m} size={32} tappable={false} />{/snippet}
            </Row>
          {/each}
        </Group>
      {:else if mode}
        <form class="form" onsubmit={(e) => { e.preventDefault(); save(); }}>
          <p class="t-foot what">{t(mode.n === 1 ? 'ledg.plus' : 'ledg.minus')}</p>
          <Field label={t('ledg.reason')} bind:value={reason} maxlength={200} enterkeyhint="done" />
          <div class="two">
            <Button kind="secondary" size="l" full onclick={() => (mode = null)}>{t('common.cancel')}</Button>
            <Button kind="primary" size="l" full type="submit" disabled={!okReason}>{t('common.save')}</Button>
          </div>
        </form>
      {/if}

      {#if p.shifts.length}
        <Group caption={t('ledg.shifts')} footnote={p.open ? t('ledg.openNote') : undefined}>
          {#each p.shifts as s (s.id)}
            <Row dense title={s.title ?? t('ledg.byHand')} subtitle={[span(s), s.byHand && s.title && !s.unmarked ? t('ledg.byHand') : null, s.unmarked ? t('ledg.unmarkedTag') : null, s.team && !s.gone ? t('ledg.teamTag') : null, s.gone ? t('ledg.removed') + (s.goneReason ? ': ' + s.goneReason : '') : null].filter(Boolean).join(' · ')}
              value={s.gone || s.team ? undefined : s.outAt ? duration(s.outAt - s.inAt) : t('ledg.noOut')} whole menu={edit ? shiftMenu(s) : undefined} />
          {/each}
        </Group>
      {/if}

      {#if p.missed.length || p.manual.length}
        <Group caption={t('ledg.missed')}>
          {#each p.missed as m (m.session)}<Row dense title={m.title} value={dayMonth(m.at)} />{/each}
          {#each p.manual as m (m.id)}
            <Row dense title={t(m.n === 1 ? 'ledg.plus' : 'ledg.minus')} value={dayMonth(m.at)}
              menu={edit ? [{ label: t('ledg.undoMiss'), destructive: true, onselect: () => void dropMiss(m.id) }] : undefined} />
          {/each}
        </Group>
      {/if}

      {#if p.raw}
        {#each Object.entries(p.raw) as [sheet, cols] (sheet)}
          <Group caption={sheet}>
            {#each Object.entries(cols) as [k, x] (k)}<Row dense title={k} value={x} />{/each}
          </Group>
        {/each}
      {/if}

      {#if p.edits?.length}
        <Group caption={t('ledg.history')}>
          {#each p.edits as e, i (i)}<Row dense title={editName(e.what)} subtitle={[e.reason, dayMonth(e.at)].filter(Boolean).join(' · ')} />{/each}
        </Group>
      {/if}
    </div>
  {/if}
</Sheet>

<style>
  .body { display: flex; flex-direction: column; gap: var(--s-4); margin-top: var(--s-2); }
  .hero { display: flex; align-items: center; gap: var(--s-3); padding: 0 var(--s-1); }
  .txt { display: flex; flex-direction: column; gap: 2px; }
  .txt b { font: 800 var(--fs-sec)/1.1 var(--font-display); letter-spacing: -0.02em; }
  .form { display: flex; flex-direction: column; gap: var(--s-3); }
  .what { margin: 0 var(--s-4); }
  .two { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: var(--s-2); align-items: end; }
</style>
