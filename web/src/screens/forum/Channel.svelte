<script lang="ts">
  // The Forum tab (Nov 1: the in-app forum became the public channel @KBTUappForum). Posts only: the channel's feed,
  // newest first and nothing else (owner, Nov 3: a pinned "popular" block put old posts first; a post being discussed
  // says so in place), laid out as Threads (owner, Nov 2): no boxes, the words the hero, a hairline between posts from
  // the words' edge; the face on the left (an accent dot on it: new since my last visit), name · time, the words. Under
  // them one quiet row: Telegram's reactions on the left as counts (read-only: they are Telegram's), and on the right
  // the one way to the comments, which live in Telegram and say so ("Discuss in Telegram", who replied, how many); the
  // post itself opens nothing. My own posts are marked (on their way, under review, removed) and can be deleted.
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
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Flag from '@lucide/svelte/icons/flag';
  import { menu } from '../../ui/menu';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import Avatar from '../../ui/Avatar.svelte';
  import { initials } from '../../ui/OrgLogo.svelte';
  import { api, ApiErr, type ChannelFeedPost } from '../../lib/api';
  import { session, asStudent } from '../../lib/state/session.svelte';
  import { channel, loadChannel, loadOlder, touched } from '../../lib/state/channel.svelte';
  import { ui, say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { haptic, on, openLink } from '../../lib/tg';
  import { ago } from '../../lib/time';
  import { compact } from '../../lib/chats';
  import { TAB_ICON } from '../../ui/icons';
  import EmptyState from '../../ui/EmptyState.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Button from '../../ui/Button.svelte';

  const CHANNEL = 'https://t.me/KBTUappForum';
  const me = $derived(session.me);
  const here = $derived(ui.tab === 'forum');
  // "New since the last visit": the newest channel post seen, kept in this browser (a convenience: lost storage only
  // means no line). since: where this visit's line is (0: a first visit, nothing marked); while here, all on screen counts
  // as seen for the next one
  const SEEN = 'kb-fc-seen';
  function readSeen(): number { try { return Number(localStorage.getItem(SEEN)) || 0; } catch { return 0; } }
  let since = $state(0);
  const fresh = (p: ChannelFeedPost) => since > 0 && p.id > since && !p.mine && !!p.msg;

  // what's on screen: the posts already shown (known), the older pages under them, mine; a refresh's others wait for
  // the pill (or come in by themselves while I'm at the top). known empty: the first look, all of it
  let known = $state(new Set<number>()), atTop = $state(true), scroller = $state<HTMLElement>();
  const floor = $derived(known.size ? Math.min(...known) : Infinity);
  const shown = (p: ChannelFeedPost) => p.id < 0 || p.mine || known.has(p.id) || p.id < floor;
  const list = $derived((channel.feed ?? []).filter(shown));
  const waiting = $derived((channel.feed ?? []).filter((p) => !shown(p)).length);
  const showAll = () => { known = new Set((channel.feed ?? []).map((p) => p.id)); };
  $effect(() => { if (channel.feed && (atTop || !known.size) && (waiting || !known.size)) untrack(showAll); });
  function seeNew() { haptic.tap(); showAll(); scroller?.scrollTo({ top: 0, behavior: 'smooth' }); }

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
  // middle and lit for a moment; one not in the feed (deleted, taken down): just the tab
  let lit = $state<number | null>(null);
  async function seek() {
    const id = channel.focus;
    if (id == null) return;
    channel.focus = null;
    if (!channel.feed?.some((p) => p.id === id)) return;
    showAll(); open[id] = true;
    await tick();
    document.querySelector(`[data-post="${id}"]`)?.scrollIntoView({ block: 'center', behavior: 'smooth' });
    lit = id;
    setTimeout(() => { if (lit === id) lit = null; }, 1800);
  }

  // the comments in Telegram: opened at the bot's first comment (?comment=, Telegram's link into a post's comments);
  // an older post without one: the post itself, its Comments bar under it
  const comments = (p: ChannelFeedPost) => `${CHANNEL}/${p.msg}${p.thread ? `?comment=${p.thread}` : ''}`;
  // a reaction as plain text (the heart's label): a custom emoji (only its id comes) and a paid star as their nearest
  const glyph = (e: string) => e.startsWith('custom:') ? '✨' : e === 'paid' ? '⭐' : e;

  // my own post's mark beside the time: on its way (the AI looking), under review, removed, else simply "mine"
  const mark = (p: ChannelFeedPost) => p.id < 0 ? { tone: 'quiet', key: 'fc.checking' } as const
    : p.status === 'held' ? (p.human ? { tone: 'warning', key: 'fc.human' } as const : { tone: 'quiet', key: 'fc.checking' } as const)
    : p.status === 'hidden' ? { tone: 'quiet', key: 'fc.hidden' } as const : { tone: 'accent', key: 'fc.mine' } as const;

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
    if (!me?.student) asStudent(() => sheets.channelPost());
    else if (me.student.manual) sheets.login();
    else sheets.channelPost();
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

  // someone else's post: ⋯ → Report (the app's report sheet; into the admin's queue, whose it is stays hidden)
  function more(e: MouseEvent, p: ChannelFeedPost) {
    menu(e.currentTarget as Element, [{ label: t('cm.report'), icon: Flag, destructive: true, onselect: () => sheets.report('fpost', p.id, p.body.slice(0, 120)) }], 'end');
  }

  // the comments, in Telegram: its button alone opens them
  const talk = (p: ChannelFeedPost) => { haptic.tap(); openLink(comments(p)); };
</script>

<div class="page scroll" bind:this={scroller} onscroll={(e) => { atTop = e.currentTarget.scrollTop < 40; }}>
  <!-- new posts from the refresh while I read further down: a pill, never a jump -->
  <div class="pill">{#if waiting && !atTop}<span class="pin" transition:slide={{ duration: 220, axis: 'y' }}>
    <Button kind="glass" size="s" onclick={seeNew}>{#snippet icon()}<ArrowUp size={16} strokeWidth={2.4} />{/snippet}{tn('fc.newSince', waiting)}</Button>
  </span>{/if}</div>
  <!-- the way to write: my face and a quiet prompt, the pen at the end (Threads' composer); the whole row a tap -->
  <button class="compose" onclick={write}>
    {#if me}<Avatar person={me} size={36} tappable={false} />{:else}<span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>{/if}
    <span class="prompt ellipsis">{t('fc.share')}</span>
    <span class="pen" aria-hidden="true"><SquarePen size={18} strokeWidth={2} /></span>
  </button>

  {#if channel.feed?.length}
    <div class="feed">
      {#each list as p, i (p.id)}
        {@const m = p.mine ? mark(p) : null}
        {@const live = !!p.msg && p.status === 'live'}
        <!-- one element per post (flip needs it) -->
        <div class="item" animate:flip={{ duration: 420, easing: cubicOut }} transition:slide={{ duration: 360, easing: cubicOut }}>
        <div class="post" style:--i={Math.min(i, 8)} class:off={p.status === 'hidden'} class:lit={lit === p.id} class:cut={cut?.id === p.id} data-post={p.id}>
          {#if cut?.id === p.id}<div class="nw" role="separator"><span class="nwl"><ArrowUp size={12} strokeWidth={2.5} />{tn('fc.newSince', cut.n)}</span></div>{/if}
          <div class="rail">
            {#if p.person}<Avatar person={p.person} size={36} />
            {:else}
              <!-- anonymous: the mask; an author no longer here (a deleted account): the signature's initials -->
              <span class="av" class:anon={p.anon} aria-hidden="true">{#if p.anon}<VenetianMask size={18} strokeWidth={2} />{:else}{initials(p.sign)}{/if}</span>
            {/if}
            {#if fresh(p)}<span class="dot" aria-hidden="true"></span>{/if}
          </div>
          <div class="main">
            <div class="head">
              {#if p.person}<button class="name" onclick={() => { haptic.tap(); sheets.person(p.person!.id); }}><b class="ellipsis">{p.person.name}</b></button>
              {:else}<b class="ellipsis">{p.sign}</b>{/if}
              <span class="when">{ago(p.at)}</span>
              {#if m}<span class="mk {m.tone}">{t(m.key)}</span>
              {:else if p.hot && live}<span class="mk hot">{t('fc.hot')}</span>{/if}
              {#if p.mine && p.id > 0}<span class="del"><IconButton kind="plain" size="s" icon={Trash2} label={t('fc.delete')} onclick={() => drop(p)} /></span>
              {:else if live && !p.mine}<span class="del"><IconButton kind="plain" size="s" icon={Ellipsis} label={t('common.more')} onclick={(e) => more(e, p)} /></span>{/if}
            </div>
            <p class="tx" class:fade={long[p.id] && !open[p.id]} class:open={open[p.id]} style:--h="{full[p.id] ?? 0}px" use:measure={p.id}>{p.body}</p>
            {#if p.mine && p.human}<p class="why">{t('fc.humanWhy')}</p>{/if}
            <!-- the AI looking: a running bar under the words, not just a word (owner, Nov 2) -->
            {#if p.id < 0}<div class="chk" role="progressbar" aria-label={t('fc.checking')}><span></span></div>{/if}
            {#if long[p.id] && !open[p.id]}<span class="more"><Button kind="plain" size="s" onclick={() => { open[p.id] = true; }}>{t('common.more')}</Button></span>{/if}
            {#if live}
              <div class="acts">
                <!-- Telegram's reactions as counts, read-only (left in Telegram); none: nothing -->
                {#if p.reactions.length}<span class="rx" role="img" aria-label="{t('fc.reactions')}: {p.reactions.map((r) => `${glyph(r.emoji)} ${r.n}`).join(', ')}">
                  {#each p.reactions as r (r.emoji)}<span class="r"><span class="e">{glyph(r.emoji)}</span>{compact(r.n)}</span>{/each}
                </span>{/if}
                <!-- the one way to the talk, in Telegram: who replied (faces; no ids come: a face's colour by its letter), the words, how many -->
                <button class="talk" onclick={() => talk(p)} aria-label="{t('fc.comments')}{p.comments ? `: ${p.comments}` : ''}">
                  {#if p.faces.length}<span class="faces">{#each p.faces as f, i (i)}<Avatar person={{ ...f, id: f.name.charCodeAt(0) }} size={18} tappable={false} />{/each}</span>{/if}
                  <MessageCircle size={17} strokeWidth={1.9} />
                  <span class="tl">{t('fc.comments')}</span>
                  {#if p.comments}<span class="n">{compact(p.comments)}</span>{/if}
                </button>
              </div>
              <!-- my anonymous post: answering in its comments as the mask, through the bot (ChannelReply) -->
              {#if p.mine && p.anon}<span class="areply"><Button kind="secondary" size="s" onclick={() => sheets.channelReply({ id: p.id, body: p.body })}>{#snippet icon()}<VenetianMask size={16} strokeWidth={2} />{/snippet}{t('fcr.entry')}</Button></span>{/if}
            {/if}
          </div>
        </div>
        </div>
      {/each}
    </div>
    {#if channel.more}<div class="earlier"><Button kind="plain" size="m" loading={older} onclick={earlier}>{t('fc.earlier')}</Button></div>{/if}
  {:else if channel.feed}
    <EmptyState icon={TAB_ICON.forum} title={t('fc.emptyTitle')} text={t('fc.emptyText')} />
  {/if}

  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; }
  .page > :global(*) { flex-shrink: 0; }
  /* the composer and the posts run edge to edge; the hairlines start at the words' edge (Threads) */
  .compose, .feed { margin: 0 calc(-1 * var(--gutter)); }
  .compose, .post { --rule: calc(var(--gutter) + 36px + var(--s-3)); }

  /* the composer: my face, a quiet prompt, the pen; a hairline under it */
  .compose { position: relative; display: flex; align-items: center; gap: var(--s-3); padding: var(--s-1) var(--gutter) var(--s-4); text-align: left;
    transition: background var(--t-base) var(--ease); }
  .compose::after, .item + .item > .post::before { content: ''; position: absolute; left: var(--rule); right: 0; height: 0.5px; background: var(--separator); }
  .compose::after { bottom: 0; }
  .item + .item > .post::before { top: 0; }
  /* the "N new" pill: floats under the capsule, takes no room in the list */
  .pill { position: sticky; top: calc(var(--head-bottom) + var(--s-2) - var(--page-top)); z-index: var(--z-sticky); height: 0; display: flex; justify-content: center; }
  .pin { display: flex; height: max-content; }
  .compose:active { background: var(--surface); transition-duration: 60ms; }
  .prompt { flex: 1; min-width: 0; font: 450 var(--fs-body)/1.3 var(--font-text); color: var(--text-3); }
  .pen { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--accent-soft); color: var(--accent-text);
    transition: transform 380ms var(--ease-bounce); }
  .compose:active .pen { transform: scale(0.9); transition-duration: 80ms; }

  /* a post: the face's rail and the words; under them, when people replied, their faces and the count */
  .post { position: relative; display: grid; grid-template-columns: 36px minmax(0, 1fr); column-gap: var(--s-3);
    padding: var(--s-4) var(--gutter) var(--s-1); animation: rise 420ms cubic-bezier(.2, .9, .25, 1.05) backwards; animation-delay: calc(var(--i) * 40ms); /* the first screen settles top down */
    transition: background var(--t-base) var(--ease); }
  .post:not(:has(.acts)) { padding-bottom: var(--s-4); }
  /* the line between the new and the seen: a word on a hairline in the accent, in place of the post's own hairline */
  .post.cut::before { display: none; }
  .nw { grid-column: 2; display: flex; align-items: center; gap: var(--s-2); margin: calc(-1 * var(--s-2)) calc(-1 * var(--gutter)) var(--s-3) 0; /* from the words' edge, as the hairlines */
    font: 600 var(--fs-cap)/1 var(--font-text); color: var(--accent-text); letter-spacing: 0.02em; }
  .nw::before, .nw::after { content: ''; flex: 1; height: 1px; background: currentColor; opacity: 0.35; }
  .nw::before { display: none; }
  .nwl { display: inline-flex; align-items: center; gap: 3px; } /* the arrow: the new ones are above the line */
  /* the post the bot's button pointed at: an accent wash that fades */
  .post.lit { animation: lit 1.8s var(--ease); }
  @keyframes lit { 0%, 45% { background: var(--accent-soft); } }

  .rail { position: relative; }
  .av { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2);
    color: var(--text-2); font: 600 var(--fs-cap)/1 var(--font-text); letter-spacing: 0.02em; }
  .av.anon { background: var(--fill-2); color: var(--text); }
  /* new since my last visit: a small accent dot on the face's shoulder, cut out of it by the ground */
  .dot { position: absolute; top: 0; right: -1px; width: 10px; height: 10px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 2px var(--bg); }

  .main { min-width: 0; }
  /* name · time, my mark, delete: one line */
  .head { display: flex; align-items: baseline; gap: 6px; min-height: 20px; margin-top: 1px; }
  .head b { font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text); letter-spacing: -0.01em; }
  .name { display: flex; min-width: 0; padding: 0; text-align: left; }
  .head > .name, .head > b { flex-shrink: 0; max-width: 62%; } /* the name keeps its room; the mark gives way */
  .name:active { opacity: 0.6; }
  .when, .mk { flex: none; font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); white-space: nowrap; }
  .mk { flex-shrink: 10; min-width: 0; overflow: hidden; text-overflow: ellipsis; } /* at 320 the mark gives way before the name */
  .mk::before { content: '·'; margin-right: 6px; color: var(--text-3); }
  .chk { position: relative; height: 3px; margin-top: var(--s-2); border-radius: var(--r-full); background: var(--surface-2); overflow: hidden; }
  .chk span { position: absolute; inset: 0 auto 0 0; width: 40%; border-radius: inherit; background: var(--accent); animation: chk 1.1s ease-in-out infinite; }
  @keyframes chk { from { transform: translateX(-100%); } to { transform: translateX(250%); } }
  @media (prefers-reduced-motion: reduce) { .chk span { animation: none; width: 100%; opacity: 0.5; } }
  .mk.accent { color: var(--accent-text); }
  .mk.warning { color: var(--warning-text); }
  .mk.hot { color: var(--warning-text); text-transform: lowercase; } /* being discussed: a quiet tinted word by the time (no emoji: it shouted) */
  .del { align-self: center; display: flex; flex: none; margin: -8px -8px -8px auto; --plain-ink: var(--text-3); }

  /* the words: four lines and a fade while long and closed; open, the height glides to the whole */
  .tx { margin-top: 2px; font: 450 var(--fs-body)/1.47 var(--font-text); letter-spacing: -0.006em; color: var(--text); white-space: pre-line; overflow-wrap: break-word;
    max-height: 5.7em; overflow: hidden; transition: max-height 420ms var(--ease); }
  .why { margin-top: 4px; font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  .tx.fade { -webkit-mask-image: linear-gradient(to bottom, black 50%, transparent); mask-image: linear-gradient(to bottom, black 50%, transparent); }
  .tx.open { max-height: var(--h); }
  .post.off .tx { color: var(--text-3); }
  .more { display: flex; margin: 0 0 0 calc(-1 * var(--s-2)); --plain-ink: var(--text-2); }

  /* the row under the words, on the words' edges, quiet: the reactions left (plain counts), the talk right (under the
     thumb); no fills, a press only dims; 44 high to hit, the air around the marks is the target */
  .acts { display: flex; align-items: center; gap: var(--s-2); margin: -4px 0 -2px; } /* the hit areas reach into the air */
  .rx, .talk { display: inline-flex; align-items: center; height: 44px; color: var(--text-2); font: 500 var(--fs-sub)/1 var(--font-text); font-variant-numeric: tabular-nums; }
  .rx { flex: none; gap: var(--s-3); }
  .r { display: inline-flex; align-items: center; gap: 4px; }
  .e { font-size: var(--fs-body); line-height: 1; }
  .talk { min-width: 0; margin-left: auto; justify-content: flex-end; gap: 6px; padding-left: var(--s-3); color: var(--accent-text);
    transition: opacity var(--t-base) var(--ease), transform 380ms var(--ease-bounce); }
  .talk:active { opacity: 0.45; transform: scale(0.96); transition-duration: 60ms; }
  .talk :global(svg) { flex: none; }
  .tl { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .n { color: var(--text-2); }
  .faces { display: flex; margin-right: 4px; }
  .faces :global(.av) { box-shadow: 0 0 0 1.5px var(--bg); }
  .faces :global(.av + .av) { margin-left: -5px; }
  .faces :global(.av:first-child) { z-index: 2; } /* the newest on top */
  .faces :global(.av:nth-child(2)) { z-index: 1; }
  @media (max-width: 359px) { .r:nth-child(n + 2), .faces { display: none; } } /* 320: the top reaction, the words to the talk */

  .areply { display: flex; margin: 0 0 var(--s-3); }
  .earlier { display: flex; justify-content: center; padding: var(--s-3) 0; }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } }
  .tail { height: calc(var(--bottom) + var(--s-8)); }
</style>
