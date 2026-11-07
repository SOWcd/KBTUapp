<script lang="ts">
  // Studio → an event: the organizer's screen (owner, Oct 11: "inside Studio a tap on an event must open another
  // screen than from the Afisha"; he couldn't find how much had come in). Money first for a paid event: what should
  // have come (paying tickets × price), what the receipts say (OCR), the receipts to check (flagged ones open the
  // attendee list, flagged first); then the people; then the tools. "As students see it" opens the usual sheet.
  // ponytail: no "message the participants" yet (no such API; the questions thread and the bot's changes cover it).
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import UserCheck from '@lucide/svelte/icons/user-check';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import Pencil from '@lucide/svelte/icons/pencil';
  import Eye from '@lucide/svelte/icons/eye';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import MonitorUp from '@lucide/svelte/icons/monitor-up';
  import { onMount } from 'svelte';
  import DoorOpen from '@lucide/svelte/icons/door-open';
  import DoorClosed from '@lucide/svelte/icons/door-closed';
  import { api, ApiErr, staffEvents, type Attendee, type EventCard, type Id, type PersonRef, type TeamAsk } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, eventById, phrase, studioChanged } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { session } from '../../lib/state/session.svelte';
  import { t, money, placeOf } from '../../lib/i18n/index.svelte';
  import { relDay, time, nowTs } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import Notice from '../../ui/Notice.svelte';
  import ShieldCheck from '@lucide/svelte/icons/shield-check';
  import { inner, may } from '../../lib/perms';
  import Sheet from '../../ui/Sheet.svelte';
  import SlidersHorizontal from '@lucide/svelte/icons/sliders-horizontal';
  import Poster from '../../ui/Poster.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import X from '@lucide/svelte/icons/x';

  // staff: opened from Admin, the app's admin runs it as its organizers do (api staffEvents), never its door or money
  let { overlay, id, staff = false }: { overlay: Overlay; id: Id; staff?: boolean } = $props();

  const e = $derived(eventById(id));
  const mem = $derived(session.me?.memberships.find((m) => m.org.id === e?.org.id));
  const head = $derived(staff || may(mem, 'events'));
  // Admin put it in staffEvents before opening; it leaves with this screen, so the event's own sheet is a student's again
  $effect(() => () => { if (staff) staffEvents.delete(id); });
  const started = $derived(!!e && e.startsAt <= nowTs());
  const live = $derived(e?.status === 'published');

  // everything below comes from the attendee list (Head+), asked again whenever Studio changes (a receipt checked)
  let list = $state<Attendee[] | null>(null);
  $effect(() => { void data.rev; if (head) api.attendees(id).then((l) => (list = l)).catch(() => (list = [])); });
  const of = (s: Attendee['status']) => (list ?? []).filter((a) => a.status === s);
  const going = $derived(of('going'));
  const came = $derived(going.filter((a) => a.checkedInAt).length);
  const price = $derived(e?.price ?? 0);
  const paying = $derived(going.filter((a) => !a.free).length);
  const byReceipts = $derived(going.reduce((n, a) => n + (a.receipt?.amount ?? 0), 0));
  const unread = $derived(going.filter((a) => a.receipt && a.receipt.amount == null).length);
  // the event's Telegram group: open it, or "Create chat" adds our bot to a group the organizer picks
  let chat = $state<string | null>(null);
  // door helpers (server crew.py): the server sends the list to a running club's President or Vice only
  let crewN = $state<number | null>(null);
  $effect(() => { if (head) api.event(id).then((x) => { chat = x.chat ?? null; crewN = x.crew ? x.crew.length : null; }).catch(() => {}); });
  async function openChat() {
    haptic.tap();
    if (chat) { openLink(chat); return; }
    if (!(await sheets.ask({ title: t('chat.ask'), text: t('chat.askText'), ok: t('chat.go'), cancel: t('common.cancel') }))) return;
    try { openLink(await api.chatStart(id)); } catch { say(t('common.error'), 'warning_3d'); }
  }
  // "Who brought" (a member's KPI): signed up by their link, paid (an accepted receipt), came; the ones who came most first
  const brought = $derived.by(() => {
    const by = new Map<Id, { person: PersonRef; signed: number; paid: number; came: number }>();
    for (const a of list ?? []) {
      if (!a.by) continue;
      const x = by.get(a.by.id) ?? by.set(a.by.id, { person: a.by, signed: 0, paid: 0, came: 0 }).get(a.by.id)!;
      x.signed++;
      if (a.status === 'going' && a.receipt && (a.receipt.reviewed || !a.receipt.flags.length)) x.paid++; // a flagged receipt nobody checked isn't paid yet
      if (a.byCame) x.came++;
    }
    return [...by.values()].sort((a, b) => b.came - a.came || b.paid - a.paid || b.signed - a.signed);
  });
  const toCheck = $derived(going.filter((a) => a.receipt?.flags.length && !a.receipt.reviewed).length);

  async function removeEvent() {
    if (!(await sheets.ask({ title: t('studio.deleteAsk'), text: t('studio.deleteText'), ok: t('ed.deleteGo'), cancel: t('tk.keep'), danger: true }))) return;
    try { await api.deleteEvent(id); studioChanged(); haptic.warn(); say(phrase('say.eventDeleted'), 'waving_hand_3d_default'); close(overlay.id); }
    catch (x) {
      haptic.error();
      if (!(x instanceof ApiErr && x.message === 'paid')) { say(t('common.error'), 'warning_3d'); return; }
      // receipts are the only record of money that changed hands: only the creator deletes such an event (owner,
      // Oct 18: say why, and a way to ask him, with the message already written)
      if (await sheets.ask({ title: t('studio.deletePaid'), text: t('studio.deletePaidText'), ok: t('studio.deletePaidAsk'), cancel: t('common.close') }))
        openLink(`https://t.me/Sowers?text=${encodeURIComponent(t('studio.deletePaidMsg', { title: e?.title ?? '' }))}`);
    }
  }
  // "Close registration" (organizers asked to stop sign-ups; theirs and Admin's alike): closes now, the toast's Undo puts the old deadline back
  const regClosed = $derived(!!e?.regUntil && e.regUntil <= nowTs());
  const regOn = (r: EventCard['regUntil']) => { const x = eventById(id); if (x) x.regUntil = r; };
  async function setReg(until: number | 'now' | null, done: string, was: EventCard['regUntil']) {
    try { regOn((await api.setRegUntil(id, until)).regUntil); studioChanged(); haptic.ok(); say(done, 'locked_3d', () => void setReg(was ?? null, t(!was || was > nowTs() ? 'mg.regOpened' : 'mg.regClosed'), e?.regUntil)); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function closeReg() {
    if (!(await sheets.ask({ title: t('mg.closeRegAsk'), text: t('mg.closeRegText'), ok: t('mg.closeRegGo'), cancel: t('common.cancel'), danger: true }))) return;
    void setReg('now', t('mg.regClosed'), e?.regUntil);
  }
  // the door (owner, Nov 7): shut until T-30, or until the club's President or a Vice opens it, from 4 h before (server
  // organizing.open_door; the app's admin never). An hour or more ahead asks twice, the second "Open" after 2 s.
  const doorAt = $derived(e?.doorAt ?? (e ? e.startsAt - 1800 : 0));
  let tick = $state(nowTs());  // a ticking now: "opens at" turns into "open since" at T-30 with the screen open
  onMount(() => { const i = setInterval(() => (tick = nowTs()), 10_000); return () => clearInterval(i); });
  const doorOpen = $derived(doorAt <= tick);
  const opener = $derived(mem?.role === 'president' || mem?.role === 'vice');
  const setDoor = (at: number) => { const x = eventById(id); if (x) x.doorAt = at; };
  async function openDoor() {
    if (!e) return;
    haptic.tap();
    const ask = { ok: t('door.openGo'), cancel: t('common.cancel') };
    if (!(await sheets.ask({ ...ask, title: t('door.openAsk'), text: t('door.openText') }))) return;
    if (e.startsAt - nowTs() > 3600 && !(await sheets.ask({ ...ask, title: t('door.openSure'), text: t('door.openSureText'), wait: 2000 }))) return;
    const was = doorAt;
    tick = nowTs(); setDoor(tick);
    try { await api.openDoor(id); haptic.ok(); say(t('door.opened'), 'party_popper_3d'); }
    catch { setDoor(was); haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // the club's own people asking to come as guests (server seats.team_ask): the President and the Vices answer here
  let asks = $state<TeamAsk[]>([]);
  $effect(() => { void data.rev; if (opener && !staff) api.teamAsks(id).then((l) => (asks = l)).catch(() => {}); });
  async function decide(x: TeamAsk, yes: boolean) {
    haptic.tap();
    asks = asks.filter((y) => y !== x); // at once; back if the server says no
    try { await api.teamDecide(id, x.person.id, yes); haptic.ok(); say(t(yes ? 'ta.saidYes' : 'ta.saidNo'), yes ? 'party_popper_3d' : 'waving_hand_3d_default'); studioChanged(); }
    catch { asks = [x, ...asks]; haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function cancelEvent() {
    if (!(await sheets.ask({ title: t('studio.cancelAsk'), text: t('studio.cancelText'), ok: t('studio.cancelGo'), cancel: t('tk.keep'), danger: true }))) return;
    try { await api.cancelEvent(id); studioChanged(); haptic.warn(); say(t('say.eventCancelled'), 'crying_face_3d'); }
    catch { say(t('common.error'), 'warning_3d'); }
  }
</script>

<Sheet {overlay} icon={SlidersHorizontal} full title={t('mg.title')}>
  {#if e}
    <div class="pg">
      {#if staff}<Notice icon={ShieldCheck} text={t('mg.asStaff')} />{/if}
      <Group>
        <Row title={e.title} subtitle="{relDay(e.startsAt)}, {time(e.startsAt)} · {placeOf(e.place)}" accessory="chevron" onclick={() => sheets.event(id)}>
          {#snippet lead()}<Poster item={e} size={56} radius={16} dim={e.status === 'cancelled'} />{/snippet}
        </Row>
      </Group>

      {#if asks.length}
        <Group caption={t('ta.caption')}>
          {#each asks as x (x.person.id)}
            <Row dense title={x.person.name}>
              {#snippet lead()}<Avatar person={x.person} size={36} />{/snippet}
              {#snippet trailing()}<span class="yn"><IconButton icon={X} size="s" kind="gray" label={t('ta.no')} onclick={() => decide(x, false)} />
                <Button kind="tinted" size="s" onclick={() => decide(x, true)}>{t('ta.yes')}</Button></span>{/snippet}
            </Row>
          {/each}
        </Group>
      {/if}

      {#if head && price && list}
        <Group caption={t('mg.money')}>
          <Row title={t('mg.expected')} subtitle="{paying} × {money(price)}" value={money(paying * price)} />
          <Row title={t('mg.byReceipts')} subtitle={unread ? t('mg.unread', { n: unread }) : undefined}>
            {#snippet detail()}<span class="sum num" class:short={byReceipts < paying * price}>{money(byReceipts)}</span>{/snippet}
          </Row>
          {#if toCheck}<Row icon={TriangleAlert} title={t('mg.check')} count={toCheck} accessory="chevron" onclick={() => sheets.attendees(id)} />{/if}
        </Group>
      {/if}

      {#if head && list}
        <Group caption={t('mg.people')}>
          <Row title={t('mg.going')} value="{going.length}{e.seats ? ' / ' + e.seats : ''}" />
          <Row title={t('mg.came')} value={String(came)} />
          {#if price}<Row title={t('mg.holds')} value={String(of('hold').length)} />{/if}
          <Row title={t('mg.waitlist')} value={String(of('waitlist').length)} />
          {#if e.savedBy}<Row title={t('mg.saved')} value={String(e.savedBy)} />{/if}
        </Group>
      {/if}

      {#if head && brought.length}
        <Group caption={t('mg.brought')}>
          {#each brought as x (x.person.id)}
            <Row dense title={x.person.name} accessory="chevron" onclick={() => sheets.person(x.person.id)}
              subtitle={[`${t('mg.broughtSigned')} ${x.signed}`, price && `${t('mg.broughtPaid')} ${x.paid}`, `${t('mg.came')} ${x.came}`].filter(Boolean).join(' · ')}>
              {#snippet lead()}<Avatar person={x.person} size={36} tappable={false} />{/snippet}
            </Row>
          {/each}
        </Group>
      {/if}

      <Group>
        {#if live && !e.guestHost && (e.endsAt ?? e.startsAt + 6 * 3600) > nowTs()}
          {#if doorOpen}<Row icon={DoorOpen} title={t('door.openedAt', { time: time(doorAt) })} />
          {:else if opener && !staff && e.startsAt - 4 * 3600 <= tick}<Row icon={DoorClosed} title={t('door.open')} subtitle={t('door.openAt', { time: time(doorAt) })} accessory="chevron" onclick={openDoor} />
          {:else}<Row icon={DoorClosed} title={t('door.openAt', { time: time(doorAt) })} />{/if}
        {/if}
        {#if live && !e.guestHost && !staff}<!-- a partner's event has no door; Admin never works the door -->
          {#if inner(e)}<Row icon={UserCheck} title={t('studio.marks')} accessory="chevron" onclick={() => sheets.scanner(id, true)} />
          {:else}<Row icon={ScanLine} title={t('studio.scanner')} accessory="chevron" onclick={() => sheets.scanner(id)} />{/if}
        {/if}
        {#if head}
          <Row icon={UsersRound} title={t('studio.attendees')} accessory="chevron" onclick={() => sheets.attendees(id)} />
          <!-- the big screen at the door (/show): a free public-ish event's own check-in session -->
          {#if crewN != null && live && !inner(e) && !e.guestHost && (e.endsAt ?? e.startsAt + 6 * 3600) > nowTs()}
            <Row icon={ScanLine} title={t('crew.title')} count={crewN} accessory="chevron" onclick={() => sheets.crew(id, (n) => (crewN = n))} />
          {/if}
          {#if live && !price && !e.guestHost && !staff}<Row icon={MonitorUp} title={t('scr.title')} accessory="chevron" onclick={() => sheets.screens(undefined, id)} />{/if}
          <Row icon={Pencil} title={t('studio.edit')} accessory="chevron" onclick={() => sheets.editor(e.org.id, id)} />
          {#if e.status !== 'cancelled' && !staff}<Row icon={MessagesSquare} title={t(chat ? 'chat.open' : 'chat.create')} accessory={chat ? 'external' : 'chevron'} onclick={openChat} />{/if}
          {#if e.needsVolunteers}<Row icon={HandHeart} title={t('vol.list')} count={e.volunteersAsked ?? 0} accessory="chevron" onclick={() => sheets.volunteers(id, e.needsVolunteers!)} />{/if}
        {/if}
        <Row icon={Eye} title={t('mg.asStudents')} accessory="chevron" onclick={() => sheets.event(id)} />
      </Group>

      {#if head && live && !e.guestHost && (!started || e.lateSignup)}
        <Group>
          {#if regClosed}<Row title={t('mg.openReg')} onclick={() => setReg(null, t('mg.regOpened'), e.regUntil)} />
          {:else}<Row tone="destructive" title={t('mg.closeReg')} onclick={closeReg} />{/if}
        </Group>
      {/if}
      {#if head && live && !started}<Group><Row tone="destructive" title={t('studio.cancelEvent')} onclick={cancelEvent} /></Group>{/if}
      {#if head && e.status === 'cancelled'}<Group><Row tone="destructive" title={t('studio.deleteEvent')} onclick={removeEvent} /></Group>{/if}
    </div>
  {/if}
</Sheet>

<style>
  .pg { display: flex; flex-direction: column; gap: var(--gap-group); margin-top: var(--s-1); }
  .sum { margin-left: auto; color: var(--text-3); }
  .sum.short { color: var(--warning-text); }
  .yn { display: flex; align-items: center; gap: var(--s-2); }
</style>
