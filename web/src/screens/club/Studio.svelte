<script lang="ts">
  // Tab 2 → Studio (Head+) or Club (Member): "To do" on top only when something waits (new applications, the memo on
  // Tue-Wed, recruitment at a term's start, questions, receipts to check), the club's next event with the door
  // scanner and "New event", a row of small actions (memo, recruitment, invite, club profile), its events by state
  // (owner, Oct 15). Several clubs → a picker on top. Drafts open the editor; the rest the organizer's screen for Head+
  // (EventManage: money, people, tools), the event sheet for Members. Look of mockup v24 (owner, Oct 21): the club's
  // mark by its name, the next event with how full it is, the actions as tiles. "Link a channel" waits for its backend.
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
  const members = $derived(data.orgs.find((x) => x.id === m?.org.id)?.members ?? 0);

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
  // the club's creator alone in it, often not its President (owner, Oct 17): invite them, then hand it over in Team
  const alone = $derived(m?.role === 'president' && (data.orgs.find((x) => x.id === m.org.id)?.members ?? 2) <= 1);
  const todo = $derived(alone || fresh > 0 || memoDue || askRecruit || asking.length > 0 || checking.length > 0 || volunteering.length > 0);
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
      <div class="title">
        <OrgLogo org={m.org} size={46} />
        <span class="name"><h1 class="ellipsis">{m.org.name}</h1>
          <p class="t-foot role">{#if m.role === 'president'}<Crown size={14} strokeWidth={2.6} />{/if}{roleName(m.role, m.title)}{members ? ' · ' + tn('studio.members', members) : ''}</p></span>
        <!-- the club's page, edited from up here (owner, Oct 17: the row of buttons below said nothing) -->
        {#if vice}<button class="ic" onclick={() => { haptic.tap(); sheets.clubEdit(m.org.id); }} aria-label={t('ce.title')}><Pencil size={19} /></button>{/if}
      </div>
    </header>

    {#if todo}
      <h2 class="sec">{t('studio.todo')}</h2>
      <div class="todo surface">
        {#if alone}
          <button onclick={() => shareInvite(m.org)}><Crown size={20} /><span class="tx"><b class="ellipsis">{t('studio.todoPres')}</b><i class="t-foot">{t('studio.todoPresHint')}</i></span><ChevronRight size={18} /></button>
        {/if}
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

    <h2 class="sec">{t('studio.next')}</h2>
    {#if next}
      <article class="hero surface">
        <button class="top" onclick={() => openRow(next)}>
          <Poster item={next} size={60} radius={16} />
          <span class="txt">
            <span class="t-foot when" class:now={today}>{relDay(next.startsAt)}, {time(next.startsAt)} · {placeOf(next.place)}</span>
            <b class="t-title clamp-2">{next.title}</b>
          </span>
        </button>
        <!-- how full it is -->
        <div class="seats"><span class="t-foot"><b class="num">{tn('event.going', next.taken)}</b>{next.seats ? ' / ' + next.seats : ''}</span>
          {#if next.seats}<span class="bar"><i style="width:{Math.min(100, (next.taken / next.seats) * 100)}%"></i></span>{/if}</div>
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

    <!-- the actions as tiles (mockup v24): a new event, recruitment while it runs (closed: a "To do" at a term's start),
         the memo to DMP; inviting lives on Team, editing the club up top (owner, Oct 17) -->
    {#if staff || may(m, 'memo') || (vice && recruiting) || (casting && round)}
      <div class="qa">
        {#if staff}<button class="qt surface" onclick={() => { haptic.tap(); sheets.editor(m.org.id); }}><Plus size={22} /><b>{t('studio.newShort')}</b><small>{t('studio.newSub')}</small></button>{/if}
        {#if (vice && recruiting) || (casting && round)}<button class="qt surface" onclick={() => { haptic.tap(); openRecruit(); }}><UserPlus size={22} /><b>{t('cast.card')}</b><small>{fresh ? tn('studio.newApps', fresh) : t('studio.recruitOpen')}</small>{#if fresh}<i class="qd num">{fresh}</i>{/if}</button>{/if}
        {#if may(m, 'memo')}<button class="qt surface" onclick={() => { haptic.tap(); sheets.memo(m.org.id); }}><Mail size={22} /><b>{t('studio.memoShort')}</b><small>{t('studio.memoSub')}</small></button>{/if}
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
  .title { display: flex; align-items: center; gap: 12px; }
  .name { flex: 1; min-width: 0; }
  .name h1 { font: 800 var(--fs-sec)/1.15 var(--font-display); letter-spacing: -0.025em; }
  .ic { width: 38px; height: 38px; flex: none; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent-text);
    transition: transform var(--t-fast) var(--ease), box-shadow var(--t-fast) var(--ease); }
  /* a press glows (owner, Oct 17: a tap must show it was seen) */
  .ic:active { transform: scale(0.92); box-shadow: 0 0 0 4px var(--accent-soft), 0 0 22px rgba(59, 107, 255, 0.55); }
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
  .qa { display: grid; grid-template-columns: repeat(auto-fit, minmax(96px, 1fr)); gap: 10px; margin-top: 12px; }
  .qt { position: relative; display: flex; flex-direction: column; align-items: flex-start; gap: 2px; padding: 14px; border-radius: var(--r-l); text-align: left; color: var(--accent-text); }
  .qt:active { transform: scale(0.97); }
  .qt b { margin-top: 10px; font: 680 var(--fs-body)/1.2 var(--font-text); color: var(--text); }
  .qt small { font: 500 var(--fs-cap)/1.25 var(--font-text); color: var(--text-3); }
  .qd { position: absolute; top: 12px; right: 12px; min-width: 22px; height: 22px; padding: 0 6px; border-radius: 11px; background: var(--danger); color: #fff; font: 700 12px/22px var(--font-text); font-style: normal; text-align: center; }
  .sec { margin: 26px 4px 12px; font: 760 var(--fs-sec)/1.1 var(--font-display); letter-spacing: -0.025em; }
  .seats { display: flex; flex-direction: column; gap: 6px; }
  .seats b { color: var(--text); font-weight: 650; }
  .bar { height: 6px; border-radius: 3px; background: var(--surface-3); overflow: hidden; }
  .bar i { display: block; height: 100%; border-radius: inherit; background: linear-gradient(90deg, var(--accent), var(--accent-2)); }
  .count.warn { background: var(--warning-text); color: var(--bg); }
  .count { min-width: 24px; height: 24px; padding: 0 7px; border-radius: 12px; background: var(--accent); color: var(--on-accent); font: 700 13px/24px var(--font-text); text-align: center; }
  .hero { display: flex; flex-direction: column; gap: 12px; padding: 14px; border-radius: var(--r-l); }
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
  .seg { margin: 18px 0 12px; }
  .list { display: flex; flex-direction: column; gap: 8px; }
  .empty { padding: 16px 4px; }
  .tail { height: calc(var(--bottom) + 24px); }
</style>
