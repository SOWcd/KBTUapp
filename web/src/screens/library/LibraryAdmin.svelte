<script lang="ts">
  // Admin → Library (server logic/library.py): rooms and their tables (seat counts), each table's seats live (free /
  // taken / being checked, never who), the sticker sheet as a PDF into the bot's chat, and the room's big-screen link
  // (/show?lib=<key>, for a laptop on the wall). Removing confirms first and can be undone.
  import { onMount } from 'svelte';
  import Armchair from '@lucide/svelte/icons/armchair';
  import Plus from '@lucide/svelte/icons/plus';
  import Printer from '@lucide/svelte/icons/printer';
  import MonitorUp from '@lucide/svelte/icons/monitor-up';
  import { api, ApiErr, type LibRoom } from '../../lib/api';
  import { staffOnly } from '../../lib/state/staffGate.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { copyText } from '../../ui/copy';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import { stickerPages } from './stickers';

  let { overlay }: { overlay: Overlay } = $props();
  staffOnly(() => overlay);
  let rooms = $state<LibRoom[] | null>(null), printing = $state(0);
  const load = () => api.libRooms().then((r) => (rooms = r), () => {});
  onMount(() => {
    void load();
    // ponytail: the live view reads again every 10 s while this sheet is open (no push channel to the app exists; the
    // admin's sheet only). Upgrade: the same server-sent stream when /show gets one
    const every = setInterval(() => { if (document.visibilityState === 'visible') void load(); }, 10_000);
    return () => clearInterval(every);
  });
  async function run(job: Promise<LibRoom[]>, ok?: string, undo?: () => void) {
    try { rooms = await job; haptic.ok(); if (ok) say(ok, 'books_3d', undo); } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }

  async function addRoom() {
    const name = await sheets.askText({ title: t('lib.adm.roomAsk'), ok: t('common.save'), cancel: t('common.cancel'), placeholder: t('lib.adm.roomPh'), max: 60, line: true });
    if (name?.trim()) void run(api.libAddRoom(name.trim()));
  }
  async function addTables(r: LibRoom) {
    const v = await sheets.askText({ title: t('lib.adm.addAsk'), text: t('lib.adm.addText'), ok: t('lib.adm.add'), cancel: t('common.cancel'), placeholder: '10 × 4', max: 12, line: true });
    const m = v && /^\s*(\d{1,2})\s*[x×*\s]\s*(\d{1,2})\s*$/i.exec(v);
    if (v == null) return;
    if (!m || +m[1] < 1 || +m[1] > 50 || +m[2] < 1 || +m[2] > 12) { say(t('lib.adm.addBad'), 'pleading_face_3d'); return; }
    void run(api.libAddTables(r.id, +m[2], +m[1]));
  }
  async function rename(r: LibRoom) {
    const name = await sheets.askText({ title: t('lib.adm.roomAsk'), ok: t('common.save'), cancel: t('common.cancel'), placeholder: t('lib.adm.roomPh'), max: 60, line: true, value: r.name });
    if (name?.trim() && name.trim() !== r.name) void run(api.libEditRoom(r.id, { name: name.trim() }));
  }
  async function dropRoom(r: LibRoom) {
    if (!(await sheets.ask({ title: t('lib.adm.dropRoomAsk', { room: r.name }), text: t('lib.adm.dropText'), ok: t('lib.adm.drop'), cancel: t('common.cancel'), danger: true }))) return;
    void run(api.libEditRoom(r.id, { gone: true }), t('lib.adm.dropped'), () => void run(api.libEditRoom(r.id, { gone: false })));
  }
  async function label(id: number, was: string) {
    const v = await sheets.askText({ title: t('lib.adm.labelAsk'), ok: t('common.save'), cancel: t('common.cancel'), placeholder: '12', max: 12, line: true, value: was });
    if (v?.trim() && v.trim() !== was) void run(api.libEditTable(id, { label: v.trim() }));
  }
  async function seats(id: number, was: number) {
    const v = await sheets.askText({ title: t('lib.adm.seatsAsk'), ok: t('common.save'), cancel: t('common.cancel'), placeholder: '4', max: 2, line: true, value: String(was) });
    const n = Number(v);
    if (v == null || n === was) return;
    if (!Number.isInteger(n) || n < 1 || n > 12) { say(t('lib.adm.addBad'), 'pleading_face_3d'); return; }
    void run(api.libEditTable(id, { seats: n }));
  }
  async function dropTable(id: number, name: string) {
    if (!(await sheets.ask({ title: t('lib.adm.dropTableAsk', { table: name }), text: t('lib.adm.dropText'), ok: t('lib.adm.drop'), cancel: t('common.cancel'), danger: true }))) return;
    void run(api.libEditTable(id, { gone: true }), t('lib.adm.dropped'), () => void run(api.libEditTable(id, { gone: false })));
  }
  async function print(r: LibRoom) {
    if (!r.tables.length || printing) return;
    printing = r.id; haptic.tap();
    try {
      const pages = await stickerPages(r.name, r.tables.map((x) => ({ label: x.label, seats: x.seats.length, code: x.code })));
      await api.libStickers(r.id, pages);
      haptic.ok(); say(t('lib.adm.sent'), 'books_3d');
    } catch (e) {
      haptic.error(); say(t(e instanceof ApiErr && e.message === 'no_dm' ? 'lib.adm.noDm' : 'common.error'), 'warning_3d');
    } finally { printing = 0; }
  }
  const wall = (r: LibRoom) => `${location.origin}/show?lib=${encodeURIComponent(r.screen)}`;
</script>

<Sheet {overlay} icon={Armchair} full title={t('lib.title')}>
  <div class="page">
    <p class="t-foot sub">{t('lib.adm.sub')}</p>
    {#each rooms ?? [] as r (r.id)}
      <Group caption={`${r.name} · ${t('lib.freeOf', { free: r.free, total: r.total })}`}>
        {#each r.tables as x (x.id)}
          <!-- the seats live: a dot each (free, taken, being checked), the free count as the row's value -->
          <Row dense title={t('lib.sticker.table', { table: x.label })} value={`${x.seats.filter((s) => s === 'free').length}/${x.seats.length}`} menu={[
            { label: t('lib.adm.label'), onselect: () => void label(x.id, x.label) },
            { label: t('lib.adm.seats'), onselect: () => void seats(x.id, x.seats.length) },
            { label: t('lib.adm.drop'), destructive: true, onselect: () => void dropTable(x.id, x.label) },
          ]}>
            {#snippet detail()}<span class="dots">{#each x.seats as s, i (i)}<i class={s === 'free' ? 'free' : s === 'taken' ? 'taken' : 'check'}></i>{/each}</span>{/snippet}
          </Row>
        {/each}
        <Row icon={Plus} tone="add" title={t('lib.adm.add')} onclick={() => void addTables(r)} />
        <Row icon={Printer} title={t('lib.adm.print')} subtitle={t('lib.adm.printSub')} disabled={!r.tables.length || !!printing} onclick={() => void print(r)} />
        <Row icon={MonitorUp} title={t('lib.adm.wall')} subtitle={t('lib.adm.wallSub')} onclick={() => void copyText(wall(r), t('lib.adm.copied'))} />
        <Row title={t('lib.adm.more')} menu={[
          { label: t('lib.adm.rename'), onselect: () => void rename(r) },
          { label: t('lib.adm.dropRoom'), destructive: true, onselect: () => void dropRoom(r) },
        ]} />
      </Group>
    {/each}
    {#if rooms && !rooms.length}<p class="t-foot sub">{t('lib.adm.none')}</p>{/if}
  </div>
  {#snippet footer()}
    <Button kind="secondary" size="l" full onclick={addRoom}>{#snippet icon()}<Plus size={20} />{/snippet}{t('lib.adm.roomAdd')}</Button>
  {/snippet}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-4); }
  .sub { padding: 0 var(--s-4); }
  .dots { display: inline-flex; flex-wrap: wrap; gap: 4px; max-width: 120px; justify-content: flex-end; }
  .dots i { width: 10px; height: 10px; border-radius: 50%; background: var(--success); }
  .dots i.taken { background: var(--text-3); }
  .dots i.check { background: var(--warning); }
</style>
