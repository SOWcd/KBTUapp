<script lang="ts">
  // Who registered for an event (Head+; organizers see full names). Going first, then holds and the
  // waitlist; a check-in shows its time. A tap opens the person's card. "Export" has the bot send the list as a CSV
  // to the organizer's chat (opens on any phone, can be forwarded to DMP). A paid event: how much should have
  // come to the club's Kaspi, and each receipt a tap away; flagged ones (⚠) on top.
  // Cancelled paid seats wait folded at the end, their receipts there for refunds even after signing up again.
  // ⋯ "Write in Telegram": one person's @username, asked for on the tap (never in the list; server attendee_contact).
  import { onMount, untrack } from 'svelte';
  import FileDown from '@lucide/svelte/icons/file-down';
  import ReceiptIcon from '@lucide/svelte/icons/receipt';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import X from '@lucide/svelte/icons/x';
  import Chip from '../../ui/Chip.svelte';
  import { menu } from '../../ui/menu';
  import { api, ApiErr, staffEvents, type Attendee, type Id } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { haptic, inTelegram, openLink } from '../../lib/tg';
  import { eventById, studioChanged } from '../../lib/state/data.svelte';
  import { readState } from '../../lib/state/readState.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { may } from '../../lib/perms';
  import { sheets } from '../../lib/state/sheets';
  import { t, money } from '../../lib/i18n/index.svelte';
  import { hit } from '../../lib/search';
  import { time, whenLine } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import ClipboardList from '@lucide/svelte/icons/clipboard-list';
  import Avatar from '../../ui/Avatar.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Notice from '../../ui/Notice.svelte';
  import SearchField from '../../ui/SearchField.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import { checkinMessages } from './checkinMessages';
  import SortChip from '../../ui/SortChip.svelte';
  import { sorted, byName, newest, usual, type Order } from '../../lib/sort.svelte';
  import { screenful } from '../../lib/screenful.svelte';

  let { overlay, id, only: from }: { overlay: Overlay; id: Id; only?: 'check' | 'hold' | 'waitlist' } = $props();
  // opened from one of EventManage's rows (receipts to check, holds, the waitlist): just those, a chip away from everyone
  let only = $state(untrack(() => from));
  const ONLY = { check: 'mg.check', hold: 'mg.holds', waitlist: 'mg.waitlist' } as const;
  const inOnly = (a: Attendee) => !only || (only === 'check' ? a.status === 'going' && !!a.receipt?.flags.length && !a.receipt.reviewed : a.status === only);

  const { state: roster, load } = readState(() => api.attendees(id));
  const list = $derived(roster.value);
  onMount(() => { void load(); });
  let q = $state('');
  // the server's: going first, then holds and the waitlist, flagged receipts on top
  const ORDERS: Order<Attendee>[] = [usual(), byName((a) => a.fullName), newest((a) => a.at), { id: 'came', label: 'sort.came', by: (a) => a.checkedInAt, desc: true }];
  const found = $derived(sorted('attendees', ORDERS, (list ?? []).filter((a) => !q.trim() || hit(q, [a.fullName, a.person.nick]))));
  // cancelled after paying (server attendees): folded at the end, their receipt there for the refund;
  // outside every total
  const shown = $derived(found.filter((a) => a.status !== 'cancelled' && inOnly(a)));
  const removed = $derived(found.filter((a) => a.status === 'cancelled'));
  const draw = screenful(() => shown.length); // a big event's guests: a screenful with the sheet, the rest after it paints
  let removedOpen = $state(false);
  const going = $derived((list ?? []).filter((a) => a.status === 'going').length);
  const came = $derived((list ?? []).filter((a) => a.checkedInAt).length);
  const title = $derived(eventById(id)?.title ?? '');
  // check in by name (no QR) while the door is open: 3 h before the start until the end (or 6 h after the start)
  const ev = $derived(eventById(id));
  const price = $derived(ev?.price ?? 0);
  // a co-host's event team reads short names only: no receipts, no file, no profiles (server cohosts.py)
  // the app's admin from Admin (staffEvents) reads it as the host's team does; not the door, not the receipts (money);
  // the creator works the door as its President (server app.viewer), the receipts still the club's (the server hides them)
  const staff = $derived(staffEvents.has(id));
  const plain = $derived(staff && !session.me?.founder);
  const host = $derived(staff || !ev || may(session.me?.memberships.find((m) => m.org.id === ev.org.id), 'events'));
  const paid = $derived((list ?? []).filter((a) => a.receipt && a.status !== 'cancelled').length);
  const read = $derived((list ?? []).reduce((n, a) => n + (a.status !== 'cancelled' && a.receipt?.amount || 0), 0)); // what OCR read off the receipts
  // a spot check or a receipt read in part (nothing wrong found, a person looks anyway) isn't a warning: the receipt
  // icon, tinted while nobody has looked at it
  const flagged = (a: Attendee) => !!a.receipt?.flags.some((f) => f !== 'spot' && f !== 'partial') && !a.receipt.reviewed;
  const doorOpen = $derived(!plain && !!ev && Date.now() / 1000 >= (ev.doorAt ?? ev.startsAt - 1800) && Date.now() / 1000 <= (ev.endsAt ?? ev.startsAt + 6 * 3600));
  let undoFor = $state<number | null>(null);
  let undoTimer: ReturnType<typeof setTimeout> | undefined;
  let marking = $state<Id[]>([]); // one check-in per row at a time: a second tap waits for the first
  async function mark(a: Attendee, admit = false) {
    if (marking.includes(a.person.id)) return;
    marking = [...marking, a.person.id];
    let again = false; // admitted past a flagged receipt: once this one has let go of the row
    try {
      const r = await api.checkinPerson(id, a.person.id, admit);
      if (r.result === 'ask_org') { haptic.error(); say(t('mk.askOrg'), 'warning_3d'); return; }
      if (r.result === 'flagged') { // nothing recorded yet: a look at the receipt first (server organizing._held)
        again = !admit && await sheets.ask({ title: t('mk.admitAsk'), ok: t('mk.admit'), cancel: t('common.cancel') });
        return;
      }
      if (!('at' in r)) { haptic.error(); say(t(checkinMessages[r.result]), 'pleading_face_3d'); return; }
      a.checkedInAt = r.at; a.manual = r.result === 'ok';
      haptic.ok();
      undoFor = a.person.id; clearTimeout(undoTimer); undoTimer = setTimeout(() => (undoFor = null), 8000);
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { marking = marking.filter((x) => x !== a.person.id); if (again) void mark(a, true); }
  }
  // a receipt looked at: the next flagged one opens by itself (the list re-read first; never the same one again)
  const openReceipt = (a: Attendee) => {
    const r = a.receipt!, was = flagged(a);
    sheets.receipt(r, a.fullName, () => void load().then(() => {
      const next = was && (roster.value ?? []).find((x) => x.status !== 'cancelled' && flagged(x) && x.receipt!.id !== r.id);
      if (next) openReceipt(next);
    }));
  };
  async function undo(a: Attendee) {
    try { await api.undoCheckin(id, a.person.id); a.checkedInAt = null; a.manual = false; undoFor = null; haptic.soft(); say(t('door.undone'), 'waving_hand_3d_default'); }
    catch { say(t('common.error'), 'warning_3d'); }
  }

  // the organizer takes someone off before the start (server seats.remove_seats): not a co-host, not someone who came
  // the app's admin from Admin never on a paid event (money is the club's; server remove_seats)
  const removable = (a: Attendee) => host && !(plain && price) && a.status !== 'cancelled' && !!ev && Date.now() / 1000 < ev.startsAt && !a.checkedInAt;
  async function remove(a: Attendee) {
    if (!list || !(await sheets.ask({ title: t('att.removeAsk', { name: a.fullName }), text: t(a.receipt ? 'att.removePaid' : 'att.removeText'),
      ok: t('att.remove'), cancel: t('common.cancel'), danger: true }))) return;
    const was = list;
    roster.value = list.filter((x) => x.person.id !== a.person.id); haptic.tap();
    try { await api.removePerson(id, a.person.id); haptic.ok(); say(t('att.removed'), 'waving_hand_3d_default'); void load(); studioChanged(); } // the waitlist moved in
    catch (e) { roster.value = was; haptic.error(); say(e instanceof ApiErr && e.message === 'checked_in' ? t('att.removeCame') : t('common.error'), 'warning_3d'); }
  }

  // a seat on this event (a ticket, or a hold waiting on its receipt) until a week after the end: the host's own
  // organizer only, never a co-host or staff from Admin (server organizing.attendee_contact)
  const writable = (a: Attendee) => host && !staff && (a.status === 'going' || a.status === 'hold') && !!ev && a.person.id !== session.me?.id
    && Date.now() / 1000 < (ev.endsAt ?? ev.startsAt + 3 * 3600) + 7 * 86400;
  async function write(a: Attendee) {
    try {
      const { username, asked } = await api.attendeeContact(id, a.person.id);
      if (username) { openLink(`https://t.me/${encodeURIComponent(username)}`); return; }
      if (asked) { say(t('att.asked'), 'waving_hand_3d_default'); return; }
      if (!inTelegram) { say(t('att.askInTelegram'), 'warning_3d'); return; }
      // no @username: the bot asks them to write to me instead (my own Telegram on its button)
      if (!(await sheets.ask({ title: t('att.askTitle'), text: t('att.askText'), ok: t('att.askOk'), cancel: t('common.cancel') }))) return;
      await api.askToWrite(id, a.person.id);
      haptic.ok(); say(t('att.asked'), 'waving_hand_3d_default');
    } catch (e) {
      haptic.error();
      say(!(e instanceof ApiErr) ? t('common.error') : e.code === 'rate_limited' ? t('att.writeTooMany') : e.message === 'own_username' ? t('att.ownUsername') : t('common.error'), 'warning_3d');
    }
  }
  const more = (a: Attendee) => [...(writable(a) ? [{ label: t('person.write'), onselect: () => void write(a) }] : []),
    ...(removable(a) ? [{ label: t('att.remove'), destructive: true, onselect: () => remove(a) }] : [])];

  let sending = $state(false);
  async function exportList() {
    sending = true;
    try {
      await api.exportAttendees(id);
      haptic.ok(); say(t('att.sent'), 'party_popper_3d');
    } catch (e) {
      haptic.error(); say(e instanceof ApiErr && e.message === 'no_dm' ? t('att.noDm') : t('common.error'), 'warning_3d');
    } finally { sending = false; }
  }
</script>

{#snippet people(xs: Attendee[])}
  {#each xs as a (a.person.id)}
    {@const acts = (!!a.receipt && !staff) || undoFor === a.person.id || (!a.checkedInAt && a.status === 'going' && doorOpen) || removable(a) || writable(a)}
    <!-- a row with buttons at its end can't be a button itself: then the avatar opens the person -->
    <Row dense title={a.fullName} subtitle={a.person.name + (a.free ? ' · ' + t('att.free') : '') + (a.walkIn ? ' · ' + t('att.walkIn') : '') + (a.manual ? ' · ' + t('att.manual') : '')}
      {...(acts ? { trailing: end } : { detail: end, onclick: host ? () => sheets.person(a.person.id) : undefined })}>
      {#snippet lead()}<Avatar person={a.person} size={36} tappable={acts && host} />{/snippet}
    </Row>
    {#snippet end()}
      {#if a.receipt && !staff}<IconButton size="s" icon={flagged(a) ? TriangleAlert : ReceiptIcon} kind={flagged(a) ? 'destructive' : a.receipt.reviewed ? 'gray' : 'tinted'} label={t('rc.title')}
        onclick={() => openReceipt(a)} />{/if}
      {#if a.checkedInAt}
        {#if undoFor === a.person.id}<Button kind="secondary" size="s" onclick={() => undo(a)}>{t('door.undo')}</Button>{/if}
        <Tag tone="success">{t('att.in', { time: time(a.checkedInAt) })}</Tag>
      {:else if a.status === 'going' && doorOpen}<Button kind="secondary" size="s" loading={marking.includes(a.person.id)} onclick={() => mark(a)}>{t('door.mark')}</Button>
      {:else if a.status === 'going'}<Tag tone="accent">{t('att.going')}</Tag>
      {:else if a.status === 'hold'}<Tag tone="warning">{t('att.hold')}</Tag>
      {:else if a.status === 'waitlist'}<Tag>{t('att.waitlist')}</Tag>{/if}
      {#if removable(a) || writable(a)}<IconButton size="s" icon={Ellipsis} kind="plain" label={t('common.more')}
        onclick={(e) => menu(e.currentTarget as Element, more(a))} />{/if}
    {/snippet}
    {#if !staff}{#each a.previousReceipts ?? [] as old (old.id)}
      <Row dense icon={ReceiptIcon} title={t('rc.title')} subtitle={whenLine(old.at)} value={old.amount ? money(old.amount) : undefined}
        accessory="chevron" onclick={() => sheets.receipt(old, a.fullName, load)} />
    {/each}{/if}
    <!-- engine: Row needs content under it (the answers to the event's questions) -->
    {#if a.answers?.length}<dl class="ans">{#each a.answers as x, k (k)}<dt>{x.q}</dt><dd class="selectable">{x.a}</dd>{/each}</dl>{/if}
  {/each}
{/snippet}

<Sheet {overlay} icon={ClipboardList} full title={t('studio.attendees')}>
  {#if title}<p class="t-foot ev ellipsis">{title}</p>{/if}
  {#if roster.status === 'error'}<EmptyState onretry={load} />{:else if roster.status === 'loading' && !shown.length}<Skeleton />{/if}
  {#if list}<div class="col">
    <div class="bar"><p class="stats">{t('att.stats', { going, came })}</p>
      {#if list.length && host}<Button kind="secondary" size="s" loading={sending} onclick={exportList}>{#snippet icon()}<FileDown size={16} />{/snippet}{t('att.export')}</Button>{/if}</div>
    {#if price && paid}
      <Notice tone={read && read < paid * price ? 'warning' : 'neutral'} icon={ReceiptIcon} text={t('att.expected', { sum: money(paid * price), n: paid, price: money(price) })}>
        {#if read}<p class="by">{t('att.byReceipts', { sum: money(read) })}</p>{/if}
      </Notice>
    {/if}
    {#if only}<span class="only"><Chip selected icon={X} onclick={() => { haptic.tap(); only = undefined; }}>{t(ONLY[only])}</Chip></span>{/if}
    {#if list.length > 8}<SearchField bind:value={q} placeholder={t('att.search')} />{/if}
    {#if shown.length}
      {#if shown.length > 1}<SortChip list="attendees" orders={ORDERS} />{/if}
      <Group>{@render people(shown.slice(0, draw.n))}</Group>
    {:else if roster.status === 'ready'}
      <EmptyState inline text={q.trim() || only ? t('clubs.nothing') : t('att.none')} />
    {/if}
    {#if removed.length && !staff}
      <Group>
        <Row title={t('att.removedFold')} value={String(removed.length)} accessory="disclosure" open={removedOpen} onclick={() => { haptic.tap(); removedOpen = !removedOpen; }} />
        {#if removedOpen}{@render people(removed)}{/if}
      </Group>
    {/if}
  </div>{/if}
</Sheet>

<style>
  .ev { margin-top: 2px; }
  .only { display: flex; }
  .bar { display: flex; align-items: center; justify-content: space-between; gap: var(--s-3); }
  .stats { font: 600 var(--fs-row)/1.3 var(--font-text); }
  .by { font: 450 var(--fs-body)/1.35 var(--font-text); color: var(--text-2); }
  .col { display: flex; flex-direction: column; gap: var(--s-3); margin-top: var(--s-3); }
  /* the answers to the event's own questions, under the name, from where the name starts */
  .ans { display: grid; grid-template-columns: auto 1fr; gap: 3px var(--s-3); margin-left: calc(var(--s-4) + 36px + var(--s-3)); padding: 0 var(--s-4) var(--s-3) 0;
    font: 450 var(--fs-sub)/1.35 var(--font-text); }
  .ans:not(:last-child) { border-bottom: 0.5px solid var(--separator); }
  .ans dt { color: var(--text-3); }
  .ans dd { margin: 0; color: var(--text); overflow-wrap: anywhere; }
</style>
