<script module lang="ts">
  // the light on its way back to the button after a close: it outlives its sheet, so the next opening can take it over
  // mid-air (take: where it is now, how much of the colonnade is left in it, and the button's veil to hand on)
  let back: { take: () => { x: number; y: number; r: number; m: number; veil: Animation } } | null = null;
  const FLY = 520, ACROSS = 'cubic-bezier(.4, 0, .2, 1)', ALONG = 'cubic-bezier(.2, .8, .25, 1)';
  const turnOf = (e: Element) => e.getAnimations({ subtree: true }).find((a) => (a.effect as KeyframeEffect | null)?.pseudoElement === '::before');
</script>

<script lang="ts">
  // The students' assistant (server logic/assistant.py: "where is my dean's office?" and the app knows
  // the school, the year, the timetable, the campus, what's on). A chat: suggestions to start, the answer with up to
  // three buttons (a room or the whole map, an event, a club, my classes, a Settings page, the Gallery, the news, a tab,
  // my tickets, friends, awards, the subjects, a new forum post, my club's Studio or a new event there), checked by the
  // server against what it told the model; a button only opens a screen. The bar's corner opens it (Nav), so the map,
  // which was there, is the round button beside the field. Under an answer 👍/👎 (on 👎, the student may send that one question
  // and answer); when the server sees distress, its fixed help card with the helplines (nothing of
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
  import { sheets, openMapFrom, takeIris, peekIris } from '../../lib/state/sheets';
  import { data, eventById } from '../../lib/state/data.svelte';
  import { conversation, rememberConversation, type AskCtx, type Turn } from '../../lib/state/assistant.svelte';
  import ChatMessage from './ChatMessage.svelte';
  import { answer } from '../../lib/answer';
  import { power } from '../../lib/state/power.svelte';
  import RotateCw from '@lucide/svelte/icons/rotate-cw';
  import { session, asStudent } from '../../lib/state/session.svelte';
  import type { AssistAction } from '../../lib/api/types';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { PSYCHOLOGIST } from '../../lib/academic';
  import Sheet from '../../ui/Sheet.svelte';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Composer from '../../ui/Composer.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import { keyboard as kbd } from '../../lib/state/keyboard.svelte';
  import { resting, rest, setKriGoogle } from '../../lib/kriGoogle';

  // ctx: opened from a card's "Ask AI" (an event, a club); another card, or none, starts a fresh conversation
  let { overlay, ctx, focus = false, keyboard, opener }: { overlay: Overlay; ctx?: AskCtx; focus?: boolean; keyboard?: HTMLInputElement | null; opener?: HTMLElement | null } = $props();
  // focus (a fresh one): the keyboard comes up with it, App's stand-in held it from the tap; a conversation to read: down
  const chat = untrack(() => conversation(ctx));
  $effect(() => {
    if (!overlay.closing && !overlays.some((o) => o.id > overlay.id && !o.closing)) rememberConversation(chat);
  });
  let born = $state(untrack(() => chat.turns.length)); // what was said before this opening stands still; only the new comes in
  function retry(i: number) {
    const q = chat.turns[i].q;
    if (!q || busy) return;
    chat.turns.splice(i - 1, 2); born = Math.min(born, i - 1);
    void ask(q, false);
  }
  // KRI is a light, not a sheet with a hello and a list: it leaves the button that was
  // pressed and takes its place in the middle, over the greeting, while the Sheet's circle opens from that same button, waits beside
  // "thinking", and stands over the newest answer only. It flies in the footer (the body clips at the footer's edge) and
  // hands over on landing. Power saving, less motion, a conversation to read: no flight, it is in its place
  // The round button itself turns into the light: its glyph fades into the colonnade on the way up, the button is not
  // seen while the light is out of it. On any close from the empty opening the light goes back the same road,
  // over the leaving sheet, and the next opening tapped meanwhile takes it from where it is
  // svelte-ignore state_referenced_locally
  const btn = !focus && !power.lite ? peekIris() : null; // the button it opened from (Nav): where it goes back to
  const mid = btn && !chat.turns.length ? back?.take() : null;
  const from = !chat.turns.length ? mid ?? btn : null;
  let veil = !from ? null : btn?.el?.animate({ opacity: mid ? [0, 0] : [1, 0] }, { duration: 120, fill: 'forwards' }) ?? null;
  mid?.veil.cancel();
  $effect(() => () => veil?.cancel()); // gone without a flight back: the button is itself again
  let orb = $state<HTMLElement>(), fly = $state<HTMLElement>(), flying = $state(!!from);
  $effect(() => {
    const o = orb, f = fly;
    if (!from || !o || !f) return;
    // after the layout, before the paint: no layout forced inside the tap
    const ro = new ResizeObserver(() => {
      ro.disconnect();
      // (from the footer's padding edge, inside its top line: counted from the border, the light landed 1 px low)
      const b = o.getBoundingClientRect(), par = f.offsetParent as HTMLElement, p = par.getBoundingClientRect();
      f.style.cssText = `left:${b.left - p.left - par.clientLeft}px;top:${b.top - p.top - par.clientTop}px;width:${b.width}px;height:${b.height}px;visibility:visible`;
      const dx = from.x - b.left - b.width / 2, dy = from.y - b.top - b.height / 2, m = mid?.m ?? 0;
      // across and up on two curves: an arc, not a ruler's line
      f.animate({ translate: [`${dx}px 0`, '0 0'] }, { duration: FLY, easing: ACROSS });
      f.animate({ transform: [`translateY(${dy}px) scale(${(from.r * 2) / b.width})`, 'none'] }, { duration: FLY, easing: ALONG })
        .finished.catch(() => {}).finally(() => (flying = false));
      if (!mid) f.animate({ opacity: [0, 1] }, { duration: 90 }); // over the button as that fades: no pop
      f.querySelector('.mark')!.animate({ opacity: [m, 1] }, { duration: FLY * 0.45 });
      f.querySelector('.glyph')!.animate({ opacity: [1 - m, 0] }, { duration: FLY * 0.45, fill: 'forwards' });
    });
    ro.observe(o);
    return () => ro.disconnect();
  });
  // The way back. A copy of the light on the page itself (the sheet clips its own and goes), from where the light is
  // now (at rest, moved by the keyboard, or still flying in) to the button: transform and opacity only, the colonnade
  // fading back into the button's glyph, the button showing through at the end. Not from a conversation (its small
  // light is over an answer, often scrolled away: the sheet's own circle closes into the button as before), not with
  // less motion or power saving. After Sheet's own look at the close (typed text may ask first): a microtask
  let gone = false;
  $effect(() => { if (overlay.closing) queueMicrotask(() => { if (overlay.closing && !gone) { gone = true; goBack(); } }); });
  function goBack() {
    const src = flying ? fly : orb;
    if (!btn?.el || !src || !orb || tight || getComputedStyle(src).visibility === 'hidden' && src === fly || matchMedia('(prefers-reduced-motion: reduce)').matches) { veil?.cancel(); veil = null; return; }
    const b = src.getBoundingClientRect(), w = orb.offsetWidth, el = orb.cloneNode(true) as HTMLElement;
    const mark = el.querySelector<HTMLElement>('.mark')!, glyph = el.querySelector<HTMLElement>('.glyph')!;
    const m = Number(getComputedStyle(src.querySelector('.mark')!).opacity), at = turnOf(src)?.currentTime;
    el.classList.remove('hid', 'land');
    el.style.cssText = `position:fixed;left:${b.left + b.width / 2 - w / 2}px;top:${b.top + b.height / 2 - w / 2}px;margin:0;z-index:calc(var(--z-sheet) + 4);pointer-events:none;visibility:visible`;
    orb.style.visibility = 'hidden'; if (fly) fly.style.visibility = 'hidden'; // one light on the screen
    document.body.append(el);
    const spin = turnOf(el); if (spin && at != null) spin.currentTime = at; // its colours where they were, not from the start
    const dx = btn.x - b.left - b.width / 2, dy = btn.y - b.top - b.height / 2;
    el.animate({ translate: ['0 0', `${dx}px 0`] }, { duration: FLY, easing: ACROSS, fill: 'forwards' });
    const a = el.animate({ transform: [`scale(${b.width / w})`, `translateY(${dy}px) scale(${(btn.r * 2) / w})`] }, { duration: FLY, easing: ALONG, fill: 'forwards' });
    el.animate({ opacity: [1, 1, 0], offset: [0, 0.72, 1] }, { duration: FLY, fill: 'forwards' });
    mark.animate({ opacity: [m, 0] }, { duration: FLY * 0.45, fill: 'forwards' });
    glyph.animate({ opacity: [1 - m, 1] }, { duration: FLY * 0.45, fill: 'forwards' });
    // the button comes through as the light fades over it; this veil takes over from the opening's
    const show = btn.el.animate({ opacity: [0, 0, 1], offset: [0, 0.72, 1] }, { duration: FLY });
    veil?.cancel(); veil = null;
    const me = (back = { take: () => {
      const r = el.getBoundingClientRect(), left = Number(getComputedStyle(mark).opacity);
      el.remove(); back = null;
      return { x: r.left + r.width / 2, y: r.top + r.height / 2, r: r.width / 2, m: left, veil: show };
    } });
    void a.finished.catch(() => {}).finally(() => { el.remove(); if (back === me) back = null; });
  }
  const first = $derived((session.me?.student?.firstName || session.me?.tg.firstName || '').trim());
  let draft = $state(untrack(() => keyboard?.value ?? ''));
  const busy = $derived(chat.busy);
  let list = $state<HTMLDivElement>();
  // The opening (as Gemini opens): the light in the middle
  // with the colonnade in it, the greeting, one starter under it that keeps changing, all of them low over the field
  const SUGGEST = $derived(chat.ctx?.kind === 'event' ? ['as.e1', 'as.e2', 'as.e3'] as const
    : chat.ctx?.kind === 'club' ? ['as.c1', 'as.c2'] as const : ['as.s1', 'as.s2', 'as.s3', 'as.s4'] as const);
  let qi = $state(0); // the question on show
  $effect(() => {
    // power saving, less motion: the first question stays; a hidden tab: it waits
    if (chat.turns.length || power.lite || matchMedia('(prefers-reduced-motion: reduce)').matches) return;
    const n = SUGGEST.length, id = setInterval(() => { if (!document.hidden) qi = (qi + 1) % n; }, 3600);
    return () => clearInterval(id);
  });
  const pick = (k: (typeof SUGGEST)[number]) => { haptic.tap(); void ask(t(k)); };
  // Gemini's card (lib/kriGoogle.ts): one quiet question on the empty opening of a student who hasn't answered. It
  // shares the starters' cell over the field (the taller sets its height for this opening), so going moves nothing:
  // the starters come up where it was. "Turn on": the yes at once; "Not now": rests 30 days on this phone
  const offer = untrack(() => session.me?.kriGoogle === false && !resting());
  let later = $state(false);
  const asking = $derived(offer && session.me?.kriGoogle === false && !later);
  function gemini(on: boolean) {
    if (on) void setKriGoogle(true);
    else { haptic.tap(); rest(); later = true; }
  }
  // The keyboard: Sheet raises the footer over the body and the body stays as it is, so the middle moves itself to the
  // middle of what is left in view (a transform on the keyboard's timing, no layout), smaller; no room for it: it fades.
  // Not under a light still flying to its place: it lands first, then goes up
  const kb = $derived(flying ? 0 : kbd.h);
  // (room for what the middle holds at its smaller size and 8 px over and under it; layout sizes, not the moved box's)
  const tight = $derived.by(() => {
    const last = orb?.parentElement?.lastElementChild as HTMLElement | null;
    return kb > 0 && !!orb && !!last && (list?.clientHeight ?? 0) - kb < 0.8 * (last.offsetTop + last.offsetHeight - orb.offsetTop) + 16;
  });
  const down = () => setTimeout(() => list?.lastElementChild?.scrollIntoView({ block: 'end', behavior: 'smooth' }), 30);
  $effect(() => { void chat.turns.length; untrack(down); });

  // the newest answer, the light's place while nothing is on its way (thinking: it is beside the word)
  const top = $derived.by(() => { if (busy) return -1; for (let i = chat.turns.length - 1; i >= 0; i--) if (chat.turns[i].role === 'assistant') return i; return -1; });
  let left = $state(-1); // the answer the light has just left: it closes the gap in a glide, not a jump
  async function ask(q: string, glide = true) {
    q = q.trim();
    if (!q || busy) return;
    left = glide ? top : -1;
    const history = chat.turns.filter((m) => m.text).slice(-6).map(({ role, text }) => ({ role, text }));
    chat.turns.push({ role: 'user', text: q });
    draft = ''; chat.busy = true;
    try {
      const a = await api.assistant(q, history, chat.ctx ? { kind: chat.ctx.kind, id: chat.ctx.id } : undefined);
      chat.turns.push({ role: 'assistant', ...a, q });
      haptic.soft();
    } catch (e) {
      const why = e instanceof ApiErr ? e.code : '';
      chat.turns.push({ role: 'assistant', text: t(why === 'rate_limited' ? 'as.limit' : why === 'unavailable' ? 'as.busy' : why === 'forbidden' ? 'as.consent' : 'common.error'),
        q, err: why !== 'rate_limited' && why !== 'forbidden' });
      haptic.error();
      if (why === 'forbidden') sheets.consent(); // the new policy first: here it is
    } finally { chat.busy = false; }
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
  const gisOf = (id: number) => { const e = eventById(id); return e && !e.online ? e.placeUrl || addressGis(e.place) : null; };
  const shown = (a: AssistAction) => {
    if (a.type === 'club' && chat.ctx?.kind === 'club' && a.id === chat.ctx.id) return false;
    return a.type !== 'route' || !!gisOf(a.id);
  };
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
  // the circle, and the whole opening stutters on a phone; dropped here before Sheet takes it
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

<Sheet {overlay} {opener} icon={Sparkles} tall shut title={t('as.title')}>
  <div class="list" class:flown={!!from} bind:this={list}>
    {#if !chat.turns.length}
      <div class={['mid', { up: kb > 0, tight }]} style:--kb="{kb}px">
        <i class="orb big live" class:hid={flying} class:land={!from} bind:this={orb} aria-hidden="true"><span class="mark"><KbtuMark /></span><span class="mark glyph"><Sparkles strokeWidth={2} /></span></i>
        <h2 class="greeting clamp-2">{chat.ctx ? t('as.about', { title: chat.ctx.title }) : t('as.hello', { name: first ? ', ' + first : '' })}</h2>
        <!-- every question in one cell: the tallest holds the height, a change moves nothing -->
        <button class="rot" onclick={() => pick(SUGGEST[qi])}>
          {#each SUGGEST as k, i (k)}<span class:on={i === qi} aria-hidden={i !== qi}>{t(k)}</span>{/each}
        </button>
      </div>
    {:else if chat.ctx}
      <!-- engine: ui/Tag could truncate a long label with "…" (an event's title); till then this label is local -->
      <p class="ctx"><Sparkles size={13} strokeWidth={2.2} /><span class="ellipsis">{chat.ctx.title}</span></p>
    {/if}
    {#each chat.turns as m, i (i)}
      {#if m.role === 'user'}
        <ChatMessage mine text={m.text} fresh={i >= born} />
      {:else if m.text}
        {@const p = answer(m.text)}
        <div class="ans" class:new={i >= born} class:err={m.err != null} class:left={i === left}>
          {#if i === top}<i class="orb" aria-hidden="true"></i>{/if}
          <ChatMessage lines={p.lines} fresh={i >= born} />
          {#if (m.mark && !m.care) || p.source}
            <!-- the source and 👍/👎 on one line, right under the words they are about -->
            <div class="meta" style:--i={p.lines.length}>
              <p class="src selectable">{p.source}</p>
              {#if m.mark && !m.care}
                <IconButton kind="plain" size="s" icon={ThumbsUp} label={t('as.good')} on={m.vote === 'up'} disabled={!!m.vote} onclick={() => vote(m, 'up')} />
                <IconButton kind="plain" size="s" icon={ThumbsDown} label={t('as.bad')} on={m.vote === 'down'} disabled={!!m.vote} onclick={() => vote(m, 'down')} />
              {/if}
            </div>
          {/if}
          {#if m.vote === 'down' && !m.care}
            <div class="offer">{#if m.sent}<p>{t('as.sent')}</p>{:else}
              <Button kind="plain" size="s" onclick={() => send(m)}>{t('as.sendQ')}</Button><p>{t('as.sendNote')}</p>{/if}</div>
          {/if}
          {#if m.actions?.some(shown) || m.err}
            <!-- the answer's buttons as plain rows: › opens a screen here, ↗ leaves the app (2GIS); a failed call: once more -->
            <div class="acts" style:--i={p.lines.length + 1}><Group>
              {#each (m.actions ?? []).filter(shown) as a, k (k)}
                <Row dense icon={iconOf(a)} title={label(a)} accessory={a.type === 'route' ? 'external' : 'chevron'} onclick={() => go(a, m.q)} />
              {/each}
              {#if m.err}<Row dense icon={RotateCw} title={t('common.retry')} tone="action" onclick={() => retry(i)} />{/if}
            </Group></div>
          {/if}
        </div>
      {/if}
      {#if m.care && m.help}
        <div class="help" class:new={i >= born}>
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
    {#if busy}<div class="think" role="status"><i class="orb live" aria-hidden="true"></i><span>{t('as.thinking')}</span></div>{/if}
  </div>

  {#snippet footer()}
    {#if flying}<i class="orb live fly" bind:this={fly} aria-hidden="true"><span class="mark"><KbtuMark /></span><span class="mark glyph"><Sparkles strokeWidth={2} /></span></i>{/if}
    {#if !chat.turns.length}
      <!-- the starters in the footer: they ride over the keyboard with the field, nothing of the body has to scroll -->
      <div class="over">
        {#if offer}
          <div class="gem" class:out={!asking} inert={!asking}>
            <p class="gt">{t('kri.gT')}</p>
            <p class="gx">{t('kri.gText')}</p>
            <div class="btns gb">
              <Button kind="primary" size="s" full onclick={() => gemini(true)}>{t('kri.gOn')}</Button>
              <Button kind="secondary" size="s" full onclick={() => gemini(false)}>{t('kri.gLater')}</Button>
            </div>
          </div>
        {/if}
        <div class="eg" class:out={asking} inert={asking}>{#each SUGGEST as k (k)}<button onclick={() => pick(k)}>{t(k)}</button>{/each}</div>
      </div>
    {/if}
    <div class="bar">
      <!-- the map, one tap away as when it had the bar's corner: beside the field, there with or without a conversation -->
      <button class="mapb" aria-label={t('as.map')} onclick={openMap}><MapIcon size={20} /></button>
      <div class="inp"><Composer bind:value={draft} placeholder={t('as.ph')} maxlength={300} sending={busy} label={t('cm.send')} onsend={() => ask(draft)} pill {focus} /></div>
    </div>
    <p class="note">{t('as.note')}</p>
  {/snippet}
</Sheet>

<style>
  .list { display: flex; flex-direction: column; gap: var(--s-3); min-height: 100%; padding: 6px 0 4px; }
  .list:has(> .mid) { padding: 0; }
  /* empty: the light in the middle of the body with the words under it. The keyboard: Sheet raises the footer over the
     body, the middle moves itself (a transform, no layout) or, with no room, fades */
  .mid { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; padding: var(--s-2) var(--s-1);
    transition: transform 250ms cubic-bezier(.2, .8, .3, 1), opacity 180ms ease-out; }
  .mid.up { transform: translateY(calc(var(--kb) / -2)) scale(0.8); }
  .mid.tight { opacity: 0; pointer-events: none; }
  .greeting { max-width: 100%; margin-top: var(--s-5); font: 700 var(--fs-t1)/1.1 var(--font-display); letter-spacing: -0.03em; overflow-wrap: anywhere; text-wrap: balance; animation: down 480ms var(--ease) var(--land, 0ms) backwards; }
  .rot { display: grid; max-width: 100%; padding: var(--s-2) var(--s-3); border-radius: var(--r-m); color: var(--text-3);
    font: 600 var(--fs-row)/1.25 var(--font-display); letter-spacing: -0.016em; text-wrap: balance;
    animation: down 480ms var(--ease) calc(var(--land, 0ms) + 50ms) backwards; transition: opacity var(--t-fast); }
  .rot:active { opacity: 0.6; }
  /* one leaves, then the next comes up: the two are never read through each other */
  .rot span { grid-area: 1 / 1; align-self: center; opacity: 0; transform: translateY(6px); transition: opacity 240ms ease-in, transform 240ms ease-in; }
  .rot span.on { opacity: 1; transform: none; transition: opacity 420ms var(--ease) 220ms, transform 420ms var(--ease) 220ms; }
  .flown { --land: 380ms; } /* the light is flying in: the words wait until it is over them, not on them; no flight, no wait */
  @keyframes down { from { opacity: 0; transform: translateY(-12px); } }
  .ctx { align-self: center; display: inline-flex; align-items: center; gap: 6px; max-width: 86%; height: 28px; padding: 0 12px; border-radius: var(--r-full);
    background: var(--fill); color: var(--text-2); font: 600 var(--fs-cap)/1 var(--font-text); }

  /* the light: two flat gradients, the lower one turning where it is alive; no blur, no filter */
  .orb { position: relative; flex: none; display: block; width: 20px; height: 20px; border-radius: 50%; overflow: hidden; }
  .orb::before { content: ''; position: absolute; inset: -20%; border-radius: 50%;
    background: conic-gradient(from 200deg, var(--accent), var(--tile-teal), var(--accent-2), var(--tile-purple), var(--accent)); }
  .orb::after { content: ''; position: absolute; inset: 0; border-radius: 50%;
    background: radial-gradient(circle at 30% 24%, rgba(255, 255, 255, 0.6), rgba(255, 255, 255, 0) 52%), radial-gradient(circle, rgba(8, 10, 40, 0) 52%, rgba(8, 10, 40, 0.3)); }
  .orb.live::before { animation: turn 7s linear infinite; animation-play-state: var(--sheet-loop, running); }
  @keyframes turn { to { transform: rotate(360deg); } }
  .orb.big { width: 84px; height: 84px; }
  .orb.big, .orb.fly { box-shadow: 0 10px 28px -8px rgba(98, 104, 255, 0.6); }
  .orb.land { animation: land 520ms var(--ease) backwards; } /* no button to fly from: it comes up in its place */
  @keyframes land { from { opacity: 0; transform: scale(0.6); } }
  .orb.hid { visibility: hidden; }
  .orb.fly { position: absolute; z-index: 1; visibility: hidden; pointer-events: none; }

  .mark { position: absolute; inset: 0; z-index: 1; display: grid; place-items: center; color: rgb(255, 255, 255); }
  .mark :global(svg) { width: 44%; height: auto; }
  /* the button's own glyph, its size there (24 of 54) when the light is the button's size: seen only in flight */
  .glyph { opacity: 0; }
  .glyph :global(svg) { width: 44.4%; }
  /* Gemini's card and the starters in one cell: one shows, the other keeps its place hidden */
  .over { display: grid; margin-bottom: var(--s-2); }
  .over > * { grid-area: 1 / 1; transition: opacity 220ms var(--ease), visibility 0s; }
  .over > .out { opacity: 0; visibility: hidden; transition: opacity 160ms ease-out, visibility 0s 160ms; }
  .gem { align-self: end; display: flex; flex-direction: column; gap: 4px; padding: var(--s-3); border-radius: var(--r-m); background: var(--fill); }
  .gt { font: 600 var(--fs-body)/1.25 var(--font-text); }
  .gx { font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-2); text-wrap: pretty; }
  .gb { display: flex; gap: var(--s-2); margin-top: var(--s-2); }
  /* the starters over the field, two by two, the words on two lines; an odd last one takes the row */
  .eg { align-self: end; display: grid; grid-template-columns: 1fr 1fr; gap: var(--s-2); }
  .eg button { display: flex; align-items: center; min-height: var(--ctl-l); padding: var(--s-2) var(--s-3); border-radius: var(--r-m); background: var(--fill); color: var(--text);
    font: 600 var(--fs-sub)/1.25 var(--font-text); text-align: left; text-wrap: balance; overflow-wrap: anywhere; transition: transform var(--t-fast); }
  .eg button:active { transform: scale(0.96); }
  .eg button:last-child:nth-child(odd) { grid-column: 1 / -1; }

  .help p { font: 450 var(--fs-body)/1.45 var(--font-text); white-space: pre-wrap; overflow-wrap: anywhere; }
  .ans { display: flex; flex-direction: column; padding: 0 var(--s-1); }
  .ans > .orb { margin: 2px 0 var(--s-2); }
  /* where the word "thinking" stood beside it: it stays in its place and the lines come down from under it */
  .new > .orb { animation: still 420ms var(--ease-bounce) backwards; }
  @keyframes still { from { transform: scale(0.82); } }
  .new .meta, .new .acts, .help.new { animation: down 460ms var(--ease) calc(80ms + var(--i, 0) * 70ms) backwards; }
  /* the light has gone to the next answer: this one rises into its room (30 px: the light and its margins) */
  .ans.left { animation: rise 360ms var(--ease) backwards; }
  @keyframes rise { from { transform: translateY(30px); } }
  .err { color: var(--text-2); }
  .meta { display: flex; align-items: center; min-height: 36px; margin: 2px -6px 0 0; --plain-ink: var(--text-3); }
  .meta :global(.btn[aria-pressed='true']) { color: var(--accent-text); opacity: 1; }
  .src { flex: 1; min-width: 0; padding-right: var(--s-2); font: 450 var(--fs-cap)/1.3 var(--font-text); color: var(--text-3); overflow-wrap: anywhere; }
  .acts { margin: var(--s-2) calc(-1 * var(--s-1)) 0; }
  .offer { display: flex; flex-direction: column; align-items: flex-start; gap: 4px; margin: 0 0 var(--s-1) -6px; animation: down 300ms var(--ease) backwards; }
  .offer p { padding: 0 6px; font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .help { display: flex; flex-direction: column; gap: var(--s-2); --i: 2; }
  .help p { padding: 0 var(--s-1) var(--s-1); }
  .first { display: flex; align-items: center; justify-content: center; gap: var(--s-2); height: var(--ctl-m); padding: 0 var(--s-5); border-radius: var(--r-full);
    background: var(--accent); color: var(--on-accent); font: 600 var(--fs-body)/1 var(--font-text); text-decoration: none; }
  .first:active { opacity: 0.8; }
  .think { display: flex; align-items: center; gap: 10px; padding: 2px var(--s-1); font: 450 var(--fs-body)/1 var(--font-text); color: var(--text-3); animation: up 300ms var(--ease) backwards; }
  .think .orb { animation: breathe 1.5s ease-in-out infinite alternate; }
  @keyframes up { from { opacity: 0; transform: translateY(10px); } }
  @keyframes breathe { from { transform: scale(0.82); } to { transform: scale(1.08); } }
  /* power saving: nothing moves without end; less motion asked: nothing moves at all, everything is in its place */
  :global(html.lowfx) .orb::before, :global(html.lowfx) .think .orb { animation: none; }
  @media (prefers-reduced-motion: reduce) {
    .list *, .orb, .orb::before { animation: none !important; }
    .mid, .rot span, .over > * { transition: none !important; }
  }

  .bar { display: flex; align-items: flex-end; gap: var(--s-2); }
  .inp { flex: 1; min-width: 0; }
  /* flat, the field's own ground: a control in the sheet, not floating chrome */
  .mapb { flex: none; display: grid; place-items: center; width: 44px; height: 44px; border-radius: var(--r-full); background: var(--fill); color: var(--text-2);
    transition: transform var(--t-fast); }
  .mapb:active { transform: scale(0.92); }
  .note { margin: var(--s-2) 4px 0; text-align: center; font: 450 var(--fs-cap)/1.3 var(--font-text); color: var(--text-3); }
</style>
