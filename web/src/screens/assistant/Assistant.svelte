<script lang="ts">
  // The students' assistant (server logic/assistant.py; owner, Oct 30: "where is my dean's office?" and the app knows
  // the school, the year, the timetable, the campus, what's on). A chat: suggestions to start, the answer with up to
  // three buttons (a room or the whole map, an event, a club, my classes, a Settings page, the Gallery, the news, a tab,
  // my tickets, friends, awards, the subjects, a new forum post, my club's Studio or a new event there), checked by the
  // server against what it told the model; a button only opens a screen. The bar's corner opens it (Nav), so the map,
  // which was there, is the round button beside the field. Under an answer 👍/👎 (on 👎, the student may send that one question
  // and answer); when the server sees distress, its fixed help card with the helplines (review, Oct 31: nothing of
  // it is kept or sent by us; the student calls or writes themselves). When KRI didn't know, "Ask a person" (ASK): the
  // help desk's composer with the question in it, sent only on the student's tap.
  import { untrack } from 'svelte';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import Navigation from '@lucide/svelte/icons/navigation';
  import { addressGis } from '../../lib/map';
  import MapIcon from '@lucide/svelte/icons/map';
  import Ticket from '@lucide/svelte/icons/ticket';
  import UserRound from '@lucide/svelte/icons/user-round';
  import Trophy from '@lucide/svelte/icons/trophy';
  import BookOpen from '@lucide/svelte/icons/book-open';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import LayoutDashboard from '@lucide/svelte/icons/layout-dashboard';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import { TAB_ICON } from '../../ui/icons';
  import CalendarDays from '@lucide/svelte/icons/calendar-days';
  import Users from '@lucide/svelte/icons/users';
  import CalendarClock from '@lucide/svelte/icons/calendar-clock';
  import Settings from '@lucide/svelte/icons/settings';
  import Images from '@lucide/svelte/icons/images';
  import Newspaper from '@lucide/svelte/icons/newspaper';
  import MessageCircleQuestion from '@lucide/svelte/icons/message-circle-question-mark';
  import ThumbsUp from '@lucide/svelte/icons/thumbs-up';
  import ThumbsDown from '@lucide/svelte/icons/thumbs-down';
  import Phone from '@lucide/svelte/icons/phone';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import HeartHandshake from '@lucide/svelte/icons/heart-handshake';
  import { api, ApiErr } from '../../lib/api';
  import { say, close, goTab, overlays, toTickets, type Overlay, type Tab } from '../../lib/state/ui.svelte';
  import { sheets, openMapFrom, takeIris } from '../../lib/state/sheets';
  import { data, eventById } from '../../lib/state/data.svelte';
  import { chat, fresh, type AskCtx, type Turn } from '../../lib/state/assistant.svelte';
  import { session, asStudent } from '../../lib/state/session.svelte';
  import type { AssistAction } from '../../lib/api/types';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { PSYCHOLOGIST } from '../../lib/academic';
  import Sheet from '../../ui/Sheet.svelte';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import Landmark from '@lucide/svelte/icons/landmark';
  import UtensilsCrossed from '@lucide/svelte/icons/utensils-crossed';
  import Backpack from '@lucide/svelte/icons/backpack';
  import UserPlus from '@lucide/svelte/icons/user-plus';
  import Info from '@lucide/svelte/icons/info';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Composer from '../../ui/Composer.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';

  // ctx: opened from a card's "Ask AI" (an event, a club); another card, or none, starts a fresh conversation
  let { overlay, ctx, focus = false, keyboard, opener }: { overlay: Overlay; ctx?: AskCtx; focus?: boolean; keyboard?: HTMLInputElement | null; opener?: HTMLElement | null } = $props();
  // focus (a fresh one): the keyboard comes up with it, App's stand-in held it from the tap; a conversation to read: down
  untrack(() => { if (fresh(ctx)) { chat.turns = []; chat.ctx = ctx ?? null; } });
  const first = $derived((session.me?.student?.firstName || session.me?.tg.firstName || '').trim());
  let draft = $state(untrack(() => keyboard?.value ?? '')), busy = $state(false);
  let list = $state<HTMLDivElement>();
  // the starters: plain rows, each with its own icon (a list, not a pile of pills)
  const SUGGEST = $derived(chat.ctx?.kind === 'event' ? [['as.e1', Backpack], ['as.e2', Navigation], ['as.e3', Users]] as const
    : chat.ctx?.kind === 'club' ? [['as.c1', UserPlus], ['as.c2', Info]] as const
    : [['as.s1', Landmark], ['as.s2', CalendarClock], ['as.s3', CalendarDays], ['as.s4', UtensilsCrossed]] as const);
  const down = () => setTimeout(() => list?.lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' }), 30);
  $effect(() => { void chat.turns.length; untrack(down); });

  async function ask(q: string) {
    q = q.trim();
    if (!q || busy) return;
    const history = chat.turns.filter((m) => m.text).slice(-6).map(({ role, text }) => ({ role, text }));
    chat.turns.push({ role: 'user', text: q });
    draft = ''; busy = true;
    try {
      const a = await api.assistant(q, history, chat.ctx ? { kind: chat.ctx.kind, id: chat.ctx.id } : undefined);
      chat.turns.push({ role: 'assistant', ...a, q });
      haptic.soft();
    } catch (e) {
      const why = e instanceof ApiErr ? e.code : '';
      chat.turns.push({ role: 'assistant', text: t(why === 'rate_limited' ? 'as.limit' : why === 'unavailable' ? 'as.busy' : why === 'forbidden' ? 'as.consent' : 'common.error') });
      haptic.error();
      if (why === 'forbidden') sheets.consent(); // the new policy first: here it is
    } finally { busy = false; }
  }
  // labels from our own strings and store, never the model's words
  const SET = { school: 'look.school', course: 'pd.course', notify: 'me.notifications' } as const;
  const mine = (id: number) => session.me?.memberships.find((m) => m.org.id === id)?.org.name ?? t('as.club');
  const PLAIN = { timetable: 'list.classes', gallery: 'gallery.title', ask: 'ask.button', news: 'page.news', afisha: 'tab.afisha', forum: 'tab.forum',
    clubs: 'page.clubs', profile: 'tab.profile', tickets: 'as.tickets', friends: 'page.friends', awards: 'page.awards', subjects: 'sj.title', post: 'as.post' } as const;
  const label = (a: AssistAction) => a.type === 'map' ? (a.room ? t('as.onMap', { room: a.room }) : t('as.map'))
    : a.type === 'event' ? eventById(a.id)?.title ?? t('as.event') : a.type === 'route' ? t('event.route')
    : a.type === 'club' ? [...data.orgs, ...data.small].find((o) => o.id === a.id)?.name ?? t('as.club')
    : a.type === 'studio' ? t('as.studio', { name: mine(a.id) }) : a.type === 'new_event' ? t('as.newEvent', { name: mine(a.id) })
    : a.type === 'settings' ? t(SET[a.kind]) : t(PLAIN[a.type]);
  const ICON = { map: MapPin, event: CalendarDays, club: Users, timetable: CalendarClock, settings: Settings, gallery: Images, news: Newspaper, ask: MessageCircleQuestion,
    afisha: TAB_ICON.afisha, forum: TAB_ICON.forum, clubs: TAB_ICON.club, profile: TAB_ICON.profile, tickets: Ticket, friends: UserRound, awards: Trophy,
    subjects: BookOpen, post: SquarePen, studio: LayoutDashboard, new_event: CalendarPlus, route: Navigation };
  // an off-campus event's way there: its 2GIS link, or 2GIS's search for its typed address (the event page's own rule)
  const gisOf = (id: number) => { const e = eventById(id); return e ? e.placeUrl || addressGis(e.place) : null; };
  const shown = (a: AssistAction) => a.type !== 'route' || !!gisOf(a.id); // no way there: no button
  const iconOf = (a: AssistAction) => a.type === 'map' && !a.room ? MapIcon : ICON[a.type];
  /** a tab: every sheet over the tabs goes (this one and the card it was asked from), the tab shows (the screens below
   *  are the app's own openers) */
  function tab(k: Tab) { for (const o of overlays) close(o.id, false); goTab(k); }
  function go(a: AssistAction, q?: string) {
    if (a.type === 'route') { const u = gisOf(a.id); if (u) openLink(u); }
    else if (a.type === 'map') sheets.map(a.room);
    else if (a.type === 'event') sheets.event(a.id);
    else if (a.type === 'club') sheets.club(a.id);
    else if (a.type === 'settings') sheets.settings(a.kind);
    else if (a.type === 'timetable') sheets.week();
    else if (a.type === 'gallery') sheets.gallery();
    else if (a.type === 'ask') sheets.askHuman(q);
    else if (a.type === 'news') sheets.news();
    else if (a.type === 'afisha') tab('afisha');
    else if (a.type === 'tickets') { tab('afisha'); toTickets.fn?.(); } // Afisha drops its search, its ticket in view (List.svelte)
    else if (a.type === 'forum' || a.type === 'profile') tab(a.type);
    else if (a.type === 'clubs') tab('club');
    else if (a.type === 'friends') sheets.friends();
    else if (a.type === 'awards') sheets.awards();
    else if (a.type === 'subjects') sheets.subjects();
    else if (a.type === 'studio') { tab('club'); sheets.studio(a.id); } // as App's toClub
    else if (a.type === 'new_event') sheets.editor(a.id);
    else { tab('forum'); void write(); }
  }
  // the forum's + (Channel.svelte write): KBTU-confirmed students write, the rest sign in first
  async function write() {
    const { compose } = await import('../forum/ChannelCompose.svelte');
    const me = session.me;
    if (!me?.student) asStudent(() => compose());
    else if (me.student.manual) sheets.login();
    else compose();
  }
  const openMap = openMapFrom;
  // opening with the keyboard: the plain rise. The iris holds the sheet in place while the keyboard resizes it under
  // the circle, and the whole opening stutters on a phone (owner's recording, Nov 17); dropped here before Sheet takes it
  // svelte-ignore state_referenced_locally
  if (focus) takeIris();
  // optimistic: the tap shows at once; a failed call quietly takes it back
  function vote(m: Turn, v: 'up' | 'down') {
    if (m.vote || !m.mark) return;
    m.vote = v;
    api.assistantVote(m.mark, v).catch((e) => { if (!(e instanceof ApiErr && e.code === 'conflict')) m.vote = undefined; }); // conflict: counted already
  }
  function send(m: Turn) {
    if (m.sent || !m.q || !m.mark || !m.pair) return;
    m.sent = true;
    api.assistantSend(m.mark, m.pair, m.q, m.text).catch((e) => {
      m.sent = false; haptic.error();
      say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'as.sendFull' : 'common.error'), 'pleading_face_3d'); // past the day's cap: not kept, said so
    });
  }
</script>

<Sheet {overlay} {opener} icon={Sparkles} tall title={t('as.title')}>
  <div class="list" bind:this={list}>
    {#if !chat.turns.length}
      <!-- as in the AI apps: the greeting and the starters sit over the field, where the thumb is; the space above stays calm -->
      <div class="hello">
        <h2 class="greeting">{t('as.hello', { name: first ? ', ' + first : '' })}</h2>
        <p class="what clamp-2">{chat.ctx ? t('as.about', { title: chat.ctx.title }) : t('as.what')}</p>
      </div>
      <div class="sugg"><Group>{#each SUGGEST as [k, Icon] (k)}
        <Row icon={Icon} title={t(k)} onclick={() => { haptic.tap(); void ask(t(k)); }} />
      {/each}</Group></div>
    {:else if chat.ctx}
      <!-- engine: ui/Tag could truncate a long label with "…" (an event's title); till then this label is local -->
      <p class="ctx"><Sparkles size={13} strokeWidth={2.2} /><span class="ellipsis">{chat.ctx.title}</span></p>
    {/if}
    {#each chat.turns as m, i (i)}
      {#if m.text}
        <div class="b {m.role}">
          <p class="selectable">{m.text}</p>
          {#if m.actions?.length}
            <!-- the answer's buttons as plain rows: › opens a screen here, ↗ leaves the app (2GIS) -->
            <div class="acts"><Group>{#each m.actions.filter(shown) as a, k (k)}
              <Row icon={iconOf(a)} title={label(a)} accessory={a.type === 'route' ? 'external' : 'chevron'} onclick={() => go(a, m.q)} />
            {/each}</Group></div>
          {/if}
        </div>
      {/if}
      {#if m.mark && !m.care}
        <div class="rate">
          <IconButton kind="plain" size="s" icon={ThumbsUp} label={t('as.good')} on={m.vote === 'up'} disabled={!!m.vote} onclick={() => vote(m, 'up')} />
          <IconButton kind="plain" size="s" icon={ThumbsDown} label={t('as.bad')} on={m.vote === 'down'} disabled={!!m.vote} onclick={() => vote(m, 'down')} />
        </div>
        {#if m.vote === 'down'}
          <div class="offer">{#if m.sent}<p>{t('as.sent')}</p>{:else}
            <Button kind="plain" size="s" onclick={() => send(m)}>{t('as.sendQ')}</Button><p>{t('as.sendNote')}</p>{/if}</div>
        {/if}
      {/if}
      {#if m.care && m.help}
        <div class="b assistant help">
          <p class="selectable">{m.help}</p>
          <!-- ponytail: a tel: link; Telegram's openLink takes http(s) only. If a client won't dial, the number is in the text above -->
          <!-- engine: Button href (a link drawn as a primary Button); till then this one link is styled here -->
          <a class="first" href="tel:1303" onclick={() => haptic.tap()}><Phone size={17} />{t('as.call1303')}</a>
          <Group>
            <Row icon={MessageCircle} title={t('as.write150')} accessory="external" onclick={() => openLink('https://wa.me/77081060810')} />
            <Row icon={HeartHandshake} title={t('as.psych')} accessory="external" onclick={() => openLink(PSYCHOLOGIST)} />
          </Group>
        </div>
      {/if}
    {/each}
    {#if busy}<div class="b assistant typing" aria-label={t('as.thinking')}><i></i><i></i><i></i></div>{/if}
  </div>

  {#snippet footer()}
    <div class="bar">
      <!-- the map, one tap away as when it had the bar's corner: beside the field, there with or without a conversation -->
      <button class="mapb" aria-label={t('as.map')} onclick={openMap}><MapIcon size={20} /></button>
      <div class="inp"><Composer bind:value={draft} placeholder={t('as.ph')} maxlength={300} sending={busy} label={t('cm.send')} onsend={() => ask(draft)} pill {focus} /></div>
    </div>
    <p class="note">{t('as.note')}</p>
  {/snippet}
</Sheet>

<style>
  .list { display: flex; flex-direction: column; gap: 14px; min-height: 100%; padding: 6px 0 4px; }
  /* empty: everything sits low, over the field; the space above is the calm */
  .hello { margin-top: auto; padding: 0 var(--s-1) var(--s-1); animation: in 380ms cubic-bezier(.2, .9, .25, 1) backwards; }
  .greeting { font: 700 var(--fs-title)/1.1 var(--font-display); letter-spacing: -0.03em; overflow-wrap: anywhere; text-wrap: balance; }
  .what { margin-top: 6px; font: 600 var(--fs-t3)/1.25 var(--font-display); letter-spacing: -0.016em; color: var(--text-3); overflow-wrap: anywhere; }
  .sugg { animation: in 380ms cubic-bezier(.2, .9, .25, 1) 60ms backwards; }
  .ctx { align-self: center; display: inline-flex; align-items: center; gap: 6px; max-width: 86%; height: 28px; padding: 0 12px; border-radius: var(--r-full);
    background: var(--fill); color: var(--text-2); font: 600 var(--fs-cap)/1 var(--font-text); }
  /* the chat, as in ChatGPT and Claude: my words in a bubble on the right, KRI's plain on the ground (bespoke content: no ui/ part draws a message) */
  .b { max-width: 86%; animation: in 300ms cubic-bezier(.2, .9, .25, 1) backwards; }
  @keyframes in { from { opacity: 0; transform: translateY(8px) scale(0.98); } }
  .b p { font: 450 var(--fs-body)/1.45 var(--font-text); white-space: pre-wrap; overflow-wrap: anywhere; }
  .b.user { align-self: flex-end; padding: 10px 14px; border-radius: var(--r-l); background: var(--fill); }
  .b.assistant { align-self: stretch; max-width: none; padding: 0 var(--s-1); }
  .acts { margin: var(--s-3) calc(-1 * var(--s-1)) 0; }
  .rate { display: flex; gap: 2px; margin: -8px 0 0 -4px; --plain-ink: var(--text-3); }
  .rate :global(.btn[aria-pressed='true']) { color: var(--accent-text); opacity: 1; }
  .offer { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; max-width: 86%; margin: -2px 0 0 0; animation: in 300ms cubic-bezier(.2, .9, .25, 1) backwards; }
  .offer p { padding: 0 var(--s-2); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .b.help { display: flex; flex-direction: column; gap: var(--s-2); padding: 0; }
  .b.help p { padding: 0 var(--s-1) var(--s-1); }
  .first { display: flex; align-items: center; justify-content: center; gap: var(--s-2); height: var(--ctl-m); padding: 0 var(--s-5); border-radius: var(--r-full);
    background: var(--accent); color: var(--on-accent); font: 600 var(--fs-body)/1 var(--font-text); text-decoration: none; }
  .first:active { opacity: 0.8; }
  .typing { display: flex; gap: 5px; padding: 6px var(--s-1); }
  .typing i { width: 7px; height: 7px; border-radius: 50%; background: var(--text-3); animation: dot 1s ease-in-out infinite; }
  .typing i:nth-child(2) { animation-delay: 150ms; } .typing i:nth-child(3) { animation-delay: 300ms; }
  @keyframes dot { 30% { transform: translateY(-4px); opacity: 1; } 0%, 60%, 100% { opacity: 0.4; } }
  .bar { display: flex; align-items: flex-end; gap: var(--s-2); }
  .inp { flex: 1; min-width: 0; }
  /* flat, the field's own ground: a control in the sheet, not floating chrome */
  .mapb { flex: none; display: grid; place-items: center; width: 44px; height: 44px; border-radius: var(--r-full); background: var(--fill); color: var(--text-2);
    transition: transform var(--t-fast); }
  .mapb:active { transform: scale(0.92); }
  .note { margin: var(--s-2) 4px 0; text-align: center; font: 450 var(--fs-cap)/1.3 var(--font-text); color: var(--text-3); }
</style>
