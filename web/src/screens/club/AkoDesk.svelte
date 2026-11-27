<script lang="ts">
  import { akoTeam } from '../../lib/api/akoTeam';
  // Studio → admissions (AKO): the team's desk. Two parts: the applicants (filter, search, a tap opens the package) and
  // the interview days (each day's Teams link and its times). Managers (desk.manage) change things; a reviewer reads.
  // Every change shows at once and rolls back with the toast when the server says no.
  import { onMount } from 'svelte';
  import { ApiErr, type Id, type AkoDesk, type AkoRow, type AkoSlot } from '../../lib/api';
  import { open, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { i18n, t } from '../../lib/i18n/index.svelte';
  import { aw, awn } from '../../lib/i18n/ako';
  import { dateInput, dayMonth, nowTs, time, weekday, whenLine } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import { menu } from '../../ui/menu';
  import Pane from '../../ui/Pane.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import Plus from '@lucide/svelte/icons/plus';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Search from '@lucide/svelte/icons/search';
  import ChevronsUpDown from '@lucide/svelte/icons/chevrons-up-down';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import Check from '@lucide/svelte/icons/check';
  import Inbox from '@lucide/svelte/icons/inbox';
  import CalendarClock from '@lucide/svelte/icons/calendar-clock';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import Link from '@lucide/svelte/icons/link';
  import UserRound from '@lucide/svelte/icons/user-round';
  import Video from '@lucide/svelte/icons/video';
  import Trash2 from '@lucide/svelte/icons/trash-2';

  let { overlay, org, slug }: { overlay: Overlay; org: Id; slug: string } = $props();

  let desk = $state<AkoDesk | null>(null);
  let failed = $state(false);
  let tab = $state<'apps' | 'slots'>('apps');
  const manage = $derived(!!desk?.manage);
  const now = nowTs();

  async function load() {
    failed = false;
    try { desk = await akoTeam.akoDesk(org); }
    catch { if (!desk) failed = true; say(t('common.error'), 'warning_3d'); }
  }
  onMount(() => { void load(); });

  /** optimistic: apply now, send, put everything back when it fails; returns the error (null: it went through) */
  async function change(apply: (d: AkoDesk) => void, send: () => Promise<unknown>): Promise<unknown> {
    if (!desk) return true;
    const was = $state.snapshot(desk) as AkoDesk;
    apply(desk);
    try { await send(); haptic.ok(); return null; }
    catch (e) { desk = was; haptic.error(); return e ?? true; }
  }

  // ---- the sheets (each its own chunk) ----
  const openApp = (id: Id) => void import('./AkoAppSheet.svelte').then((x) => desk && open(x.default, { org, id, desk, onchange: load }));
  const newApp = () => void import('./AkoNewSheet.svelte').then((x) => desk && open(x.default, { org, desk, onchange: load }));
  const addDay = () => void import('./AkoDaySheet.svelte').then((x) => desk && open(x.default, { org, desk, onchange: load }));

  async function copyPublic() {
    try { await navigator.clipboard.writeText(`${location.origin}/ako/o/${slug}`); haptic.ok(); say(aw('akd.copied')); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  const more = (e: MouseEvent) => menu(e.currentTarget as Element, [
    { label: aw('akd.publicLink'), icon: Link, onselect: copyPublic },
    { label: aw('akd.addDay'), icon: CalendarPlus, onselect: addDay },
  ], 'end');

  // ---- applicants ----
  const FILTERS = ['all', 'sent', 'review', 'draft', 'done'] as const;
  type Filter = typeof FILTERS[number];
  let filter = $state<Filter>('all');
  let q = $state('');
  const fits = (a: AkoRow, f: Filter) => f === 'all' || (f === 'done' ? a.status === 'accepted' || a.status === 'declined' : a.status === f);
  const count = (f: Filter) => desk?.apps.filter((a) => fits(a, f)).length ?? 0;
  const shown = $derived.by(() => {
    const s = q.trim().toLowerCase();
    return (desk?.apps ?? []).filter((a) => fits(a, filter) && (!s || a.name.toLowerCase().includes(s)));
  });
  const pickFilter = (e: MouseEvent) => menu(e.currentTarget as Element, FILTERS.map((f) => ({
    label: `${aw(`akd.filter.${f}`)} · ${count(f)}`, checked: f === filter, onselect: () => { haptic.select(); filter = f; },
  })), 'start');

  /** the grey line: the program, then the interview (only where the program has one) */
  function line(a: AkoRow): string {
    const p = desk?.programs.find((x) => x.key === a.program), info = p?.info[i18n.lang];
    return [info?.title, info?.sub, a.slot ? whenLine(a.slot.at) : p?.interview ? aw('akd.noSlot') : ''].filter(Boolean).join(' · ');
  }

  // ---- interview days ----
  type Day = { key: string; title: string; teams: string; free: number; slots: AkoSlot[] };
  const byId = $derived(new Map((desk?.apps ?? []).map((a) => [a.id, a])));
  const names = (s: AkoSlot) => s.apps.map((id) => byId.get(id)?.name).filter(Boolean).join(', ');
  const days = $derived.by(() => {
    const out: Day[] = [];
    if (!desk) return out;
    for (const s of [...desk.slots].sort((a, b) => a.at - b.at)) {
      if (s.at + s.minutes * 60 < now) continue;
      const key = dateInput(s.at);
      let d = out.at(-1);
      if (!d || d.key !== key) {
        const wd = weekday(s.at);
        out.push((d = { key, title: `${wd.charAt(0).toUpperCase()}${wd.slice(1)}, ${dayMonth(s.at)}`, teams: desk.days[key] ?? '', free: 0, slots: [] }));
      }
      d.slots.push(s);
      d.free += Math.max(0, s.cap - s.apps.length);
    }
    return out;
  });
  const short = (url: string) => url.replace(/^https?:\/\//, '');
  const under = (s: AkoSlot) => [s.who, s.teams ? aw('akd.slotTeams') : '', s.cap > 1 ? `${s.apps.length}/${s.cap}` : ''].filter(Boolean).join(' · ') || undefined;

  // one small editor under the day it belongs to: the day's link, a time's own link or interviewer, a booked time's reason
  type Ed = { mode: 'day' | 'teams' | 'who' | 'drop'; day: string; slot?: AkoSlot; text: string; error: string; busy: boolean };
  let ed = $state<Ed | null>(null);
  const edit = (mode: Ed['mode'], day: string, slot: AkoSlot | undefined, text: string) => { ed = { mode, day, slot, text, error: '', busy: false }; };
  const edLabel = (e: Ed) => (e.mode === 'day' ? aw('akd.teams') : `${time(e.slot!.at)} · ${aw(e.mode === 'who' ? 'akd.who' : e.mode === 'teams' ? 'akd.slotTeams' : 'akd.reason')}`);
  function reveal(node: HTMLElement) {
    node.scrollIntoView({ block: 'center', behavior: matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' });
    node.querySelector<HTMLElement>('input, textarea')?.focus({ preventScroll: true });
  }

  function slotMenu(e: MouseEvent, s: AkoSlot) {
    const day = dateInput(s.at);
    menu(e.currentTarget as Element, [
      ...s.apps.map((id) => ({ label: byId.get(id)?.name ?? '', icon: UserRound, onselect: () => openApp(id) })),
      { label: aw('akd.who'), icon: UserRound, onselect: () => edit('who', day, s, s.who) },
      { label: aw('akd.slotTeams'), icon: Video, onselect: () => edit('teams', day, s, s.teams ?? '') },
      { label: aw('akd.dropSlot'), icon: Trash2, destructive: true, onselect: () => (s.apps.length ? edit('drop', day, s, '') : void drop(s, false, '')) },
    ], 'end');
  }
  const tapSlot = (s: AkoSlot) => (manage ? (e: MouseEvent) => slotMenu(e, s) : s.apps.length ? () => openApp(s.apps[0]) : undefined);

  async function drop(s: AkoSlot, force: boolean, reason: string) {
    const id = s.id;
    const err = await change((d) => {
      d.slots = d.slots.filter((x) => x.id !== id);
      for (const a of d.apps) if (a.slot?.id === id) a.slot = null;
    }, () => akoTeam.akoDropSlot(org, id, force, reason));
    if (err) say(t('common.error'), 'warning_3d');
    if (err || force) void load(); // someone booked it meanwhile, or its people now need a new time: the server's truth
  }

  async function save() {
    const e = ed;
    if (!e || e.busy) return;
    const text = e.text.trim();
    if (e.mode === 'drop') {
      const s = e.slot!;
      if (!(await sheets.ask({ title: aw('akd.dropBooked', { name: names(s) }), text: text || undefined, ok: aw('akd.dropSlot'), cancel: t('common.cancel'), danger: true }))) return;
      ed = null;
      return drop(s, true, text);
    }
    const link = e.mode !== 'who';
    if (link && text && !/^https:\/\/\S+$/.test(text)) { e.error = aw('akd.teamsBad'); haptic.warn(); return; }
    e.busy = true;
    const err = await change((d) => {
      if (e.mode === 'day') { if (text) d.days[e.day] = text; else delete d.days[e.day]; return; }
      const s = d.slots.find((x) => x.id === e.slot!.id);
      if (s && e.mode === 'who') s.who = text;
      else if (s) s.teams = text || null;
    }, () => (e.mode === 'day' ? akoTeam.akoSetDay(org, e.day, text) : akoTeam.akoUpdateSlot(org, e.slot!.id, e.mode === 'who' ? { who: text } : { teams: text })));
    e.busy = false;
    if (!err) ed = null;
    else if (link && err instanceof ApiErr && err.message === 'bad_input') e.error = aw('akd.teamsBad');
    else say(t('common.error'), 'warning_3d');
  }
</script>

<Pane {overlay} title={aw('akd.title')}>
  <div class="page">
    <div class="bar">
      <div class="segs">
        <Segmented items={[{ value: 'apps', label: aw('akd.tabApps') }, { value: 'slots', label: aw('akd.tabSlots') }]} bind:value={tab}
          label={t('studio.ako')} onchange={() => { haptic.select(); ed = null; }} />
      </div>
      {#if manage}
        <Button kind="secondary" size="s" round label={aw('akd.more')} onclick={more}>{#snippet icon()}<Ellipsis size={18} />{/snippet}</Button>
        <Button size="s" round label={aw('akd.new')} onclick={newApp}>{#snippet icon()}<Plus size={18} strokeWidth={2.4} />{/snippet}</Button>
      {/if}
    </div>

    {#if !desk}
      {#if failed}<EmptyState onretry={load} />{:else}<Skeleton kind="rows" n={6} />{/if}
    {:else if tab === 'apps'}
      <section class="part">
        {#if !desk.apps.length}
          <EmptyState icon={Inbox} title={aw('akd.empty')} text={aw('akd.emptyLead')} action={manage ? { label: aw('akd.new'), onclick: newApp } : undefined} />
        {:else}
          {#if desk.apps.length > 8}
            <label class="find"><Search size={18} /><input type="search" bind:value={q} placeholder={aw('akd.search')} aria-label={aw('akd.search')} enterkeyhint="search" autocomplete="off" /></label>
          {/if}
          <div class="tools">
            <button class="flt" aria-haspopup="menu" onclick={pickFilter}>{aw(`akd.filter.${filter}`)}<span class="n num">{count(filter)}</span><ChevronsUpDown size={16} /></button>
            {#if !manage}<span class="ro">{aw('akd.reviewOnly')}</span>{/if}
          </div>
          <Group>
            {#each shown as a (a.id)}
              <Row dense title={a.name || a.phone} subtitle={line(a)} accessory="chevron" onclick={() => openApp(a.id)}>
                {#snippet detail()}
                  <span class="meta">
                    <span class="chip {a.status}">{#if a.rebook}<span class="mark" role="img" aria-label={aw('akd.noSlot')}><TriangleAlert size={12} strokeWidth={2.4} /></span>{/if}{aw(`akd.status.${a.status}`)}</span>
                    {#if a.missing.length}<span class="miss" title={awn('akd.missingN', a.missing.length)}>{awn('akd.missShort', a.missing.length)}</span>
                    {:else}<span class="miss ok" role="img" aria-label={aw('akd.complete')}><Check size={14} strokeWidth={2.4} /></span>{/if}
                  </span>
                {/snippet}
              </Row>
            {:else}
              <EmptyState inline text={aw('akd.noneHere')} />
            {/each}
          </Group>
        {/if}
      </section>
    {:else}
      <section class="part">
        {#if !days.length}
          <EmptyState icon={CalendarClock} title={aw('akd.noSlots')} text={aw('akd.noSlotsLead')} action={manage ? { label: aw('akd.addDay'), onclick: addDay } : undefined} />
        {:else}
          {#each days as d (d.key)}
            <div class="day">
              <Group caption={d.title} note={awn('akd.freeN', d.free)}>
                <Row dense title={aw('akd.teamsRow')} value={d.teams ? short(d.teams) : undefined} onclick={manage ? () => edit('day', d.key, undefined, d.teams) : undefined}>
                  {#snippet detail()}{#if !d.teams}<span class="warn"><TriangleAlert size={14} strokeWidth={2.2} />{aw('akd.teamsMissing')}</span>{/if}{/snippet}
                </Row>
                {#each d.slots as s (s.id)}
                  <Row dense title={time(s.at)} subtitle={under(s)} value={s.apps.length ? undefined : aw('akd.free')} onclick={tapSlot(s)}>
                    {#snippet detail()}{#if s.apps.length}<span class="who">{names(s)}</span>{/if}{/snippet}
                  </Row>
                {/each}
              </Group>
              {#if ed && ed.day === d.key}
                <div class="ed" use:reveal>
                  <Field label={edLabel(ed)} bind:value={ed.text} error={ed.error || undefined} multiline={ed.mode === 'drop'} rows={2} maxlength={ed.mode === 'drop' ? 300 : undefined}
                    type={ed.mode === 'day' || ed.mode === 'teams' ? 'url' : 'text'} inputmode={ed.mode === 'day' || ed.mode === 'teams' ? 'url' : 'text'}
                    placeholder={ed.mode === 'day' || ed.mode === 'teams' ? aw('akd.teamsPh') : undefined} enterkeyhint="done" />
                  <div class="acts btns">
                    <Button kind="secondary" full onclick={() => (ed = null)}>{t('common.cancel')}</Button>
                    <Button kind={ed.mode === 'drop' ? 'destructive' : 'primary'} full loading={ed.busy} onclick={save}>{aw(ed.mode === 'drop' ? 'akd.dropSlot' : 'akd.save')}</Button>
                  </div>
                </div>
              {/if}
            </div>
          {/each}
          {#if manage}<Group><Row tone="add" title={aw('akd.addDay')} onclick={addDay} /></Group>{/if}
          <p class="quiet">{aw('akd.cutoff', { n: Math.round(desk.cutoff / 3600) })}</p>
        {/if}
      </section>
    {/if}
  </div>
</Pane>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-4); }
  .bar { display: flex; align-items: center; gap: var(--s-2); }
  .segs { flex: 1; min-width: 0; }
  .part { display: flex; flex-direction: column; gap: var(--s-3); animation: part-in var(--t-base) var(--ease) both; }
  @keyframes part-in { from { opacity: 0; transform: translateY(6px); } }
  @media (prefers-reduced-motion: reduce) { .part { animation: none; } }
  .num { font-variant-numeric: tabular-nums; }

  /* search: the M control on --fill; 17 px text, so iOS doesn't zoom in */
  .find { display: flex; align-items: center; gap: var(--s-2); height: var(--ctl-m); padding: 0 var(--s-4); border-radius: var(--r-full); background: var(--fill); color: var(--text-3); }
  .find input { flex: 1; min-width: 0; height: 100%; background: none; color: var(--text); font: 450 var(--fs-row)/1.3 var(--font-text); letter-spacing: -0.012em; }
  .find input::placeholder { color: var(--text-3); }
  .find input::-webkit-search-cancel-button { display: none; }

  /* the filter: one quiet pull-down, the list's own heading */
  .tools { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); margin: 0 var(--s-1); }
  .flt { display: inline-flex; align-items: center; gap: var(--s-1); min-height: var(--tap); color: var(--text); font: 600 var(--fs-body)/1.2 var(--font-text); letter-spacing: -0.008em; }
  .flt .n { margin-left: 2px; color: var(--text-3); font-weight: 500; }
  .flt :global(svg) { color: var(--text-3); }
  .flt:active { opacity: 0.6; transform: none; }
  .ro { color: var(--text-3); font: 450 var(--fs-sub)/1.2 var(--font-text); }

  /* an applicant's end: the status, under it what's missing (or a quiet check) */
  .meta { display: flex; flex-direction: column; align-items: flex-end; gap: var(--s-1); }
  .chip { display: inline-flex; align-items: center; gap: var(--s-1); padding: var(--s-1) var(--s-2); border-radius: var(--r-full); background: var(--fill); color: var(--text-2);
    font: 600 var(--fs-cap)/1.2 var(--font-text); white-space: nowrap; }
  .chip.sent { background: var(--accent-soft); color: var(--accent-text); }
  .chip.accepted { background: var(--success-soft); color: var(--success-text); }
  .chip.declined { background: var(--danger-soft); color: var(--danger-text); }
  .chip.draft { padding-inline: 0; background: none; color: var(--text-3); font-weight: 500; }
  .mark { display: inline-flex; color: var(--warning-text); }
  .miss { display: inline-flex; color: var(--text-3); font: 450 var(--fs-cap)/1.2 var(--font-text); white-space: nowrap; }
  .miss.ok { color: var(--success-text); }

  /* a day: its group, then (when asked) its editor */
  .part:has(.day) { gap: var(--gap-group); }
  .day { display: flex; flex-direction: column; gap: var(--s-3); }
  .day :global(.tt) { font-variant-numeric: tabular-nums; }
  .warn { display: inline-flex; align-items: center; gap: var(--s-1); color: var(--warning-text); font: 500 var(--fs-sub)/1.2 var(--font-text); white-space: nowrap; }
  .who { max-width: 46vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text); font: 500 var(--fs-body)/1.3 var(--font-text); }
  .ed { display: flex; flex-direction: column; gap: var(--s-3); animation: part-in var(--t-base) var(--ease) both; }
  @media (prefers-reduced-motion: reduce) { .ed { animation: none; } }
  .acts { display: flex; gap: var(--s-2); }
  .quiet { margin: calc(-1 * var(--s-2)) var(--s-4) 0; color: var(--text-3); font: 450 var(--fs-sub)/1.4 var(--font-text); }
</style>
