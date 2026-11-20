<script lang="ts">
  // The Forum tab (the in-app forum became the public channel @KBTUappForum). Posts only: the channel's feed,
  // newest first and nothing else (a pinned "popular" block put old posts first; a post being discussed
  // says so in place). Liquid Glass (flat cards read as old iOS): a still, soft light behind the feed, each post a clear
  // pane over it (a translucent body, a lit rim, no blur: fifty live blurs would cook an old iPhone), the composer and
  // the side doors real glass (base.css .glass-pill, Button's glass). Each post a card: the face
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
  import { slide } from 'svelte/transition';
  import { cubicOut } from 'svelte/easing';
  import ArrowUp from '@lucide/svelte/icons/arrow-up';
  import ArrowUpRight from '@lucide/svelte/icons/arrow-up-right';
  import Lightbulb from '@lucide/svelte/icons/lightbulb';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Flag from '@lucide/svelte/icons/flag';
  import MessageCircleReply from '@lucide/svelte/icons/message-circle-reply';
  import Share from '@lucide/svelte/icons/share';
  import { menu } from '../../ui/menu';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import BookOpen from '@lucide/svelte/icons/book-open';
  import Avatar from '../../ui/Avatar.svelte';
  import { initials } from '../../ui/OrgLogo.svelte';
  import { api, ApiErr, type ChannelFeedPost } from '../../lib/api';
  import { session, asStudent } from '../../lib/state/session.svelte';
  import { channel, loadChannel, loadOlder, touched } from '../../lib/state/channel.svelte';
  import { ui, say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { nickName } from '../../lib/i18n/nicks';
  import { haptic, on, openLink, shareCard } from '../../lib/tg';
  import { phrase } from '../../lib/state/data.svelte';
  import { ago } from '../../lib/time';
  import { compact } from '../../lib/chats';
  import { TAB_ICON } from '../../ui/icons';
  import EmptyState from '../../ui/EmptyState.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Button from '../../ui/Button.svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import Marked from './Marked.svelte';
  import PullSearch, { PULL } from '../../ui/PullSearch.svelte';
  import { hit } from '../../lib/search';
  import { compose } from './ChannelCompose.svelte';

  const CHANNEL = 'https://t.me/KBTUappForum';
  const me = $derived(session.me);
  const here = $derived(ui.tab === 'forum');
  // "New since the last visit": the newest channel post seen, kept in this browser (a convenience: lost storage only
  // means no line). since: where this visit's line is (0: a first visit, nothing marked); while here, all on screen counts
  // as seen for the next one
  const SEEN = 'kb-fc-seen';
  function readSeen(): number { try { return Number(localStorage.getItem(SEEN)) || 0; } catch { return 0; } }
  let since = $state(0);
  // my own anonymous post gets it as anyone's: leaving it out would tell whose it is
  const fresh = (p: ChannelFeedPost) => since > 0 && p.id > since && (!p.mine || p.anon) && !!p.msg;

  // what's on screen: the posts already shown (known), the older pages under them, mine; a refresh's others wait for
  // the pill (or come in by themselves while I'm at the top). known empty: the first look, all of it
  let known = $state(new Set<number>()), atTop = $state(true), scroller = $state<HTMLElement>();
  const floor = $derived(known.size ? Math.min(...known) : Infinity);
  const shown = (p: ChannelFeedPost) => p.id < 0 || p.mine || known.has(p.id) || p.id < floor;
  const list = $derived((channel.feed ?? []).filter(shown));
  const waiting = $derived((channel.feed ?? []).filter((p) => !shown(p)).length);
  const showAll = () => { known = new Set((channel.feed ?? []).map((p) => p.id)); };
  $effect(() => { if (channel.feed && (atTop || !known.size) && (waiting || !known.size)) untrack(showAll); });
  function seeNew() { haptic.tap(); showAll(); scroller?.scrollTo({ top: PULL, behavior: 'smooth' }); }
  // the pull-down search, over the posts held, by their words only (never a signature: an anonymous post has none to match)
  // ponytail: the loaded pages only; a server search when the channel outgrows them
  let q = $state('');
  const searching = $derived(!!q.trim());
  const matched = $derived(searching ? list.filter((p) => hit(q, [p.body])) : list);

  // the line stands above the first post seen before, when some new one is above it: "N new", how many
  const cut = $derived.by(() => {
    const i = list.findIndex((p) => p.id > 0 && p.id <= since), n = i > 0 ? list.slice(0, i).filter(fresh).length : 0;
    return n ? { id: list[i].id, n } : null;
  });

  // older posts: the next page under the last one (they come in under it, nothing above moves)
  let older = $state(false);
  async function earlier() {
    haptic.tap(); older = true;
    try { await loadOlder(); } catch (e) { fail(e); } finally { older = false; }
  }

  // a visit starts when the tab comes into view: the line between new and seen is where the last one ended
  // (declared before the effect below that moves the mark: effects run in order)
  $effect(() => { if (here) untrack(() => { since = readSeen(); void loadChannel().then(seek); }); });
  $effect(() => {
    if (!here) return;
    const top = Math.max(0, ...(channel.feed ?? []).filter((p) => p.msg).map((p) => p.id));
    if (top > untrack(readSeen)) try { localStorage.setItem(SEEN, String(top)); } catch { /* private mode: no line next time */ }
  });

  // fresh while open: back from the background (Telegram's activated, the page shown again) and every 30 s while seen;
  // a new post slides in at the top, the rest glide down (flip)
  $effect(() => {
    if (!here) return;
    const pull = () => { if (!document.hidden) void loadChannel(); };
    const every = setInterval(pull, 30_000);
    document.addEventListener('visibilitychange', pull);
    const off = on('activated', pull);
    return () => { clearInterval(every); document.removeEventListener('visibilitychange', pull); off(); };
  });

  // the bot's "Open in the app" (startapp=fp_<id>): once the feed is fresh, that post opened in full, scrolled to the
  // middle and lit for a moment; one not in the feed (deleted, taken down): the tab and a quiet word, unless it may
  // simply be older than the pages held
  let lit = $state<number | null>(null);
  async function seek() {
    const id = channel.focus;
    if (id == null) return;
    channel.focus = null;
    if (!channel.feed?.some((p) => p.id === id)) {
      if (!channel.more || id > Math.min(...channel.feed!.filter((p) => p.id > 0).map((p) => p.id))) say(t('fc.gone'), 'thinking_face_3d');
      return;
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
    : p.status === 'hidden' ? { tone: 'quiet', key: 'fc.hidden' } as const : !p.msg ? { tone: 'quiet', key: 'fc.publishing' } as const : null;
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

  function fail(e: unknown) {
    haptic.error();
    say(t(e instanceof ApiErr && e.code === 'rate_limited' ? 'fc.slow' : 'common.error'), 'pleading_face_3d');
  }

  async function drop(p: ChannelFeedPost) {
    if (!(await sheets.ask({ title: t('fc.deleteAsk'), text: t('fc.deleteText'), ok: t('fc.delete'), cancel: t('common.cancel'), danger: true }))) return;
    const before = channel.feed;
    channel.feed = (channel.feed ?? []).filter((x) => x.id !== p.id); haptic.ok(); touched();
    try { await api.deleteChannelPost(p.id); } catch (e) { channel.feed = before; fail(e); }
  }

  // every post in the channel: ⋯, the same on every card. Someone else's: Report (into the admin's queue, whose it is
  // stays hidden); mine: answer as the mask (an anonymous one) and Delete, inside it, so nothing on the card says whose
  function more(e: MouseEvent, p: ChannelFeedPost) {
    menu(e.currentTarget as Element, p.mine ? [
      ...(p.anon ? [{ label: t('fcr.entry'), icon: MessageCircleReply, onselect: () => sheets.channelReply({ id: p.id, body: p.body }) }] : []),
      { label: t('fc.delete'), icon: Trash2, destructive: true, onselect: () => drop(p) },
    ] : [{ label: t('cm.report'), icon: Flag, destructive: true, onselect: () => sheets.report('fpost', p.id, p.body.slice(0, 120)) }], 'end');
  }

  // pass a post on: our bot's card (its opening words, a button into it by id only: never whose), as an event's
  const share = (p: ChannelFeedPost) => {
    haptic.tap();
    shareCard({ kind: 'fp', id: String(p.id) }, `https://t.me/KBTUappBot?startapp=fp_${p.id}`, t('fc.sharedPost'))
      .then((sent) => { if (sent) say(phrase('say.shared'), 'party_popper_3d'); })
      .catch(() => { haptic.error(); say(t('common.error'), 'warning_3d'); });
  };

  // the comments, in Telegram: its button alone opens them
  const talk = (p: ChannelFeedPost) => { haptic.tap(); openLink(comments(p)); };
</script>

<div class="page scroll" bind:this={scroller} onscroll={(e) => { atTop = e.currentTarget.scrollTop < PULL + 40; }}>
  <PullSearch bind:value={q} placeholder={t('fc.search')} />
  <!-- new posts from the refresh while I read further down: a pill, never a jump -->
  <div class="pill">{#if waiting && !atTop}<span class="pin" transition:slide={{ duration: 220, axis: 'y' }}>
    <Button kind="glass" size="s" onclick={seeNew}>{#snippet icon()}<ArrowUp size={16} strokeWidth={2.4} />{/snippet}{tn('fc.newSince', waiting)}</Button>
  </span>{/if}</div>
  <!-- the way to write: a glass capsule, my face and a quiet prompt, the pen at the end; the whole capsule a tap -->
  <button class="compose glass glass-pill" class:away={channel.writing > 0} data-compose onclick={write}>
    {#if me}<Avatar person={me} size={36} tappable={false} />{:else}<span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>{/if}
    <span class="prompt ellipsis">{t('fc.share')}</span>
    <span class="pen" aria-hidden="true"><SquarePen size={18} strokeWidth={2} /></span>
  </button>
  <!-- the tab's two side doors, small glass pills under the composer (two full cards here crowded the feed's head):
       the subjects' cards (SUBJECTS_FILE) and the other way to speak up (APPEALS: to the Student Government alone) -->
  {#if me?.subjects || me?.appeals}
    <div class="doors">
      {#if me?.subjects}<Button kind="glass" size="s" onclick={() => { haptic.tap(); sheets.subjects(); }}>{#snippet icon()}<BookOpen size={16} strokeWidth={2} />{/snippet}{t('sj.row')}</Button>{/if}
      {#if me?.appeals}<Button kind="glass" size="s" onclick={() => { haptic.tap(); sheets.appeals(); }}>{#snippet icon()}<Megaphone size={16} strokeWidth={2} />{/snippet}{t('apl.chip')}</Button>{/if}
    </div>
  {/if}

  {#if channel.feed?.length}
    <div class="feed">
      {#each matched as p, i (p.id)}
        {@const m = p.mine ? mark(p) : null}
        {@const live = !!p.msg && p.status === 'live'}
        {@const why = p.mine && p.human ? heldWhy(p) : undefined}
        {@const quote = p.mine && p.human ? (channel.why[p.id] ?? p.review?.explain)?.quote : undefined}
        <!-- one element per post (flip needs it) -->
        <div class="item" animate:flip={{ duration: 420, easing: cubicOut }} transition:slide={{ duration: 360, easing: cubicOut }}>
        {#if !searching && cut?.id === p.id}<div class="nw" role="separator"><span class="nwl"><ArrowUp size={12} strokeWidth={2.5} />{tn('fc.newSince', cut.n)}</span></div>{/if}
        <article class="post" style:--i={Math.min(i, 8)} class:off={p.status === 'hidden'} class:lit={lit === p.id} data-post={p.id}>
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
              <span class="meta"><span>{ago(p.at)}</span>
                {#if m}<span class="mk {m.tone}">{t(m.key)}</span>
                {:else if p.hot && live}<span class="mk hot">{t('fc.hot')}</span>{/if}</span>
            </span>
            {#if live}<span class="end"><IconButton kind="plain" size="s" icon={Ellipsis} label={t('common.more')} onclick={(e) => more(e, p)} /></span>
            {:else if p.mine && p.id > 0}<span class="end"><IconButton kind="plain" size="s" icon={Trash2} label={t('fc.delete')} onclick={() => drop(p)} /></span>{/if}
          </div>
          <p class="tx" class:fade={long[p.id] && !open[p.id]} class:open={open[p.id]} style:--h="{full[p.id] ?? 0}px" use:measure={p.id}><Marked text={p.body} {quote} /></p>
          <!-- the photos (up to 4, the channel's album): a tap shows them whole -->
          {#if p.photos?.length}<div class="pics n{p.photos.length}" style:--ar={p.photos.length === 1 ? Math.min(2, Math.max(0.75, p.photos[0].w / p.photos[0].h)) : null}>{#each p.photos as ph, i (i)}<button class="ph" aria-label={t('fc.photo')}
            onclick={() => sheets.photos(p.photos.map((x, j) => ({ ...x, id: j + 1, by: null, mine: p.mine, canDelete: false })), i)}><img src={ph.thumb} alt="" loading="lazy" decoding="async" /></button>{/each}</div>{/if}
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
          {#if live}
            <div class="acts">
              <!-- Telegram's reactions as small counts, read-only (left in Telegram); none: nothing -->
              {#if p.reactions.length}<span class="rx" role="img" aria-label="{t('fc.reactions')}: {p.reactions.map((r) => `${glyph(r.emoji)} ${r.n}`).join(', ')}">
                {#each p.reactions as r (r.emoji)}<span class="r"><span class="e">{glyph(r.emoji)}</span>{compact(r.n)}</span>{/each}
              </span>{/if}
              <!-- the talk lives in Telegram: who replied (faces; no ids come: a face's colour by its letter), then one button -->
              {#if p.faces.length}<span class="faces" aria-hidden="true">{#each p.faces as f, i (i)}<span class="f" style:z-index={p.faces.length - i}><Avatar person={{ ...f, id: f.name.charCodeAt(0) }} size={20} tappable={false} /></span>{/each}</span>{/if}
              <span class="share"><IconButton kind="plain" size="s" icon={Share} label={t('event.share')} onclick={() => share(p)} /></span>
              <span class="talk"><Button kind="gray" size="s" label="{t('fc.comments')}{p.comments ? `: ${p.comments}` : ''}" onclick={() => talk(p)}>
                {#snippet icon()}<TelegramMark size={16} />{/snippet}<span class="go">{t('fc.discuss')}{#if p.comments}<span class="n">{compact(p.comments)}</span>{/if}<ArrowUpRight size={14} strokeWidth={2.4} aria-hidden="true" /></span>
              </Button></span>
            </div>
          {/if}
        </article>
        </div>
      {/each}
      {#if searching && !matched.length}<EmptyState inline text={t('clubs.nothing')} />{/if}
    </div>
    {#if channel.more}<div class="earlier"><Button kind="plain" size="m" loading={older} onclick={earlier}>{t('fc.earlier')}</Button></div>{/if}
  {:else if channel.feed}
    <EmptyState icon={TAB_ICON.forum} title={t('fc.emptyTitle')} text={t('fc.emptyText')} />
  {/if}

  <div class="tail"></div>
</div>

<style>
  /* the ground: three soft cool lights that stay put while the feed scrolls (a scroller's own background doesn't
     move with its content), so every pane and the capsule have something to bend. Static paint, no filter, no motion:
     nothing to stop under lowfx or reduced motion.
     ponytail: still lights; a slow drift on a layer of its own (transform only) if the owner wants it alive */
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column;
    --pane: rgba(255, 255, 255, 0.05); --pane-sheen: rgba(255, 255, 255, 0.05);
    --pane-hi: rgba(255, 255, 255, 0.42); --pane-lo: rgba(255, 255, 255, 0.14); --pane-rim: rgba(255, 255, 255, 0.07);
    --pane-lift: 0 16px 30px -22px rgba(0, 0, 0, 0.7);
    background:
      radial-gradient(90% 38% at 8% 30%, rgba(59, 107, 255, 0.24), transparent 70%),
      radial-gradient(75% 40% at 105% 58%, rgba(124, 92, 255, 0.15), transparent 70%),
      radial-gradient(85% 50% at -5% 95%, rgba(40, 160, 255, 0.13), transparent 70%); }
  /* light: white rims vanish on white, so a pane is a milky body with a white lit arc, an ink reflection and a navy lift */
  :global(:root[data-theme='light']) .page {
    --pane: rgba(255, 255, 255, 0.56); --pane-sheen: rgba(255, 255, 255, 0.55);
    --pane-hi: var(--lg-rim-hi); --pane-lo: rgba(11, 20, 51, 0.16); --pane-rim: rgba(11, 20, 51, 0.05);
    --pane-lift: 0 1px 2px rgba(24, 36, 90, 0.04), 0 14px 28px -18px rgba(24, 36, 90, 0.22);
    background:
      radial-gradient(90% 38% at 8% 30%, rgba(59, 107, 255, 0.2), transparent 70%),
      radial-gradient(75% 40% at 105% 58%, rgba(150, 110, 255, 0.15), transparent 70%),
      radial-gradient(85% 50% at -5% 95%, rgba(60, 180, 255, 0.16), transparent 70%); }
  .page > :global(*) { flex-shrink: 0; }
  /* a post: a clear pane over the lights. The glass family's recipe (base.css, ui/Button) without the live blur: a
     translucent body with a sheen in its top, a rim bright on the arc that faces the light and dim on the opposite
     one (two gradients through a ring mask, painted once), a soft lift */
  .post { border-radius: var(--r-xl); background: linear-gradient(180deg, var(--pane-sheen), transparent 96px) var(--pane); box-shadow: var(--pane-lift); }
  .post::after { content: ''; position: absolute; inset: 0; border-radius: inherit; pointer-events: none; padding: 1px;
    background:
      radial-gradient(ellipse 60% 110px at 22% 0%, var(--pane-hi), transparent 72%),
      radial-gradient(ellipse 55% 90px at 78% 100%, var(--pane-lo), transparent 75%),
      var(--pane-rim);
    -webkit-mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    -webkit-mask-composite: xor;
    mask-composite: exclude; }

  /* the composer: the capsule's glass (base.css .glass-pill: the one live blur here besides the doors'), my face, a
     quiet prompt, the pen */
  .compose { position: relative; display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3); border-radius: var(--r-full); text-align: left;
    transition: transform 450ms var(--ease-bounce); }
  .compose:active { transform: scale(0.985); transition-duration: 80ms; }
  .compose.away { visibility: hidden; } /* it is the writing window meanwhile (ChannelCompose grows out of it and folds back) */
  /* the side doors: a row of small glass pills, no card; a scroller on a narrow phone (4 px above: their hit areas;
     the room below, taken back by the margin: their lift, which the scroller would cut) */
  .doors { display: flex; gap: var(--s-2); margin: var(--s-3) calc(-1 * var(--gutter)) -14px; padding: 4px var(--gutter) 18px; overflow-x: auto; scrollbar-width: none; }
  .doors :global(.btn) { box-shadow: var(--lg-bevel), var(--lg-lift); }
  .doors::-webkit-scrollbar { display: none; }
  /* the "N new" pill: floats under the capsule, takes no room in the list */
  .pill { position: sticky; top: calc(var(--head-bottom) + var(--s-2) - var(--page-top)); z-index: var(--z-sticky); height: 0; display: flex; justify-content: center; }
  .pin { display: flex; height: max-content; }
  .prompt { flex: 1; min-width: 0; font: 450 var(--fs-body)/1.3 var(--font-text); color: var(--text-3); }
  /* the pen: a quiet lens in the capsule, not an accent blob (a saturated blue circle read as childish); the whole capsule is the tap */
  .pen { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--fill); color: var(--text);
    box-shadow: inset 0 1px 0.5px var(--lg-rim-lo), inset 0 0 0 0.5px var(--line-2); }

  .feed { display: flex; flex-direction: column; gap: var(--s-3); margin-top: var(--s-3); }
  /* a post: the head (face, name and when, the menu), the words, the row under them */
  .post { position: relative; display: flex; flex-direction: column; padding: var(--s-4);
    animation: rise 420ms var(--ease) backwards; animation-delay: calc(var(--i) * 40ms); /* the first screen settles top down */ }
  .post:has(.acts) { padding-bottom: var(--s-3); }
  /* the line between the new and the seen: a word on a hairline in the accent, between the cards */
  .nw { display: flex; align-items: center; gap: var(--s-2); margin: var(--s-1) var(--s-2) var(--s-3);
    font: 600 var(--fs-cap)/1 var(--font-text); color: var(--accent-text); letter-spacing: 0.02em; }
  .nw::before, .nw::after { content: ''; flex: 1; height: 1px; background: currentColor; opacity: 0.35; }
  .nwl { display: inline-flex; align-items: center; gap: 3px; } /* the arrow: the new ones are above the line */
  /* the post the bot's button pointed at: an accent wash that fades */
  .post.lit { animation: lit 1.8s var(--ease); }
  @keyframes lit { 0%, 45% { background: var(--accent-soft); } }
  .post.off { opacity: 0.6; }

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
  @media (prefers-reduced-motion: reduce) { .chk span { animation: none; width: 100%; opacity: 0.5; } }

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

  /* the row under the words: Telegram's reactions on the left (bare counts: they are read-only, a chip promised a tap),
     the talk's faces and its one button on the right (under the thumb); 36 seen, 44 to the finger */
  .acts { display: flex; align-items: center; gap: var(--s-2); min-height: 36px; margin-top: var(--s-3); }
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
  /* the button's glass on a clear body here (Button's sits on the solid surface): the pane and its light show through */
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
