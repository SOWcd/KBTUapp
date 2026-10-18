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
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import { api, ApiErr, type Attendee, type Id } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { data, eventById, phrase, studioChanged } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { session } from '../../lib/state/session.svelte';
  import { t, money, placeOf } from '../../lib/i18n/index.svelte';
  import { relDay, time, nowTs } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import { inner, may } from '../../lib/perms';
  import Sheet from '../../ui/Sheet.svelte';
  import Poster from '../../ui/Poster.svelte';
  import Button from '../../ui/Button.svelte';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();

  const e = $derived(eventById(id));
  const mem = $derived(session.me?.memberships.find((m) => m.org.id === e?.org.id));
  const head = $derived(may(mem, 'events'));
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
  // the event's Telegram group (owner, Oct 15): open it, or "Create chat" adds our bot to a group the organizer picks
  let chat = $state<string | null>(null);
  $effect(() => { if (head) api.event(id).then((x) => (chat = x.chat ?? null)).catch(() => {}); });
  async function openChat() {
    haptic.tap();
    if (chat) { openLink(chat); return; }
    if (!(await sheets.ask({ title: t('chat.ask'), text: t('chat.askText'), ok: t('chat.go'), cancel: t('common.cancel') }))) return;
    try { openLink(await api.chatStart(id)); } catch { say(t('common.error'), 'pleading_face_3d'); }
  }
  const toCheck = $derived(going.filter((a) => a.receipt?.flags.length && !a.receipt.reviewed).length);

  async function removeEvent() {
    if (!(await sheets.ask({ title: t('studio.deleteAsk'), text: t('studio.deleteText'), ok: t('ed.deleteGo'), cancel: t('tk.keep'), danger: true }))) return;
    try { await api.deleteEvent(id); studioChanged(); haptic.warn(); say(phrase('say.eventDeleted'), 'waving_hand_3d_default'); close(overlay.id); }
    catch (x) {
      haptic.error();
      if (!(x instanceof ApiErr && x.message === 'paid')) { say(t('common.error'), 'pleading_face_3d'); return; }
      // receipts are the only record of money that changed hands: only the creator deletes such an event (owner,
      // Oct 18: say why, and a way to ask him, with the message already written)
      if (await sheets.ask({ title: t('studio.deletePaid'), text: t('studio.deletePaidText'), ok: t('studio.deletePaidAsk'), cancel: t('common.close') }))
        openLink(`https://t.me/Sowers?text=${encodeURIComponent(t('studio.deletePaidMsg', { title: e?.title ?? '' }))}`);
    }
  }
    async function cancelEvent() {
    if (!(await sheets.ask({ title: t('studio.cancelAsk'), text: t('studio.cancelText'), ok: t('studio.cancelGo'), cancel: t('tk.keep'), danger: true }))) return;
    try { await api.cancelEvent(id); studioChanged(); haptic.warn(); say(t('say.eventCancelled'), 'crying_face_3d'); }
    catch { say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

<Sheet {overlay} tall title={t('mg.title')}>
  {#if e}
    <button class="hd" onclick={() => sheets.event(id)}>
      <Poster item={e} size={56} radius={16} dim={e.status === 'cancelled'} />
      <span class="txt">
        <b class="t-title clamp-2">{e.title}</b>
        <span class="t-foot">{relDay(e.startsAt)}, {time(e.startsAt)} · {placeOf(e.place)}</span>
      </span>
    </button>

    {#if head && price && list}
      <h3 class="t-cap sec">{t('mg.money')}</h3>
      <div class="card surface">
        <div class="row"><i>{t('mg.expected')}</i><b>{money(paying * price)}</b><span class="t-foot">{paying} × {money(price)}</span></div>
        <div class="row"><i>{t('mg.byReceipts')}</i><b class:short={byReceipts < paying * price}>{money(byReceipts)}</b>
          {#if unread}<span class="t-foot">{t('mg.unread', { n: unread })}</span>{/if}</div>
        {#if toCheck}
          <button class="check" onclick={() => sheets.attendees(id)}><TriangleAlert size={18} /><span>{t('mg.check')}</span><b>{toCheck}</b><ChevronRight size={18} /></button>
        {/if}
      </div>
    {/if}

    {#if head && list}
      <h3 class="t-cap sec">{t('mg.people')}</h3>
      <div class="nums">
        <div><b>{going.length}{e.seats ? ' / ' + e.seats : ''}</b><i>{t('mg.going')}</i></div>
        <div><b>{came}</b><i>{t('mg.came')}</i></div>
        {#if price}<div><b>{of('hold').length}</b><i>{t('mg.holds')}</i></div>{/if}
        <div><b>{of('waitlist').length}</b><i>{t('mg.waitlist')}</i></div>
        {#if e.savedBy}<div><b>{e.savedBy}</b><i>{t('mg.saved')}</i></div>{/if}
      </div>
    {/if}

    <div class="tools">
      {#if live}
        {#if inner(e)}<button onclick={() => sheets.scanner(id, true)}><UserCheck size={20} />{t('studio.marks')}</button>
        {:else}<button onclick={() => sheets.scanner(id)}><ScanLine size={20} />{t('studio.scanner')}</button>{/if}
      {/if}
      {#if head}
        <button onclick={() => sheets.attendees(id)}><UsersRound size={20} />{t('studio.attendees')}</button>
        <button onclick={() => sheets.editor(e.org.id, id)}><Pencil size={20} />{t('studio.edit')}</button>
        {#if e.status !== 'cancelled'}<button onclick={openChat}><MessagesSquare size={20} />{t(chat ? 'chat.open' : 'chat.create')}</button>{/if}
        {#if e.needsVolunteers}<button onclick={() => sheets.volunteers(id, e.needsVolunteers!)}><HandHeart size={20} />{t('vol.list')}{e.volunteersAsked ? ` · ${e.volunteersAsked}` : ''}</button>{/if}
      {/if}
      <button onclick={() => sheets.event(id)}><Eye size={20} />{t('mg.asStudents')}</button>
    </div>

    {#if head && live && !started}<div class="kill"><Button kind="danger" size="m" full onclick={cancelEvent}>{t('studio.cancelEvent')}</Button></div>{/if}
    {#if head && e.status === 'cancelled'}<div class="kill"><Button kind="danger" size="m" full onclick={removeEvent}>{t('studio.deleteEvent')}</Button></div>{/if}
  {/if}
</Sheet>

<style>
  .hd { display: flex; align-items: center; gap: 12px; width: 100%; text-align: left; margin-top: 4px; }
  .txt { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .sec { margin: 20px 2px 8px; }
  .card { display: flex; flex-direction: column; padding: 4px 14px; }
  .row { display: flex; align-items: baseline; gap: 10px; min-height: 50px; padding: 14px 0 12px; }
  .row + .row { border-top: 1px solid var(--line); }
  .row i { flex: none; width: 112px; font: 550 13.5px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .row b { font: 750 20px/1 var(--font-display); letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
  .row b.short { color: var(--warning-text); }
  .row .t-foot { margin-left: auto; text-align: right; }
  .check { display: flex; align-items: center; gap: 10px; margin: 2px -6px 10px; padding: 12px; border-radius: var(--r-m); text-align: left;
    background: var(--warning-soft); color: var(--warning-text); font: 650 15px/1.2 var(--font-text); }
  .check span { flex: 1; }
  .check b { min-width: 24px; height: 24px; padding: 0 7px; border-radius: 12px; background: var(--warning-text); color: var(--bg); font: 700 13px/24px var(--font-text); text-align: center; }
  .check:active { transform: scale(0.98); }
  .nums { display: grid; grid-template-columns: repeat(auto-fit, minmax(72px, 1fr)); gap: 8px; }
  .nums div { display: flex; flex-direction: column; gap: 4px; padding: 12px; border-radius: var(--r-l); background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); }
  .nums b { font: 750 20px/1 var(--font-display); letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }
  .nums i { font: 550 12.5px/1.2 var(--font-text); font-style: normal; color: var(--text-2); }
  .tools { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 20px; }
  .tools button { display: flex; align-items: center; gap: 10px; height: 54px; padding: 0 14px; border-radius: var(--r-l); background: var(--surface);
    box-shadow: inset 0 0 0 1px var(--line); color: var(--text); font: 620 15px/1 var(--font-text); }
  .tools button :global(svg) { color: var(--accent-text); flex: none; }
  .tools button:active { transform: scale(0.97); }
  .kill { margin-top: 18px; }
</style>
