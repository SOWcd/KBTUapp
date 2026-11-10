<script lang="ts">
  // The Forum tab (Nov 1: the in-app forum became the public channel @KBTUappForum). Posts only: the channel's feed,
  // newest first and nothing else (owner, Nov 3: a pinned "popular" block put old posts first; a post being discussed
  // says so in place). Each post a card on the ground (owner, Nov 4: the flat Threads list on black "limped"): the face
  // (an accent dot on it: new since my last visit), the name over the time, the words; under them Telegram's reactions
  // as small chips (read-only: they are Telegram's) and, on the right, the one way to the comments, which live in
  // Telegram: who replied, and a real button with Telegram's mark and the count. The post itself opens nothing. My own posts are marked (on their way, under review, removed) and can be deleted.
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
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import Lightbulb from '@lucide/svelte/icons/lightbulb';
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
  import { nickName } from '../../lib/i18n/nicks';
  import { haptic, on, openLink } from '../../lib/tg';
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

  // the comments in Telegram: opened at the newest comment, the bot's first with none yet (?comment=, Telegram's link into a post's comments);
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

  // someone else's post: ⋯ → Report (the app's report sheet; into the admin's queue, whose it is stays hidden)
  function more(e: MouseEvent, p: ChannelFeedPost) {
    menu(e.currentTarget as Element, [{ label: t('cm.report'), icon: Flag, destructive: true, onselect: () => sheets.report('fpost', p.id, p.body.slice(0, 120)) }], 'end');
  }

  // the comments, in Telegram: its button alone opens them
  const talk = (p: ChannelFeedPost) => { haptic.tap(); openLink(comments(p)); };
</script>

<div class="page scroll" bind:this={scroller} onscroll={(e) => { atTop = e.currentTarget.scrollTop < PULL + 40; }}>
  <PullSearch bind:value={q} placeholder={t('fc.search')} />
  <!-- new posts from the refresh while I read further down: a pill, never a jump -->
  <div class="pill">{#if waiting && !atTop}<span class="pin" transition:slide={{ duration: 220, axis: 'y' }}>
    <Button kind="glass" size="s" onclick={seeNew}>{#snippet icon()}<ArrowUp size={16} strokeWidth={2.4} />{/snippet}{tn('fc.newSince', waiting)}</Button>
  </span>{/if}</div>
  <!-- the way to write: a card of its own, my face and a quiet prompt, the pen at the end; the whole card a tap -->
  <button class="compose" class:away={channel.writing > 0} data-compose onclick={write}>
    {#if me}<Avatar person={me} size={36} tappable={false} />{:else}<span class="av" aria-hidden="true"><VenetianMask size={18} strokeWidth={2} /></span>{/if}
    <span class="prompt ellipsis">{t('fc.share')}</span>
    <span class="pen" aria-hidden="true"><SquarePen size={18} strokeWidth={2} /></span>
  </button>

  {#if channel.feed?.length}
    <div class="feed">
      {#each matched as p, i (p.id)}
        {@const m = p.mine ? mark(p) : null}
        {@const live = !!p.msg && p.status === 'live'}
        {@const why = p.mine && p.human ? channel.why[p.id] : undefined}
        <!-- one element per post (flip needs it) -->
        <div class="item" animate:flip={{ duration: 420, easing: cubicOut }} transition:slide={{ duration: 360, easing: cubicOut }}>
        {#if !searching && cut?.id === p.id}<div class="nw" role="separator"><span class="nwl"><ArrowUp size={12} strokeWidth={2.5} />{tn('fc.newSince', cut.n)}</span></div>{/if}
        <article class="post" style:--i={Math.min(i, 8)} class:off={p.status === 'hidden'} class:lit={lit === p.id} data-post={p.id}>
          <!-- the face, the name and when, my mark; the post's one menu at the end -->
          <div class="head">
            <span class="rail">
              {#if p.person}<Avatar person={p.person} size={40} />
              {:else}
                <!-- anonymous: the mask; an author no longer here (a deleted account): the signature's initials -->
                <span class="av" class:anon={p.anon} aria-hidden="true">{#if p.anon}<VenetianMask size={19} strokeWidth={2} />{:else}{initials(p.sign)}{/if}</span>
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
            {#if p.mine && p.id > 0}<span class="end"><IconButton kind="plain" size="s" icon={Trash2} label={t('fc.delete')} onclick={() => drop(p)} /></span>
            {:else if live && !p.mine}<span class="end"><IconButton kind="plain" size="s" icon={Ellipsis} label={t('common.more')} onclick={(e) => more(e, p)} /></span>{/if}
          </div>
          <p class="tx" class:fade={long[p.id] && !open[p.id]} class:open={open[p.id]} style:--h="{full[p.id] ?? 0}px" use:measure={p.id}><Marked text={p.body} quote={why?.quote} /></p>
          <!-- the photos (up to 4, the channel's album): a tap shows them whole -->
          {#if p.photos?.length}<div class="pics n{p.photos.length}">{#each p.photos as ph, i (i)}<button class="ph" aria-label={t('fc.photo')}
            onclick={() => sheets.photos(p.photos.map((x, j) => ({ ...x, id: j + 1, by: null, mine: p.mine, canDelete: false })), i)}><img src={ph.thumb} alt="" loading="lazy" decoding="async" /></button>{/each}</div>{/if}
          {#if long[p.id] && !open[p.id]}<span class="more"><Button kind="plain" size="s" onclick={() => { open[p.id] = true; }}>{t('common.more')}</Button></span>{/if}
          <!-- my post the AI passed to a moderator: why, in its words once they come (to me alone), else the plain line -->
          {#if p.mine && p.human}
            <div class="held">
              <p>{why?.reason ?? t('fc.humanWhy')}</p>
              {#if why?.fix}<p class="fix"><Lightbulb size={15} strokeWidth={2} aria-hidden="true" /><span>{why.fix}</span></p>{/if}
            </div>
          {/if}
          <!-- the AI looking: a running bar under the words, not just a word (owner, Nov 2) -->
          {#if p.id < 0}<div class="chk" role="progressbar" aria-label={t('fc.checking')}><span></span></div>{/if}
          {#if live}
            <div class="acts">
              <!-- Telegram's reactions as small counts, read-only (left in Telegram); none: nothing -->
              {#if p.reactions.length}<span class="rx" role="img" aria-label="{t('fc.reactions')}: {p.reactions.map((r) => `${glyph(r.emoji)} ${r.n}`).join(', ')}">
                {#each p.reactions as r (r.emoji)}<span class="r"><span class="e">{glyph(r.emoji)}</span>{compact(r.n)}</span>{/each}
              </span>{/if}
              <!-- the talk lives in Telegram: who replied (faces; no ids come: a face's colour by its letter), then one button -->
              {#if p.faces.length}<span class="faces" aria-hidden="true">{#each p.faces as f, i (i)}<span class="f" style:z-index={p.faces.length - i}><Avatar person={{ ...f, id: f.name.charCodeAt(0) }} size={20} tappable={false} /></span>{/each}</span>{/if}
              <span class="talk"><Button kind="tinted" size="s" label="{t('fc.comments')}{p.comments ? `: ${p.comments}` : ''}" onclick={() => talk(p)}>
                {#snippet icon()}<TelegramMark size={16} />{/snippet}{t('fc.discuss')}{#if p.comments}<span class="n">{compact(p.comments)}</span>{/if}
              </Button></span>
            </div>
            <!-- my anonymous post: answering in its comments as the mask, through the bot (ChannelReply): a row of the card -->
            {#if p.mine && p.anon}<button class="areply" onclick={() => { haptic.tap(); sheets.channelReply({ id: p.id, body: p.body }); }}>
              <span class="ai" aria-hidden="true"><VenetianMask size={17} strokeWidth={2} /></span>
              <span class="al">{t('fcr.entry')}</span>
              <ChevronRight size={18} strokeWidth={2} aria-hidden="true" />
            </button>{/if}
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
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; }
  .page > :global(*) { flex-shrink: 0; }
  /* every post a card on the ground (owner, Nov 4: "just a black background"): the app's surface and radius, a hairline
     rim in the dark (no shadow there), the soft card shadow in the light; the composer is the first card */
  .compose, .post { border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-card), inset 0 0 0 0.5px var(--line); }

  /* the composer: my face, a quiet prompt, the pen */
  .compose { display: flex; align-items: center; gap: var(--s-3); padding: var(--s-3) var(--s-3) var(--s-3) var(--s-4); text-align: left;
    transition: transform 450ms var(--ease-bounce); }
  .compose:active { transform: scale(0.98); transition-duration: 80ms; }
  .compose.away { visibility: hidden; } /* it is the writing window now (ChannelCompose grows out of it and folds back) */
  /* the "N new" pill: floats under the capsule, takes no room in the list */
  .pill { position: sticky; top: calc(var(--head-bottom) + var(--s-2) - var(--page-top)); z-index: var(--z-sticky); height: 0; display: flex; justify-content: center; }
  .pin { display: flex; height: max-content; }
  .prompt { flex: 1; min-width: 0; font: 450 var(--fs-body)/1.3 var(--font-text); color: var(--text-3); }
  .pen { flex: none; width: 36px; height: 36px; border-radius: 50%; display: grid; place-items: center; background: var(--accent); color: var(--on-accent);
    box-shadow: 0 4px 12px -4px var(--accent); transition: transform 380ms var(--ease-bounce); }
  .compose:active .pen { transform: scale(0.9); transition-duration: 80ms; }

  .feed { display: flex; flex-direction: column; gap: var(--s-3); margin-top: var(--s-3); }
  /* a post: the head (face, name and when, the menu), the words, the row under them */
  .post { position: relative; display: flex; flex-direction: column; padding: var(--s-3) var(--s-4) var(--s-4);
    animation: rise 420ms cubic-bezier(.2, .9, .25, 1.05) backwards; animation-delay: calc(var(--i) * 40ms); /* the first screen settles top down */ }
  .post:has(.acts) { padding-bottom: var(--s-2); }
  .post:has(.areply) { padding-bottom: 0; }
  /* the line between the new and the seen: a word on a hairline in the accent, between the cards */
  .nw { display: flex; align-items: center; gap: var(--s-2); margin: var(--s-1) var(--s-2) var(--s-3);
    font: 600 var(--fs-cap)/1 var(--font-text); color: var(--accent-text); letter-spacing: 0.02em; }
  .nw::before, .nw::after { content: ''; flex: 1; height: 1px; background: currentColor; opacity: 0.35; }
  .nwl { display: inline-flex; align-items: center; gap: 3px; } /* the arrow: the new ones are above the line */
  /* the post the bot's button pointed at: an accent wash that fades */
  .post.lit { animation: lit 1.8s var(--ease); }
  @keyframes lit { 0%, 45% { background: var(--accent-soft); } }
  .post.off { opacity: 0.6; }

  .head { display: flex; align-items: center; gap: var(--s-3); min-height: 40px; }
  .rail { position: relative; flex: none; display: flex; }
  .av { flex: none; width: 40px; height: 40px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2);
    color: var(--text-2); font: 600 var(--fs-cap)/1 var(--font-text); letter-spacing: 0.02em; }
  .compose .av { width: 36px; height: 36px; }
  .av.anon { background: var(--fill-2); color: var(--text); }
  /* new since my last visit: a small accent dot on the face's shoulder, cut out of it by the card */
  .dot { position: absolute; top: 0; right: -1px; width: 10px; height: 10px; border-radius: 50%; background: var(--accent); box-shadow: 0 0 0 2px var(--surface-solid); }
  .who { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .who b { font: 600 var(--fs-body)/1.25 var(--font-text); color: var(--text); letter-spacing: -0.01em; }
  .name { display: flex; min-width: 0; max-width: 100%; padding: 0; text-align: left; }
  .name:active { opacity: 0.6; }
  .meta { display: flex; gap: 6px; min-width: 0; font: 450 var(--fs-cap)/1.3 var(--font-text); color: var(--text-3); white-space: nowrap; }
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
  .pics { display: grid; gap: 2px; margin-top: var(--s-3); border-radius: var(--r-m); overflow: hidden; }
  .pics.n2, .pics.n4 { grid-template-columns: 1fr 1fr; }
  .pics.n3 { grid-template-columns: 2fr 1fr; grid-template-rows: 1fr 1fr; }
  .pics.n3 .ph:first-child { grid-row: span 2; }
  .ph { display: block; aspect-ratio: 4 / 3; background: var(--surface-2); overflow: hidden; }
  .pics.n1 .ph { aspect-ratio: 16 / 10; }
  .pics.n3 .ph { aspect-ratio: auto; min-height: 90px; }
  .ph img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .tx { margin-top: var(--s-2); font: 450 var(--fs-body)/1.47 var(--font-text); letter-spacing: -0.006em; color: var(--text); white-space: pre-line; overflow-wrap: break-word;
    max-height: 5.9em; overflow: hidden; transition: max-height 420ms var(--ease); }
  .tx.fade { -webkit-mask-image: linear-gradient(to bottom, black 50%, transparent); mask-image: linear-gradient(to bottom, black 50%, transparent); }
  .tx.open { max-height: var(--h); }
  .more { display: flex; margin: 0 0 0 calc(-1 * var(--s-2)); --plain-ink: var(--text-2); }
  /* my held post's why: a quiet tinted block under the words */
  .held { margin-top: var(--s-3); padding: var(--s-3); border-radius: var(--r-m); background: var(--warning-soft);
    font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-2); }
  .held .fix { display: flex; gap: 6px; margin-top: var(--s-2); color: var(--text); }
  .held .fix :global(svg) { flex: none; margin-top: 1px; color: var(--warning-text); }

  /* the row under the words: Telegram's reactions on the left (small chips), the talk's faces and its one button on
     the right (under the thumb); 44 to the finger */
  .acts { display: flex; align-items: center; gap: var(--s-2); min-height: 44px; margin-top: var(--s-2); }
  .rx { flex: none; display: flex; gap: 6px; }
  .r { display: inline-flex; align-items: center; gap: 4px; height: 28px; padding: 0 9px; border-radius: var(--r-full); background: var(--fill);
    color: var(--text-2); font: 600 var(--fs-cap)/1 var(--font-text); font-variant-numeric: tabular-nums; }
  .e { font-size: var(--fs-sub); line-height: 1; }
  /* as many faces as the row has room for, the newest first and on top: the ones that don't fit wrap to a second
     line, out of sight (whole faces only, never a cut one) */
  .faces { flex: 1; min-width: 24px; display: flex; flex-wrap: wrap; justify-content: flex-end; row-gap: 8px; height: 24px; padding: 2px; overflow: hidden; }
  .f { display: flex; }
  .f + .f { margin-left: -6px; }
  .faces :global(.av) { box-shadow: 0 0 0 1.5px var(--surface-solid); }
  .talk { flex: none; display: flex; margin-left: auto; }
  .faces + .talk { margin-left: 0; }
  .n { margin-left: 2px; opacity: 0.7; font-variant-numeric: tabular-nums; }
  @media (max-width: 359px) { .r:nth-child(n + 2), .faces { display: none; } } /* 320: the top reaction, the button */

  /* my anonymous post's way into its comments: the card's last row, under a hairline (a Settings row's grammar) */
  .areply { position: relative; display: flex; align-items: center; gap: var(--s-3); width: calc(100% + 2 * var(--s-4)); min-height: 48px;
    margin: var(--s-1) calc(-1 * var(--s-4)) 0; padding: 0 var(--s-3) 0 var(--s-4); border-radius: 0 0 var(--r-l) var(--r-l); text-align: left;
    color: var(--accent-text); font: 500 var(--fs-body)/1.2 var(--font-text); transition: background var(--t-base) var(--ease); }
  .areply::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .areply:active { background: var(--fill); transition-duration: 60ms; }
  .ai { flex: none; width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center; background: var(--accent-soft); }
  .al { flex: 1; min-width: 0; }
  .areply > :global(svg:last-child) { flex: none; color: var(--text-3); }

  .earlier { display: flex; justify-content: center; padding: var(--s-3) 0; }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } }
  .tail { height: calc(var(--bottom) + var(--s-8)); }
</style>
