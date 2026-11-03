<script lang="ts">
  // Afisha → News, a sheet from the news circles' "All" ("one news feed is the killer feature"; PLAN 58): KBTU's news in
  // one place, not only events: the broadcasts "From DMP and KBTU App" first (a gradient edge, "new" until seen; seeing
  // them clears the dot), then every club's and office's public posts, newest first (a club's new
  // event is on the list already, not here too). Writing is in Studio. A post: the club, when, its label, a photo, the text (long ones fold), the two
  // reactions, comments. A club's Head+ edit their post, pin it, or take it down (⋯).
  import { onMount, untrack } from 'svelte';
  import Sheet from '../../ui/Sheet.svelte';
  import Newspaper from '@lucide/svelte/icons/newspaper';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import Pin from '@lucide/svelte/icons/pin';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import Eye from '@lucide/svelte/icons/eye';
  import Play from '@lucide/svelte/icons/play';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import SocialIcon from '../../ui/SocialIcon.svelte';
  import Linked from '../../ui/Linked.svelte';
  import { videoLinks } from '../../lib/social';
  import { api, type Post } from '../../lib/api';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { data, loadNews, phrase } from '../../lib/state/data.svelte';
  import { say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago } from '../../lib/time';
  import { tagName } from '../../lib/posts';
  import { focusPos } from '../../lib/photo';
  import { haptic, openLink } from '../../lib/tg';
  import { compact } from '../../lib/chats';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Tag from '../../ui/Tag.svelte';
  import Button from '../../ui/Button.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import Section from '../../ui/Section.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';
  import Skeleton from '../../ui/Skeleton.svelte';
  import { menu } from '../../ui/menu';
  import Emoji from '../../ui/Emoji.svelte';
  import { nameOf } from '../../lib/short';
  import { theme } from '../../lib/state/theme.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const me = $derived(session.me);
  const student = $derived(!!me?.student); // a boolean: a fresh Me (the dot's count) doesn't reload the page
  // loaded with the app (and kept for the next launch), so the page opens full; coming into view refreshes it quietly
  const casts = $derived(data.news?.casts ?? []);
  // every public post, not only my clubs' (the circles on List keep those): the copy the app loads with the Afisha and
  // keeps for the next launch, so the page opens full (it used to wait for its own request); each visit
  // refreshes it quietly
  const posts = $derived(data.eventsReady ? data.posts : null);
  const loadAll = () => api.posts('all').then((l) => (data.posts = l)).catch(() => {});
  onMount(() => { if (student) void loadNews(); void loadAll(); }); // staff read the feed too
  $effect(() => { if (casts) untrack(() => seen(casts)); });
  // the unread broadcasts on screen count as read after a moment (their "new" stays until the next visit)
  // (a sheet now: closed sooner, the marks still go, as Stories does)
  let timer: ReturnType<typeof setTimeout> | undefined;
  let pending: number[] = [];
  const send = () => { const ids = pending; pending = []; if (ids.length) api.readPosts(ids).then(() => loadMe()).catch(() => {}); };
  function seen(list: Post[]) {
    pending = list.filter((p) => !p.read).map((p) => p.id);
    clearTimeout(timer);
    if (pending.length) timer = setTimeout(send, 1500);
  }
  $effect(() => () => { clearTimeout(timer); send(); });

  let open = $state<Set<number>>(new Set()); // posts unfolded
  // a channel post's video plays in our own player on a tap: the server finds its file on Telegram's CDN (the address
  // expires, so only now; mirror.video); nothing loads before the tap. No file (a long video, Telegram changed its page,
  // the file won't play): Telegram's own post widget (t.me/<channel>/<id>?embed=1), which says its height by postMessage.
  let playing = $state<Map<number, { src: string; poster: string | null } | 'wait' | 'widget'>>(new Map());
  const play = (id: number, v: { src: string; poster: string | null } | 'wait' | 'widget') => (playing = new Map(playing).set(id, v));
  async function watch(id: number) {
    haptic.tap();
    play(id, 'wait');
    play(id, await api.postVideo(id).catch(() => 'widget' as const));
  }
  // the tap on "watch" was the user's play: start it, with sound; a browser that refuses waits for its own play button
  const start = (el: HTMLVideoElement) => { el.play().catch(() => {}); };
  const embed = (url: string) => `${url}?embed=1&userpic=false${theme.current === 'dark' ? '&dark=1' : ''}`;
  function fit(el: HTMLIFrameElement) {
    const on = (e: MessageEvent) => {
      if (e.source !== el.contentWindow || e.origin !== 'https://t.me') return;
      let d: { event?: string; height?: number | null };
      try { d = JSON.parse(e.data); } catch { return; }
      if (d.event === 'resize' && (d.height ?? 0) > 0) el.style.height = Math.ceil(d.height!) + 'px'; // null before its layout
    };
    addEventListener('message', on);
    return { destroy: () => removeEventListener('message', on) };
  }
  const long = (p: Post) => p.body.length > 220 || p.body.split('\n').length > 4;

  async function react(p: Post, kind: 'fire' | 'heart') {
    const on = !p.mine[kind];
    p.mine[kind] = on; p.reactions[kind] += on ? 1 : -1; // at once; the server's answer settles it
    haptic.select();
    try { Object.assign(p, await api.react(p.id, kind, on)); if (on) say(phrase(kind === 'fire' ? 'say.fire' : 'say.heart'), kind === 'fire' ? 'fire_3d' : 'smiling_face_with_heart_eyes_3d'); }
    catch { p.mine[kind] = !on; p.reactions[kind] += on ? -1 : 1; say(t('common.error'), 'warning_3d'); }
  }
  async function takeDown(p: Post) {
    if (!(await sheets.ask({ title: t('news.hideAsk'), text: t('news.hideText'), ok: t('news.hide'), cancel: t('common.cancel'), danger: true }))) return;
    try {
      await api.hidePost(p.id);
      if (data.news) data.news = { casts: data.news.casts.filter((x) => x.id !== p.id), posts: data.news.posts.filter((x) => x.id !== p.id) };
      data.posts = data.posts.filter((x) => x.id !== p.id);
      haptic.ok(); say(t('news.hidden'), 'waving_hand_3d_default');
    } catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // the ⋯ menu on a post, the shared one at the button (featuring one on top of List is in Admin)
  function more(e: MouseEvent, p: Post) {
    menu(e.currentTarget as Element, [
      ...(p.canEdit ? [{ label: t('news.edit'), onselect: () => sheets.composer(p.org.id, p) },
        { label: p.pinned ? t('news.unpin') : t('news.pin'), onselect: () => void pin(p) }] : []),
      // anyone but its own club's writers: the one report sheet
      ...(!p.canEdit && session.me?.student ? [{ label: t('cm.report'), onselect: () => sheets.report('post', p.id, p.title) }] : []),
      ...(p.canDelete ? [{ label: t('news.hide'), destructive: true, onselect: () => void takeDown(p) }] : []),
    ], 'end');
  }
  // the club's Head+: one pinned post per club, on top of its news; the lists reload in the server's order
  async function pin(p: Post) {
    try { await api.updatePost(p.id, { pinned: !p.pinned }); haptic.ok(); say(phrase(p.pinned ? 'news.unpinSay' : 'news.pinSay'), 'sparkles_3d'); void loadNews(); void loadAll(); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
  }
  // by time only: a club's pin holds on its own page, not over everyone's news
  const feed = $derived<Post[] | null>(posts && [...posts].sort((a, b) => b.createdAt - a.createdAt));
  // "your club" / "you follow"; anyone else's post says only when
  const why = (p: Post) => (me?.memberships.some((m) => m.org.id === p.org.id) ? t('news.yourClub') + ' · ' : data.orgs.some((o) => o.id === p.org.id && o.subscribed) ? t('news.following') + ' · ' : '');
</script>

{#snippet card(p: Post, cast: boolean)}
  <article class="post" class:cast class:unread={cast && !p.read}>
    <header class="ph">
      <OrgLogo org={p.org} size={36} />
      <span class="who"><b class="ellipsis">{nameOf(p.org)}</b><i><span class="when">{#if !cast}{why(p)}{/if}{ago(p.createdAt)}{#if p.editedAt}{' · ' + t('news.edited')}{/if}</span>{#if p.pinned}<span class="pinned"><Pin size={12} />{t('news.pinned')}</span>{/if}</i></span>
      {#if cast && !p.read}<Tag tone="accent">{t('news.new')}</Tag>{/if}
      {#if p.tag}<Tag tone={p.tag === 'important' ? 'warning' : 'accent'}>{tagName(p.tag)}</Tag>{/if}
      {#if p.canEdit || p.canDelete || session.me?.student}<span class="more"><IconButton icon={Ellipsis} kind="plain" size="s" label={t('common.more')} onclick={(e) => more(e, p)} /></span>{/if}
    </header>
    <!-- the card crops it: a tap shows it whole -->
    {#if p.photo}{@const ph = p.photo}<button class="pic" aria-label={p.title} onclick={() => sheets.photos([{ ...ph, id: ph.id ?? -p.id, by: null, mine: true, canDelete: false }], 0)}>
      <img src={ph.url} alt="" loading="lazy" decoding="async" style:object-position={focusPos(ph)} /></button>{/if}
    <h3 class="tt">{p.title}</h3>
    {#if p.body}
      <p class="bd" class:fold={long(p) && !open.has(p.id)}><Linked text={p.body} /></p>
      {#if long(p) && !open.has(p.id)}<span class="unfold"><Button kind="plain" size="s" onclick={() => (open = new Set([...open, p.id]))}>{t('news.more')}</Button></span>{/if}
    {/if}
    <div class="vl">{#each videoLinks(p.body) as l (l.url)}<Button kind="tinted" size="s" onclick={() => openLink(l.url)}>{#snippet icon()}<SocialIcon kind={l.kind} size={16} />{/snippet}{l.label}</Button>{/each}</div>
    {#if p.tg}
      <!-- the club's Telegram channel post: its counts and comments live there, its video plays in Telegram's widget (PLAN 86) -->
      {@const tg = p.tg}
      {@const v = playing.get(p.id)}
      {#if tg.media === 'video' && v === 'wait'}<div class="tgv-wait" aria-busy="true"></div>
      {:else if tg.media === 'video' && typeof v === 'object'}
        <!-- svelte-ignore a11y_media_has_caption (a channel's video comes without captions) -->
        <video class="tgplay" src={v.src} poster={v.poster ?? undefined} controls playsinline preload="metadata"
          use:start onerror={() => play(p.id, 'widget')}></video>
      {:else if tg.media === 'video' && v}
        <iframe class="tgw" src={embed(tg.url)} title={p.title} use:fit allow="fullscreen; picture-in-picture" referrerpolicy="no-referrer"
          sandbox="allow-scripts allow-same-origin allow-popups allow-popups-to-escape-sandbox allow-presentation"></iframe>
      {:else if tg.media === 'video'}<span class="tgm"><Button kind="tinted" size="s" onclick={() => watch(p.id)}>{#snippet icon()}<Play size={16} />{/snippet}{t('tg.video')}</Button></span>
      {:else if tg.media}<span class="tgm"><Button kind="tinted" size="s" onclick={() => openLink(tg.url)}>{#snippet icon()}<Play size={16} />{/snippet}{t('tg.file')}</Button></span>{/if}
      <footer class="re tgf">
        {#each tg.reactions.slice(0, 2) as [e, n] (e)}<Button kind="gray" size="s" onclick={() => openLink(tg.url)}>{#snippet icon()}<span class="tge">{e}</span>{/snippet}<span class="num">{compact(n)}</span></Button>{/each}
        {#if tg.views}<span class="tgv"><Eye size={15} />{compact(tg.views)}</span>{/if}
        <span class="cm"><Button kind="gray" size="s" onclick={() => openLink(tg.url)}>{#snippet icon()}<TelegramMark size={16} />{/snippet}{t('tg.open')}</Button></span>
      </footer>
    {:else}
    <footer class="re">
      <Button kind="gray" size="s" on={p.mine.fire} onclick={() => react(p, 'fire')}>{#snippet icon()}<span class="ej"><Emoji name="fire_3d" size={20} /></span>{/snippet}<span class="num">{p.reactions.fire}</span></Button>
      <Button kind="gray" size="s" on={p.mine.heart} onclick={() => react(p, 'heart')}>{#snippet icon()}<span class="ej"><Emoji name="blue_heart_3d" size={20} /></span>{/snippet}<span class="num">{p.reactions.heart}</span></Button>
      {#if p.commentsOn || p.comments}
        <span class="cm"><Button kind="gray" size="s" round={!p.comments} label={t('cm.title')} onclick={() => sheets.comments('post', p.id, p.title, (n) => (p.comments = n))}>{#snippet icon()}<MessageCircle size={18} />{/snippet}{#if p.comments}<span class="num">{p.comments}</span>{/if}</Button></span>
      {/if}
    </footer>
    {/if}
  </article>
{/snippet}

<Sheet {overlay} tall title={t('page.news')} icon={Newspaper}>
<div class="news">
  <header class="hd">
    <p class="t-foot">{t('news.sub')}</p>
  </header>

  {#if casts && posts}
    {#if casts.length}
      <Section title={t('news.broadcasts', { dmp: t('tab.dmp') })}>
        <div class="list">{#each casts as p, i (p.id)}<div class="in" style="--i:{i}">{@render card(p, true)}</div>{/each}</div>
      </Section>
    {/if}
    {#if feed?.length}
      {#snippet clubs()}<div class="list">{#each feed as p, i (p.id)}<div class="in" style="--i:{i + (casts.length ? 2 : 0)}">{@render card(p, false)}</div>{/each}</div>{/snippet}
      {#if casts.length}<Section title={t('news.clubs')}>{@render clubs()}</Section>{:else}{@render clubs()}{/if}
    {:else if !casts.length}
      <EmptyState icon={Newspaper} title={t('news.emptyTitle')} text={t('news.emptyText')} />
    {/if}
  {:else}
    <Skeleton kind="cards" n={3} />
  {/if}
</div>
</Sheet>

<style>
  .news { display: flex; flex-direction: column; gap: var(--s-3); }
  .news > :global(*) { flex-shrink: 0; }
  .hd { margin-bottom: 2px; }
  .list { display: flex; flex-direction: column; gap: 10px; }
  .in { animation: rise 440ms cubic-bezier(.2, .9, .25, 1.05) backwards; animation-delay: calc(var(--i) * 60ms); }

  .post { position: relative; display: flex; flex-direction: column; gap: 8px; padding: 12px 14px 10px; border-radius: var(--r-l); background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); }
  /* a broadcast: an edge in the brand gradient (a 1.5 px ring painted under the card) */
  .post.cast { background: radial-gradient(120% 70% at 0% 0%, rgba(124, 77, 255, 0.12), transparent 60%), var(--surface); box-shadow: none; }
  .post.cast::before { content: ''; position: absolute; inset: 0; padding: 1.5px; border-radius: inherit; pointer-events: none;
    background: linear-gradient(135deg, rgba(59, 107, 255, 0.85), rgba(124, 77, 255, 0.6) 40%, var(--line) 70%);
    -webkit-mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0); mask: linear-gradient(black 0 0) content-box, linear-gradient(black 0 0);
    -webkit-mask-composite: xor; mask-composite: exclude; }
  .ph { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .who { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .who b { font: 600 var(--fs-body)/1.2 var(--font-text); }
  /* when · edited, then the pin: on a narrow phone the pin takes the next line whole */
  .who i { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 8px; font: 500 var(--fs-cap)/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .when { max-width: 100%; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; } /* a narrow phone: "…", never under the tag */
  .pinned { display: inline-flex; align-items: center; gap: 3px; white-space: nowrap; color: var(--accent-text); }
  .more { flex: none; display: flex; margin: -4px -6px -4px 0; --plain-ink: var(--text-3); }
  .pic { display: block; width: 100%; aspect-ratio: 16 / 10; overflow: hidden; border-radius: var(--r-m); background: var(--surface-2); }
  .pic img { width: 100%; height: 100%; object-fit: cover; }
  .tt { font: 700 var(--fs-card)/1.25 var(--font-display); letter-spacing: -0.015em; }
  .bd { font: 450 var(--fs-body)/1.45 var(--font-text); color: var(--text-2); white-space: pre-line; overflow-wrap: anywhere; }
  .bd.fold { display: -webkit-box; -webkit-line-clamp: 4; line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }
  .unfold { align-self: flex-start; margin: -6px 0 0 calc(-1 * var(--s-2)); }
  .re { display: flex; align-items: center; gap: 6px; margin-top: 2px; }
  /* my reaction: Button's calm "on" with the count in the accent */
  .re :global(.btn[aria-pressed='true'] .lbl) { color: var(--accent-text); }
  .re .cm { display: flex; margin-left: auto; }
  .tgf { flex-wrap: wrap; row-gap: 6px; }
  .tge { font-size: var(--fs-card); line-height: 1; }
  .tgv { display: inline-flex; align-items: center; gap: 5px; padding: 0 6px; font: 600 var(--fs-sub)/1 var(--font-text); color: var(--text-3); }
  /* the widget draws the channel's card around the video: its own height (fit), our corners */
  .tgw { display: block; width: 100%; height: 360px; margin: 2px 0 6px; border: 0; border-radius: var(--r-m); background: var(--surface-2); color-scheme: normal; }
  /* our own player: the card's width, the video's own shape (a tall one stops at most of the screen), our corners */
  .tgplay { display: block; width: 100%; max-height: 70vh; margin: 2px 0 6px; border-radius: var(--r-m); background: var(--surface-2); object-fit: contain; }
  .tgv-wait { aspect-ratio: 16 / 9; margin: 2px 0 6px; border-radius: var(--r-m); background: var(--surface-2); animation: pulse 1.2s ease-in-out infinite; }
  .vl { display: flex; flex-wrap: wrap; gap: 8px; } .vl:empty { display: none; }
  .tgm { display: flex; align-self: flex-start; margin: 2px 0 8px; }
  .ej { display: flex; }
  .re :global(.btn[aria-pressed='true'] .ej) { animation: boop 420ms cubic-bezier(.2, 1.6, .4, 1); }
  @keyframes boop { 30% { transform: scale(1.45) rotate(-8deg); } }

  @keyframes pulse { 50% { opacity: 0.5; } }
  @keyframes rise { from { opacity: 0; transform: translateY(14px) scale(0.98); } }
</style>
