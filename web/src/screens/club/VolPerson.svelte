<script lang="ts">
  // One volunteer of the club's ledger (server logic/vol.py): hours, shifts, misses. Readers also see the club's own
  // columns and the edits; the President alone edits (her own record too), each change with a reason. `mine`: my own
  // record, from Studio's "My hours" (hours, shifts and misses only).
  import { api, ApiErr, type Id, type VolPerson, type VolShift } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, loadVol } from '../../lib/state/data.svelte';
  import { loadMe, session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn, type Key } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { dateInput, dayMonth, duration, fromInputs, nowTs, time } from '../../lib/time';
  import type { MenuItem } from '../../ui/menu';
  import Clock from '@lucide/svelte/icons/clock';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  let { overlay, id, mine = false }: { overlay: Overlay; id: Id; mine?: boolean } = $props();
  // the list's row shows at once; the rest (shifts, misses) as it comes
  const seed = data.vol?.people.find((x) => x.id === id);
  let p = $state<VolPerson | null>(seed ? { ...seed, balance: 0, shifts: [], missed: [], manual: [] } : null);
  // no longer mine to see: nothing of it stays on screen
  $effect(() => { (mine ? api.volMine() : api.volPerson(id)).then((x) => (p = x)).catch((e) => { if (e instanceof ApiErr && (e.code === 'forbidden' || e.code === 'not_found')) { p = null; close(overlay.id, false); } }); });
  const edit = $derived(!!session.me?.vol?.edit && !mine);

  // the President's form: one at a time
  type Mode = { k: 'shift'; s?: VolShift } | { k: 'balance' } | { k: 'miss'; n: 1 | -1 } | { k: 'link' };
  let mode = $state<Mode | null>(null);
  let day = $state(''), from = $state(''), to = $state(''), hours = $state(''), reason = $state('');
  function open(m: Mode) {
    haptic.tap();
    mode = m; reason = '';
    if (m.k === 'shift') {
      const s = m.s;
      day = dateInput(s?.inAt ?? nowTs()); from = s ? time(s.inAt) : ''; to = s?.outAt ? time(s.outAt) : '';
    }
    if (m.k === 'balance') hours = p ? String(Math.round((p.balance / 60) * 10) / 10) : '';
  }
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
    if (!mode || !p) return;
    const r = reason.trim(), pid = p.id;
    if (mode.k === 'shift') {
      const i = fromInputs(day, from);
      let o: number | null = to ? fromInputs(day, to) : null;
      if (o !== null && o <= i) o += 86400; // past midnight
      if (!Number.isFinite(i) || (o !== null && !Number.isFinite(o))) return;
      const s = mode.s;
      void done(() => (s ? api.volEditShift(s.id, { inAt: i, outAt: o }, r) : api.volAddShift(pid, i, o, r)));
    } else if (mode.k === 'balance') {
      const h = Number(hours.replace(',', '.'));
      if (!Number.isFinite(h) || h < 0) return;
      void done(() => api.volBalance(pid, Math.round(h * 60), r));
    } else if (mode.k === 'miss') {
      const n = mode.n;
      void done(() => api.volAddMiss(pid, n, r));
    }
  }
  async function gone(s: VolShift, on: boolean) {
    if (!p) return;
    const r = await sheets.askText({ title: t(on ? 'ledg.remove' : 'ledg.restore'), placeholder: t('ledg.reason'), max: 200, ok: t('common.save'), cancel: t('common.cancel') });
    if (!r?.trim() || r.trim().length < 2) return;
    p = { ...p, shifts: p.shifts.map((x) => (x.id === s.id ? { ...x, gone: on } : x)) }; // at once
    void done(() => api.volEditShift(s.id, { gone: on }, r.trim()));
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
    { label: t('ledg.editTime'), onselect: () => open({ k: 'shift', s }) },
    s.gone ? { label: t('ledg.restore'), onselect: () => void gone(s, false) } : { label: t('ledg.remove'), destructive: true, onselect: () => void gone(s, true) },
  ];
  const span = (s: VolShift) => `${dayMonth(s.inAt)}, ${time(s.inAt)}–${s.outAt ? time(s.outAt) : '…'}`;
  const editName = (what: string) => t(('ledg.e.' + what) as Key);
</script>

<Sheet {overlay} icon={Clock} full title={mine ? t('ledg.mine') : (p?.name || t('ledg.title'))}>
  {#if p}
    <div class="body">
      <div class="hero">
        {#if p.person && !mine}<Avatar person={p.person} size={44} tappable={false} />{/if}
        <span class="txt"><b class="num">{duration(p.minutes * 60)}</b>
          <span class="t-foot">{tn('ledg.misses', p.misses)}{p.tg && !mine ? ' · @' + p.tg : ''}</span></span>
      </div>

      {#if edit}
        <Group>
          <Row tone="action" title={t('ledg.addShift')} onclick={() => open({ k: 'shift' })} />
          <Row tone="action" title={t('ledg.addMiss')} onclick={() => open({ k: 'miss', n: 1 })} />
          <Row tone="action" title={t('ledg.excuse')} onclick={() => open({ k: 'miss', n: -1 })} />
          <Row tone="action" title={t('ledg.balance')} value={duration(p.balance * 60)} onclick={() => open({ k: 'balance' })} />
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
          {#if mode.k === 'shift'}
            <label class="fl"><span>{t('ed.date')}</span><input type="date" bind:value={day} /></label>
            <div class="two">
              <label class="fl"><span>{t('ledg.in')}</span><input type="time" bind:value={from} /></label>
              <label class="fl"><span>{t('ledg.out')}</span><input type="time" bind:value={to} /></label>
            </div>
          {:else if mode.k === 'balance'}
            <Field label={t('ledg.hoursField')} type="text" inputmode="decimal" bind:value={hours} maxlength={8} />
          {:else}
            <p class="t-foot what">{t(mode.n === 1 ? 'ledg.plus' : 'ledg.minus')}</p>
          {/if}
          <Field label={t('ledg.reason')} bind:value={reason} maxlength={200} enterkeyhint="done" />
          <div class="two">
            <Button kind="secondary" size="l" full onclick={() => (mode = null)}>{t('common.cancel')}</Button>
            <Button kind="primary" size="l" full type="submit" disabled={!okReason || (mode.k === 'shift' && (!day || !from))}>{t('common.save')}</Button>
          </div>
        </form>
      {/if}

      {#if p.shifts.length}
        <Group caption={t('ledg.shifts')} footnote={p.open ? t('ledg.openNote') : undefined}>
          {#each p.shifts as s (s.id)}
            <Row dense title={s.title ?? t('ledg.byHand')} subtitle={[span(s), s.byHand && s.title ? t('ledg.byHand') : null, s.gone ? t('ledg.removed') : null].filter(Boolean).join(' · ')}
              value={s.gone ? undefined : s.outAt ? duration(s.outAt - s.inAt) : t('ledg.noOut')} menu={edit ? shiftMenu(s) : undefined} />
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
  /* Field's look for the date and time inputs it can't take (as MemoAsks) */
  .fl { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
  .fl > span { padding: 0 var(--s-4); font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .fl > input { width: 100%; min-width: 0; min-height: var(--ctl-l); padding: 0 var(--s-4); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 450 var(--fs-row)/1.35 var(--font-text); }
</style>
