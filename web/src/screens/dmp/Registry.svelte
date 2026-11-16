<script lang="ts">
  // DMP's clubs registry (SPEC §4.13): every club with its live numbers for this month and its President — instead of
  // asking in chats who leads what and instead of monthly reports. A club opens its roster; a name or a student ID finds a
  // member and their clubs; CSV sends every roster into my chat with the bot. A sheet, from Studio (DMP) and the Admin panel.
  // wide (a computer's window, RegistrySheet): the same registry as a sortable table with the chosen club's roster beside it,
  // for a desk: "/" to the search, arrows move the chosen row, Esc clears.
  import Maximize2 from '@lucide/svelte/icons/maximize-2';
  import ArrowUp from '@lucide/svelte/icons/arrow-up';
  import ArrowDown from '@lucide/svelte/icons/arrow-down';
  import RosterBody from './RosterBody.svelte';
  import { i18n } from '../../lib/i18n/index.svelte';
  import { chosen } from '../../lib/desk';
  import FileDown from '@lucide/svelte/icons/file-down';
  import OfficialMark from '../../ui/OfficialMark.svelte';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import ChevronLeft from '@lucide/svelte/icons/chevron-left';
  import { api, ApiErr, type RegistryHit, type RegistryOrg, type SentMemo } from '../../lib/api';
  import { say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { monthName, nowTs, relDay, time } from '../../lib/time';
  import { roleLabel, withNick } from '../../lib/perms';
  import { haptic, tg } from '../../lib/tg';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import { data, loadRegistry } from '../../lib/state/data.svelte';
  import { untrack } from 'svelte';
  import { nameOf, schoolShort, shortOf } from '../../lib/short';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';

  // top: nothing stands over the registry (its keys are its own only then)
  let { inSheet = false, wide = false, top = true }: { inSheet?: boolean; wide?: boolean; top?: boolean } = $props();
  // the month: this one (loaded with the app, so the page opens full), or up to a year back (the numbers DMP used to
  // collect as monthly reports)
  let back = $state(0);
  let past = $state<RegistryOrg[] | null>(null);
  const orgs = $derived(back === 0 ? data.registry : past);
  $effect(() => {
    const b = back;
    untrack(() => {
      if (b === 0) { void loadRegistry().then((ok) => { if (!ok) { data.registry ??= []; say(t('common.error'), 'warning_3d'); } }); return; }
      past = null;
      api.registry(b).then((l) => { if (b === back) past = l; }).catch(() => { past = []; say(t('common.error'), 'warning_3d'); });
    });
  });
  const monthTs = $derived.by(() => { const d = new Date((nowTs() + 5 * 3600) * 1000); return Date.UTC(d.getUTCFullYear(), d.getUTCMonth() - back, 15) / 1000; });
  const people = $derived((orgs ?? []).reduce((s, o) => s + o.members, 0));

  // the memos clubs marked sent this week (DMP sees them in the app, not only in its mailbox)
  let memos = $state<SentMemo[]>([]);
  $effect(() => { api.registryMemos().then((l) => (memos = l)).catch(() => {}); });

  let q = $state('');
  let hits = $state<RegistryHit[] | null>(null);
  let timer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    const s = q.trim();
    clearTimeout(timer);
    if (s.length < 2) { hits = null; return; }
    timer = setTimeout(() => { api.registrySearch(s).then((l) => { if (q.trim() === s) hits = l; }).catch(() => {}); }, 250);
  });

  let sending = $state(false);
  async function exportCsv() {
    sending = true; haptic.tap();
    try { await api.registryExport(); haptic.ok(); say(t('reg.sent'), 'sparkles_3d'); }
    catch (e) { haptic.error(); say(e instanceof ApiErr && e.message === 'no_dm' ? t('att.noDm') : t('common.error'), 'warning_3d'); }
    finally { sending = false; }
  }

  // ---- wide ----
  type Col = 'club' | 'pres' | 'people' | 'events' | 'regs' | 'came' | 'ok';
  const COLS: { col: Col; key: 'reg.cClub' | 'reg.cPres' | 'reg.cPeople' | 'reg.cEvents' | 'reg.cRegs' | 'reg.cCame' | 'reg.cOfficial'; num?: boolean }[] = [
    { col: 'club', key: 'reg.cClub' }, { col: 'pres', key: 'reg.cPres' }, { col: 'people', key: 'reg.cPeople', num: true },
    { col: 'events', key: 'reg.cEvents', num: true }, { col: 'regs', key: 'reg.cRegs', num: true }, { col: 'came', key: 'reg.cCame', num: true },
    { col: 'ok', key: 'reg.cOfficial', num: true },
  ];
  const val = (o: RegistryOrg, c: Col): string | number => c === 'club' ? nameOf(o.org) : c === 'pres' ? o.president?.fullName ?? '\uffff'
    : c === 'people' ? o.members : c === 'events' ? o.month.events : c === 'regs' ? o.month.registrations : c === 'came' ? o.month.came : o.org.official ? 1 : 0;
  // the server's order until a column head is tapped; text A→Z first, numbers the most first
  let sort = $state<{ col: Col; dir: 1 | -1 } | null>(null);
  const by = (col: Col) => (sort = sort?.col === col ? { col, dir: sort.dir === 1 ? -1 : 1 } : { col, dir: col === 'club' || col === 'pres' ? 1 : -1 });
  const rows = $derived.by(() => {
    const l = orgs ?? [];
    if (!sort) return l;
    const { col, dir } = sort;
    return [...l].sort((a, b) => { const x = val(a, col), y = val(b, col); return (typeof x === 'number' ? x - (y as number) : x.localeCompare(y as string, i18n.lang)) * dir; });
  });
  // the chosen club by id: its row's current object, and only while the list on screen has it (lib/desk.ts)
  let selId = $state<number | null>(null);
  const sel = $derived(chosen(selId, orgs, hits));
  const pick = (o: RegistryOrg) => { selId = o.org.id; document.getElementById(`reg-${o.org.id}`)?.scrollIntoView({ block: 'nearest' }); };
  let find = $state<HTMLDivElement>();
  // a document listener runs before the app's own Esc on the window (which closes the sheet): Esc clears here first.
  // Only while the registry is on top, and from no field but its own search (a question over it keeps its keys)
  function keys(e: KeyboardEvent) {
    if (!wide || !top || e.defaultPrevented || e.metaKey || e.ctrlKey || e.altKey) return;
    const field = (e.target as Element | null)?.closest?.('input, textarea, select, [contenteditable]');
    if (field && !find?.contains(field)) return;
    if (e.key === 'Escape' && (q || sel)) { e.stopPropagation(); e.preventDefault(); if (q) q = ''; else selId = null; (field as HTMLElement | null)?.blur(); return; }
    if (field) return;
    if (e.key === '/') { e.preventDefault(); find?.querySelector('input')?.focus(); return; }
    if ((e.key === 'ArrowDown' || e.key === 'ArrowUp') && !hits && rows.length) {
      e.preventDefault();
      const i = rows.findIndex((o) => o.org.id === sel?.id);
      pick(rows[i < 0 ? 0 : Math.max(0, Math.min(rows.length - 1, i + (e.key === 'ArrowDown' ? 1 : -1)))]);
    }
  }
  const official = (id: number, on: boolean) => { const o = orgs?.find((x) => x.org.id === id); if (o) o.org = { ...o.org, official: on }; };
</script>

<svelte:document onkeydown={keys} />

{#snippet head()}
  <header class="hd">
    <span><h1 class="t-h1">{t('reg.title')}</h1><p class="t-foot">{orgs ? `${tn('reg.clubs', orgs.length)} · ${tn('reg.people', people)}` : ' '}</p></span>
    <span class="acts">
      <!-- a computer's Telegram window too narrow for the table: Telegram's own full screen (8.0+), never forced -->
      {#if inSheet && !wide && tg.canFullscreen()}<IconButton icon={Maximize2} label={t('reg.full')} kind="plain" size="s" onclick={() => tg.fullscreen()} />{/if}
      <Button kind="tinted" size="s" loading={sending} onclick={exportCsv}>{#snippet icon()}<FileDown size={17} />{/snippet}CSV</Button>
    </span>
  </header>
{/snippet}

{#snippet month()}
  <div class="mh">
    <IconButton icon={ChevronLeft} label="‹" kind="plain" size="s" disabled={back >= 12} onclick={() => back++} />
    <h3 class="cap">{t('reg.month', { month: monthName(monthTs) })}</h3>
    <IconButton icon={ChevronRight} label="›" kind="plain" size="s" disabled={back <= 0} onclick={() => back--} />
  </div>
{/snippet}

{#snippet found(hits: RegistryHit[])}
  <Group>
    {#each hits as h (h.person.id)}
      <Row dense title={withNick(h.fullName, h.person)} subtitle={[h.studentId, h.course && t('person.year', { n: h.course }), h.school && schoolShort(h.school)].filter(Boolean).join(' · ')}>
        {#snippet lead()}<Avatar person={h.person} size={36} />{/snippet}
      </Row>
      {#each h.clubs as c (c.org.id)}
        <Row dense title="{shortOf(c.org)} · {roleLabel(c)}" accessory="chevron" onclick={() => (wide ? (selId = c.org.id) : sheets.roster(c.org))}>
          {#snippet lead()}<span class="in"><OrgLogo org={c.org} size={24} /></span>{/snippet}
        </Row>
      {/each}
    {:else}<EmptyState inline text={t('reg.nobody')} />{/each}
  </Group>
{/snippet}

{#snippet sent()}
  <Group caption={t('reg.memos')} footnote={t('reg.memoNote')}>
    {#each memos as m (`${m.org.id}:${m.sentAt}`)}
      <Row dense title={nameOf(m.org)} subtitle={t('reg.memoSent', { who: m.by ?? '—', when: `${relDay(m.sentAt)} ${time(m.sentAt)}` })}>
        {#snippet lead()}<OrgLogo org={m.org} size={36} />{/snippet}
      </Row>
      {#each m.events as e (e.id)}<Row dense title={e.title} value={relDay(e.startsAt)} accessory="chevron" onclick={() => sheets.event(e.id)} />{/each}
    {/each}
  </Group>
{/snippet}

{#if wide}
  <div class="wd">
    <section class="lt">
      {@render head()}
      <div class="bar">
        <div class="find" bind:this={find}><SearchField bind:value={q} placeholder={t('reg.find')} /></div>
        {@render month()}
      </div>
      {#if hits}
        {@render found(hits)}
      {:else if orgs}
        <table class="tb">
          <thead>
            <tr>
              {#each COLS as c (c.col)}
                <th class={{ num: c.num }} aria-sort={sort?.col === c.col ? (sort.dir === 1 ? 'ascending' : 'descending') : undefined}>
                  <button onclick={() => by(c.col)} aria-label={t(c.key)}>
                    {#if c.col === 'ok'}<OfficialMark size={14} />{:else}{t(c.key)}{/if}
                    {#if sort?.col === c.col}{#if sort.dir === 1}<ArrowUp size={12} strokeWidth={2.6} />{:else}<ArrowDown size={12} strokeWidth={2.6} />{/if}{/if}
                  </button>
                </th>
              {/each}
            </tr>
          </thead>
          <tbody>
            {#each rows as o (o.org.id)}
              <!-- a whole row is the target for a mouse; the keyboard's way is the arrows (keys above) and the club's button -->
              <tr id="reg-{o.org.id}" class={{ on: sel?.id === o.org.id }} onclick={() => (selId = o.org.id)}>
                <td><button class="club" aria-current={sel?.id === o.org.id || undefined} onclick={(e) => { e.stopPropagation(); selId = o.org.id; }}><OrgLogo org={o.org} size={28} /><span class="ellipsis">{nameOf(o.org)}</span></button></td>
                <td class="pres ellipsis">{o.president?.fullName ?? '—'}</td>
                <td class="num">{o.members}</td>
                <td class="num">{o.month.events}</td>
                <td class="num">{o.month.registrations}</td>
                <td class="num">{o.month.came}</td>
                <td class="num seal">{#if o.org.official}<OfficialMark size={15} />{/if}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      {:else}
        <Skeleton n={6} />
      {/if}
    </section>
    <aside class="rt">
      {#if sel}
        {@const id = sel.id}
        {#key id}<RosterBody org={sel} onofficial={(on) => official(id, on)} />{/key}
      {:else}
        {#if back === 0 && memos.length}{@render sent()}{/if}
        <p class="pick t-foot">{t('reg.pick')}</p>
      {/if}
    </aside>
  </div>
{:else}
<div class="pg" class:page={!inSheet} class:scroll={!inSheet}>
  {@render head()}

  <SearchField bind:value={q} placeholder={t('reg.find')} />

  {#if hits}
    {@render found(hits)}
  {:else if orgs}
    {#if back === 0 && memos.length}{@render sent()}{/if}
    <section class="mo">
      {@render month()}
      <Group>
        {#each orgs as o (o.org.id)}
          <Row dense title={nameOf(o.org)} accessory="chevron" onclick={() => sheets.roster(o.org, (on) => (o.org = { ...o.org, official: on }))}
            subtitle={[o.president ? t('reg.president', { name: o.president.fullName }) : t('reg.noPresident'), `${o.members} ${tn('reg.members', o.members)}`,
              `${o.month.events} ${tn('reg.events', o.month.events)}`, `${o.month.registrations} ${tn('reg.regs', o.month.registrations)}`, `${o.month.came} ${tn('reg.came', o.month.came)}`].join(' · ')}>
            {#snippet lead()}<OrgLogo org={o.org} size={40} />{/snippet}
            <!-- engine: Row's mark after the title (the official ✓); here it stands at the row's end -->
            {#snippet detail()}{#if o.org.official}<span class="ok"><OfficialMark size={15} /></span>{/if}{/snippet}
          </Row>
        {/each}
      </Group>
    </section>
  {:else}
    <Skeleton n={3} />
  {/if}
  {#if !inSheet}<div class="tail"></div>{/if}
</div>
{/if}

<style>
  .pg { display: flex; flex-direction: column; gap: var(--gap-group); }
  /* as a page of DMP's tab (the sheet brings its own): under the capsule, the bottom nav's room at the end */
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; background: var(--glow), var(--bg); }
  .tail { flex: none; height: calc(var(--bottom) + 24px); }
  .hd { display: flex; align-items: flex-end; justify-content: space-between; gap: var(--s-3); margin-bottom: calc(var(--s-3) - var(--gap-group)); }
  .hd p { margin-top: var(--s-1); }
  .mo { display: flex; flex-direction: column; }
  .mh { display: flex; align-items: center; gap: var(--s-1); margin-bottom: var(--s-2); }
  /* Group's caption, between the month's arrows */
  .cap { flex: 1; min-width: 0; text-align: center; font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; }
  .in { padding-left: var(--s-8); }
  .ok { display: inline-flex; color: var(--accent-text); }
  .acts { flex: none; display: inline-flex; align-items: center; gap: var(--s-1); }

  /* wide: the table on the left, the chosen club's roster on the right, each pane under the capsule */
  .wd { display: grid; grid-template-columns: minmax(0, 1fr) minmax(380px, 0.7fr); gap: var(--s-6); max-width: 1440px; margin: 0 auto; padding: 0 var(--s-4); }
  .lt { min-width: 0; display: flex; flex-direction: column; gap: var(--s-4); }
  .lt .hd { margin-bottom: 0; }
  .bar { display: flex; align-items: center; gap: var(--s-4); }
  .find { flex: 1; max-width: 420px; }
  .bar .mh { margin: 0 0 0 auto; min-width: 280px; }
  .rt { position: sticky; top: var(--page-top); align-self: start; max-height: calc(100vh - var(--page-top) - var(--s-4)); overflow-y: auto; overscroll-behavior: contain;
    padding-bottom: var(--s-4); }
  .pick { padding: var(--s-6) var(--s-4); text-align: center; color: var(--text-3); }
  .tb { width: 100%; border-collapse: separate; border-spacing: 0; table-layout: fixed; background: var(--surface); border-radius: var(--r-group);
    font: 450 var(--fs-body)/1.3 var(--font-text); }
  .tb th { position: sticky; top: var(--page-top); z-index: 1; height: 38px; padding: 0 var(--s-3); background: var(--surface-solid); border-bottom: 1px solid var(--line);
    text-align: left; font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-3); white-space: nowrap; }
  /* the corners by hand: an overflow on the table would end the sticky head */
  .tb th:first-child { width: 58%; border-top-left-radius: var(--r-group); }
  .tb th:last-child { border-top-right-radius: var(--r-group); }
  .tb tr:last-child td:first-child { border-bottom-left-radius: var(--r-group); }
  .tb tr:last-child td:last-child { border-bottom-right-radius: var(--r-group); }
  .tb th:nth-child(2) { width: 42%; }
  .tb th.num { width: 72px; padding-left: 0; }
  .tb th:last-child { width: 44px; }
  .tb th button { display: inline-flex; align-items: center; gap: 3px; height: 100%; color: inherit; }
  .tb th button:hover, .tb th[aria-sort] button { color: var(--text); }
  .tb .num { text-align: right; font-variant-numeric: tabular-nums; }
  .tb th.num button { flex-direction: row-reverse; }
  .tb td { height: 48px; padding: 0 var(--s-3); border-bottom: 0.5px solid var(--line); white-space: nowrap; }
  .tb tr:last-child td { border-bottom: 0; }
  .tb tbody tr { cursor: pointer; }
  .tb tbody tr:hover td { background: var(--fill); }
  .tb tbody tr.on td { background: var(--accent-soft); }
  .tb .pres { color: var(--text-2); }
  .tb td.seal { color: var(--accent-text); }
  .tb td.seal :global(svg) { display: inline-block; vertical-align: middle; }
  .club { display: flex; align-items: center; gap: var(--s-3); width: 100%; min-width: 0; font: 600 var(--fs-row)/1.25 var(--font-text); letter-spacing: -0.01em; }
  .club :global(*) { flex: none; }
  .club .ellipsis { flex: 1; min-width: 0; }
</style>
