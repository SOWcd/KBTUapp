<script lang="ts">
  // The organizer's side of /show (server checkin.py): a scan of the laptop's pairing QR (sh_<code>) binds it to my
  // session, and here are the controls the screen itself no longer has: Start, Finish, the list, "disconnect". Anyone
  // who doesn't run a session gets a polite no and the screen stays as it was. From an event (`event`): its own session,
  // made on first use, with the way to the laptop. `seed` (the capsule): that running session alone, there in the first
  // frame. `org` (Studio): a new session of that club, no event: who is expected, then Start. Without any (Profile's
  // "Big screen"): my sessions, open ones first, the finished folded; "Start check-in" and "Connect a screen" on top.
  import { untrack } from 'svelte';
  import { api, ApiErr, type Id, type ScreenSession, type VolDoor } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { data, eventById } from '../../lib/state/data.svelte';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { may } from '../../lib/perms';
  import { t } from '../../lib/i18n/index.svelte';
  import { downloadFile, haptic, scanQr } from '../../lib/tg';
  import { nameOf } from '../../lib/short';
  import { menu } from '../../ui/menu';
  import { dayMonth, nowTs } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import MonitorPlay from '@lucide/svelte/icons/monitor-play';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import MonitorUp from '@lucide/svelte/icons/monitor-up';
  import Play from '@lucide/svelte/icons/play';
  import Square from '@lucide/svelte/icons/square';
  import Download from '@lucide/svelte/icons/download';
  import Unplug from '@lucide/svelte/icons/unplug';
  import LogOut from '@lucide/svelte/icons/log-out';
  import LogIn from '@lucide/svelte/icons/log-in';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import DoorOpen from '@lucide/svelte/icons/door-open';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import UserX from '@lucide/svelte/icons/user-x';
  import History from '@lucide/svelte/icons/history';

  let { overlay, code, event, seed, org }: { overlay: Overlay; code?: string; event?: Id; seed?: ScreenSession; org?: Id } = $props();
  let list = $state<ScreenSession[] | null>(untrack(() => (seed ? [seed] : null)));
  let pick = $state(false);   // an unpaired screen and several open sessions: which one
  let note = $state('');      // why there's nothing to do here
  let busy = $state(0);
  let bound = 0;              // the session the laptop just showed: first in the list, the one to start
  let made = untrack(() => seed?.session ?? 0); // the one session this sheet is about (the capsule's, or the one `org` just made)
  // a co-hosted event's session: its co-host starts the screen; the rest (finish, unpair, the CSV) is the host's (server cohosts.py)
  const own = (s: ScreenSession) => { const ev = s.event ? eventById(s.event) : null; return !ev?.coHost || may(session.me?.memberships.find((m) => m.org.id === ev.org.id), 'events'); };

  // from an event, only its session stays in view
  const refresh = () => { if (org && !made) return; void api.screens().then((l) => { if (!pick) list = event ? l.filter((x) => x.event === event) : made ? l.filter((x) => x.session === made) : first(l); }).catch(() => {}); };
  const first = (l: ScreenSession[]) => [...l.filter((x) => x.session === bound), ...l.filter((x) => x.session !== bound)];
  let pairing = untrack(() => code ?? ''); // the screen's code being bound: the link's, or one scanned here
  async function bind(sid?: Id) {
    try {
      const s = await api.bindScreen(pairing, sid);
      pick = false; bound = s.session; haptic.ok(); say(t('scr.paired'), 'sparkles_3d');
      list = first([s, ...(await api.screens().catch(() => [])).filter((x) => x.session !== s.session)]);
    } catch (e) {
      const m = e instanceof ApiErr ? e.message : '';
      if (m === 'pick') { pick = true; list = (await api.screens().catch(() => [])).filter((x) => !x.ended); return; }
      haptic.error();
      // who runs events but has no session yet hears that, not "this isn't for you"
      const none = m === 'screen' && session.me?.bigScreen === 'pair' && !(await api.screens().catch(() => [])).length;
      note = m === 'pair' ? t('scr.stale') : none ? t('scr.noneOpen') : m === 'screen' ? t('scr.notYours') : t('common.error');
      list = [];
    }
  }
  $effect(() => {
    if (code) void bind();
    else if (event) api.eventScreen(event).then((s) => (list = [s])).catch(() => { haptic.error(); note = t('common.error'); list = []; });
    else if (!org) void refresh();
    const id = setInterval(() => { void refresh(); for (const k of Object.keys(doors)) void loadDoor(Number(k)); }, 4000); // the count goes up while people scan; a door of mine: answers given in its sheet
    return () => clearInterval(id);
  });

  // finished: the capsule lets go at once, without waiting for the next refresh
  $effect(() => { const c = session.me?.checkin; if (c && list?.some((x) => x.session === c.session && x.ended)) session.me!.checkin = null; });

  // the volunteers ledger's sessions (s.vol): their door, when it is mine (its President, a Vice, the hand-over link's
  // holder; nobody else gets one): who left without checking out, the link. Read as such a session appears or finishes
  let doors = $state<Record<Id, VolDoor>>({});
  const volKey = $derived((list ?? []).filter((s) => s.vol).map((s) => `${s.session}:${s.ended ?? 0}`).join());
  const loadDoor = (id: Id) => api.volDoor(id).then((x) => (doors[id] = x)).catch(() => { delete doors[id]; });
  $effect(() => { if (volKey) for (const k of volKey.split(',')) void loadDoor(Number(k.split(':')[0])); });
  const waiting = (s: ScreenSession) => doors[s.session]?.unmarked.filter((x) => x.outAt === null).length ?? 0;
  const handed = (s: ScreenSession) => !!doors[s.session] && !doors[s.session].lead; // the link's holder: the door's work, not the list or the screens

  // who may let a helper in: the club's President or Vice (the privacy policy's door helper), or the app's admin (server checkin._hands_over)
  const board = (s: ScreenSession) => { if (session.me?.role === 'admin' && !code) return true; const ev = s.event ? eventById(s.event) : null; return !!ev && !!session.me?.memberships.some((m) => m.org.id === ev.org.id && (m.role === 'president' || m.role === 'vice')); };

  // the badge to everyone counted lives in Admin → Badges (staff controls only there)
  async function act(s: ScreenSession, a: 'start' | 'finish' | 'unpair' | 'out' | 'in') {
    if (busy) return;
    if (a === 'finish' && !(await sheets.ask({ title: t('scr.finishAsk'), text: t('scr.finishText'), ok: t('scr.finish'), cancel: t('scr.keep') }))) return;
    if (a === 'unpair' && !(await sheets.ask({ title: t('scr.unpairAsk'), text: t('scr.unpairText'), ok: t('scr.unpair'), cancel: t('scr.keep') }))) return;
    busy = s.session;
    try {
      const n = await api.screenAct(s.session, a);
      list = (list ?? []).map((x) => (x.session === n.session ? n : x)); haptic.ok();
      if (a === 'start') void loadMe(true); // the capsule
      if (a === 'finish' && n.vol) { // who left without checking out: answered for right away
        const door = await api.volDoor(n.session).catch(() => null);
        if (door) { doors[n.session] = door; if (door.unmarked.some((x) => x.outAt === null)) sheets.volDoor(n.session, n.title); }
      }
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); } finally { busy = 0; }
  }
  // a session without an event: this phone shows its QR (EventQr's `sess`, the same signed codes and lease as /show), started first
  async function showQr(s: ScreenSession) {
    if (!s.started) await act(s, 'start');
    if (list?.find((x) => x.session === s.session)?.started) sheets.helperQr(s.session, null, false);
  }
  // a new session of a club: who is expected (the whole club, a department, anyone), then made and started in one tap
  const clubs = $derived((session.me?.memberships ?? []).filter((m) => may(m, 'events')));
  let starting = $state<Id>(untrack(() => org ?? 0));
  let who = $state<'club' | 'all' | Id>('club');
  let depts = $state<{ id: Id; name: string; count: number }[]>([]);
  $effect(() => { const o = starting; depts = []; who = 'club'; if (o) api.teamSetup(o).then((x) => { if (starting === o) depts = x.tags.filter((g) => g.department && g.count); }).catch(() => {}); });
  const members = $derived(data.orgs.find((x) => x.id === starting)?.members);
  function startFor(ev: MouseEvent) {
    haptic.tap();
    if (clubs.length === 1) starting = clubs[0].org.id;
    else menu(ev.currentTarget as Element, clubs.map((m) => ({ label: nameOf(m.org), onselect: () => (starting = m.org.id) })));
  }
  let creating = $state(false);
  async function create() {
    if (creating || !starting) return;
    creating = true;
    try {
      const s = await api.clubScreen(starting, t('scr.meeting', { date: dayMonth(nowTs()) }), who);
      const n = await api.screenAct(s.session, 'start').catch(() => s);
      haptic.ok(); void loadMe(true); // the capsule
      if (org) made = n.session;
      list = [n, ...(list ?? []).filter((x) => x.session !== n.session)]; starting = 0; note = '';
    } catch (e) { haptic.error(); say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'scr.tooMany' : 'common.error'), 'warning_3d'); }
    finally { creating = false; }
  }

  // a laptop's /show: its pairing QR scanned here (Telegram's own scanner), bound to this session (or asked which)
  const PAIR_QR = /[?&]startapp=sh_([0-9a-f]{16})$/;
  function pairScan(sid?: Id) {
    haptic.tap();
    let wrong = '';
    const can = scanQr(t('scr.aim'), (text) => {
      const m = text.match(PAIR_QR);
      if (m) { haptic.ok(); pairing = m[1]; note = ''; void bind(sid); return true; }
      if (text !== wrong) { wrong = text; haptic.error(); } // another QR: said once, the scanner stays up
      return false;
    });
    if (!can) say(t('give.phone'), 'pleading_face_3d');
  }

  // marked by hand: a student's badge QR (their profile's), when their own scanner fails; the server checks it all
  const BADGE = /\bu_\d+_[A-Z2-7]{10}\b/;
  function byHand(s: ScreenSession) {
    haptic.tap();
    let wrong = '';
    const can = scanQr(t('scr.byHandAim'), (text) => {
      if (!BADGE.test(text)) { if (text !== wrong) { wrong = text; haptic.error(); } return false; }
      api.screenBadge(s.session, text).then((r) => { haptic.ok(); say(t('scr.marked', { name: r.person }), 'sparkles_3d'); void refresh(); absentOf(s, true); },
        (e) => { haptic.error(); say(t(e instanceof ApiErr ? (e.message === 'already' ? 'scr.already' : e.code === 'closed' ? 'scr.closed' : e.code === 'not_found' ? 'scan.notFound' : 'common.error') : 'common.error'), 'warning_3d'); });
      return true;
    });
    if (!can) say(t('give.phone'), 'pleading_face_3d');
  }

  // who of the expected hasn't come: read when opened, again after a mark by hand
  let absent = $state<Record<Id, string[]>>({});
  function absentOf(s: ScreenSession, again = false) {
    if (absent[s.session] && !again) { delete absent[s.session]; return; }
    if (!again) haptic.tap();
    if (again && !absent[s.session]) return;
    api.screenAbsent(s.session).then((l) => (absent[s.session] = l)).catch(() => {});
  }

  const all = $derived(!code && !event && !seed && !org); // Profile's list: the finished folded
  let past = $state(false);
  const shown = $derived(all && !pick && !past ? (list ?? []).filter((x) => !x.ended) : (list ?? []));
  const ended = $derived(all && !pick ? (list ?? []).filter((x) => x.ended).length : 0);

  async function csv(s: ScreenSession) {
    try { const l = await api.screenCsv(s.session); downloadFile(location.origin + l.url, l.name); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
</script>

<Sheet {overlay} icon={MonitorPlay} title={t('scr.title')}>
  <h2 class="t-h2 hd">{pick ? t('scr.pick') : t('scr.title')}</h2>
  {#if starting}
    <div class="ss">
      <Group caption={t('scr.who')}>
        <Row title={t('scr.whoClub')} value={members ? String(members) : undefined} accessory="check" checked={who === 'club'} onclick={() => (who = 'club')} />
        {#each depts as d (d.id)}<Row title={d.name} value={String(d.count)} accessory="check" checked={who === d.id} onclick={() => (who = d.id)} />{/each}
        <Row title={t('scr.whoAll')} accessory="check" checked={who === 'all'} onclick={() => (who = 'all')} />
      </Group>
      <Button kind="primary" size="l" full loading={creating} onclick={create}>{#snippet icon()}<Play size={18} />{/snippet}{t('scr.start')}</Button>
    </div>
  {:else if all && !pick && clubs.length}
    <div class="ss"><Group>
      <Row icon={QrCode} title={t('scr.start')} subtitle={t('scr.newSub')} accessory="chevron" onclick={startFor} />
      <Row icon={MonitorUp} title={t('scr.connect')} accessory="chevron" onclick={() => pairScan()} />
    </Group></div>
  {/if}
  {#if note}
    <EmptyState icon={MonitorUp} title={note} />
  {:else if list && !list.length && !starting && !org}
    <EmptyState icon={MonitorUp} title={pick ? t('scr.noneOpen') : t('scr.none')} />
  {/if}
  {#each shown as s (s.session)}
    <div class="ss">
      <Group>
        <Row title={s.title}>
          {#snippet detail()}<Tag tone={s.started && !s.ended ? 'accent' : 'neutral'}>{s.ended ? t('scr.closed') : s.started ? t('scr.live') : t('scr.waiting')}</Tag>{/snippet}
        </Row>
        <!-- of the expected (a club's own list), and who else came; without a list, everyone counted -->
        {#if s.expected}<Row title={t('scr.cameOf', { n: s.came ?? 0, m: s.expected })} subtitle={[s.done > (s.came ?? 0) ? t('scr.also', { n: s.done - (s.came ?? 0) }) : '', s.pending ? t('scr.joining', { n: s.pending }) : ''].filter(Boolean).join(' · ') || undefined} />
        {:else}<Row title="{s.done} {t('scr.done')}" subtitle={s.pending ? t('scr.joining', { n: s.pending }) : undefined} />{/if}
        {#if s.expected > (s.came ?? 0) && own(s) && !handed(s)}<Row icon={UserX} title={t('scr.absent')} value={String(s.expected - (s.came ?? 0))} accessory="disclosure" open={!!absent[s.session]} onclick={() => absentOf(s)} />
          {#each absent[s.session] ?? [] as name, i (i)}<Row dense title={name} />{/each}{/if}
        {#if s.phase === 'out' || s.departed}<Row icon={LogOut} title={s.phase === 'out' ? t('scr.outNow', { n: s.departed }) : t('scr.leftN', { n: s.departed })} />{/if}
        <Row icon={MonitorUp} title={s.screens ? t('scr.screens', { n: s.screens }) : t('scr.howTo', { url: location.host + '/show' })} onclick={s.screens || s.ended || pick ? undefined : () => pairScan(s.session)} />
        {#if handed(s) && doors[s.session].by}<Row icon={DoorOpen} title={t('ledg.handedBy', { name: doors[s.session].by!.name })} />{/if}
      </Group>
      <div class="acts">
        {#if pick}
          <Button kind="primary" size="m" full onclick={() => bind(s.session)}>{t('scr.here')}</Button>
        {:else}
          {#if !s.ended}<Button kind="filled" size="m" full onclick={() => { haptic.tap(); if (s.event) sheets.eventQr(s.event); else void showQr(s); }}>{#snippet icon()}<QrCode size={17} />{/snippet}{t('aw.show')}</Button>{/if}
          {#if !s.started}<Button kind="primary" size="m" full loading={busy === s.session} onclick={() => act(s, 'start')}>{#snippet icon()}<Play size={17} />{/snippet}{t('scr.start')}</Button>{/if}
          {#if s.started && !s.ended}<Button kind="secondary" size="m" full onclick={() => byHand(s)}>{#snippet icon()}<ScanLine size={17} />{/snippet}{t('scr.byHand')}</Button>{/if}
          {#if s.started && !s.ended && board(s)}<Button kind="secondary" size="m" full onclick={() => { haptic.tap(); sheets.handQr(s.session); }}>{#snippet icon()}<UserPlus size={17} />{/snippet}{t('scr.hand')}</Button>{/if}
          {#if s.started && !s.ended && own(s)}<Button kind="secondary" size="m" full onclick={() => act(s, s.phase === 'out' ? 'in' : 'out')}>{#snippet icon()}{#if s.phase === 'out'}<LogIn size={17} />{:else}<LogOut size={17} />{/if}{/snippet}{t(s.phase === 'out' ? 'scr.toIn' : 'scr.toOut')}</Button>{/if}
          {#if s.started && !s.ended && own(s)}<Button kind="secondary" size="m" full loading={busy === s.session} onclick={() => act(s, 'finish')}>{#snippet icon()}<Square size={16} />{/snippet}{t('scr.finish')}</Button>{/if}
          {#if doors[s.session] && (waiting(s) || (doors[s.session].lead && (!s.ended || doors[s.session].hand)))}<Button kind="secondary" size="m" full onclick={() => { haptic.tap(); sheets.volDoor(s.session, s.title); }}>{#snippet icon()}<DoorOpen size={17} />{/snippet}{waiting(s) ? t('ledg.unresolvedN', { n: waiting(s) }) : t('ledg.hand')}</Button>{/if}
          {#if s.started && own(s) && !handed(s)}<Button kind="secondary" size="m" full onclick={() => csv(s)}>{#snippet icon()}<Download size={17} />{/snippet}{t('scr.csv')}</Button>{/if}
          {#if s.paired && own(s) && !handed(s)}<Button kind="plain" size="m" full onclick={() => act(s, 'unpair')}>{#snippet icon()}<Unplug size={17} />{/snippet}{t('scr.unpair')}</Button>{/if}
        {/if}
      </div>
    </div>
  {/each}
  {#if ended && !past}
    <Group><Row icon={History} title={t('scr.past')} value={String(ended)} accessory="disclosure" onclick={() => { haptic.tap(); past = true; }} /></Group>
  {/if}
</Sheet>

<style>
  .hd { margin: var(--s-1) 0 var(--s-3); }
  .ss { display: flex; flex-direction: column; gap: var(--s-3); margin-bottom: var(--gap-group); }
  .acts { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  /* side by side while whole labels fit, else a line each (a label is never cut) */
  .acts :global(.btn.full) { flex: 1 1 auto; width: auto; min-width: 0; }
</style>
