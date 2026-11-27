<script lang="ts">
  // Studio's «Guest list» (server organizing.guest_list): the organizers' own .xlsx or .csv, read in the browser
  // (lib/sheet.ts), its columns guessed from the header row and fixable, then a preview of exactly what saving does
  // (the server runs it and rolls back): who gets a ticket, who is on the door's list by name, repeats, bad rows and
  // why, app sign-ups the first list ends. Saving again with a corrected file keeps who came and the door's 18+ marks.
  // The door's list as a CSV, after the event too, comes from the bot (like the attendees').
  import FileSpreadsheet from '@lucide/svelte/icons/file-spreadsheet';
  import Download from '@lucide/svelte/icons/download';
  import { api, ApiErr, type GuestListResult, type Id } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { studioChanged } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { FIELDS, guessColumns, isHeader, pickRows, readSheet, SheetError, type Columns, type Field } from '../../lib/sheet';
  import Sheet from '../../ui/Sheet.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();

  const MAX_ROWS = 3000; // server guests.LIST_ROWS
  let input = $state<HTMLInputElement>();
  let file = $state('');
  let table = $state<string[][]>([]);
  let header = $state(false);
  let cols = $state<Columns>({ name: null, sid: null, adult: null, username: null, team: null });
  let result = $state<GuestListResult | null>(null);
  let busy = $state(false);
  let sending = $state(false);

  const body = $derived(header ? table.slice(1) : table);
  const width = $derived(Math.max(0, ...table.slice(0, 50).map((r) => r.length)));
  // a column's name for the picker: its header cell, else its letter and the first value
  const letter = (i: number): string => (i >= 26 ? letter(Math.floor(i / 26) - 1) : '') + String.fromCharCode(65 + (i % 26));
  const label = (i: number) => {
    const sample = (header ? table[0]?.[i] : body.find((r) => r[i]?.trim())?.[i])?.trim();
    return sample ? `${letter(i)} · ${sample.slice(0, 28)}` : letter(i);
  };

  async function picked() {
    const f = input?.files?.[0];
    if (input) input.value = ''; // the same file again after a fix still fires
    if (!f) return;
    result = null;
    try {
      const rows = await readSheet(f);
      if (!rows.length) throw new SheetError('empty');
      table = rows; file = f.name;
      header = isHeader(rows[0]);
      cols = header ? guessColumns(rows[0]) : { name: 0, sid: null, adult: null, username: null, team: null };
      haptic.ok();
      if (body.length > MAX_ROWS) { haptic.error(); say(t('gl.err.many'), 'warning_3d'); }
      else void check(true); // the preview at once, no extra tap
    } catch (e) {
      haptic.error();
      const why = e instanceof SheetError ? e.message : '';
      say(t(why === 'big' ? 'gl.err.big' : why === 'xls' ? 'gl.err.xls' : why === 'empty' ? 'gl.err.empty' : 'gl.err.read'), 'warning_3d');
    }
  }

  function setCol(f: Field, i: number | null) {
    haptic.tap();
    for (const g of FIELDS) if (i != null && g !== f && cols[g] === i) cols[g] = null; // a column means one thing
    cols[f] = i; result = null;
    void check(true); // a fixed column: the preview again by itself
  }
  const colItems = (f: Field) => [
    { label: t('gl.noCol'), checked: cols[f] == null, onselect: () => setCol(f, null) },
    ...Array.from({ length: width }, (_, i) => ({ label: label(i), checked: cols[f] === i, onselect: () => setCol(f, i) })),
  ];
  const ready = $derived(!!body.length && body.length <= MAX_ROWS && cols.name != null);

  const fail = (e: unknown) => {
    haptic.error();
    const m = e instanceof ApiErr ? e.message : '';
    say(t(m === 'too_many' || m === 'too_big' ? 'gl.err.many' : m === 'no_rows' ? 'gl.err.empty' : e instanceof ApiErr && e.code === 'closed' ? 'mk.closed' : 'common.error'), 'warning_3d');
  };
  // auto: after a file or a column change, quiet while the name's column is missing; the latest check wins
  let seq = 0;
  async function check(auto = false) {
    if (!ready) { if (!auto) { haptic.error(); say(t('gl.needName'), 'warning_3d'); } return; }
    const n = ++seq;
    busy = true;
    try { const r = await api.guestList(id, pickRows(body, cols), false); if (n === seq) { result = r; if (!auto) haptic.ok(); } }
    catch (e) { if (n === seq) fail(e); }
    finally { if (n === seq) busy = false; }
  }
  async function save() {
    if (!result || busy) return;
    if (result.dropped && !(await sheets.ask({ title: t('gl.dropAsk'), text: t('gl.dropText', { n: result.dropped }), ok: t('common.save'), cancel: t('common.cancel'), danger: true }))) return;
    busy = true; seq++; // a check still on its way must not land over the save
    try {
      result = await api.guestList(id, pickRows(body, cols), true);
      haptic.ok(); say(t('gl.saved'), 'party_popper_3d');
      studioChanged();
      table = []; file = '';
    } catch (e) { fail(e); }
    finally { busy = false; }
  }
  async function exportList() {
    if (sending) return;
    sending = true;
    try { await api.exportGuestList(id); haptic.ok(); say(t('att.sent'), 'party_popper_3d'); }
    catch (e) { haptic.error(); say(e instanceof ApiErr && e.message === 'no_dm' ? t('att.noDm') : t('common.error'), 'warning_3d'); }
    finally { sending = false; }
  }
</script>

<Sheet {overlay} icon={FileSpreadsheet} full title={t('mk.guestList')}>
  <div class="col">
    <input bind:this={input} type="file" hidden onchange={picked}
      accept=".xlsx,.csv,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" />
    {#if !table.length}
      <p class="t-foot hint">{t('gl.hint')}</p>
      <Button kind="primary" size="l" full onclick={() => { haptic.tap(); input?.click(); }}>{#snippet icon()}<FileSpreadsheet size={19} />{/snippet}{t('gl.pick')}</Button>
    {:else}
      <Group>
        <Row icon={FileSpreadsheet} title={file} subtitle={t('gl.file', { n: body.length })}
          value={t('gl.other')} onclick={() => { haptic.tap(); input?.click(); }} />
        <Row title={t('gl.header')} accessory="switch" checked={header} onchange={(on) => { header = on; result = null; if (on) cols = guessColumns(table[0]); void check(true); }} />
      </Group>
      <Group caption={t('gl.cols')}>
        {#each FIELDS as f (f)}
          <Row dense title={t(`gl.col.${f}`)} value={cols[f] == null ? t('gl.noCol') : label(cols[f]!)} invalid={f === 'name' && cols.name == null} menu={colItems(f)} />
        {/each}
      </Group>
      {#if result}
        <Group caption={t('gl.preview')}>
          <Row dense title={t('gl.pRows')} value={String(result.rows)} />
          <Row dense title={t('gl.pInApp')} value={String(result.inApp)} />
          <Row dense title={t('gl.pOnList')} value={String(result.onList)} />
          {#if result.dupes}<Row dense title={t('gl.pDupes')} value={String(result.dupes)} />{/if}
          {#if result.removed}<Row dense title={t('gl.pRemoved')} value={String(result.removed)} />{/if}
          {#if result.dropped}<Row dense title={t('gl.pDropped')} value={String(result.dropped)} />{/if}
        </Group>
        {#if result.badCount}
          <Group caption="{t('gl.pBad')} · {result.badCount}">
            {#each result.bad as b (b.row)}<Row dense title={t(`gl.why.${b.why}`, { row: b.row + (header ? 1 : 0) })} />{/each}
            {#if result.badCount > result.bad.length}<Row dense title={t('gl.more', { n: result.badCount - result.bad.length })} />{/if}
          </Group>
        {/if}
        <p class="t-foot hint">{t('gl.keep')}</p>
        <Button kind="primary" size="l" full loading={busy} disabled={!result.rows} onclick={save}>{t('gl.save')}</Button>
      {:else}
        <Button kind="primary" size="l" full loading={busy} onclick={() => check()}>{t('gl.check')}</Button>
      {/if}
    {/if}
    <Group>
      <Row icon={Download} title={t('gl.export')} disabled={sending} accessory="chevron" onclick={exportList} />
    </Group>
  </div>
</Sheet>

<style>
  .col { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-1); }
  .hint { color: var(--text-3); padding: 0 var(--s-2); }
</style>
