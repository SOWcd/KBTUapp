<script lang="ts">
  // "Check-in", the check-in page (owner, Nov 13: the sheet was "awful"; a control room, one obvious action per state).
  // The organizer's side of /show (server checkin.py): Start, the QR, the lists, a laptop paired by its QR (sh_<code>).
  // Nothing open: a calm hero, "Start check-in" (one tap, the club's members expected; anyone may scan and is listed
  // apart) and "Connect a screen". Something open: that session is the page; several: a switcher on top. Past ones at
  // the bottom, each opening the same view. Ways in: Studio (`org`: that club), an event's guests (`event`) or its team
  // (`crew`: made and started on the first tap, then the same one), the capsule (`seed`), a scanned pairing QR (`code`),
  // Profile's row for whom Studio doesn't lead here (a door handed over, the app's admin).
  import { untrack } from 'svelte';
  import { api, ApiErr, type Id, type ScreenSession, type VolDoor } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { eventById } from '../../lib/state/data.svelte';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { may } from '../../lib/perms';
  import { t } from '../../lib/i18n/index.svelte';
  import { downloadFile, haptic, scanQr } from '../../lib/tg';
  import { nameOf } from '../../lib/short';
  import { menu } from '../../ui/menu';
  import { dayMonth, nowTs } from '../../lib/time';
  import Pane from '../../ui/Pane.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import ScanQrCode from '@lucide/svelte/icons/scan-qr-code';
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
  import UserCheck from '@lucide/svelte/icons/user-check';
  import UserX from '@lucide/svelte/icons/user-x';
  import UserRound from '@lucide/svelte/icons/user-round';
  import Check from '@lucide/svelte/icons/check';

  let { overlay, code, event, seed, org, crew }: { overlay: Overlay; code?: string; event?: Id; seed?: ScreenSession; org?: Id; crew?: Id } = $props();
  // the first frame from the store: the capsule's session (mine, running), else the hero until the list comes
  const mine = untrack(() => { const c = session.me?.checkin; return seed ?? (c && !c.helper && !event && !crew && !code ? c : null); });
  let list = $state<ScreenSession[] | null>(untrack(() => (mine ? [mine] : null)));
  let pick = $state(false);   // an unpaired screen and several open sessions: which one
  let note = $state('');      // why there's nothing to do here
  let busy = $state(0);
  let made = $state(untrack(() => seed?.session ?? 0)); // the one session this page is about (the capsule's, the team's)
  let sel = $state<Id>(0);    // the session in view: an open one picked on the switcher, or a past one opened
  let paired = $state(0);     // the session a screen was just paired to: a short "Screen connected" on the page
  // a co-hosted event's session: its co-host starts the screen; the rest (finish, unpair, the CSV) is the host's (server cohosts.py)
  const own = (s: ScreenSession) => { const ev = s.event ? eventById(s.event) : null; return !ev?.coHost || may(session.me?.memberships.find((m) => m.org.id === ev.org.id), 'events'); };

  const scope = (l: ScreenSession[]) => (event ? l.filter((x) => x.event === event) : made ? l.filter((x) => x.session === made) : l);
  const refresh = () => { if (crew && !made) return; void api.screens().then((l) => { if (!pick) list = scope(l); }).catch(() => {}); };
  let pairing = untrack(() => code ?? ''); // the screen's code being bound: the link's, or one scanned here
  async function bind(sid?: Id) {
    try {
      const s = await api.bindScreen(pairing, sid);
      pick = false; haptic.ok(); paired = sel = s.session; setTimeout(() => { if (paired === s.session) paired = 0; }, 4000);
      list = [s, ...(await api.screens().catch(() => [])).filter((x) => x.session !== s.session)];
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
  // the event's team: made on the first tap and started (one per event: the server returns the one there is)
  async function team(eid: Id) {
    const ev = eventById(eid), name = ev?.title ?? '';
    try {
      let s = await api.crewScreen(eid, `${name.length > 48 ? name.slice(0, 47).trimEnd() + '…' : name} · ${t('scr.teamMark')}`);
      if (!s.started && !s.ended) { s = await api.screenAct(s.session, 'start').catch(() => s); void loadMe(true); }
      made = s.session; list = [s];
    } catch (e) { haptic.error(); note = t(e instanceof ApiErr && e.code === 'rate_limited' ? 'scr.tooMany' : 'common.error'); list = []; }
  }
  $effect(() => untrack(() => { // once, as the page opens (team() and bind() write what refresh reads)
    if (code) void bind();
    else if (crew) void team(crew);
    else if (event) api.eventScreen(event).then((s) => (list = [s])).catch(() => { haptic.error(); note = t('common.error'); list = []; });
    else void refresh();
    const id = setInterval(() => { void refresh(); for (const k of Object.keys(doors)) void loadDoor(Number(k)); }, 4000); // the count goes up while people scan; a door of mine: answers given in its sheet
    return () => clearInterval(id);
  }));

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

  async function act(s: ScreenSession, a: 'start' | 'finish' | 'unpair' | 'out' | 'in') {
    if (busy) return;
    if (a === 'finish' && !(await sheets.ask({ title: t('scr.finishAsk'), text: t('scr.finishText'), ok: t('scr.finish'), cancel: t('scr.keep'), danger: true }))) return;
    if (a === 'unpair' && !(await sheets.ask({ title: t('scr.unpairAsk'), text: t('scr.unpairText'), ok: t('scr.unpair'), cancel: t('scr.keep') }))) return;
    busy = s.session;
    try {
      const n = await api.screenAct(s.session, a);
      list = (list ?? []).map((x) => (x.session === n.session ? n : x)); haptic.ok();
      if (a === 'start' || a === 'finish') void loadMe(true); // the capsule
      if (a === 'finish') sel = n.session; // stays in view, finished: its lists and the CSV
      if (a === 'finish' && n.vol) { // who left without checking out: answered for right away
        const door = await api.volDoor(n.session).catch(() => null);
        if (door) { doors[n.session] = door; if (door.unmarked.some((x) => x.outAt === null)) sheets.volDoor(n.session, n.title); }
      }
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); } finally { busy = 0; }
  }
  // the QR on this phone (EventQr: full screen, the same signed codes and lease as /show), started first
  async function showQr(s: ScreenSession) {
    haptic.tap();
    if (s.event) { sheets.eventQr(s.event); return; }
    if (!s.started) await act(s, 'start');
    if (list?.find((x) => x.session === s.session)?.started) sheets.helperQr(s.session, null, false);
  }

  // a new session of a club: one tap, its members expected (server checkin.club_new), started at once
  const clubs = $derived((session.me?.memberships ?? []).filter((m) => may(m, 'events') && (!org || m.org.id === org)));
  let creating = $state(false);
  async function create(o: Id): Promise<ScreenSession | null> {
    if (creating) return null;
    creating = true;
    try {
      const s = await api.clubScreen(o, t('scr.meeting', { date: dayMonth(nowTs()) }), 'club');
      const n = await api.screenAct(s.session, 'start').catch(() => s);
      haptic.ok(); void loadMe(true); // the capsule
      list = [n, ...(list ?? []).filter((x) => x.session !== n.session)]; sel = n.session; note = '';
      return n;
    } catch (e) { haptic.error(); say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'scr.tooMany' : 'common.error'), 'warning_3d'); return null; }
    finally { creating = false; }
  }
  // which club, when I run several (Studio's row says which)
  function forClub(ev: MouseEvent, then: (o: Id) => void) {
    haptic.tap();
    if (clubs.length === 1) then(clubs[0].org.id);
    else menu(ev.currentTarget as Element, clubs.map((m) => ({ label: nameOf(m.org), onselect: () => then(m.org.id) })));
  }

  // a laptop's /show: Telegram's own scanner at once (full screen); its pairing QR binds it to the session (none open:
  // the club's new one); another QR: said once, the scanner closes
  const PAIR_QR = /[?&]startapp=sh_([0-9a-f]{16})$/;
  function pairScan(sid?: Id, club?: Id) {
    haptic.tap();
    const can = scanQr(t('scr.aim'), (text) => {
      const m = text.match(PAIR_QR);
      if (!m) { haptic.error(); say(t('scr.wrongQr'), 'pleading_face_3d'); return true; }
      pairing = m[1]; note = '';
      if (sid || !club) void bind(sid);
      else void create(club).then((s) => s && bind(s.session));
      return true;
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
      api.screenBadge(s.session, text).then((r) => { haptic.ok(); say(t('scr.marked', { name: r.person }), 'sparkles_3d'); void refresh(); },
        (e) => { haptic.error(); say(t(e instanceof ApiErr ? (e.message === 'already' ? 'scr.already' : e.message === 'flagged' ? 'scr.flagged' : e.code === 'closed' ? 'scr.closed' : e.code === 'not_found' ? 'scan.notFound' : 'common.error') : 'common.error'), 'warning_3d'); });
      return true;
    });
    if (!can) say(t('give.phone'), 'pleading_face_3d');
  }

  // the three lists (server checkin.people): the members who came, who came not on the list, the members who haven't
  type Who = 'came' | 'other' | 'absent';
  let open = $state<Who | null>(null);
  let people = $state<Record<Id, Record<Who, string[]>>>({});
  function unfold(w: Who) { haptic.tap(); open = open === w ? null : w; }
  // read as a list opens, and again as new scans count while it's open
  $effect(() => { const id = curId; void curDone; if (id && open) api.screenPeople(id).then((p) => (people[id] = p)).catch(() => {}); });

  // past: finished, or made and never started for a day (nobody will: not "waiting" any more)
  const over = (x: ScreenSession) => !!x.ended || (!x.started && !!x.created && x.created < nowTs() - 86400);
  const live = $derived((list ?? []).filter((x) => !over(x)));
  const past = $derived((list ?? []).filter(over));
  let showPast = $state(false);
  const cur = $derived((list ?? []).find((x) => x.session === sel) ?? (made || event ? list?.[0] : live[0]) ?? null);
  const curId = $derived(cur?.session ?? 0), curDone = $derived(cur?.done ?? 0);
  $effect(() => { void curId; open = null; });
  const pastOpen = $derived(!!cur && over(cur) && !made && !event);

  async function csv(s: ScreenSession) {
    haptic.tap();
    try { const l = await api.screenCsv(s.session); downloadFile(location.origin + l.url, l.name); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  const when = (s: ScreenSession) => dayMonth(s.started ?? s.created ?? nowTs());
</script>

<Pane {overlay} title={t('scr.page')} icon={ScanQrCode}>
  <div class="pg">
    {#if pick}
      <p class="lead">{t('scr.pick')}</p>
      <Group>{#each list ?? [] as s (s.session)}<Row title={s.title} accessory="chevron" onclick={() => bind(s.session)} />{/each}</Group>
    {:else if note}
      <div class="hero"><span class="mark"><MonitorUp size={34} strokeWidth={1.6} /></span><p class="lead">{note}</p></div>
    {:else if cur}
      {@const s = cur}
      {#if live.length > 1 && !made && !event && !pastOpen}
        <Segmented items={live.map((x) => ({ value: x.session, label: x.title }))} value={s.session} onchange={(v) => { haptic.tap(); sel = v; }} />
      {/if}
      <header class="head">
        <h2 class="t-h2 ttl">{s.title}</h2>
        <Tag tone={s.started && !s.ended ? 'accent' : 'neutral'}>{s.ended ? `${t('scr.closed')} · ${when(s)}` : s.started ? t('scr.live') : t('scr.waiting')}</Tag>
      </header>
      <!-- the members who came of the club's members; without a list (an event's guests), everyone counted -->
      <div class="big">
        {#if s.expected}<span class="n">{s.came ?? 0}</span><span class="of">{t('scr.ofM', { m: s.expected })}</span>
        {:else}<span class="n">{s.done}</span><span class="of">{t('scr.done')}</span>{/if}
      </div>
      {#if s.pending || s.phase === 'out' || s.departed}
        <p class="sub">{[s.pending ? t('scr.joining', { n: s.pending }) : '', s.phase === 'out' ? t('scr.outNow', { n: s.departed }) : s.departed ? t('scr.leftN', { n: s.departed }) : ''].filter(Boolean).join(' · ')}</p>
      {/if}
      {#if paired === s.session}<p class="ok"><Check size={16} strokeWidth={2.6} />{t('scr.paired')}</p>{/if}

      {#if !s.ended}
        <div class="cta">
          <!-- an event's guests (EventManage → More → Big screen): its QR and helpers live on the door screen; here the laptop -->
          {#if event && s.started}<Button kind="primary" size="l" full onclick={() => pairScan(s.session)}>{#snippet icon()}<MonitorUp size={19} />{/snippet}{t('scr.connect')}</Button>
          {:else if s.started}<Button kind="primary" size="l" full onclick={() => showQr(s)}>{#snippet icon()}<QrCode size={19} />{/snippet}{t('aw.show')}</Button>
          {:else}<Button kind="primary" size="l" full loading={busy === s.session} onclick={() => act(s, 'start')}>{#snippet icon()}<Play size={18} />{/snippet}{t('scr.start')}</Button>{/if}
          <!-- what the door person needs next (owner, Nov 14): hand the check-in over -->
          {#if s.started && board(s) && !event}<Button kind="secondary" size="l" full onclick={() => { haptic.tap(); sheets.handQr(s.session); }}>{#snippet icon()}<UserPlus size={18} />{/snippet}{t('scr.hand')}</Button>{/if}
        </div>
      {/if}

      {#if s.expected && own(s) && !handed(s)}
        {@const p = people[s.session]}
        <Group>
          <Row icon={UserCheck} title={t('scr.cameL')} value={String(s.came ?? 0)} accessory="disclosure" open={open === 'came'} onclick={() => unfold('came')} />
          {#if open === 'came'}{#each p?.came ?? [] as name, i (i)}<Row dense title={name} />{/each}{/if}
          {#if s.done > (s.came ?? 0)}<Row icon={UserRound} title={t('scr.other')} value={String(s.done - (s.came ?? 0))} accessory="disclosure" open={open === 'other'} onclick={() => unfold('other')} />
            {#if open === 'other'}{#each p?.other ?? [] as name, i (i)}<Row dense title={name} />{/each}{/if}{/if}
          <Row icon={UserX} title={t('scr.absentL')} value={String(s.expected - (s.came ?? 0))} accessory="disclosure" open={open === 'absent'} onclick={() => unfold('absent')} />
          {#if open === 'absent'}{#each p?.absent ?? [] as name, i (i)}<Row dense title={name} />{/each}{/if}
        </Group>
      {/if}

      <Group>
        {#if s.started && !s.ended && s.phase !== 'out' && !event}<Row icon={ScanLine} title={t('scr.byHand')} accessory="chevron" onclick={() => byHand(s)} />{/if}
        {#if s.started && !s.ended && own(s)}<Row icon={s.phase === 'out' ? LogIn : LogOut} title={t(s.phase === 'out' ? 'scr.toIn' : 'scr.toOut')} onclick={() => act(s, s.phase === 'out' ? 'in' : 'out')} />{/if}
        {#if doors[s.session] && (waiting(s) || (doors[s.session].lead && (!s.ended || doors[s.session].hand)))}<Row icon={DoorOpen} title={waiting(s) ? t('ledg.unresolvedN', { n: waiting(s) }) : t('ledg.hand')} accessory="chevron" onclick={() => { haptic.tap(); sheets.volDoor(s.session, s.title); }} />{/if}
        {#if handed(s) && doors[s.session].by}<Row icon={DoorOpen} title={t('ledg.handedBy', { name: doors[s.session].by!.name })} />{/if}
        {#if s.started && own(s) && !handed(s)}<Row icon={Download} title={t('scr.csv')} accessory="chevron" onclick={() => csv(s)} />{/if}
        {#if s.paired && own(s) && !handed(s) && !s.ended}<Row icon={Unplug} title={t('scr.unpair')} onclick={() => act(s, 'unpair')} />{/if}
      </Group>
      {#if s.started && !s.ended && own(s)}
        <Group><Row tone="destructive" icon={Square} title={t('scr.finish')} onclick={() => act(s, 'finish')} /></Group>
      {/if}
      {#if pastOpen || (!live.length && clubs.length && !made && !event)}
        <div class="cta"><Button kind="secondary" size="l" full loading={creating} onclick={(ev) => forClub(ev, (o) => void create(o))}>{#snippet icon()}<Play size={18} />{/snippet}{t('scr.start')}</Button></div>
      {/if}
    {:else if list || !(made || event || crew || code)}
      <!-- nothing open: what this is, one obvious action, and the laptop's way in -->
      <div class="hero">
        <span class="mark"><ScanQrCode size={36} strokeWidth={1.6} /></span>
        <p class="lead">{t('scr.heroText')}</p>
        {#if clubs.length}
          <Button kind="primary" size="l" full loading={creating} onclick={(ev) => forClub(ev, (o) => void create(o))}>{#snippet icon()}<Play size={18} />{/snippet}{t('scr.start')}</Button>
          <Button kind="plain" size="m" full onclick={(ev) => forClub(ev, (o) => pairScan(undefined, o))}>{#snippet icon()}<MonitorUp size={17} />{/snippet}{t('scr.connect')}</Button>
        {:else if list}<p class="sub">{t('scr.none')}</p>{/if}
      </div>
    {/if}

    {#if past.length && !made && !event && !pick && !note}
      {#if showPast}
        <Group caption={t('scr.past')}>
          {#each past as x (x.session)}<Row title={x.title} subtitle={when(x)} value={x.expected ? `${x.came ?? 0}/${x.expected}` : String(x.done)} accessory="chevron" onclick={() => { haptic.tap(); sel = x.session; showPast = false; }} />{/each}
        </Group>
      {:else}
        <button class="past" onclick={() => { haptic.tap(); showPast = true; }}>{t('scr.past')} · {past.length}</button>
      {/if}
    {/if}
  </div>
</Pane>

<style>
  .pg { display: flex; flex-direction: column; gap: var(--gap-group); padding-bottom: calc(var(--s-6) + env(safe-area-inset-bottom)); }
  .hero { display: flex; flex-direction: column; align-items: center; gap: var(--s-3); text-align: center; padding: 12vh var(--s-2) var(--s-4); }
  .mark { display: grid; place-items: center; width: 76px; height: 76px; border-radius: var(--r-l); background: var(--accent-soft, var(--fill-2)); color: var(--accent); margin-bottom: var(--s-2); }
  .lead { margin: 0 0 var(--s-3); font-size: var(--fs-card); line-height: 1.35; color: var(--text-2); max-width: 30ch; }
  .sub { margin: 0; color: var(--text-3); font-size: var(--fs-sub); }
  .head { display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-2); }
  .ttl { margin: 0; overflow-wrap: anywhere; }
  .big { display: flex; align-items: baseline; gap: var(--s-2); margin: var(--s-1) 0 calc(-1 * var(--s-2)); }
  .n { font-size: calc(var(--fs-title) * 1.9); line-height: 1; font-weight: 700; letter-spacing: -0.03em; font-variant-numeric: tabular-nums; }
  .of { font-size: var(--fs-t3); color: var(--text-3); }
  .ok { display: flex; align-items: center; gap: var(--s-1); margin: 0; color: var(--success-text, var(--success)); font-weight: 600; font-size: var(--fs-body); animation: rise .3s ease-out; }
  .cta { display: flex; flex-direction: column; gap: var(--s-2); }
  .past { align-self: center; border: 0; background: none; padding: var(--s-2) var(--s-3); color: var(--text-3); font: inherit; font-size: var(--fs-body); }
  @keyframes rise { from { opacity: 0; transform: translateY(4px); } }
</style>
