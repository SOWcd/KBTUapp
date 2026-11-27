<script module lang="ts">
  export const CONSENT = 'lib1'; // the feature's own consent (server library.CONSENT), asked on the first seat or report
  export const PREFIX = 'KBTU-LIB-'; // a table's sticker: a bare code, only this scanner takes it (server library.PREFIX)
</script>

<script lang="ts">
  // Library seats (server logic/library.py, LIBRARY): my seat with its time, my "nobody here" report, a scanned table's
  // seats as free / taken / being checked (never who), the rooms' free seats. Every seat action carries the sticker's
  // code: only someone at the table acts on it. Each tap answers at once (the seat changes in place) and the server's
  // answer settles it; a refusal puts it back and says why.
  import { onMount } from 'svelte';
  import Armchair from '@lucide/svelte/icons/armchair';
  import ScanQrCode from '@lucide/svelte/icons/scan-qr-code';
  import { api, ApiErr, type LibAct, type LibSeat, type LibState, type LibTable } from '../../lib/api';
  import { data } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { closeScanner, haptic, scanQr } from '../../lib/tg';
  import { countdown, dayMonth, nowTs, time } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Notice from '../../ui/Notice.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const lib = $derived(data.library);
  let table = $state<LibTable | null>(null), code = '', busy = $state(false), now = $state(nowTs());
  onMount(() => {
    void api.library().then((s) => (data.library = s), () => {}); // fresh on open; the copy from the launch shows meanwhile
    const tick = setInterval(() => (now = nowTs()), 1000);
    return () => { clearInterval(tick); closeScanner(); };
  });

  const mine = $derived(lib?.mine && lib.mine.until > now ? lib.mine : null);
  const asked = $derived(mine?.asked && mine.asked > now ? mine.asked : null);
  const report = $derived(lib?.report && (!lib.report.until || lib.report.until > now) ? lib.report : null);
  const blocked = $derived(lib?.blockedUntil && lib.blockedUntil > now ? lib.blockedUntil : null);
  const left = (until: number) => countdown(Math.max(0, until - now));

  function settle(r: LibAct | LibState) {
    if ('table' in r) { table = r.table; data.library = r.state; } else data.library = r;
    if (session.me?.library && data.library?.consent) session.me.library.consent = true;
  }
  function fail(e: unknown) {
    haptic.error();
    const m = e instanceof ApiErr ? e.message : '';
    const key = m === 'taken' ? 'lib.taken' : m === 'reported' ? 'lib.already' : m === 'waiting' ? 'lib.oneAtATime' : m === 'strikes' ? 'lib.blockedNow'
      : m === 'table' ? 'lib.notTable' : m === 'gone' ? 'lib.late' : e instanceof ApiErr && e.code === 'rate_limited' ? 'lib.slow'
      : e instanceof ApiErr && e.code === 'unavailable' ? 'common.offline' : 'common.error';
    say(t(key), 'pleading_face_3d');
    if (code) void api.libTable(code).then((x) => (table = x), () => {}); // the table as it really is now
  }

  /** undefined: agreed before; the version: just agreed; null: said no */
  async function agree(): Promise<string | undefined | null> {
    if (lib?.consent) return undefined;
    const yes = await sheets.ask({ title: t('lib.consentT'), text: t('lib.consentText'), ok: t('lib.consentOk'), cancel: t('common.cancel') });
    return yes ? CONSENT : null;
  }

  // the scanner: a sticker of ours opens its table (and runs what waited for it); anything else is no table
  let after: ((code: string) => void) | null = null;
  function scan(next: ((code: string) => void) | null = null) {
    after = next;
    const can = scanQr(t('lib.aim'), (text) => { void opened(text.trim()); return true; });
    if (!can) say(t('give.phone'), 'pleading_face_3d');
  }
  async function opened(text: string) {
    if (!text.toUpperCase().startsWith(PREFIX)) { haptic.error(); say(t('lib.notTable'), 'pleading_face_3d'); return; }
    busy = true;
    try {
      table = await api.libTable(text);
      code = text; haptic.ok();
      const next = after; after = null;
      next?.(text);
    } catch (e) { code = ''; fail(e); } finally { busy = false; }
  }

  // a seat tapped: mine again extends it, a free one is mine, a taken one can be "nobody here"
  const shown = (n: number, s: LibSeat) => (table ? { ...table, seats: table.seats.map((x, i) => (i === n - 1 ? s : x === 'mine' && s === 'mine' ? 'free' : x)) } : null);
  async function tap(n: number, s: LibSeat) {
    if (!table || !code) return;
    if (s === 'free' || s === 'mine') return sit(n);
    if (s === 'reported') { say(t('lib.checking'), 'thinking_face_3d'); return; }
    if (s === 'asked') { if (report?.state === 'here' && report.seat === n) return still(); say(t('lib.waiting'), 'thinking_face_3d'); return; }
    if (blocked) { say(t('lib.blocked', { date: dayMonth(blocked) }), 'pleading_face_3d'); return; }
    if (!(await sheets.ask({ title: t('lib.reportAsk', { seat: n }), text: t('lib.reportText'), ok: t('lib.reportOk'), cancel: t('common.cancel') }))) return;
    const consent = await agree();
    if (consent === null) return;
    const was = table; table = shown(n, 'asked'); haptic.tap();
    try { settle(await api.libReport(code, n, consent)); say(t('lib.reported'), 'thinking_face_3d'); } catch (e) { table = was; fail(e); }
  }
  async function sit(n: number) {
    const consent = await agree();
    if (consent === null) return;
    const again = table?.seats[n - 1] === 'mine', was = table;
    table = shown(n, 'mine'); haptic.ok();
    try { settle(await api.libSit(code, n, consent)); say(t(again ? 'lib.extended' : 'lib.seated', { until: time(nowTs() + (lib?.hold ?? 10800)) }), 'books_3d'); } catch (e) { table = was; fail(e); }
  }
  async function here() {
    const was = data.library;
    if (data.library?.mine) data.library.mine.asked = null;
    haptic.ok();
    try { settle(await api.libHere()); say(t('lib.answered'), 'raising_hands_3d_default'); } catch (e) { data.library = was; fail(e); }
  }
  async function leave() {
    const was = data.library;
    if (data.library) data.library.mine = null;
    if (table) table = { ...table, seats: table.seats.map((x) => (x === 'mine' ? 'free' : x)) };
    haptic.tap();
    try { settle(await api.libLeave()); say(t('lib.left'), 'waving_hand_3d_default'); } catch (e) { data.library = was; fail(e); }
  }
  // "still not here": with this table's code (I'm at it); from the card, a scan first when the table isn't open
  async function still(withCode = code) {
    const r = report;
    if (!r) return;
    if (!withCode || table?.id !== r.tableId) { scan((c) => void still(c)); return; }
    if (!(await sheets.ask({ title: t('lib.stillAsk'), text: t('lib.stillText'), ok: t('lib.stillOk'), cancel: t('common.cancel'), danger: true }))) return;
    haptic.tap();
    try { settle(await api.libStill(withCode, r.id)); say(t('lib.freedNow'), 'books_3d'); } catch (e) { fail(e); }
  }
  // the freed seat of my report: sit on it (a scan first when its table isn't open)
  function take() {
    const r = report;
    if (!r) return;
    if (code && table?.id === r.tableId) void sit(r.seat);
    else scan(() => void sit(r.seat));
  }
  async function withdraw() {
    if (!(await sheets.ask({ title: t('lib.withdrawAsk'), text: t('lib.withdrawText'), ok: t('lib.withdrawOk'), cancel: t('common.cancel'), danger: true }))) return;
    try {
      await api.libWithdraw();
      if (session.me?.library) session.me.library.consent = false;
      if (data.library) { data.library.consent = false; data.library.mine = null; data.library.report = null; }
      table = null; code = '';
      say(t('lib.withdrawn'), 'waving_hand_3d_default');
    } catch (e) { fail(e); }
  }
  const pct = (m: { since: number; until: number }) => Math.max(0, Math.min(100, ((m.until - now) / Math.max(1, m.until - m.since)) * 100));
</script>

<Sheet {overlay} title={t('lib.title')} icon={Armchair} full>
  <div class="page">
    {#if mine}
      <section class="seat surface" class:alarm={!!asked}>
        <p class="t-cap">{t('lib.mineCap')}</p>
        <p class="big">{t('lib.seatAt', { table: mine.table, seat: mine.seat })}</p>
        <p class="t-foot">{mine.room} · {t('lib.until', { until: time(mine.until) })}</p>
        <i class="bar"><i style="width:{pct(mine)}%"></i></i>
        <div class="acts">
          <Button kind="secondary" size="s" onclick={() => scan()}>{t('lib.extend')}</Button>
          <Button kind="secondary" size="s" onclick={leave}>{t('lib.leave')}</Button>
        </div>
      </section>
      {#if asked}
        <Notice tone="danger" title={t('lib.askedT')} text={t('lib.askedText', { left: left(asked) })} stack action={{ label: t('lib.here'), onclick: here }} />
      {/if}
    {/if}

    {#if report}
      {#if report.state === 'wait' && report.until}
        <Notice tone="neutral" title={t('lib.waitT', { table: report.table, seat: report.seat })} text={t('lib.waitText', { left: left(report.until) })} />
      {:else if report.state === 'here' && report.until}
        <Notice tone="warning" title={t('lib.hereT', { table: report.table, seat: report.seat })} text={t('lib.hereText', { left: left(report.until) })}
          stack action={{ label: t('lib.stillOk'), onclick: () => void still() }} />
      {:else if report.state === 'freed' && !(table?.id === report.tableId && table.seats[report.seat - 1] === 'mine')}
        <Notice tone="accent" title={t('lib.freedT', { table: report.table, seat: report.seat })} text={t('lib.freedText')}
          stack action={{ label: t('lib.sit'), onclick: take }} />
      {/if}
    {/if}

    {#if table}
      <Group caption={t('lib.tableCap', { table: table.label, room: table.room })} footnote={t('lib.tapHint')}>
        <div class="seats">
          {#each table.seats as s, i (i)}
            <button class="s {s}" onclick={() => void tap(i + 1, s)} aria-label={`${i + 1} · ${t(`lib.st.${s}`)}`}>
              <b>{i + 1}</b><span>{t(`lib.st.${s}`)}</span>
            </button>
          {/each}
        </div>
      </Group>
    {:else if !mine}
      <div class="hero">
        <span class="orb"><ScanQrCode size={34} strokeWidth={1.8} /></span>
        <p class="t-h3">{t('lib.heroT')}</p>
        <p class="t-foot">{t('lib.heroText', { hours: Math.round((lib?.hold ?? 10800) / 3600) })}</p>
      </div>
    {/if}

    {#if lib?.rooms.length}
      <Group caption={t('lib.rooms')}>
        {#each lib.rooms as r (r.id)}
          <Row dense title={r.name} subtitle={t('lib.freeOf', { free: r.free, total: r.total })} />
        {/each}
      </Group>
    {/if}
    {#if blocked}<p class="t-foot fine">{t('lib.blocked', { date: dayMonth(blocked) })}</p>{/if}
    <p class="t-foot fine">{t('lib.privacy')}</p>
    {#if lib?.consent}<button class="t-foot fine link" onclick={withdraw}>{t('lib.withdraw')}</button>{/if}
  </div>

  {#snippet footer()}
    <Button kind="primary" size="l" full loading={busy} onclick={() => scan()}>{#snippet icon()}<ScanQrCode size={20} />{/snippet}{t('lib.scan')}</Button>
  {/snippet}
</Sheet>

<style>
  .page { display: flex; flex-direction: column; gap: var(--s-4); }
  .seat { padding: var(--s-4); border-radius: var(--r-group); display: grid; gap: 4px; transition: box-shadow var(--t-fast) var(--ease); }
  .seat.alarm { box-shadow: inset 0 0 0 2px var(--danger); }
  .big { font: 700 var(--fs-sec)/1.15 var(--font-display); letter-spacing: -0.02em; }
  .bar { display: block; height: 6px; border-radius: var(--r-full); background: var(--fill); overflow: hidden; margin: var(--s-2) 0 var(--s-1); }
  .bar > i { display: block; height: 100%; border-radius: inherit; background: var(--accent); transition: width 1s linear; }
  .acts { display: flex; gap: var(--s-2); }
  .seats { display: grid; grid-template-columns: repeat(auto-fill, minmax(72px, 1fr)); gap: var(--s-2); padding: var(--s-3); }
  .s { display: grid; place-items: center; gap: 2px; aspect-ratio: 1; border-radius: var(--r-m); background: var(--success-soft); color: var(--success-text);
    transition: transform var(--t-fast) var(--ease), background var(--t-fast) var(--ease); }
  .s:active { transform: scale(0.94); }
  .s b { font: 700 var(--fs-t3)/1 var(--font-display); }
  .s span { font: 600 var(--fs-micro)/1.1 var(--font-text); text-align: center; padding: 0 4px; }
  .s.taken { background: var(--surface-2); color: var(--text-3); }
  .s.reported, .s.asked { background: var(--warning-soft); color: var(--warning-text); }
  .s.mine { background: var(--accent); color: var(--on-accent); }
  .hero { display: grid; justify-items: center; gap: var(--s-2); text-align: center; padding: var(--s-5) var(--s-4) var(--s-2); }
  .orb { width: 72px; height: 72px; border-radius: 50%; display: grid; place-items: center; background: var(--accent-soft); color: var(--accent); margin-bottom: var(--s-1); }
  .fine { padding: 0 var(--s-4); }
  .link { text-align: left; color: var(--danger-text); }
</style>
