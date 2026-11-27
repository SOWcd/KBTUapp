<script lang="ts">
  // The Forum tab has a personalized order and the public channel's order. The composer is glass (base.css
  // .glass-pill), the places under it lens-glass tiles; each post the app's card on the plain ground: the face
  // (an accent dot on it: new since my last visit), the name over the time, the words; under them Telegram's reactions
  // as bare counts (read-only: they are Telegram's; no chip around them, nothing to press) and, on the right, the one way
  // to the comments, which live in Telegram: who replied, and a grey button with Telegram's mark and the count (an accent
  // one on every card outshouted the words). The post itself opens nothing. My own posts are marked (on their way, under review, removed) and can be deleted.
  // Nothing jumps: the 30 s refresh never puts posts above the one I'm reading; they wait behind an "N new" pill (at
  // the top already: they just come in). Under the 50th, "Show earlier" brings the next 50.
  // No large title (the capsule names the tab): the feed starts with a "Share with KBTU…" row that opens the new post
  // screen (ChannelCompose). A signed post shows its author as the app does (his profile on a tap); an anonymous one a
  // mask, nobody behind it (the API sends no one). Every tap answers at once (a new post stands at the top "checking";
  // a delete leaves the list before the server says so). It looks the same for every viewer, staff too: the channel's
  // moderation lives in Admin alone.
  import { tick, untrack } from 'svelte';
  import { flip } from 'svelte/animate';
  import { cubicOut } from 'svelte/easing';
  import { fade, type TransitionConfig } from 'svelte/transition';
  import { calm } from '../../ui/fold';
  import ArrowUp from '@lucide/svelte/icons/arrow-up';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Lightbulb from '@lucide/svelte/icons/lightbulb';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import Pencil from '@lucide/svelte/icons/pencil';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Heart from '@lucide/svelte/icons/heart';
  import Flag from '@lucide/svelte/icons/flag';
  import MessageCircleReply from '@lucide/svelte/icons/message-circle-reply';
  import Share from '@lucide/svelte/icons/share';
  import { menu } from '../../ui/menu';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import ChartNoAxesColumn from '@lucide/svelte/icons/chart-no-axes-column';
  import BookOpen from '@lucide/svelte/icons/book-open';
  import LifeBuoy from '@lucide/svelte/icons/life-buoy';
  import Check from '@lucide/svelte/icons/check';
  import Footprints from '@lucide/svelte/icons/footprints';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Avatar from '../../ui/Avatar.svelte';
  import { initials } from '../../ui/OrgLogo.svelte';
  import { api, ApiErr, type ChannelFeedPost } from '../../lib/api';
  import { session, asStudent } from '../../lib/state/session.svelte';
  import Segmented from '../../ui/Segmented.svelte';
  import { channel, loadChannel, loadOlder, markChannelSeen, pendingHearts, refreshChannel, removeChannelPost, selectChannelOrder, toggleComing, toggleHeart, touched } from '../../lib/state/channel.svelte';
  import { ui, say, overlays } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { nickName } from '../../lib/i18n/nicks';
  import { haptic, inTelegram, on, openLink, shareCard } from '../../lib/tg';
  import { count } from '../../lib/stats';
  import { phrase, loadResearch } from '../../lib/state/data.svelte';
  import { ago, nowTs } from '../../lib/time';
  import { compact } from '../../lib/chats';
  import { TAB_ICON } from '../../ui/icons';
  import EmptyState from '../../ui/EmptyState.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Button from '../../ui/Button.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import Marked from './Marked.svelte';
  import PullSearch, { PULL } from '../../ui/PullSearch.svelte';
  const TOP = inTelegram ? PULL : 0; // the pull-down search field above the feed is Telegram's only (PullSearch)
  import { hit } from '../../lib/search';
  import { compose, keyOf, type Pic } from './ChannelCompose.svelte';

  // A card (or the "N new" line, the pill) comes and goes in place by opacity and a touch of scale, the compositor's
  // work; the others glide to their new places (flip). A height slide relaid the whole feed every frame and, with
  // flip on the same rows, moved them twice. scale, not transform: flip's translate and the leaving card's own
  // (Svelte pins it where it was) stay untouched.
  function card(_: Element, _p?: unknown, o?: { direction?: 'in' | 'out' | 'both' }): TransitionConfig {
    if (calm()) return { duration: 0 };
    const away = o?.direction === 'out';
    return { duration: away ? 200 : 280, delay: away ? 0 : 60, easing: cubicOut, css: (t) => `opacity: ${t}; scale: ${0.96 + 0.04 * t}` };
  }

  const CHANNEL = 'https://t.me/KBTUappForum';
  const me = $derived(session.me);
  const here = $derived(ui.tab === 'forum');
  let visibility = $state<DocumentVisibilityState>();
  const visible = $derived(here && visibility === 'visible' && !overlays.length && !ui.gate && !session.banned);
  let since = $state<number | null>(null);
  const fresh = (p: ChannelFeedPost) => !!since && p.status === 'live' && (p.msg ?? 0) > since && (!p.mine || p.anon);

  // A held post may be published much later. Admit new public messages in channel order, whoever wrote them.
  let through = $state(0), atTop = $state(true), scroller = $state<HTMLElement>();
  let focusedPost = $state<ChannelFeedPost | null>(null);
  let focusRequest = 0;
  const feed = $derived(focusedPost && !channel.feed?.some((p) => p.id === focusedPost?.id)
    ? [focusedPost, ...(channel.feed ?? [])] : (channel.feed ?? []));
  const latestMsg = (posts: ChannelFeedPost[]) => posts.reduce((max, p) => p.status === 'live' ? Math.max(max, p.msg ?? 0) : max, 0);
  const latest = $derived(latestMsg(feed));
  // an ask for help leaves on its minute, before the next refresh says so (clock: a tick a minute while here)
  let clock = $state(nowTs());
  $effect(() => { if (!here) return; clock = nowTs(); const every = setInterval(() => { clock = nowTs(); }, 60_000); return () => clearInterval(every); });
  const up = (p: ChannelFeedPost) => !p.help || p.help.until > clock;
  const shown = (p: ChannelFeedPost) => up(p) && (p.status !== 'live' || (p.msg ?? 0) <= through);
  const list = $derived(feed.filter(shown));
  const waiting = $derived(feed.filter((p) => up(p) && !shown(p)).length);
  const showAll = () => { through = latest; };
  $effect(() => { if ((atTop || !through) && latest > through) through = latest; });
  function seeNew() { haptic.tap(); showAll(); scroller?.scrollTo({ top: TOP, behavior: 'smooth' }); }
  // the pull-down search, over the posts held, by their words only (never a signature: an anonymous post has none to match)
  // ponytail: the loaded pages only; a server search when the channel outgrows them
  let q = $state('');
  const searching = $derived(!!q.trim());
  const matched = $derived(searching ? list.filter((p) => hit(q, [p.body])) : list);

  // the line stands above the first post seen before, when some new one is above it: "N new", how many
  const cut = $derived.by(() => {
    if (channel.order !== 'new' || focusedPost) return null;
    const i = list.findIndex((p) => p.status === 'live' && !!p.msg && p.msg <= (since ?? 0)), n = i > 0 ? list.slice(0, i).filter(fresh).length : 0;
    return n ? { id: list[i].id, n } : null;
  });
  // the rows: the posts, and the line a row of its own above its post (inside the post's row it pushed that card down
  // in one step as it came)
  const rows = $derived(matched.flatMap((p): (ChannelFeedPost | 'nw')[] => (!searching && cut?.id === p.id ? ['nw', p] : [p])));
  // the first screen settles top down (rise); later cards come by their own transition only
  let settled = $state(false);
  $effect(() => { if (channel.feed?.length && !settled) { const t = setTimeout(() => (settled = true), 900); return () => clearTimeout(t); } });

  // older posts: the next page under the last one (they come in under it, nothing above moves)
  let older = $state(false);
  async function earlier() {
    haptic.tap(); older = true;
    try { await loadOlder(); } catch (e) { fail(e); } finally { older = false; }
  }

  $effect(() => { if (here) untrack(() => { void refreshChannel(); void loadResearch(); }); });
  $effect(() => { if (here && channel.focus != null) untrack(() => { void seek(); }); });
  // Keep the divider at this visit's starting point. Prefetches, covered tabs and posts behind
  // the "N new" pill do not advance the server cursor.
  const top = $derived(latestMsg(matched));
  $effect(() => {
    const visit = channel.visit;
    if (!here) { since = null; return; }
    if (!visible || !visit) return;
    since ??= visit.seen;
    if (top > visit.seen) untrack(() => { void markChannelSeen(top); });
  });

  // fresh while open: back from the background (Telegram's activated, the page shown again) and every 30 s while seen;
  // a new post fades in at the top, the rest glide down (flip)
  $effect(() => {
    if (!here) return;
    const pull = () => {
      if (document.hidden) return;
      void loadChannel();
      const id = focusedPost?.id;
      if (id == null) return;
      const request = ++focusRequest;
      void api.channelPost(id).then((post) => {
        if (request === focusRequest && focusedPost?.id === id) focusedPost = post;
      }).catch((e) => {
        if (request === focusRequest && focusedPost?.id === id && e instanceof ApiErr && e.code === 'not_found') focusedPost = null;
      });
    };
    const every = setInterval(pull, 30_000);
    document.addEventListener('visibilitychange', pull);
    const off = on('activated', pull);
    return () => { clearInterval(every); document.removeEventListener('visibilitychange', pull); off(); };
  });

  // A shared post can sit anywhere in the ranked feed. Open it directly if its page isn't loaded.
  let lit = $state<number | null>(null);
  async function seek() {
    const id = channel.focus;
    if (id == null) return;
    channel.focus = null;
    const request = ++focusRequest;
    focusedPost = null;
    if (!channel.feed?.some((p) => p.id === id)) {
      try {
        const post = await api.channelPost(id);
        if (request !== focusRequest || !here) return;
        focusedPost = post;
      } catch (e) {
        if (request === focusRequest && here) {
          if (e instanceof ApiErr && e.code === 'not_found') say(t('fc.gone'), 'thinking_face_3d');
          else fail(e);
        }
        return;
      }
    }
    showAll(); open[id] = true;
    await tick();
    document.querySelector(`[data-post="${id}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    lit = id;
    setTimeout(() => { if (lit === id) lit = null; }, 1800);
  }

  // the comments in Telegram: opened at the newest comment, the bot's first with none yet (?comment=, Telegram's link into a post's comments);
  // an older post without one: the post itself, its Comments bar under it
  const comments = (p: ChannelFeedPost) => `${CHANNEL}/${p.msg}${p.thread ? `?comment=${p.thread}` : ''}`;
  // a reaction as plain text (the heart's label): a custom emoji (only its id comes) and a paid star as their nearest
  const glyph = (e: string) => e.startsWith('custom:') ? '✨' : e === 'paid' ? '⭐' : e;

  // my own post's mark beside the time while only I see it: on its way (the AI looking), under review, removed, being
  // published (out, the channel's message not back yet). Once in the channel: none, a card like anyone's
  // ("Mine" by a mask outs its author to whoever looks at the screen)
  const mark = (p: ChannelFeedPost) => p.id < 0 ? { tone: 'quiet', key: 'fc.checking' } as const
    : p.status === 'held' ? (p.human ? { tone: 'warning', key: 'fc.human' } as const : { tone: 'quiet', key: 'fc.checking' } as const)
    : p.status === 'hidden' ? { tone: 'quiet', key: 'fc.hidden' } as const : !p.msg ? { tone: 'quiet', key: 'fc.publishing' } as const
    : p.edit === 'held' ? { tone: 'warning', key: 'fc.editHeld' } as const : p.edit === 'declined' ? { tone: 'quiet', key: 'fc.editDeclined' } as const : null;
  // my held post's why, to me alone: I sent it to a moderator, it has photos and a mask, or the AI's words (kept by the
  // server: a reload keeps them; channel.why: this session's, as soon as they come)
  const heldWhy = (p: ChannelFeedPost) => p.review?.kind === 'appeal' ? { reason: t('fc.appealedWhy'), fix: null }
    : p.review?.kind === 'photo' ? { reason: t('fc.photoWhy'), fix: null }
    : p.review?.kind === 'tg' ? { reason: t('fc.tgWhy'), fix: null }
    : { reason: (channel.why[p.id] ?? p.review?.explain)?.reason ?? t('fc.humanWhy'), fix: (channel.why[p.id] ?? p.review?.explain)?.fix ?? null };

  // a long post starts at four lines with a fade and a quiet "More" that opens it in place (its height glides to the
  // full one); a short one shows whole. long/full: measured while clamped, per post
  const long = $state<Record<number, boolean>>({}), open = $state<Record<number, boolean>>({}), full = $state<Record<number, number>>({});
  function measure(el: HTMLElement, id: number) {
    const check = () => { full[id] = el.scrollHeight; if (!open[id]) long[id] = el.scrollHeight > el.clientHeight + 2; };
    // no check() here: the observer's first call comes before the first paint, for all posts in one batch. A read at
    // mount forced a layout per post (each post's write dirtied it for the next): 50 layouts building the tab
    const ro = new ResizeObserver(check);
    ro.observe(el);
    return { destroy: () => ro.disconnect() };
  }

  // the channel takes posts from KBTU-confirmed students only (a typed-in ID could be anyone's): the rest sign in first
  function write() {
    haptic.tap();
    if (!me?.student) asStudent(() => compose());
    else if (me.student.manual) sheets.login();
    else compose();
  }

  // the tab's places (the tiles under the composer)
  const doors = $derived([
    { icon: ChartNoAxesColumn, tone: 'var(--tile-indigo)', label: t('research.title'), go: () => sheets.research() },
    ...(me?.subjects ? [{ icon: BookOpen, tone: 'var(--tile-teal)', label: t('sj.row'), go: () => sheets.subjects() }] : []),
    ...(me?.appeals ? [{ icon: Megaphone, tone: 'var(--tile-orange)', label: t('apl.chip'), go: () => sheets.appeals() }] : []),
  ]);

  // an ask for help: "I'm coming" (a confirmed student, as for writing), on at once; time left in the head
  function coming(p: ChannelFeedPost) {
    haptic.tap(); count('do.coming');
    const go = () => { void toggleComing(p).catch(fail); };
    if (!me?.student) asStudent(go);
    else if (me.student.manual) sheets.login();
    else go();
  }
  function left(until: number): string {
    const min = Math.max(1, Math.ceil((until - clock) / 60));
    return min < 60 ? t('fc.leftM', { n: min }) : t('fc.leftH', { n: Math.round(min / 60) });
  }

  function heart(p: ChannelFeedPost) {
    haptic.tap(); count('do.heart');
    asStudent(() => { void toggleHeart(p).catch((e) => { fail(e); void loadChannel(); }); });
  }

  function fail(e: unknown) {
    haptic.error();
    say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'fc.slow' : 'common.error'), 'pleading_face_3d');
  }

  async function drop(p: ChannelFeedPost) {
    if (!(await sheets.ask({ title: t('fc.deleteAsk'), text: t('fc.deleteText'), ok: t('fc.delete'), cancel: t('common.cancel'), danger: true }))) return;
    const undo = removeChannelPost(p.id), focused = focusedPost;
    if (focusedPost?.id === p.id) focusedPost = null;
    haptic.ok();
    try { await api.deleteChannelPost(p.id); touched(); }
    catch (e) { undo(); if (focused?.id === p.id && !focusedPost) focusedPost = focused; fail(e); }
  }

  // my live post's words (and photos) again, in the writing window: the same checks as a new post
  function edit(p: ChannelFeedPost) {
    haptic.tap();
    compose({ body: p.body, anon: p.anon, photos: p.photos.map((x): Pic => ({ ...x })),
      edit: { id: p.id, sign: p.anon ? nickName(p.nick) ?? p.sign : p.sign, was: p.body, ids: p.photos.map((x) => x.id ?? 0) } });
  }

  // every post in the channel: ⋯, the same on every card. Someone else's: Report (into the admin's queue, whose it is
  // stays hidden); mine: answer as the mask (an anonymous one) and Delete, inside it, so nothing on the card says whose
  function more(e: MouseEvent, p: ChannelFeedPost) {
    menu(e.currentTarget as Element, p.mine ? [
      ...(p.anon ? [{ label: t('fcr.entry'), icon: MessageCircleReply, onselect: () => sheets.channelReply({ id: p.id, body: p.body }) }] : []),
      { label: t('fc.editPost'), icon: Pencil, onselect: () => edit(p) },
      { label: t('fc.delete'), icon: Trash2, destructive: true, onselect: () => drop(p) },
    ] : [{ label: t('cm.report'), icon: Flag, destructive: true, onselect: () => sheets.report('fpost', p.id, p.body.slice(0, 120)) }], 'end');
  }

  // pass a post on: our bot's card (its opening words, a button into it by id only: never whose), as an event's
  const share = (p: ChannelFeedPost) => {
    haptic.tap(); count('do.share');
    shareCard({ kind: 'fp', id: String(p.id) })
      .then((sent) => { if (sent) say(phrase('say.shared'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'warning_3d'); });
  };

  // the comments, in Telegram: its button alone opens them
  const talk = (p: ChannelFeedPost) => { haptic.tap(); openLink(comments(p)); };
</script>

<svelte:document bind:visibilityState={visibility} />

<div class="page scroll" bind:this={scroller} onscroll={(e) => { atTop = e.currentTarget.scrollTop < TOP + 40; }}>
  <PullSearch bind:value={q} placeholder={t('fc.search')} />
  <!-- new posts from the refresh while I read further down: a pill, never a jump -->
  <div class="pill">{#if waiting && !atTop}<span class="pin" transition:card>
    <Button kind="glass" size="s" onclick={seeNew}>{#snippet icon()}<ArrowUp size={16} strokeWidth={2.4} />{/snippet}{tn('fc.newSince', waiting)}</Button>
  </span>{/if}</div>
  <!-- the way to write: a glass capsule, my face and a quiet prompt, the pen at the end; the whole capsule a tap
       (the prompt's button reaches over all of it; the pen is a round button of its own, never one inside another) -->
  <div class="compose glass glass-pill" class:away={channel.writing > 0} data-compose>
    <button class="open" onclick={write}>
      {#if me}<Avatar person={me} size={36} tappable={false} />{:else}<span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>{/if}
      <span class="prompt ellipsis">{t('fc.share')}</span>
    </button>
    <IconButton icon={SquarePen} size="s" label={t('fc.new')} onclick={write} />
  </div>
  <!-- the tab's places, under the composer: research (the students' voice), the subjects' cards (SUBJECTS_FILE) and
       the other way to speak up (APPEALS: to the SG alone). Tiles, not pills: an app-icon square in its own colour,
       the name and a chevron, so they read as somewhere to go and never as a filter on the feed below -->
  <nav class="doors" class:wide={doors.length < 3} style:--n={doors.length} aria-label={t('fc.places')}>
    {#each doors as d (d.label)}
      <button class="door" onclick={() => { haptic.tap(); d.go(); }}>
        <span class="sq" style:--tone={d.tone} aria-hidden="true"><d.icon size={17} strokeWidth={2.2} /></span>
        <span class="dl">{d.label}</span>
        <span class="chev" aria-hidden="true"><ChevronRight size={14} strokeWidth={2.4} /></span>
      </button>
    {/each}
  </nav>

  <div class="order">
    <Segmented items={[{ value: 'for_you', label: t('fc.forYou') }, { value: 'new', label: t('fc.newOrder') }]}
      value={channel.order} label={t('fc.order')} onchange={(order) => { haptic.select(); focusRequest++; focusedPost = null; selectChannelOrder(order); }} />
  </div>

  {#if feed.length}
    <!-- another order is another list: swapped whole with one quick fade, not every card shuffling past the others -->
    {#key channel.order}
    <div class="feed" class:settled in:fade={{ duration: calm() ? 0 : 180 }}>
      {#each rows as r, i (r === 'nw' ? r : keyOf(r))}
        <!-- one element per row (flip needs it) -->
        <div class="item" animate:flip={{ duration: calm() ? 0 : 320, easing: cubicOut }} transition:card>
        {#if r === 'nw'}<div class="nw" role="separator"><span class="nwl"><ArrowUp size={12} strokeWidth={2.5} />{tn('fc.newSince', cut?.n ?? 0)}</span></div>
        {:else}
        {@const p = r}
        {@const m = p.mine ? mark(p) : null}
        {@const live = (p.msg ?? 0) > 0 && p.status === 'live'}
        {@const why = p.mine && p.human ? heldWhy(p) : undefined}
        {@const quote = p.mine && p.human ? (channel.why[p.id] ?? p.review?.explain)?.quote : undefined}
        <article class="post" style:--i={Math.min(i, 8)} class:off={p.status === 'hidden'} class:lit={lit === p.id} class:sos={!!p.help} data-post={p.id}>
          <!-- the face, the name and when, my mark; the post's one menu at the end -->
          <div class="head">
            <span class="rail">
              {#if p.person}<Avatar person={p.person} size={36} />
              {:else}
                <!-- anonymous: the mask; an author no longer here (a deleted account): the signature's initials -->
                <span class="av" class:anon={p.anon} aria-hidden="true">{#if p.anon}<VenetianMask size={18} strokeWidth={2} />{:else}{initials(p.sign)}{/if}</span>
              {/if}
              {#if fresh(p)}<span class="dot" aria-hidden="true"></span>{/if}
            </span>
            <span class="who">
              {#if p.person}<button class="name" onclick={() => { haptic.tap(); sheets.person(p.person!.id); }}><b class="ellipsis">{p.person.name}</b></button>
              {:else}<b class="ellipsis">{nickName(p.nick) ?? p.sign}</b>{/if}
              <span class="meta"><span>{ago(p.at)}{#if p.edited} · {t('fc.edited')}{/if}</span>
                {#if m}<span class="mk {m.tone}">{t(m.key)}</span>
                {:else if p.hot && live}<span class="mk hot">{t('fc.hot')}</span>{/if}
                {#if p.help}<span class="mk left">{left(p.help.until)}</span>{/if}</span>
            </span>
            {#if live}<span class="end"><IconButton kind="plain" size="s" icon={Ellipsis} label={t('common.more')} onclick={(e) => more(e, p)} /></span>
            {:else if p.mine && p.id > 0}<span class="end"><IconButton kind="plain" size="s" icon={Trash2} label={t('fc.delete')} onclick={() => drop(p)} /></span>{/if}
          </div>
          {#if p.help}<span class="flag"><LifeBuoy size={14} strokeWidth={2.4} aria-hidden="true" />{t('fc.help')}</span>{/if}
          <p class="tx" class:fade={long[p.id] && !open[p.id]} class:open={open[p.id]} style:--h="{full[p.id] ?? 0}px" use:measure={p.id}><Marked text={p.body} {quote} /></p>
          <!-- the photos (up to 4, the channel's album): a tap shows them whole -->
          {#if p.photos?.length}<div class="pics n{p.photos.length}" style:--ar={p.photos.length === 1 ? Math.min(2, Math.max(0.75, p.photos[0].w / p.photos[0].h)) : null}>{#each p.photos as ph, i (i)}<button class="ph" aria-label={t('fc.photo')}
            onclick={() => sheets.photos(p.photos.map((x, j) => ({ ...x, id: j + 1, by: null, mine: p.mine, canDelete: false })), i)}><img draggable="false" src={ph.thumb} alt="" loading="lazy" decoding="async" /></button>{/each}</div>{/if}
          {#if long[p.id] && !open[p.id]}<span class="more"><Button kind="plain" size="s" onclick={() => { open[p.id] = true; }}>{t('common.more')}</Button></span>{/if}
          <!-- my post waiting for a moderator: why, one quiet line (to me alone), the AI's tip under it -->
          {#if why}
            <div class="held">
              <p>{why.reason}</p>
              {#if why.fix}<p class="fix"><Lightbulb size={15} strokeWidth={2} aria-hidden="true" /><span>{why.fix}</span></p>{/if}
            </div>
          {/if}
          <!-- the AI looking: a running bar under the words, not just a word -->
          {#if p.id < 0 || (p.mine && p.status === 'live' && !p.msg)}<div class="chk" role="progressbar" aria-label={t(p.id < 0 ? 'fc.checking' : 'fc.publishing')}><span></span></div>{/if}
          <!-- an ask for help: "I'm coming" and how many; its author sees who instead (to them alone, the server's rule) -->
          {#if p.help && live}
            {@const h = p.help}
            <div class="come">
              {#if p.mine}
                {#if h.who?.length}
                  <span class="who-came">{#each h.who.slice(0, 4) as w (w.id)}<span class="f"><Avatar person={w} size={28} /></span>{/each}</span>
                  <span class="cn">{t('fc.comingWho', { who: h.who.map((w) => w.name).join(', ') })}</span>
                {:else}<span class="cn quiet">{t('fc.comingNone')}</span>{/if}
              {:else}
                <Button kind="primary" size="s" on={h.me} onclick={() => coming(p)}>
                  {#snippet icon()}{#if h.me}<Check size={16} strokeWidth={2.6} />{:else}<Footprints size={16} strokeWidth={2.2} />{/if}{/snippet}{t(h.me ? 'fc.comingOn' : 'fc.coming')}
                </Button>
                {#if h.coming}<span class="cn">{tn('fc.comingN', h.coming)}</span>{/if}
              {/if}
            </div>
            <!-- said before the tap: my name goes to the author (the count is all anyone else sees) -->
            {#if !p.mine}<p class="cnote">{t('fc.comingNote')}</p>{/if}
          {/if}
          {#if live}
            {@const pick = pendingHearts[p.id] ?? p}
            <div class="feedback">
              <!-- the app's own heart: a small chip, heart and count; its name is for screen readers only (owner: the words were too big) -->
              <button class="heart" aria-pressed={pick.hearted} aria-label="{t('fc.appHearts')}: {pick.hearts}" onclick={() => heart(p)}>
                <Heart size={16} fill={pick.hearted ? 'currentColor' : 'none'} aria-hidden="true" />
                {#if pick.hearts}<span aria-hidden="true">{compact(pick.hearts)}</span>{/if}
              </button>
              <!-- Telegram's reactions as small counts, read-only (left in Telegram); none: nothing -->
              {#if p.reactions.length}<span class="rx" role="img" aria-label="{t('fc.reactions')}: {p.reactions.map((r) => `${glyph(r.emoji)} ${r.n}`).join(', ')}">
                {#each p.reactions as r (r.emoji)}<span class="r"><span class="e">{glyph(r.emoji)}</span>{compact(r.n)}</span>{/each}
              </span>{/if}
            </div>
            <div class="acts">
              <!-- the talk lives in Telegram: who replied (faces; no ids come: a face's colour by its letter), then one button -->
              {#if p.faces.length}<span class="faces" aria-hidden="true">{#each p.faces as f, i (i)}<span class="f" style:z-index={p.faces.length - i}><Avatar person={{ ...f, id: f.name.charCodeAt(0) }} size={20} tappable={false} /></span>{/each}</span>{/if}
              <span class="share"><IconButton kind="plain" size="s" icon={Share} label={t('event.share')} onclick={() => share(p)} /></span>
              <span class="talk"><Button kind="gray" size="s" label="{t('fc.discuss')}{p.comments ? ` ${compact(p.comments)}` : ''} · {t('fc.comments')}" onclick={() => talk(p)}>
                {#snippet icon()}<TelegramMark size={16} />{/snippet}<span class="go">{t('fc.discuss')} {#if p.comments}<span class="n">{compact(p.comments)}</span>{/if}<ArrowUpRight size={14} strokeWidth={2.4} aria-hidden="true" /></span>
              </Button></span>
            </div>
          {/if}
        </article>
        {/if}
        </div>
      {/each}
      {#if searching && !matched.length}<EmptyState inline text={t(channel.more ? 'fc.searchLoaded' : 'clubs.nothing')} />{/if}
    </div>
    {/key}
  {:else if searching && channel.feed}
    <EmptyState inline text={t(channel.more ? 'fc.searchLoaded' : 'clubs.nothing')} />
  {:else if channel.feed}
    <EmptyState icon={TAB_ICON.forum} title={t('fc.emptyTitle')} text={t('fc.emptyText')} />
  {/if}

  {#if channel.more}<div class="earlier"><Button kind="plain" size="m" loading={older} onclick={earlier}>{t(searching && !matched.length ? 'fc.searchMore' : channel.order === 'new' ? 'fc.earlier' : 'fc.more')}</Button></div>{/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; }
  .page > :global(*) { flex-shrink: 0; }
  /* a post: the app's card (ui/Card's surface and hair rim) */
  .post { border-radius: var(--r-l); background: var(--surface); box-shadow: var(--card-rim); }

  /* the composer: the capsule's glass (base.css .glass-pill: the one live blur here besides the doors'), my face, a
     quiet prompt, the pen */
  .compose { position: relative; display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3); border-radius: var(--r-full); text-align: left;
    transition: transform 450ms var(--ease-bounce); }
  .compose:active { transform: scale(0.985); transition-duration: 80ms; }
  .open { flex: 1; min-width: 0; display: flex; align-items: center; gap: var(--s-3); text-align: left; }
  .open::before { content: ''; position: absolute; inset: 0; border-radius: inherit; } /* the whole capsule is the tap */
  /* it is the writing window meanwhile (ChannelCompose grows out of it and folds back). It stays under the window's
     ends: gone once the window has faded in over it (its 90 ms), back at once when the fold starts, for the window
     to thin out over */
  .compose.away { opacity: 0; pointer-events: none; transition: transform 450ms var(--ease-bounce), opacity 0s linear 90ms; }
  /* the places: equal tiles in one row, the app's card (surface and hair rim: the one glass here is the composer
     above), each an app-icon square in its colour over its name, a quiet chevron in the corner */
  .doors { display: grid; grid-template-columns: repeat(var(--n), minmax(0, 1fr)); gap: var(--s-2); margin-top: var(--s-3); }
  .door { position: relative; isolation: isolate; display: flex; flex-direction: column; align-items: flex-start; gap: var(--s-2); min-height: 82px;
    padding: var(--s-3); border-radius: var(--r-m); text-align: left; color: var(--text);
    background: var(--surface); box-shadow: var(--card-rim);
    transition: transform 450ms var(--ease-bounce); -webkit-tap-highlight-color: transparent; }
  .door:active { transform: scale(0.96); transition-duration: 80ms; }
  .sq { display: grid; place-items: center; width: 30px; height: 30px; border-radius: var(--r-xs); background: var(--tone); color: var(--on-accent);
    box-shadow: inset 0 1px 0 rgb(255 255 255 / 0.25); }
  .dl { font: 600 var(--fs-sub)/1.2 var(--font-text); letter-spacing: -0.01em; overflow-wrap: break-word; hyphens: auto;
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .chev { position: absolute; top: var(--s-3); right: var(--s-2); color: var(--text-3); display: flex; }
  /* one or two places: a row each (the square, the name, the chevron on one line), so the feed starts a line higher */
  .wide .door { flex-direction: row; align-items: center; min-height: var(--ctl-l); padding: var(--s-2) var(--s-6) var(--s-2) var(--s-3); }
  .wide .sq { flex: none; }
  .wide .dl { hyphens: manual; }
  .wide .chev { top: 50%; right: var(--s-2); transform: translateY(-50%); }
  @media (max-width: 359px) { .dl { font-size: var(--fs-cap); } .door { padding: var(--s-3) var(--s-2) var(--s-3) var(--s-3); }
    .wide .door { padding: var(--s-2) var(--s-2) var(--s-2) var(--s-3); } .wide .chev { display: none; } }
  /* the "N new" pill: floats under the capsule, takes no room in the list */
  .pill { position: sticky; top: calc(var(--head-bottom) + var(--s-2) - var(--page-top)); z-index: var(--z-sticky); height: 0; display: flex; justify-content: center; }
  .pin { display: flex; height: max-content; }
  .prompt { flex: 1; min-width: 0; font: 450 var(--fs-body)/1.3 var(--font-text); color: var(--text-3); }

  .order { margin-top: var(--s-3); }
  .feed { display: flex; flex-direction: column; gap: var(--s-3); margin-top: var(--s-3); }
  /* a post: the head (face, name and when, the menu), the words, the row under them */
  .post { position: relative; display: flex; flex-direction: column; padding: var(--s-4); }
  .feed:not(.settled) .post { animation: rise 320ms var(--ease) backwards; animation-delay: calc(var(--i) * 30ms); } /* the first screen settles top down */
  .post:has(.acts) { padding-bottom: var(--s-3); }
  /* the line between the new and the seen: a word on a hairline in the accent, between the cards */
  .nw { display: flex; align-items: center; gap: var(--s-2); margin: var(--s-1) var(--s-2) 0; /* below it: the feed's gap */
    font: 600 var(--fs-cap)/1 var(--font-text); color: var(--accent-text); letter-spacing: 0.02em; }
  .nw::before, .nw::after { content: ''; flex: 1; height: 1px; background: currentColor; opacity: 0.35; }
  .nwl { display: inline-flex; align-items: center; gap: 3px; } /* the arrow: the new ones are above the line */
  /* the post the bot's button pointed at: an accent wash that fades */
  .feed .post.lit { animation: lit 1.8s var(--ease); }
  @keyframes lit { 0%, 45% { background: var(--accent-soft); } }
  .post.off { opacity: 0.6; }
  /* an ask for help: a warm wash down from the top and a warm rim, its flag over the words, the time left by the
     time; the one primary "I'm coming" under them */
  .post.sos { background: linear-gradient(180deg, var(--warning-soft), transparent 140px) var(--surface);
    box-shadow: var(--card-rim), inset 0 0 0 1.5px var(--warning-soft); }
  .flag { align-self: flex-start; display: inline-flex; align-items: center; gap: 5px; margin-top: var(--s-3); padding: 4px 10px 4px 8px; border-radius: var(--r-full);
    background: var(--warning-soft); color: var(--warning-text); font: 600 var(--fs-cap)/1.2 var(--font-text); letter-spacing: 0.01em; }
  .flag + .tx { margin-top: var(--s-2); }
  .mk.left { color: var(--warning-text); }
  .come { display: flex; align-items: center; gap: var(--s-3); min-height: 36px; margin-top: var(--s-3); }
  .cn { min-width: 0; font: 500 var(--fs-sub)/1.35 var(--font-text); color: var(--text-2);
    display: -webkit-box; -webkit-line-clamp: 2; line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .cn.quiet { color: var(--text-3); }
  .cnote { margin-top: var(--s-1); font: 450 var(--fs-cap)/1.35 var(--font-text); color: var(--text-3); }
  .who-came { flex: none; display: flex; }
  .who-came .f + .f { margin-left: -8px; }
  .who-came :global(.av) { box-shadow: 0 0 0 2px var(--surface-solid); }

  .head { display: flex; align-items: center; gap: var(--s-3); min-height: 36px; }
  .rail { position: relative; flex: none; display: flex; }
  .av { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2);
    color: var(--text-2); font: 600 var(--fs-cap)/1 var(--font-text); letter-spacing: 0.02em; }
  .av.anon { background: var(--fill-2); color: var(--text); }
  /* new since my last visit: a small accent dot on the face's shoulder, cut out of it by the card */
  .dot { position: absolute; top: 0; right: -1px; width: 10px; height: 10px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 2px var(--surface-solid); }
  .who { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .who b { font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); letter-spacing: -0.01em; }
  .name { display: flex; min-width: 0; max-width: 100%; padding: 0; text-align: left; }
  .name:active { opacity: 0.6; }
  .meta { display: flex; flex-wrap: wrap; gap: 0 6px; min-width: 0; font: 450 var(--fs-cap)/1.3 var(--font-text); color: var(--text-3); white-space: nowrap; }
  .mk { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
  .mk::before { content: '·'; margin-right: 6px; color: var(--text-3); }
  .mk.accent { color: var(--accent-text); }
  .mk.warning { color: var(--warning-text); }
  .mk.hot { color: var(--warning-text); text-transform: lowercase; } /* being discussed: a quiet tinted word by the time (no emoji: it shouted) */
  .end { flex: none; display: flex; margin: -6px -10px -6px 0; --plain-ink: var(--text-3); }
  .chk { position: relative; height: 3px; margin-top: var(--s-3); border-radius: var(--r-full); background: var(--surface-2); overflow: hidden; }
  .chk span { position: absolute; inset: 0 auto 0 0; width: 40%; border-radius: inherit; background: var(--accent); animation: chk 1.1s ease-in-out infinite; }
  @keyframes chk { from { transform: translateX(-100%); } to { transform: translateX(250%); } }
  @media (prefers-reduced-motion: reduce) { .chk span { animation: none; width: 100%; opacity: 0.5; } .feed .post { animation: none; } }

  /* the words: four lines and a fade while long and closed; open, the height glides to the whole */
  .pics { display: grid; gap: 2px; margin-top: var(--s-3); border-radius: var(--r-m); overflow: hidden; box-shadow: 0 0 0 0.5px var(--line-2); }
  .pics.n2, .pics.n4 { grid-template-columns: 1fr 1fr; }
  .pics.n3 { grid-template-columns: 2fr 1fr; grid-template-rows: 1fr 1fr; }
  .pics.n3 .ph:first-child { grid-row: span 2; }
  .ph { display: block; aspect-ratio: 4 / 3; background: var(--surface-2); overflow: hidden; }
  .pics.n1 .ph { aspect-ratio: var(--ar, 4 / 3); } /* one: whole, its own shape (between 3:4 and 2:1) */
  .pics.n3 .ph { aspect-ratio: auto; min-height: 90px; }
  .ph img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .tx { margin-top: var(--s-3); font: 450 var(--fs-body)/1.47 var(--font-text); letter-spacing: -0.006em; color: var(--text); white-space: pre-line; overflow-wrap: break-word;
    max-height: 5.9em; overflow: hidden; transition: max-height 420ms var(--ease); }
  .tx.fade { -webkit-mask-image: linear-gradient(to bottom, black 50%, transparent); mask-image: linear-gradient(to bottom, black 50%, transparent); }
  .tx.open { max-height: var(--h); }
  .more { display: flex; margin: 0 0 0 calc(-1 * var(--s-2)); --plain-ink: var(--text-2); }
  /* my held post's why: a quiet line under the words, the mark's tone */
  .held { margin-top: var(--s-2); font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-2); }
  .held .fix { display: flex; gap: 6px; margin-top: var(--s-2); color: var(--text); }
  .held .fix :global(svg) { flex: none; margin-top: 1px; color: var(--warning-text); }

  /* The heart and Telegram counts wrap together. Sharing and the discussion stay on their own row. */
  .acts { display: flex; align-items: center; gap: var(--s-2); min-height: 36px; margin-top: var(--s-3); }
  .feedback { display: flex; flex-wrap: wrap; align-items: center; gap: var(--s-2); margin-top: var(--s-3); }
  .heart { position: relative; display: inline-flex; align-items: center; gap: 5px; padding: 0 var(--s-3); min-height: 32px; border-radius: var(--r-full);
    background: var(--fill); color: var(--text-2); font: 600 var(--fs-cap)/1.2 var(--font-text); font-variant-numeric: tabular-nums; }
  .heart[aria-pressed='true'] { color: var(--danger-text); }
  .heart::before { content: ''; position: absolute; inset: -6px -2px; } /* a 44 px tap target round the small chip */
  .rx { flex: none; display: flex; gap: var(--s-3); }
  .r { display: inline-flex; align-items: center; gap: 4px; color: var(--text-2); font: 500 var(--fs-sub)/1 var(--font-text); font-variant-numeric: tabular-nums; }
  .e { font-size: var(--fs-body); line-height: 1; }
  /* as many faces as the row has room for, the newest first and on top: the ones that don't fit wrap to a second
     line, out of sight (whole faces only, never a cut one); none when the reactions and the two buttons fill the row */
  .faces { flex: 1; min-width: 0; display: flex; flex-wrap: wrap; justify-content: flex-end; row-gap: 8px; height: 24px; padding: 2px; overflow: hidden; }
  .faces::before { content: ''; height: 20px; } /* line 1's first item, so even the first face wraps away when there is no room for it */
  .f { display: flex; }
  .f + .f { margin-left: -6px; }
  .faces :global(.av) { box-shadow: 0 0 0 1.5px var(--surface-solid); }
  .talk { flex: none; display: flex; margin-left: auto; }
  /* the button's glass on a clear body here (Button's sits on the solid surface): the card shows through */
  .talk :global(.btn) { background:
    radial-gradient(ellipse 40% 60% at var(--hx) 0%, var(--lg-spot), transparent 70%),
    linear-gradient(180deg, var(--lg-sheen), transparent 60%) var(--fill); }
  .share + .talk { margin-left: 0; }
  /* share: a quiet icon just before the comments, the actions together under the thumb */
  .share { flex: none; display: flex; margin-left: auto; --plain-ink: var(--text-3); }
  .faces + .share { margin-left: 0; }
  .go { display: inline-flex; align-items: center; gap: 2px; white-space: nowrap; } /* ↗: it leaves the app, for Telegram */
  .n { margin-left: 2px; opacity: 0.6; font-variant-numeric: tabular-nums; }
  @media (max-width: 359px) { .r:nth-child(n + 2), .faces { display: none; } .faces + .share { margin-left: auto; } } /* 320: the top reaction, the button on the right */

  .earlier { display: flex; justify-content: center; padding: var(--s-3) 0; }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } }
  .tail { height: calc(var(--bottom) + var(--s-8)); }
</style>
