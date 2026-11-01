<script lang="ts">
  // The Forum tab (Nov 1: the in-app forum became the public channel @KBTUappForum). Posts only: the channel's feed,
  // newest first, signed as there; a tap opens the post in Telegram, where the comments are. My own posts are marked
  // (on their way, under review, removed) and can be deleted. Writing is a separate screen behind the plus by the
  // title (ChannelCompose), the way Studio puts its pencil. Every tap answers at once (a new post stands at the top
  // "checking"; a delete leaves the list before the server says so). Moderators see what waits, and this week's posts
  // to take one down; the owner alone can reveal a mask.
  import { untrack } from 'svelte';
  import TelegramMark from '../../ui/TelegramMark.svelte';
  import Plus from '@lucide/svelte/icons/plus';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import { api, ApiErr, type ChannelMod, type ChannelFeedPost, type ChannelModPost } from '../../lib/api';
  import { session, asStudent } from '../../lib/state/session.svelte';
  import { channel, loadChannel } from '../../lib/state/channel.svelte';
  import { ui, say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, type Key } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { ago } from '../../lib/time';
  import { glass } from '../../ui/glass';
  import { fitTitle, largeTitle } from '../../ui/title';
  import { TAB_ICON } from '../../ui/icons';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  const CHANNEL = 'https://t.me/KBTUappForum';
  const me = $derived(session.me);
  const staff = $derived(me?.role === 'admin' || me?.role === 'moderator');
  const owner = $derived(me?.role === 'admin' && !!me?.founder);
  const here = $derived(ui.tab === 'forum');
  $effect(() => { if (here) untrack(() => void loadChannel()); });
  let mod = $state<ChannelMod | null>(null);
  const loadMod = () => api.channelMod().then((m) => (mod = m)).catch(() => {});
  $effect(() => { if (here && staff) untrack(loadMod); });

  const WHY: Record<string, Key> = { ai: 'fc.whyAi', person: 'fc.whyPerson', check: 'fc.whyCheck', busy: 'fc.whyBusy', lost: 'fc.whyLost' };
  // my own row's mark: on its way (the AI looking), under review, removed, else simply "mine"
  const mark = (p: ChannelFeedPost) => p.id < 0 ? { tone: 'neutral', key: 'fc.checking' } as const
    : p.status === 'held' ? { tone: 'warning', key: 'fc.held' } as const
    : p.status === 'hidden' ? { tone: 'neutral', key: 'fc.hidden' } as const : { tone: 'accent', key: 'fc.mine' } as const;

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
    channel.feed = (channel.feed ?? []).filter((x) => x.id !== p.id); haptic.ok();
    try { await api.deleteChannelPost(p.id); } catch (e) { channel.feed = before; fail(e); }
  }

  async function decide(p: ChannelModPost, ok: boolean) {
    const before = mod;
    if (mod) mod = { held: mod.held.filter((x) => x.id !== p.id), live: ok ? [p, ...mod.live] : mod.live.filter((x) => x.id !== p.id) };
    haptic.ok();
    try { await api.channelModDecide(p.id, ok); void loadMod(); if (!ok) void loadChannel(); } catch (e) { mod = before; fail(e); }
  }

  async function reveal(p: ChannelModPost) {
    if (!(await sheets.ask({ title: t('fc.revealAsk'), text: t('fc.revealText'), ok: t('fc.reveal'), cancel: t('common.cancel') }))) return;
    try { const who = await api.revealChannelPost(p.id); say(t('fc.wrote', { name: who.name }), 'locked_3d'); } catch (e) { fail(e); }
  }
</script>

{#snippet modRow(p: ChannelModPost, held: boolean)}
  <div class="mrow">
    <p class="mt">{p.body}</p>
    <span class="mm">{p.anon ? t('fc.anon') : p.author?.name ?? ''} · {ago(p.at)}{held && p.why ? ' · ' + t(WHY[p.why] ?? 'fc.whyCheck') : ''}</span>
    <span class="mb">
      {#if held}<Button kind="tinted" size="s" onclick={() => decide(p, true)}>{t('fc.release')}</Button>{/if}
      <Button kind="gray" size="s" onclick={() => decide(p, false)}>{t('fc.takeDown')}</Button>
      {#if owner && p.anon}<Button kind="plain" size="s" onclick={() => reveal(p)}>{t('fc.reveal')}</Button>{/if}
    </span>
  </div>
{/snippet}

<div class="page scroll">
  <header class="hd">
    <h1 class="fs-title ttl" use:fitTitle use:largeTitle={'forum'}>{t('page.forum')}</h1>
    <button class="ic glass glass-pill" use:glass onclick={write} aria-label={t('fc.new')}><Plus size={22} strokeWidth={2.4} /></button>
  </header>

  {#if staff && mod?.held.length}
    <Group caption={t('fc.modTitle')}>{#each mod.held as p (p.id)}{@render modRow(p, true)}{/each}</Group>
  {/if}

  {#if channel.feed?.length}
    <Group>
      {#each channel.feed as p (p.id)}
        {@const m = p.mine ? mark(p) : null}
        <div class="post" class:off={p.status === 'hidden'}>
          <button class="pb" onclick={() => { if (p.msg) { haptic.tap(); openLink(`${CHANNEL}/${p.msg}`); } }}>
            <p class="tx">{p.body}</p>
            <span class="meta"><b class="who ellipsis">{p.sign}</b><span class="when">{ago(p.at)}</span>
              {#if m}<Tag tone={m.tone}>{t(m.key)}</Tag>{/if}</span>
          </button>
          {#if p.mine && p.id > 0}<span class="del"><IconButton icon={Trash2} label={t('fc.delete')} kind="plain" size="s" onclick={() => drop(p)} /></span>{/if}
        </div>
      {/each}
    </Group>
  {:else if channel.feed}
    <EmptyState icon={TAB_ICON.forum} title={t('fc.emptyTitle')} text={t('fc.emptyText')} />
  {/if}

  <Group>
    <Row title={t('fc.open')} icon={TelegramMark} tile="blue" accessory="external" onclick={() => openLink(CHANNEL)} />
  </Group>

  {#if staff && mod?.live.length}
    <Group caption={t('fc.modLive')}>{#each mod.live as p (p.id)}{@render modRow(p, false)}{/each}</Group>
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: var(--s-4); }
  .page > :global(*) { flex-shrink: 0; }
  .hd { display: flex; align-items: center; gap: var(--s-3); margin: 0 var(--s-1); }
  .ttl { flex: 1; min-width: 0; }
  /* the plus: Studio's round glass action by the title */
  .ic { flex: none; width: 44px; height: 44px; border-radius: 50%; display: grid; place-items: center; color: var(--text);
    transition: transform 0.45s var(--ease-bounce); }
  .ic:active { transform: scale(0.9); transition-duration: 80ms; }
  /* a post: its words (eight lines at most), then the signature, when, and my mark; my delete at the row's end */
  .post { position: relative; display: flex; align-items: flex-start; animation: rise 360ms cubic-bezier(.2, .9, .25, 1.05) backwards; }
  .post + .post::before, .mrow + .mrow::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .pb { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-3) var(--s-4); text-align: left; color: inherit; }
  .pb:active { opacity: 0.6; }
  .del { padding: var(--s-2) var(--s-2) 0 0; }
  .tx { font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text); white-space: pre-line; overflow-wrap: break-word;
    display: -webkit-box; -webkit-line-clamp: 8; line-clamp: 8; -webkit-box-orient: vertical; overflow: hidden; }
  .post.off .tx { color: var(--text-3); }
  .meta { display: flex; align-items: center; gap: var(--s-2); min-width: 0; font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .who { font-weight: 600; color: var(--text-2); min-width: 0; }
  .when { flex: none; }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } }
  /* the moderators' rows: the words, whose and why, the answers */
  .mrow { position: relative; display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-3) var(--s-4); }
  .mt { font: 450 var(--fs-body)/1.4 var(--font-text); white-space: pre-line; overflow-wrap: break-word; }
  .mm { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .mb { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  .tail { height: calc(var(--bottom) + var(--s-8)); }
</style>
