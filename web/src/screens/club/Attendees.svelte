<script lang="ts">
  // Who registered for an event (Head+; §3: organizers see full names). Going first, then holds and the
  // waitlist; a check-in shows its time. A tap opens the person's card. "Export" has the bot send the list as a CSV
  // to the organizer's chat (opens on any phone, can be forwarded to DMP). A paid event (§4.3): how much should have
  // come to the club's Kaspi, and each receipt a tap away; flagged ones (⚠) on top.
  import Search from '@lucide/svelte/icons/search';
  import FileDown from '@lucide/svelte/icons/file-down';
  import ReceiptIcon from '@lucide/svelte/icons/receipt';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import { api, ApiErr, type Attendee, type Id } from '../../lib/api';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { haptic } from '../../lib/tg';
  import { eventById } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, money } from '../../lib/i18n/index.svelte';
  import { time } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import Avatar from '../../ui/Avatar.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Button from '../../ui/Button.svelte';

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
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  async function undo(a: Attendee) {
    try { await api.undoCheckin(id, a.person.id); a.checkedInAt = null; a.manual = false; undoFor = null; haptic.soft(); say(t('door.undone'), 'waving_hand_3d_default'); }
    catch { say(t('common.error'), 'pleading_face_3d'); }
  }

  let sending = $state(false);
  async function exportList() {
    sending = true;
    try {
      await api.exportAttendees(id);
      haptic.ok(); say(t('att.sent'), 'party_popper_3d');
    } catch (e) {
      haptic.error(); say(e instanceof ApiErr && e.message === 'no_dm' ? t('att.noDm') : t('common.error'), 'pleading_face_3d');
    } finally { sending = false; }
  }
</script>

<Sheet {overlay} tall title={t('studio.attendees')}>
  <h2 class="t-h2">{t('studio.attendees')}</h2>
  {#if title}<p class="t-foot ev ellipsis">{title}</p>{/if}
  {#if list}
    <div class="bar"><p class="stats">{t('att.stats', { going, came })}</p>
      {#if list.length}<button class="exp" onclick={exportList} disabled={sending}><FileDown size={17} />{t('att.export')}</button>{/if}</div>
    {#if price && paid}<p class="due">{t('att.expected', { sum: money(paid * price), n: paid, price: money(price) })}{#if read}<br />
      <span class:short={read < paid * price}>{t('att.byReceipts', { sum: money(read) })}</span>{/if}</p>{/if}
    {#if list.length > 8}
      <label class="search"><Search size={18} /><input bind:value={q} placeholder={t('att.search')} type="search" autocomplete="off" /></label>
    {/if}
    <div class="list">
      {#each shown as a (a.person.id)}
        <div class="row">
          <button class="who" onclick={() => sheets.person(a.person.id)}>
            <Avatar person={a.person} size={40} tappable={false} />
            <span class="txt"><b class="ellipsis">{a.fullName}</b><span class="t-foot">{a.person.name}{#if a.free}{' · ' + t('att.free')}{/if}{#if a.walkIn}{' · ' + t('att.walkIn')}{/if}{#if a.manual}{' · ' + t('att.manual')}{/if}</span></span>
          </button>
          {#if a.receipt}<button class="rc" class:flag={flagged(a)} onclick={() => sheets.receipt(a.receipt!, a.fullName, load)} aria-label={t('rc.title')}>
            {#if flagged(a)}<TriangleAlert size={17} />{:else}<ReceiptIcon size={17} />{/if}</button>{/if}
          {#if a.checkedInAt}
            {#if undoFor === a.person.id}<button class="undo" onclick={() => undo(a)}>{t('door.undo')}</button>{/if}
            <Chip tone="success">{t('att.in', { time: time(a.checkedInAt) })}</Chip>
          {:else if a.status === 'going' && doorOpen}<Button kind="secondary" size="s" onclick={() => mark(a)}>{t('door.mark')}</Button>
          {:else if a.status === 'going'}<Chip tone="accent">{t('att.going')}</Chip>
          {:else if a.status === 'hold'}<Chip tone="warning">{t('att.hold')}</Chip>
          {:else}<Chip>{t('att.waitlist')}</Chip>{/if}
        </div>
      {:else}
        <p class="t-foot empty">{list.length ? t('clubs.nothing') : t('att.none')}</p>
      {/each}
    </div>
  {/if}
</Sheet>

<style>
  .ev { margin-top: 2px; }
  .bar { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin: 12px 0 10px; }
  .stats { font: 650 15px/1.3 var(--font-text); }
  .exp { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 650 13.5px/1 var(--font-text); }
  .exp:disabled { opacity: 0.55; }
  .due { margin: -4px 0 10px; font: 600 14px/1.3 var(--font-text); color: var(--text-2); }
  .due .short { color: var(--warning-text); }
  .rc { flex: none; width: 34px; height: 34px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--surface-2); color: var(--text-2); }
  .rc.flag { background: var(--warning-soft); color: var(--warning-text); }
  .search { display: flex; align-items: center; gap: 8px; height: 42px; padding: 0 12px; margin-bottom: 8px; border-radius: var(--r-m); background: var(--surface-2); color: var(--text-3); }
  .search input { flex: 1; min-width: 0; font: 500 16px/1 var(--font-text); color: var(--text); }
  .list { display: flex; flex-direction: column; }
  .row { display: flex; align-items: center; gap: 8px; padding: 8px 2px; width: 100%; }
  .who { flex: 1; min-width: 0; display: flex; align-items: center; gap: 12px; text-align: left; }
  .undo { flex: none; padding: 6px 4px; font: 620 13px/1 var(--font-text); color: var(--text-2); }
  .row + .row { border-top: 1px solid var(--line); }
  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .txt b { font: 620 15px/1.3 var(--font-text); }
  .empty { padding: 18px 2px; }
</style>
