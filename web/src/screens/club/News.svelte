<script lang="ts">
  // Tab 2 → News (SPEC §4.10), for club members and, since Oct 13, students in no club who follow some: the broadcasts "From DMP and KBTU App" first (a gradient edge, "new"
  // until seen; seeing them clears the tab's dot), then the posts of my clubs and the clubs I follow. Head+ write from
  // here (the composer, for the club picked in Studio). A post: the club, when, its label, a photo, the text (long ones
  // fold), and the two reactions. A club's Head+ edit their post, pin it, or take it down (⋯).
  import { untrack } from 'svelte';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import PenLine from '@lucide/svelte/icons/pen-line';
  import Pin from '@lucide/svelte/icons/pin';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import { api, type EventCard, type Post } from '../../lib/api';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { data, loadAfisha, loadNews, phrase } from '../../lib/state/data.svelte';
  import { ui, say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago, nowTs, relDay } from '../../lib/time';
  import EventRow from '../../ui/EventRow.svelte';
  import { tagName } from '../../lib/posts';
  import { focusPos } from '../../lib/photo';
  import { haptic } from '../../lib/tg';
  import { byRank } from '../../lib/perms';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Chip from '../../ui/Chip.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import Button from '../../ui/Button.svelte';

  const me = $derived(session.me);
  const writers = $derived([...(me?.memberships ?? [])].filter((m) => m.role !== 'member').sort(byRank));
  const here = $derived(ui.tab === 'club' && ui.page.club === 0);
  const student = $derived(!!me?.student); // a boolean: a fresh Me (the dot's count) doesn't reload the page
  // loaded with the app (and kept for the next launch), so the page opens full; coming into view refreshes it quietly
  const casts = $derived(data.news?.casts ?? null);
  const posts = $derived(data.news?.posts ?? null);
  $effect(() => { if (here && student) void untrack(loadNews); });
  $effect(() => { if (here && casts) untrack(() => seen(casts)); });
  // the unread broadcasts on screen count as read after a moment (their "new" stays until the next visit)
  let timer: ReturnType<typeof setTimeout> | undefined;
  function seen(list: Post[]) {
    const ids = list.filter((p) => !p.read).map((p) => p.id);
    clearTimeout(timer);
    if (ids.length) timer = setTimeout(() => api.readPosts(ids).then(() => loadMe()).catch(() => {}), 1500);
  }
  $effect(() => () => clearTimeout(timer));

  let open = $state<Set<number>>(new Set()); // posts unfolded
  const long = (p: Post) => p.body.length > 220 || p.body.split('\n').length > 4;

  async function react(p: Post, kind: 'fire' | 'heart') {
    const on = !p.mine[kind];
    p.mine[kind] = on; p.reactions[kind] += on ? 1 : -1; // at once; the server's answer settles it
    haptic.select();
    try { Object.assign(p, await api.react(p.id, kind, on)); if (on) say(phrase(kind === 'fire' ? 'say.fire' : 'say.heart'), kind === 'fire' ? 'fire_3d' : 'smiling_face_with_heart_eyes_3d'); }
    catch { p.mine[kind] = !on; p.reactions[kind] += on ? -1 : 1; say(t('common.error'), 'pleading_face_3d'); }
  }
  async function takeDown(p: Post) {
    if (!(await sheets.ask({ title: t('news.hideAsk'), text: t('news.hideText'), ok: t('news.hide'), cancel: t('common.cancel'), danger: true }))) return;
    try {
      await api.hidePost(p.id);
      if (data.news) data.news = { casts: data.news.casts.filter((x) => x.id !== p.id), posts: data.news.posts.filter((x) => x.id !== p.id) };
      haptic.ok(); say(t('news.hidden'), 'waving_hand_3d_default');
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  // moderators and the admin: a public post on top of Events → List for everyone, for three days (§2)
  let menu = $state<number | null>(null);
  // the club's Head+: one pinned post per club, on top of its news; the lists reload in the server's order
  async function pin(p: Post) {
    menu = null;
    try { await api.updatePost(p.id, { pinned: !p.pinned }); haptic.ok(); say(phrase(p.pinned ? 'news.unpinSay' : 'news.pinSay'), 'sparkles_3d'); void loadNews(); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  async function feature(p: Post, days: number) {
    menu = null;
    try {
      const fresh = await api.feature(p.id, days);
      const put = (l: Post[]) => l.map((x) => (x.id === p.id ? fresh : days ? { ...x, featured: false } : x));
      if (data.news) data.news = { casts: put(data.news.casts), posts: put(data.news.posts) };
      haptic.ok(); say(days ? t('news.featured') : t('news.unfeatured'), 'sparkles_3d');
      void loadAfisha(); // List's card follows
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  // a new event of my clubs and follows (published in the last two weeks, still ahead) is a card among the posts, in time:
  // clubs announce an event by publishing it, not with a post as well (owner, Oct 13)
  const near = (id: number) => !!me?.memberships.some((m) => m.org.id === id) || data.orgs.some((o) => o.id === id && o.subscribed);
  const fresh = $derived(data.events.filter((e) => e.status === 'published' && (e.publishedAt ?? 0) > nowTs() - 14 * 86400 && near(e.org.id)));
  type Item = { at: number; post: Post } | { at: number; ev: EventCard };
  const feed = $derived<Item[] | null>(posts && [...posts.filter((p) => p.pinned).map((p) => ({ at: Infinity, post: p })),
    ...[...posts.filter((p) => !p.pinned).map((p) => ({ at: p.createdAt, post: p })), ...fresh.map((e) => ({ at: e.publishedAt!, ev: e }))].sort((a, b) => b.at - a.at)]);
  // why a post is in my feed (owner, Oct 13: "your club" / "you follow"); broadcasts say nothing, they come to every member
  const why = (p: Post) => (me?.memberships.some((m) => m.org.id === p.org.id) ? t('news.yourClub') : t('news.following'));
  const write = () => sheets.composer(writers.find((m) => m.org.id === ui.club)?.org.id ?? writers[0].org.id);
</script>

{#snippet card(p: Post, cast: boolean)}
  <article class="post" class:cast class:unread={cast && !p.read}>
    <header class="ph">
      <OrgLogo org={p.org} size={36} />
      <span class="who"><b class="ellipsis">{p.org.name}</b><i><span class="when">{#if !cast}{why(p) + ' · '}{/if}{ago(p.createdAt)}{#if p.editedAt}{' · ' + t('news.edited')}{/if}</span>{#if p.pinned}<span class="pinned"><Pin size={12} />{t('news.pinned')}</span>{/if}</i></span>
      {#if cast && !p.read}<span class="new">{t('news.new')}</span>{/if}
      {#if p.tag}<Chip tone={p.tag === 'important' ? 'warning' : 'accent'}>{tagName(p.tag)}</Chip>{/if}
      {#if p.canEdit || p.canDelete || p.canFeature || session.me?.student}<button class="more" aria-label={t('common.more')} aria-expanded={menu === p.id} onclick={() => (menu = menu === p.id ? null : p.id)}><Ellipsis size={18} /></button>{/if}
    </header>
    {#if menu === p.id}
      <div class="pmenu">
        {#if p.canEdit}
          <button onclick={() => { menu = null; sheets.composer(p.org.id, p); }}>{t('news.edit')}</button>
          <button onclick={() => pin(p)}>{p.pinned ? t('news.unpin') : t('news.pin')}</button>
        {/if}
        {#if p.canFeature}<button onclick={() => feature(p, p.featured ? 0 : 3)}>{p.featured ? t('news.unfeature') : t('news.feature')}</button>{/if}
        {#if p.canDelete}<button class="danger" onclick={() => { menu = null; void takeDown(p); }}>{t('news.hide')}</button>{/if}
        <!-- anyone but its own club's writers: the one report sheet (owner, Oct 22) -->
        {#if !p.canEdit && session.me?.student}<button onclick={() => { menu = null; sheets.report('post', p.id, p.title); }}>{t('cm.report')}</button>{/if}
      </div>
    {/if}
    {#if p.photo}<img class="pic" src={p.photo.url} alt="" loading="lazy" decoding="async" style:object-position={focusPos(p.photo)} />{/if}
    <h3 class="tt">{p.title}</h3>
    {#if p.body}
      <p class="bd" class:fold={long(p) && !open.has(p.id)}>{p.body}</p>
      {#if long(p) && !open.has(p.id)}<button class="unfold" onclick={() => (open = new Set([...open, p.id]))}>{t('news.more')}</button>{/if}
    {/if}
    <footer class="re">
      <button class:on={p.mine.fire} onclick={() => react(p, 'fire')} aria-pressed={p.mine.fire}><span class="ej"><Emoji name="fire_3d" size={20} /></span><b class="num">{p.reactions.fire}</b></button>
      <button class:on={p.mine.heart} onclick={() => react(p, 'heart')} aria-pressed={p.mine.heart}><span class="ej"><Emoji name="blue_heart_3d" size={20} /></span><b class="num">{p.reactions.heart}</b></button>
      {#if p.commentsOn || p.comments}
        <button class="cm" onclick={() => sheets.comments('post', p.id, p.title, (n) => (p.comments = n))} aria-label={t('cm.title')}><MessageCircle size={18} /><b class="num">{p.comments || ''}</b></button>
      {/if}
    </footer>
  </article>
{/snippet}

<div class="page scroll">
  <header class="hd">
    <span><h1 class="t-h1">{t('page.news')}</h1><p class="t-foot">{t('news.sub')}</p></span>
    {#if writers.length}<button class="pill" onclick={write}><PenLine size={17} />{t('news.write')}</button>{/if}
  </header>

  {#if casts && posts}
    {#if casts.length}
      <h2 class="sh">{t('news.broadcasts', { dmp: t('tab.dmp') })}</h2>
      <div class="list">{#each casts as p, i (p.id)}<div class="in" style="--i:{i}">{@render card(p, true)}</div>{/each}</div>
    {/if}
    {#if feed?.length}
      {#if casts.length}<h2 class="sh">{t('news.clubs')}</h2>{/if}
      <div class="list">{#each feed as it, i ('post' in it ? `p${it.post.id}` : `e${it.ev.id}`)}<div class="in" style="--i:{i + (casts.length ? 2 : 0)}">
        {#if 'post' in it}{@render card(it.post, false)}
        {:else}
          <article class="post">
            <header class="ph"><OrgLogo org={it.ev.org} size={36} /><span class="who"><b class="ellipsis">{it.ev.org.name}</b><i><span class="when">{t('news.newEvent')} · {ago(it.at)}</span></i></span></header>
            <EventRow e={it.ev} showDate dateLine={relDay(it.ev.startsAt)} />
          </article>
        {/if}
      </div>{/each}</div>
    {:else if !casts.length}
      <section class="empty">
        <Emoji name="sparkles_3d" size={64} />
        <h2 class="t-h2">{t('news.emptyTitle')}</h2>
        <p class="t-callout">{writers.length ? t('news.emptyHead') : t('news.emptyText')}</p>
        {#if writers.length}<Button kind="primary" size="l" full onclick={write}>{#snippet icon()}<PenLine size={18} />{/snippet}{t('news.write')}</Button>{/if}
      </section>
    {/if}
  {:else}
    <div class="skel"><span></span><span class="tall"></span><span></span></div>
  {/if}
  <div class="tail"></div>
</div>

<style>
  .pmenu { display: flex; flex-wrap: wrap; gap: 6px; margin: -2px 0 10px; }
  .pmenu button { height: 32px; padding: 0 12px; border-radius: var(--r-full); background: var(--surface-2); font: 620 13px/1 var(--font-text); color: var(--text); }
  .pmenu .danger { color: var(--danger-text); background: var(--danger-soft); }
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: 12px; }
  .page > :global(*) { flex-shrink: 0; }
  .hd { display: flex; align-items: flex-end; justify-content: space-between; gap: 12px; margin-bottom: 2px; }
  .hd p { margin-top: 4px; }
  .pill { flex: none; display: inline-flex; align-items: center; gap: 6px; height: 36px; padding: 0 14px 0 12px; border-radius: var(--r-full);
    background: var(--accent-soft); color: var(--accent-text); font: 650 14px/1 var(--font-text); transition: transform var(--t-fast) var(--ease); }
  .pill:active { transform: scale(0.95); }
  .sh { font: 750 19px/1.2 var(--font-display); letter-spacing: -0.025em; margin-top: 6px; }
  .list { display: flex; flex-direction: column; gap: 10px; }
  .in { animation: rise 440ms cubic-bezier(.2, .9, .25, 1.05) backwards; animation-delay: calc(var(--i) * 60ms); }

  .post { position: relative; display: flex; flex-direction: column; gap: 8px; padding: 12px 14px 10px; border-radius: var(--r-l); background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); }
  /* a broadcast: an edge in the brand gradient (a 1.5 px ring painted under the card) */
  .post.cast { background: radial-gradient(120% 70% at 0% 0%, rgba(124, 77, 255, 0.12), transparent 60%), var(--surface); box-shadow: none; }
  .post.cast::before { content: ''; position: absolute; inset: 0; padding: 1.5px; border-radius: inherit; pointer-events: none;
    background: linear-gradient(135deg, rgba(59, 107, 255, 0.85), rgba(124, 77, 255, 0.6) 40%, var(--line) 70%);
    -webkit-mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0); mask: linear-gradient(#000 0 0) content-box, linear-gradient(#000 0 0);
    -webkit-mask-composite: xor; mask-composite: exclude; }
  .ph { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .who { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 1px; }
  .who b { font: 650 14.5px/1.2 var(--font-text); }
  /* when · edited, then the pin: on a narrow phone the pin takes the next line whole */
  .who i { display: flex; flex-wrap: wrap; align-items: center; gap: 2px 8px; font: 550 12px/1.2 var(--font-text); font-style: normal; color: var(--text-3); }
  .when { white-space: nowrap; }
  .pinned { display: inline-flex; align-items: center; gap: 3px; white-space: nowrap; color: var(--accent-text); }
  .new { flex: none; padding: 4px 8px; border-radius: var(--r-full); background: var(--accent); color: #fff; font: 700 10.5px/1 var(--font-text); letter-spacing: 0.04em; text-transform: uppercase;
    box-shadow: 0 0 0 4px var(--accent-soft); animation: glow 2s ease-in-out infinite; }
  @keyframes glow { 50% { box-shadow: 0 0 0 7px transparent; } }
  :global(html.lowfx) .new { animation: none; } /* power saving: a box-shadow glow repaints every frame */
  .more { flex: none; display: flex; padding: 4px; margin: -4px -6px -4px 0; color: var(--text-3); }
  .pic { width: 100%; aspect-ratio: 16 / 10; object-fit: cover; border-radius: 16px; background: var(--surface-2); }
  .tt { font: 720 17px/1.25 var(--font-display); letter-spacing: -0.015em; }
  .bd { font: 450 15px/1.45 var(--font-text); color: var(--text-2); white-space: pre-line; overflow-wrap: anywhere; }
  .bd.fold { display: -webkit-box; -webkit-line-clamp: 4; line-clamp: 4; -webkit-box-orient: vertical; overflow: hidden; }
  .unfold { align-self: flex-start; margin-top: -4px; font: 650 14px/1 var(--font-text); color: var(--accent-text); padding: 2px 0; }
  .re { display: flex; gap: 6px; margin-top: 2px; }
  .re button { display: inline-flex; align-items: center; gap: 6px; height: 34px; padding: 0 12px 0 8px; border-radius: var(--r-full); background: var(--surface-2);
    transition: background-color var(--t-base) var(--ease), transform var(--t-fast) var(--ease); }
  .re button:active { transform: scale(0.94); }
  .re button.on { background: var(--accent-soft); box-shadow: inset 0 0 0 1.5px color-mix(in srgb, var(--accent) 55%, transparent); }
  .re b { font: 680 13.5px/1 var(--font-text); }
  .re .cm { margin-left: auto; padding: 0 12px; color: var(--text-2); }
  .re .cm b:empty { display: none; }
  .re button.on b { color: var(--accent-text); }
  .ej { display: flex; }
  .re button.on .ej { animation: boop 420ms cubic-bezier(.2, 1.6, .4, 1); }
  @keyframes boop { 30% { transform: scale(1.45) rotate(-8deg); } }

  .empty { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 26px 18px 18px; margin-top: 6px; text-align: center; border-radius: var(--r-xl);
    background: radial-gradient(80% 60% at 50% 0%, var(--accent-soft), transparent 70%), var(--surface); box-shadow: inset 0 0 0 1px var(--line); }
  .empty p { color: var(--text-2); max-width: 32ch; }
  .skel { display: flex; flex-direction: column; gap: 10px; }
  .skel span { height: 120px; border-radius: var(--r-l); background: var(--surface-2); animation: pulse 1.2s ease-in-out infinite; }
  .skel .tall { height: 280px; }
  @keyframes pulse { 50% { opacity: 0.5; } }
  @keyframes rise { from { opacity: 0; transform: translateY(14px) scale(0.98); } }
  .tail { flex: none; height: calc(var(--bottom) + 12px); }
</style>
