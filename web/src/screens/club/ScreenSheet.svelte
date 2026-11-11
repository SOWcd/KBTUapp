<script lang="ts">
  // The organizer's side of /show (server checkin.py): a scan of the laptop's pairing QR (sh_<code>) binds it to my
  // session, and here are the controls the screen itself no longer has: Start, Finish, the list, "disconnect". Anyone
  // who doesn't run a session gets a polite no and the screen stays as it was. From an event (`event`): its own session,
  // made on first use, with the way to the laptop. `seed` (the capsule): that running session alone, there in the first
  // frame. Without any: my sessions.
  import { untrack } from 'svelte';
  import { api, ApiErr, type Id, type ScreenSession, type VolDoor } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { eventById } from '../../lib/state/data.svelte';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { may } from '../../lib/perms';
  import { t } from '../../lib/i18n/index.svelte';
  import { downloadFile, haptic } from '../../lib/tg';
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

  let { overlay, code, event, seed }: { overlay: Overlay; code?: string; event?: Id; seed?: ScreenSession } = $props();
  let list = $state<ScreenSession[] | null>(untrack(() => (seed ? [seed] : null)));
  let pick = $state(false);   // an unpaired screen and several open sessions: which one
  let note = $state('');      // why there's nothing to do here
  let busy = $state(0);
  // a co-hosted event's session: its co-host starts the screen; the rest (finish, unpair, the CSV) is the host's (server cohosts.py)
  const own = (s: ScreenSession) => { const ev = s.event ? eventById(s.event) : null; return !ev?.coHost || may(session.me?.memberships.find((m) => m.org.id === ev.org.id), 'events'); };

  // from an event, only its session stays in view
  const refresh = () => api.screens().then((l) => { if (!pick) list = event ? l.filter((x) => x.event === event) : seed ? l.filter((x) => x.session === seed.session) : l; }).catch(() => {});
  async function bind(sid?: Id) {
    try {
      const s = await api.bindScreen(code!, sid);
      pick = false; haptic.ok(); say(t('scr.paired'), 'sparkles_3d');
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
  $effect(() => {
    if (code) void bind();
    else if (event) api.eventScreen(event).then((s) => (list = [s])).catch(() => { haptic.error(); note = t('common.error'); list = []; });
    else void refresh();
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
  async function csv(s: ScreenSession) {
    try { const l = await api.screenCsv(s.session); downloadFile(location.origin + l.url, l.name); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
</script>

<Sheet {overlay} icon={MonitorPlay} title={t('scr.title')}>
  <h2 class="t-h2 hd">{pick ? t('scr.pick') : t('scr.title')}</h2>
  {#if note}
    <EmptyState icon={MonitorUp} title={note} />
  {:else if list && !list.length}
    <EmptyState icon={MonitorUp} title={pick ? t('scr.noneOpen') : t('scr.none')} />
  {/if}
  {#each list ?? [] as s (s.session)}
    <div class="ss">
      <Group>
        <Row title={s.title}>
          {#snippet detail()}<Tag tone={s.started && !s.ended ? 'accent' : 'neutral'}>{s.ended ? t('scr.closed') : s.started ? t('scr.live') : t('scr.waiting')}</Tag>{/snippet}
        </Row>
        <Row title="{s.done}{s.expected ? ' / ' + s.expected : ''} {t('scr.done')}" subtitle={s.pending ? t('scr.joining', { n: s.pending }) : undefined} />
        {#if s.phase === 'out' || s.departed}<Row icon={LogOut} title={s.phase === 'out' ? t('scr.outNow', { n: s.departed }) : t('scr.leftN', { n: s.departed })} />{/if}
        <Row icon={MonitorUp} title={s.screens ? t('scr.screens', { n: s.screens }) : t('scr.howTo', { url: location.host + '/show' })} />
      </Group>
      <div class="acts">
        {#if pick}
          <Button kind="primary" size="m" full onclick={() => bind(s.session)}>{t('scr.here')}</Button>
        {:else}
          {#if s.event && !s.ended}<Button kind="filled" size="m" full onclick={() => { haptic.tap(); sheets.eventQr(s.event!); }}>{#snippet icon()}<QrCode size={17} />{/snippet}{t('aw.show')}</Button>{/if}
          {#if !s.started}<Button kind="primary" size="m" full loading={busy === s.session} onclick={() => act(s, 'start')}>{#snippet icon()}<Play size={17} />{/snippet}{t('scr.start')}</Button>{/if}
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
</Sheet>

<style>
  .hd { margin: var(--s-1) 0 var(--s-3); }
  .ss { display: flex; flex-direction: column; gap: var(--s-3); margin-bottom: var(--gap-group); }
  .acts { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  .acts :global(.btn.full) { flex: 1 1 140px; width: auto; min-width: 0; }
</style>
