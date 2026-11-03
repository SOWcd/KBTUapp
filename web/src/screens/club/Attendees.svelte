<script lang="ts">
  // Who registered for an event (Head+; §3: organizers see full names). Going first, then holds and the
  // waitlist; a check-in shows its time. A tap opens the person's card. "Export" has the bot send the list as a CSV
  // to the organizer's chat (opens on any phone, can be forwarded to DMP). A paid event (§4.3): how much should have
  // come to the club's Kaspi, and each receipt a tap away; flagged ones (⚠) on top.
  import FileDown from '@lucide/svelte/icons/file-down';
  import ReceiptIcon from '@lucide/svelte/icons/receipt';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import { api, ApiErr, type Attendee, type Id } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { haptic } from '../../lib/tg';
  import { eventById } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { may } from '../../lib/perms';
  import { sheets } from '../../lib/state/sheets';
  import { t, money } from '../../lib/i18n/index.svelte';
  import { time } from '../../lib/time';
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

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();

  let list = $state<Attendee[] | null>(null);
  const load = () => api.attendees(id).then((l) => (list = l)).catch(() => (list = []));
  $effect(() => { void load(); });
  let q = $state('');
  const norm = (s: string) => s.toLowerCase().replace(/\u0451/g, '\u0435'); // Russian yo → ye
  const shown = $derived((list ?? []).filter((a) => !q.trim() || norm(a.fullName + ' ' + (a.person.nick ?? '')).includes(norm(q.trim()))));
  const going = $derived((list ?? []).filter((a) => a.status === 'going').length);
  const came = $derived((list ?? []).filter((a) => a.checkedInAt).length);
  const title = $derived(eventById(id)?.title ?? '');
  // check in by name (no QR, §4.4) while the door is open: 3 h before the start until the end (or 6 h after the start)
  const ev = $derived(eventById(id));
  const price = $derived(ev?.price ?? 0);
  // a co-host's event team reads short names only: no receipts, no file, no profiles (server cohosts.py)
  const host = $derived(!ev || may(session.me?.memberships.find((m) => m.org.id === ev.org.id), 'events'));
  const paid = $derived((list ?? []).filter((a) => a.receipt).length);
  const read = $derived((list ?? []).reduce((n, a) => n + (a.receipt?.amount ?? 0), 0)); // what OCR read off the receipts
  const flagged = (a: Attendee) => !!a.receipt?.flags.length && !a.receipt.reviewed;
  const doorOpen = $derived(!!ev && Date.now() / 1000 >= ev.startsAt - 3 * 3600 && Date.now() / 1000 <= (ev.endsAt ?? ev.startsAt + 6 * 3600));
  let undoFor = $state<number | null>(null);
  let undoTimer: ReturnType<typeof setTimeout> | undefined;
  async function mark(a: Attendee) {
    try {
      const r = await api.checkinPerson(id, a.person.id);
      if (r.result !== 'ok' && r.result !== 'already') { haptic.error(); say(t(r.result === 'closed' ? 'scan.closed' : 'common.error'), 'pleading_face_3d'); return; }
      a.checkedInAt = r.at; a.manual = r.result === 'ok';
      haptic.ok();
      undoFor = a.person.id; clearTimeout(undoTimer); undoTimer = setTimeout(() => (undoFor = null), 8000);
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  async function undo(a: Attendee) {
    try { await api.undoCheckin(id, a.person.id); a.checkedInAt = null; a.manual = false; undoFor = null; haptic.soft(); say(t('door.undone'), 'waving_hand_3d_default'); }
    catch { say(t('common.error'), 'warning_3d'); }
  }

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

<Sheet {overlay} icon={ClipboardList} full title={t('studio.attendees')}>
  {#if title}<p class="t-foot ev ellipsis">{title}</p>{/if}
  {#if list}<div class="col">
    <div class="bar"><p class="stats">{t('att.stats', { going, came })}</p>
      {#if list.length && host}<Button kind="secondary" size="s" loading={sending} onclick={exportList}>{#snippet icon()}<FileDown size={16} />{/snippet}{t('att.export')}</Button>{/if}</div>
    {#if price && paid}
      <Notice tone={read && read < paid * price ? 'warning' : 'neutral'} icon={ReceiptIcon} text={t('att.expected', { sum: money(paid * price), n: paid, price: money(price) })}>
        {#if read}<p class="by">{t('att.byReceipts', { sum: money(read) })}</p>{/if}
      </Notice>
    {/if}
    {#if list.length > 8}<SearchField bind:value={q} placeholder={t('att.search')} />{/if}
    {#if shown.length}
      <Group>
        {#each shown as a (a.person.id)}
          {@const acts = !!a.receipt || undoFor === a.person.id || (!a.checkedInAt && a.status === 'going' && doorOpen)}
          <!-- a row with buttons at its end can't be a button itself: then the avatar opens the person -->
          <Row dense title={a.fullName} subtitle={a.person.name + (a.free ? ' · ' + t('att.free') : '') + (a.walkIn ? ' · ' + t('att.walkIn') : '') + (a.manual ? ' · ' + t('att.manual') : '')}
            {...(acts ? { trailing: end } : { detail: end, onclick: host ? () => sheets.person(a.person.id) : undefined })}>
            {#snippet lead()}<Avatar person={a.person} size={36} tappable={acts && host} />{/snippet}
          </Row>
          {#snippet end()}
            {#if a.receipt}<IconButton size="s" icon={flagged(a) ? TriangleAlert : ReceiptIcon} kind={flagged(a) ? 'destructive' : 'gray'} label={t('rc.title')}
              onclick={() => sheets.receipt(a.receipt!, a.fullName, load)} />{/if}
            {#if a.checkedInAt}
              {#if undoFor === a.person.id}<Button kind="secondary" size="s" onclick={() => undo(a)}>{t('door.undo')}</Button>{/if}
              <Tag tone="success">{t('att.in', { time: time(a.checkedInAt) })}</Tag>
            {:else if a.status === 'going' && doorOpen}<Button kind="secondary" size="s" onclick={() => mark(a)}>{t('door.mark')}</Button>
            {:else if a.status === 'going'}<Tag tone="accent">{t('att.going')}</Tag>
            {:else if a.status === 'hold'}<Tag tone="warning">{t('att.hold')}</Tag>
            {:else}<Tag>{t('att.waitlist')}</Tag>{/if}
          {/snippet}
          <!-- engine: Row needs content under it (the answers to the event's questions) -->
          {#if a.answers?.length}<dl class="ans">{#each a.answers as x, k (k)}<dt>{x.q}</dt><dd class="selectable">{x.a}</dd>{/each}</dl>{/if}
        {/each}
      </Group>
    {:else}
      <EmptyState inline text={list.length ? t('clubs.nothing') : t('att.none')} />
    {/if}
  </div>{/if}
</Sheet>

<style>
  .ev { margin-top: 2px; }
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
