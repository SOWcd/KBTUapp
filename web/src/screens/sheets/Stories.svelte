<script lang="ts">
  // News as stories (owner, Oct 24; PLAN 46): a club's posts full screen, one at a time. A tap on the right goes on, on the
  // left back; past a club's last post the next club follows, past the last club it closes; a pull down, Back or the
  // cross closes. No timer: posts are read, not glanced at. Seen posts are marked read (the circle's ring and the dot go).
  // The post's own tools sit here now that the News page is gone: reactions, comments, and in ⋯ edit, pin, show on
  // List, take down, report.
  import { onMount } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import Ellipsis from '@lucide/svelte/icons/ellipsis';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import Pin from '@lucide/svelte/icons/pin';
  import { api, type Post } from '../../lib/api';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { data, loadAfisha, loadNews, phrase } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { ago } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import { focusPos } from '../../lib/photo';
  import { tagName, storyStart, type StoryGroup } from '../../lib/posts';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import Emoji from '../../ui/Emoji.svelte';

  // at: open on that post of the first club (a club page's news list), else its first unread
  let { overlay, groups, start = 0, at }: { overlay: Overlay; groups: StoryGroup[]; start?: number; at?: number } = $props();

  let gi = $state(0);
  let pi = $state(0);
  let menu = $state(false);
  const g = $derived(groups[gi]);
  const p = $derived(g?.posts[pi]);
  let root: HTMLDivElement;
  let gone = false;

  onMount(() => {
    gi = start; pi = at ?? storyStart(groups[start]);
    root.animate([{ opacity: 0, transform: 'scale(0.96)' }, { opacity: 1, transform: 'none' }], { duration: 260, easing: 'cubic-bezier(.2,.8,.2,1)' });
    haptic.soft();
    return hideChrome();
  });
  function leave() {
    if (gone) return;
    gone = true;
    const a = root.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: `translate3d(0,${pull}px,0) scale(0.94)` }], { duration: 220, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
    clearTimeout(timer); // the marks land before the Afisha dot is asked again
    if (read.size) void api.readPosts([...read]).catch(() => {}).then(loadMe);
  }
  $effect(() => { if (overlay.closing) leave(); });
  $effect(() => { overlay.title = g?.org.name ?? ''; overlay.theme = 'dark'; }); // the capsule names the club

  // read once on screen; sent in one go a moment later
  const read = new Set<number>();
  let timer: ReturnType<typeof setTimeout> | undefined;
  $effect(() => {
    if (!p || p.read || !session.me?.student) return;
    p.read = true; read.add(p.id);
    if (g) g.unread = g.posts.some((x) => !x.read);
    clearTimeout(timer);
    timer = setTimeout(() => api.readPosts([...read]).catch(() => {}), 600);
  });
  $effect(() => () => { clearTimeout(timer); if (!gone && read.size) api.readPosts([...read]).catch(() => {}); });

  function step(d: 1 | -1) {
    menu = false;
    if (d > 0 ? pi < g.posts.length - 1 : pi > 0) { pi += d; haptic.select(); return; }
    if (d > 0 ? gi < groups.length - 1 : gi > 0) { gi += d; pi = d > 0 ? storyStart(groups[gi]) : groups[gi].posts.length - 1; haptic.select(); return; }
    if (d > 0) close(overlay.id);
  }
  function tap(e: MouseEvent) {
    if (moved) return;
    step(e.clientX > innerWidth * 0.33 ? 1 : -1);
  }

  // pull down to close
  let pull = $state(0), dragging = $state(false), y0 = 0, moved = false;
  function down(e: PointerEvent) { y0 = e.clientY; moved = false; dragging = true; }
  function move(e: PointerEvent) { if (!dragging) return; const d = e.clientY - y0; if (d > 8) moved = true; pull = Math.max(0, d); }
  function up() { if (!dragging) return; dragging = false; if (pull > 110) close(overlay.id); else pull = 0; setTimeout(() => (moved = false)); }

  async function react(kind: 'fire' | 'heart') {
    if (!p) return;
    const q = p, on = !q.mine[kind];
    q.mine[kind] = on; q.reactions[kind] += on ? 1 : -1;
    haptic.select();
    try { Object.assign(q, await api.react(q.id, kind, on)); if (on) say(phrase(kind === 'fire' ? 'say.fire' : 'say.heart'), kind === 'fire' ? 'fire_3d' : 'smiling_face_with_heart_eyes_3d'); }
    catch { q.mine[kind] = !on; q.reactions[kind] += on ? -1 : 1; say(t('common.error'), 'pleading_face_3d'); }
  }
  async function pin() {
    if (!p) return;
    menu = false;
    try { await api.updatePost(p.id, { pinned: !p.pinned }); haptic.ok(); say(phrase(p.pinned ? 'news.unpinSay' : 'news.pinSay'), 'sparkles_3d'); p.pinned = !p.pinned; void loadNews(); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  async function feature(days: number) {
    if (!p) return;
    menu = false;
    try { Object.assign(p, await api.feature(p.id, days)); haptic.ok(); say(days ? t('news.featured') : t('news.unfeatured'), 'sparkles_3d'); void loadAfisha(); void loadNews(); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  // a post taken down or reported leaves the stories at once
  function drop(q: Post) {
    g.posts.splice(g.posts.indexOf(q), 1);
    if (data.news) data.news = { casts: data.news.casts.filter((x) => x.id !== q.id), posts: data.news.posts.filter((x) => x.id !== q.id) };
    if (!g.posts.length) { groups.splice(gi, 1); if (!groups.length) { close(overlay.id); return; } gi = Math.min(gi, groups.length - 1); pi = 0; return; }
    pi = Math.min(pi, g.posts.length - 1);
  }
  async function takeDown() {
    if (!p) return;
    menu = false;
    const q = p;
    if (!(await sheets.ask({ title: t('news.hideAsk'), text: t('news.hideText'), ok: t('news.hide'), cancel: t('common.cancel'), danger: true }))) return;
    try { await api.hidePost(q.id); haptic.ok(); say(t('news.hidden'), 'waving_hand_3d_default'); drop(q); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
  function report() { if (!p) return; menu = false; const q = p; sheets.report('post', q.id, q.title, () => drop(q)); }
</script>

<div class="st" bind:this={root} style:transform={pull ? `translate3d(0,${pull}px,0) scale(${1 - Math.min(pull, 300) / 2000})` : ''} class:back={!dragging}
  onpointerdown={down} onpointermove={move} onpointerup={up} onpointercancel={up} role="dialog" aria-modal="true" tabindex="-1" aria-label={g?.org.name}>
  {#if g && p}
    {#key p.id}
      <div class="bg" class:pic={!!p.photo}>
        {#if p.photo}<img src={p.photo.url} alt="" decoding="async" style:object-position={focusPos(p.photo)} />{/if}
      </div>
    {/key}
    <button class="tapzone" onclick={tap} aria-label={t('story.next')}></button>

    <div class="top">
      <div class="bars">{#each g.posts as x, i (x.id)}<i class:done={i < pi} class:now={i === pi}></i>{/each}</div>
      <div class="who">
        <button class="org" onclick={() => sheets.club(g.org.id)}><OrgLogo org={g.org} size={36} />
          <span><small>{ago(p.createdAt)}{#if p.tag}{' · ' + tagName(p.tag)}{/if}{#if p.editedAt}{' · ' + t('news.edited')}{/if}</small></span></button>
        {#if p.pinned}<span class="pinned" aria-label={t('news.pinned')}><Pin size={15} /></span>{/if}
        {#if p.canEdit || p.canDelete || p.canFeature || session.me?.student}<button class="ib" onclick={() => (menu = !menu)} aria-label={t('common.more')} aria-expanded={menu}><Ellipsis size={20} /></button>{/if}
        <button class="ib" onclick={() => close(overlay.id)} aria-label={t('common.close')}><X size={20} /></button>
      </div>
      {#if menu}
        <div class="menu">
          {#if p.canEdit}
            <button onclick={() => { menu = false; sheets.composer(p.org.id, p); }}>{t('news.edit')}</button>
            <button onclick={pin}>{p.pinned ? t('news.unpin') : t('news.pin')}</button>
          {/if}
          {#if p.canFeature}<button onclick={() => feature(p.featured ? 0 : 3)}>{p.featured ? t('news.unfeature') : t('news.feature')}</button>{/if}
          {#if p.canDelete}<button class="danger" onclick={takeDown}>{t('news.hide')}</button>{/if}
          {#if !p.canEdit && session.me?.student}<button onclick={report}>{t('cm.report')}</button>{/if}
        </div>
      {/if}
    </div>

    {#key p.id}
      <div class="txt">
        <h2>{p.title}</h2>
        {#if p.body}<p class="scroll" data-noswipe>{p.body}</p>{/if}
      </div>
    {/key}

    <div class="acts">
      <button class:on={p.mine.fire} onclick={() => react('fire')} aria-pressed={p.mine.fire}><Emoji name="fire_3d" size={20} /><b class="num">{p.reactions.fire}</b></button>
      <button class:on={p.mine.heart} onclick={() => react('heart')} aria-pressed={p.mine.heart}><Emoji name="blue_heart_3d" size={20} /><b class="num">{p.reactions.heart}</b></button>
      {#if p.commentsOn || p.comments}
        <button onclick={() => sheets.comments('post', p.id, p.title, (n) => (p.comments = n))} aria-label={t('cm.title')}><MessageCircle size={19} /><b class="num">{p.comments || ''}</b></button>
      {/if}
    </div>
  {/if}
</div>

<style>
  .st { position: absolute; inset: 0; z-index: var(--z-sheet); background: #000; color: #fff; overflow: hidden; touch-action: none; user-select: none; }
  .st.back { transition: transform 260ms cubic-bezier(.32,.72,0,1); }
  .bg { position: absolute; inset: 0; background: #0E0F14; animation: in 220ms ease-out both; }
  .bg img { width: 100%; height: 100%; object-fit: cover; }
  .bg::after { content: ''; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(0, 0, 0, 0.55), transparent 22%, transparent 45%, rgba(0, 0, 0, 0.85)); }
  .tapzone { position: absolute; inset: 0; }
  .top { position: absolute; left: 12px; right: 12px; top: calc(var(--head-bottom) + 8px); display: flex; flex-direction: column; gap: 10px; }
  .bars { display: flex; gap: 4px; }
  .bars i { flex: 1; height: 3px; border-radius: 2px; background: rgba(255, 255, 255, 0.3); transition: background 200ms; }
  .bars i.done, .bars i.now { background: #fff; }
  .who { position: relative; display: flex; align-items: center; gap: 6px; }
  .org { flex: 1; min-width: 0; display: flex; align-items: center; gap: 10px; text-align: left; color: #fff; }
  .org span { display: flex; flex-direction: column; min-width: 0; }
  .org small { font: 500 12px/1.3 var(--font-text); color: rgba(255, 255, 255, 0.7); }
  .pinned { display: inline-flex; color: rgba(255, 255, 255, 0.7); }
  .ib { position: relative; width: 40px; height: 40px; flex: none; border-radius: 50%; display: grid; place-items: center; color: #fff; background: rgba(255, 255, 255, 0.12); }
  .ib:active { transform: scale(0.92); }
  .menu { position: relative; display: flex; flex-wrap: wrap; gap: 6px; justify-content: flex-end; }
  .menu button { height: 34px; padding: 0 14px; border-radius: var(--r-full); background: rgba(30, 32, 40, 0.92); color: #fff; font: 620 13px/1 var(--font-text); }
  .menu .danger { color: #FF8A84; }
  .txt { position: absolute; left: 18px; right: 18px; bottom: calc(var(--safe-bottom) + 84px); display: flex; flex-direction: column; gap: 10px; pointer-events: none; animation: in 240ms ease-out both; }
  .txt h2 { margin: 0; font: 760 26px/1.12 var(--font-display); letter-spacing: -0.02em; text-wrap: balance; }
  .txt p { margin: 0; max-height: 34vh; overflow-y: auto; pointer-events: auto; white-space: pre-line; font: 450 15.5px/1.45 var(--font-text); color: rgba(255, 255, 255, 0.88); touch-action: pan-y; }
  .acts { position: absolute; left: 14px; right: 14px; bottom: calc(var(--safe-bottom) + 22px); display: flex; gap: 8px; }
  .acts button { height: 44px; padding: 0 14px; display: inline-flex; align-items: center; gap: 7px; border-radius: var(--r-full); background: rgba(255, 255, 255, 0.12); color: #fff; font: 650 14px/1 var(--font-text); }
  .acts button.on { background: rgba(255, 255, 255, 0.26); }
  .acts button:active { transform: scale(0.95); }
  @keyframes in { from { opacity: 0; } }
</style>
