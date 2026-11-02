<script lang="ts">
  // The Forum tab (Nov 1: the in-app forum became the public channel @KBTUappForum). Posts only: the channel's feed,
  // newest first, laid out as Threads (owner, Nov 2): no boxes, the words the hero, a hairline between posts from the
  // words' edge; the face on the left (an accent dot on it: new since my last visit), name · time, the words. Under them
  // one quiet row (owner, rounds 3-4: "why two buttons", "too loud"): Telegram's reactions on the left as plain emoji
  // and counts, which open the post in the channel (reacting is the one reason to go there), and on the right who
  // replied, the bubble and how many. A tap on the post opens its comments too, the main thing. My own posts are marked (on their way, under review, removed) and can be deleted.
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
  import Heart from '@lucide/svelte/icons/heart';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import Avatar from '../../ui/Avatar.svelte';
  import { initials } from '../../ui/OrgLogo.svelte';
  import { api, ApiErr, type ChannelFeedPost } from '../../lib/api';
  import { session, asStudent } from '../../lib/state/session.svelte';
  import { channel, loadChannel, touched } from '../../lib/state/channel.svelte';
  import { ui, say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, on, openLink } from '../../lib/tg';
  import { ago } from '../../lib/time';
  import { compact } from '../../lib/chats';
  import { TAB_ICON } from '../../ui/icons';
  import EmptyState from '../../ui/EmptyState.svelte';

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
  // the line stands above the first post seen before, when some new one is above it
  const cut = $derived.by(() => {
    const f = channel.feed ?? [], i = f.findIndex((p) => p.id > 0 && p.id <= since);
    return i > 0 && f.slice(0, i).some(fresh) ? f[i].id : null;
  });

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
    open[id] = true;
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
    : p.status === 'held' ? { tone: 'warning', key: 'fc.held' } as const
    : p.status === 'hidden' ? { tone: 'quiet', key: 'fc.hidden' } as const : { tone: 'accent', key: 'fc.mine' } as const;

  // a long post starts at four lines with a fade and a quiet "More" that opens it in place (its height glides to the
  // full one); a short one shows whole. long/full: measured while clamped, per post
  const long = $state<Record<number, boolean>>({}), open = $state<Record<number, boolean>>({}), full = $state<Record<number, number>>({});
  function measure(el: HTMLElement, id: number) {
    const check = () => { full[id] = el.scrollHeight; if (!open[id]) long[id] = el.scrollHeight > el.clientHeight + 2; };
    const ro = new ResizeObserver(check);
    ro.observe(el); check();
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

  // the reactions: a soft pop, then the post in the channel, where reactions are left (they are Telegram's, read-only
  // here: the counts move when Telegram's do)
  let popped = $state<number | null>(null);
  function react(p: ChannelFeedPost) {
    haptic.select(); popped = p.id;
    setTimeout(() => { if (popped === p.id) popped = null; openLink(`${CHANNEL}/${p.msg}`); }, 260);
  }

  // the comments: the pill, or a tap anywhere on the post but its buttons (Enter and Space too)
  const talk = (p: ChannelFeedPost) => { haptic.tap(); openLink(comments(p)); };
  const press = (e: MouseEvent, p: ChannelFeedPost) => { if (!(e.target as Element).closest('button, a, .nw')) talk(p); };
  const key = (e: KeyboardEvent, p: ChannelFeedPost) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); talk(p); } };
</script>

<div class="page scroll">
  <!-- the way to write: my face and a quiet prompt, the pen at the end (Threads' composer); the whole row a tap -->
  <button class="compose" onclick={write}>
    {#if me}<Avatar person={me} size={36} tappable={false} />{:else}<span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>{/if}
    <span class="prompt ellipsis">{t('fc.share')}</span>
    <span class="pen" aria-hidden="true"><SquarePen size={18} strokeWidth={2} /></span>
  </button>

  {#if channel.feed?.length}
    <div class="feed">
      {#each channel.feed as p, i (p.id)}
        {@const m = p.mine ? mark(p) : null}
        {@const live = !!p.msg && p.status === 'live'}
        <!-- one element per post (flip needs it): a live one is a button into its comments, the others plain (role by state) -->
        <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
        <div class="post" style:--i={Math.min(i, 8)} class:tap={live} class:off={p.status === 'hidden'} class:lit={lit === p.id} class:cut={cut === p.id} data-post={p.id}
          role={live ? 'button' : undefined} tabindex={live ? 0 : undefined} onclick={live ? (e) => press(e, p) : undefined} onkeydown={live ? (e) => key(e, p) : undefined}
          animate:flip={{ duration: 420, easing: cubicOut }} transition:slide={{ duration: 360, easing: cubicOut }}>
          {#if cut === p.id}<div class="nw" role="separator"><span class="nwl"><ArrowUp size={12} strokeWidth={2.5} />{t('fc.newSince')}</span></div>{/if}
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
              {:else if p.hot && live}<span class="mk hot">🔥 {t('fc.hot')}</span>{/if}
              {#if p.mine && p.id > 0}<button class="del" aria-label={t('fc.delete')} onclick={() => drop(p)}><Trash2 size={16} strokeWidth={2} /></button>{/if}
            </div>
            <p class="tx" class:fade={long[p.id] && !open[p.id]} class:open={open[p.id]} style:--h="{full[p.id] ?? 0}px" use:measure={p.id}>{p.body}</p>
            {#if long[p.id] && !open[p.id]}<button class="more" onclick={() => { haptic.tap(); open[p.id] = true; }}>{t('common.more')}</button>{/if}
            {#if live}
              <div class="acts">
                <!-- Telegram's reactions, plain emoji and counts; none yet: a small heart. To the channel, where they are left -->
                <button class="rx" class:pop={popped === p.id} onclick={() => react(p)}
                  aria-label="{t('fc.reactions')}{p.reactions.length ? `: ${p.reactions.map((r) => `${glyph(r.emoji)} ${r.n}`).join(', ')}` : ''}">
                  {#each p.reactions as r (r.emoji)}<span class="r"><span class="e">{glyph(r.emoji)}</span>{compact(r.n)}</span>
                  {:else}<span class="r none"><Heart size={19} strokeWidth={1.8} /></span>{/each}
                </button>
                <!-- the way to the talk: who replied (faces; no ids come: a face's colour by its letter), the bubble, how many -->
                <button class="talk" onclick={() => talk(p)} aria-label="{t('fc.comments')}{p.comments ? `: ${p.comments}` : ''}">
                  {#if p.faces.length}<span class="faces">{#each p.faces as f, i (i)}<Avatar person={{ ...f, id: f.name.charCodeAt(0) }} size={18} tappable={false} />{/each}</span>{/if}
                  <MessageCircle size={18} strokeWidth={1.8} />
                  {#if p.comments}<span>{compact(p.comments)}</span>{/if}
                </button>
              </div>
            {/if}
          </div>
        </div>
      {/each}
    </div>
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
  .compose::after, .post + .post::before { content: ''; position: absolute; left: var(--rule); right: 0; height: 0.5px; background: var(--separator); }
  .compose::after { bottom: 0; }
  .post + .post::before { top: 0; }
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
  .tap { cursor: pointer; -webkit-tap-highlight-color: transparent; }
  .tap:active:not(:has(button:active)) { background: var(--surface); transition-duration: 60ms; }
  .tap:focus-visible { outline: 2px solid var(--accent); outline-offset: -2px; }
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
  .head b { font: 650 var(--fs-body)/1.3 var(--font-text); color: var(--text); letter-spacing: -0.01em; }
  .name { display: flex; min-width: 0; padding: 0; text-align: left; }
  .head > .name, .head > b { flex-shrink: 0; max-width: 62%; } /* the name keeps its room; the mark gives way */
  .name:active { opacity: 0.6; }
  .when, .mk { flex: none; font: 400 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); white-space: nowrap; }
  .mk { flex-shrink: 10; min-width: 0; overflow: hidden; text-overflow: ellipsis; } /* at 320 the mark gives way before the name */
  .mk::before { content: '·'; margin-right: 6px; color: var(--text-3); }
  .mk.accent { color: var(--accent-text); }
  .mk.warning, .mk.hot { color: var(--warning-text); }
  .del { align-self: center; margin: -12px -12px -12px auto; width: 44px; height: 44px; display: grid; place-items: center; flex: none;
    color: var(--text-3); border-radius: 50%; }
  .del:active { color: var(--danger-text); }

  /* the words: four lines and a fade while long and closed; open, the height glides to the whole */
  .tx { margin-top: 2px; font: 450 var(--fs-body)/1.47 var(--font-text); letter-spacing: -0.006em; color: var(--text); white-space: pre-line; overflow-wrap: break-word;
    max-height: 5.7em; overflow: hidden; transition: max-height 420ms var(--ease); }
  .tx.fade { -webkit-mask-image: linear-gradient(to bottom, black 50%, transparent); mask-image: linear-gradient(to bottom, black 50%, transparent); }
  .tx.open { max-height: var(--h); }
  .post.off .tx { color: var(--text-3); }
  .more { margin-top: 2px; padding: var(--s-1) 0; font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }

  /* the row under the words, on the words' edges, quiet: the reactions left, the talk right (under the thumb); no
     fills, a press only dims; 44 high to hit, the air around the marks is the target */
  .acts { display: flex; align-items: center; justify-content: space-between; gap: var(--s-2); margin: -4px 0 -2px; } /* the hit areas reach into the air */
  .rx, .talk { display: inline-flex; align-items: center; min-width: 44px; height: 44px; color: var(--text-2);
    font: 500 var(--fs-sub)/1 var(--font-text); font-variant-numeric: tabular-nums; transition: opacity var(--t-base) var(--ease), transform 380ms var(--ease-bounce); }
  .rx:active, .talk:active { opacity: 0.45; transform: scale(0.96); transition-duration: 60ms; }
  .rx { gap: var(--s-3); padding-right: var(--s-3); }
  .r { display: inline-flex; align-items: center; gap: 4px; }
  .e { font-size: var(--fs-body); line-height: 1; }
  .r.none { color: var(--text-2); } /* an empty heart still reads as a button */
  /* the tap's answer: the reactions pop softly (the empty heart fills red), then the channel */
  .rx.pop .r { animation: pop 420ms var(--ease-bounce); }
  .rx.pop .none { color: var(--danger); }
  .rx.pop .none :global(svg) { fill: currentColor; }
  @keyframes pop { 0% { transform: scale(0.9); } 45% { transform: scale(1.18); } 100% { transform: scale(1); } }
  .talk { justify-content: flex-end; gap: 6px; padding-left: var(--s-3); }
  .talk :global(svg) { flex: none; }
  .faces { display: flex; margin-right: 4px; }
  .faces :global(.av) { box-shadow: 0 0 0 1.5px var(--bg); }
  .faces :global(.av + .av) { margin-left: -5px; }
  .faces :global(.av:first-child) { z-index: 2; } /* the newest on top */
  .faces :global(.av:nth-child(2)) { z-index: 1; }
  @media (max-width: 359px) { .r:nth-child(3) { display: none; } } /* 320: two reactions */

  @keyframes rise { from { opacity: 0; transform: translateY(8px); } }
  .tail { height: calc(var(--bottom) + var(--s-8)); }
</style>
