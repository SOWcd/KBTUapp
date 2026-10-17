<script lang="ts">
  // Tab 2 → Studio (Head+) or Club (Member): "To do" on top only when something waits (new applications, the memo on
  // Tue-Wed, recruitment at a term's start, questions, receipts to check), the club's next event with the door
  // scanner and "New event", a row of small actions (memo, recruitment, invite, club profile), its events by state
  // (owner, Oct 15). Several clubs → a picker on top. Drafts open the editor; the rest the organizer's screen for Head+
  // (EventManage: money, people, tools), the event sheet for Members.
  import Plus from '@lucide/svelte/icons/plus';
  import ScanLine from '@lucide/svelte/icons/scan-line';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Pencil from '@lucide/svelte/icons/pencil';
  import { api, type EventCard, type Id, type Round } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { ui, say } from '../../lib/state/ui.svelte';
  import { haptic } from '../../lib/tg';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import { data, loadStudio } from '../../lib/state/data.svelte';
  import { tick, untrack } from 'svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn, placeOf } from '../../lib/i18n/index.svelte';
  import { relDay, time, nowTs, dayNo } from '../../lib/time';
  import { may, byRank, roleName } from '../../lib/perms';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Poster from '../../ui/Poster.svelte';
  import EventRow from '../../ui/EventRow.svelte';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import ReceiptIcon from '@lucide/svelte/icons/receipt';
  import HandHeart from '@lucide/svelte/icons/hand-heart';
  import Mail from '@lucide/svelte/icons/mail';
  import Button from '../../ui/Button.svelte';
  import LinkIcon from '@lucide/svelte/icons/link';
  import Crown from '@lucide/svelte/icons/crown';
  import { shareInvite } from '../../lib/invite';
  import { termJustStarted } from '../../lib/academic';

  const mine = $derived([...(session.me?.memberships ?? [])].sort(byRank));
  const m = $derived(mine.find((x) => x.org.id === ui.club) ?? mine[0]);
  const staff = $derived(may(m, 'events'));
  const vice = $derived(may(m, 'team'));  // applications
  const casting = $derived(may(m, 'casting'));  // recruitment rounds (PLAN "Casting")
  let round = $state<Round | null>(null);
  const refreshRound = () => { const o = m?.org.id; if (o && casting) api.round(o).then((x) => { if (m?.org.id === o) round = x; }).catch(() => {}); else round = null; };
  $effect(() => { void data.rev; void m?.org.id; void casting; refreshRound(); });

  // Vice+: the applications row (§4.5) — how many wait, or whether the club takes them
  let waiting = $state(0);
  $effect(() => {
    const org = m?.org.id;
    void data.rev;
    if (org && vice) api.joinRequests(org).then((l) => { if (m?.org.id === org) waiting = l.length; }).catch(() => {});
    else waiting = 0;
  });
  const recruiting = $derived(data.orgs.find((x) => x.id === m?.org.id)?.recruiting ?? true);

  // kept per club and loaded with the app (the club in view), so Studio opens full; a visit or a change refreshes it
  const events = $derived((m && data.studio[m.org.id]) || []);
  function refresh() { if (m) void loadStudio(m.org.id); }
  $effect(() => { void data.rev; if (m) void untrack(() => loadStudio(m.org.id)); });

  const over = (e: EventCard) => (e.endsAt ?? e.startsAt + 3 * 3600) <= nowTs();
  const upcoming = $derived(events.filter((e) => e.status !== 'draft' && !over(e)));
  const drafts = $derived(events.filter((e) => e.status === 'draft'));
  const past = $derived(events.filter((e) => e.status !== 'draft' && over(e)).reverse());
  const next = $derived(upcoming.find((e) => e.status === 'published'));
  const today = $derived(!!next && dayNo(next.startsAt) === dayNo(nowTs()));
  // "Change room" on the day (rooms change on the spot): a KBTU room in one tap; who's coming hears it by the rules
  let room = $state<string | null>(null);
  let roomEl = $state<HTMLInputElement>();
  async function startMove() { room = ''; await tick(); roomEl?.focus(); }
  async function move() {
    if (!next || !room?.trim()) return;
    try { await api.changePlace(next.id, room.trim()); room = null; haptic.ok(); say(t('studio.moved'), 'sparkles_3d'); refresh(); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }

  let seg = $state(0);
  const segs = $derived(staff ? [[t('studio.upcoming'), upcoming], [t('studio.drafts'), drafts], [t('studio.past'), past]] as const : [[t('studio.upcoming'), upcoming], [t('studio.past'), past]] as const);
  const list = $derived(segs[Math.min(seg, segs.length - 1)][1]);

  // questions under our events that wait for the club's answer (Head+ see the count), the soonest first
  const asking = $derived(events.filter((e) => (e.questions ?? 0) > 0 && e.status === 'published' && !over(e)));
  const openRow = (e: EventCard) => (e.status === 'draft' ? sheets.editor(e.org.id, e.id) : staff ? sheets.manage(e.id) : sheets.event(e.id));
  const checking = $derived(events.filter((e) => (e.toCheck ?? 0) > 0));
  const volunteering = $derived(events.filter((e) => (e.volunteersAsked ?? 0) > 0 && !over(e))); // volunteers waiting for an answer
  // the week the coming Wednesday's memo to DMP covers (from Thursday on, the week after next; as the server's _next_week)
  const dayNow = $derived(dayNo(nowTs()));
  const nextWeek = $derived.by(() => { const mon = dayNow + (((2 - ((dayNow + 3) % 7)) % 7) + 7) % 7 + 5; return events.filter((e) => e.status !== 'cancelled' && dayNo(e.startsAt) >= mon && dayNo(e.startsAt) < mon + 7).length; });
  const wednesday = $derived((dayNow + 3) % 7 === 2 && (nowTs() + 5 * 3600) % 86400 < 18 * 3600);
  const memoDue = $derived(may(m, 'memo') && nextWeek > 0 && ((dayNow + 3) % 7 === 1 || wednesday));
  const fresh = $derived(waiting + (round?.counts?.new ?? 0));
  const askRecruit = $derived(vice && !recruiting && !round && termJustStarted());
  const todo = $derived(fresh > 0 || memoDue || askRecruit || asking.length > 0 || checking.length > 0 || volunteering.length > 0);
  const openRecruit = () => (vice ? sheets.joinInbox(m!.org.id) : round ? sheets.roundBoard(m!.org.id) : sheets.roundSetup(m!.org.id, null, refreshRound));
</script>

<div class="page scroll">
  {#if m}
    <header class="hd">
      {#if mine.length > 1}
        <div class="orgs">
          {#each mine as x (x.org.id)}
            <button class:on={x.org.id === m.org.id} onclick={() => { ui.club = x.org.id; seg = 0; }}><OrgLogo org={x.org} size={22} /><span class="ellipsis">{x.org.name}</span></button>
          {/each}
        </div>
      {/if}
      <h1 class="t-h1 ellipsis">{m.org.name}</h1>
      <p class="t-foot role">{#if m.role === 'president'}<Crown size={14} strokeWidth={2.6} />{/if}{roleName(m.role, m.title)}</p>
    </header>

    {#if todo}
      <h2 class="t-cap cap">{t('studio.todo')}</h2>
      <div class="todo surface">
        {#if fresh}
          <button onclick={openRecruit}><UserPlus size={20} /><span class="tx"><b class="ellipsis">{t('studio.todoApps')}</b></span><b class="count">{fresh}</b><ChevronRight size={18} /></button>
        {/if}
        {#if memoDue}
          <button onclick={() => sheets.memo(m.org.id)}><Mail size={20} /><span class="tx"><b class="ellipsis">{t('studio.todoMemo')}</b><i class="t-foot ellipsis">{t('studio.todoMemoBy', { n: nextWeek })}</i></span><ChevronRight size={18} /></button>
        {/if}
        {#if askRecruit}
          <button onclick={openRecruit}><UserPlus size={20} /><span class="tx"><b class="ellipsis">{t('studio.todoRecruit')}</b><i class="t-foot ellipsis">{t('studio.todoRecruitHint')}</i></span><ChevronRight size={18} /></button>
        {/if}
        {#each asking as e (e.id)}
          <button onclick={() => sheets.comments('event', e.id, e.title, () => void refresh())}><MessageCircle size={20} /><span class="tx"><b class="ellipsis">{e.title}</b><i class="t-foot ellipsis">{t('studio.questions')}</i></span><b class="count">{e.questions}</b><ChevronRight size={18} /></button>
        {/each}
        {#each checking as e (e.id)}
          <button onclick={() => sheets.attendees(e.id)}><ReceiptIcon size={20} /><span class="tx"><b class="ellipsis">{e.title}</b><i class="t-foot ellipsis">{t('studio.toCheck')}</i></span><b class="count warn">{e.toCheck}</b><ChevronRight size={18} /></button>
        {/each}
        {#each volunteering as e (e.id)}
          <button onclick={() => sheets.volunteers(e.id, e.needsVolunteers ?? 0)}><HandHeart size={20} /><span class="tx"><b class="ellipsis">{e.title}</b><i class="t-foot ellipsis">{t('studio.todoVol')}</i></span><b class="count">{e.volunteersAsked}</b><ChevronRight size={18} /></button>
        {/each}
      </div>
    {/if}

    <h2 class="t-cap cap">{t('studio.next')}</h2>
    {#if next}
      <article class="hero surface">
        <button class="top" onclick={() => openRow(next)}>
          <Poster item={next} size={60} radius={16} />
          <span class="txt">
            <span class="t-foot when" class:now={today}>{relDay(next.startsAt)}, {time(next.startsAt)} · {placeOf(next.place)}</span>
            <b class="t-title clamp-2">{next.title}</b>
            <span class="t-foot">{tn('event.going', next.taken)}{next.seats ? ' / ' + next.seats : ''}</span>
          </span>
        </button>
        <div class="acts">
          <Button kind={today ? 'primary' : 'secondary'} size="m" full onclick={() => sheets.scanner(next.id)}>{#snippet icon()}<ScanLine size={18} />{/snippet}{t('studio.scanner')}</Button>
          {#if staff}<Button kind="secondary" size="m" full onclick={() => sheets.attendees(next.id)}>{#snippet icon()}<UsersRound size={18} />{/snippet}{t('studio.attendees')}</Button>{/if}
        </div>
        {#if staff && today && !next.placeUrl}
          {#if room === null}
            <button class="move" onclick={startMove}><MapPin size={16} />{t('studio.move')}</button>
          {:else}
            <div class="moving">
              <label class="field"><span class="t-cap">{t('studio.newRoom')}</span>
                <input bind:this={roomEl} bind:value={room} maxlength="80" placeholder={next.place || '305'} enterkeyhint="done" onkeydown={(e) => e.key === 'Enter' && move()} /></label>
              <Button kind="primary" size="m" disabled={!room.trim()} onclick={move}>{t('common.save')}</Button>
            </div>
          {/if}
        {/if}
      </article>
    {:else}
      <p class="hero surface none t-callout">{t('studio.none')}</p>
    {/if}

    {#if staff}
      <button class="add" onclick={() => sheets.editor(m.org.id)}><Plus size={20} />{t('studio.new')}</button>
    {/if}

    <!-- small actions, each a few times a term; recruitment only while it runs (closed: a "To do" at a term's start) -->
    {#if may(m, 'memo') || vice || casting}
      <div class="chips">
        {#if may(m, 'memo')}<button onclick={() => sheets.memo(m.org.id)}><Mail size={17} />{t('memo.card')}</button>{/if}
        {#if (vice && recruiting) || (casting && round)}<button onclick={openRecruit}><UserPlus size={17} />{t('cast.card')}</button>{/if}
        {#if vice}<button onclick={() => shareInvite(m.org)}><LinkIcon size={17} />{t('studio.invite')}</button>{/if}
        {#if vice}<button onclick={() => sheets.clubEdit(m.org.id)}><Pencil size={17} />{t('ce.title')}</button>{/if}
      </div>
    {/if}

    <div class="seg" role="tablist">
      {#each segs as [label, l], i (label)}
        <button class:on={i === Math.min(seg, segs.length - 1)} onclick={() => (seg = i)}>{label}{l.length ? ' · ' + l.length : ''}</button>
      {/each}
    </div>
    <div class="list">
      {#each list as e (e.id)}<EventRow {e} showDate dateLine={relDay(e.startsAt)} onopen={() => openRow(e)} />
      {:else}<p class="t-foot empty">{t('studio.empty')}</p>{/each}
    </div>
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: calc(var(--top) + 56px) var(--gutter) 0; background: var(--glow), var(--bg); }
  .hd { margin-bottom: 18px; }
  .hd p { margin-top: 2px; }
  .role { display: flex; align-items: center; gap: 5px; }
  .role :global(svg) { color: #FFB23D; }
  .orgs { display: flex; gap: 6px; margin-bottom: 12px; overflow-x: auto; scrollbar-width: none; }
  .orgs button { display: inline-flex; align-items: center; gap: 7px; max-width: 200px; height: 34px; padding: 0 12px 0 6px; flex: none;
    border-radius: var(--r-full); background: var(--surface); color: var(--text-2); font: 620 13px/1 var(--font-text); }
  .orgs button.on { background: var(--text); color: var(--bg); }
  .todo { display: flex; flex-direction: column; margin-bottom: 18px; padding: 4px 0; }
  .todo button { display: flex; align-items: center; gap: 12px; width: 100%; min-height: 56px; padding: 8px 12px 8px 14px; text-align: left; color: var(--text-3); }
  .todo button + button { border-top: 0.5px solid var(--line); }
  .todo button:active { background: var(--surface-2); }
  .todo button > :global(svg:first-child) { flex: none; color: var(--accent-text); }
  .todo .tx { flex: 1; display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .todo .tx b { color: var(--text); font: 620 15px/1.2 var(--font-text); }
  .chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 14px; }
  .chips button { display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px 0 11px; border-radius: var(--r-full);
    background: var(--surface); color: var(--text); font: 620 14px/1 var(--font-text); transition: transform var(--t-fast) var(--ease); }
  .chips button > :global(svg) { color: var(--accent-text); }
  .chips button:active { transform: scale(0.95); }
  .count.warn { background: var(--warning-text); color: var(--bg); }
  .count { min-width: 24px; height: 24px; padding: 0 7px; border-radius: 12px; background: var(--accent); color: var(--on-accent); font: 700 13px/24px var(--font-text); text-align: center; }
  .cap { margin: 0 2px 8px; }
  .hero { display: flex; flex-direction: column; gap: 12px; padding: 12px; }
  .top { display: flex; gap: 12px; align-items: center; text-align: left; width: 100%; }
  .txt { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .when { font-weight: 620; }
  .when.now { color: var(--success-text); }
  .acts { display: flex; gap: 8px; }
  .move { display: flex; align-items: center; justify-content: center; gap: 6px; width: 100%; margin-top: 10px; padding: 6px; font: 620 14px/1 var(--font-text); color: var(--accent-text); }
  .moving { display: flex; align-items: flex-end; gap: 8px; margin-top: 10px; }
  .moving .field { flex: 1; min-width: 0; }
  .acts :global(.btn.full) { flex: 1; width: auto; min-width: 0; }
  .none { padding: 18px 16px; color: var(--text-2); }
  .add { display: flex; align-items: center; justify-content: center; gap: 8px; width: 100%; height: var(--btn-l); margin-top: 10px;
    border-radius: 16px; border: 1.5px dashed var(--line-2); color: var(--accent-text); font: 650 15px/1 var(--font-text); }
  .add:active { transform: scale(0.98); }
  .seg { margin: 18px 0 12px; }
  .list { display: flex; flex-direction: column; gap: 8px; }
  .empty { padding: 16px 4px; }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
