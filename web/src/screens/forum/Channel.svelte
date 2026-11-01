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
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import { initials } from '../../ui/OrgLogo.svelte';
  import Card from '../../ui/Card.svelte';
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
    <div class="feed">
      {#each channel.feed as p (p.id)}
        {@const m = p.mine ? mark(p) : null}
        {#snippet post()}
          <div class="who">
            <span class="av" aria-hidden="true">{#if p.anon}<VenetianMask size={16} strokeWidth={2} />{:else}{initials(p.sign)}{/if}</span>
            <span class="nm"><b class="ellipsis">{p.sign}</b><span class="when">{ago(p.at)}</span></span>
            {#if m}<Tag tone={m.tone}>{t(m.key)}</Tag>{/if}
            {#if p.mine && p.id > 0}<IconButton icon={Trash2} label={t('fc.delete')} kind="plain" size="s" onclick={() => drop(p)} />{/if}
          </div>
          <p class="tx" class:fade={long[p.id] && !open[p.id]} class:open={open[p.id]} style:--h="{full[p.id] ?? 0}px" use:measure={p.id}>{p.body}</p>
          {#if long[p.id] && !open[p.id]}<button class="more" onclick={() => { haptic.tap(); open[p.id] = true; }}>{t('common.more')}</button>{/if}
        {/snippet}
        <div class="post" class:off={p.status === 'hidden'}>
          {#if p.msg}<Card onclick={() => { haptic.tap(); openLink(`${CHANNEL}/${p.msg}`); }}>{@render post()}</Card>
          {:else}<Card>{@render post()}</Card>{/if}
        </div>
      {/each}
    </div>
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
  /* the feed: a card per post, air between them */
  .feed { display: flex; flex-direction: column; gap: var(--s-3); }
  .post { animation: rise 360ms cubic-bezier(.2, .9, .25, 1.05) backwards; }
  /* whose (initials, or the mask for an anonymous one), when, my mark and delete */
  .who { display: flex; align-items: center; gap: var(--s-3); min-height: 36px; margin: calc(-1 * var(--s-1)) 0 var(--s-3); }
  .av { flex: none; width: 32px; height: 32px; border-radius: 50%; display: grid; place-items: center; background: var(--surface-2);
    color: var(--text-2); font: 600 var(--fs-cap)/1 var(--font-text); letter-spacing: 0.02em; }
  .nm { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .nm b { font: 600 var(--fs-body)/1.2 var(--font-text); color: var(--text); }
  .when { font: 450 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); }
  .who :global(.ib) { margin-right: calc(-1 * var(--s-2)); }
  .who :global(.ib button) { color: var(--text-3); } /* the delete stays quiet: the words are the card */
  /* the words: four lines and a fade while long and closed; open, the height glides to the whole */
  .tx { font: 450 var(--fs-body)/1.45 var(--font-text); color: var(--text); white-space: pre-line; overflow-wrap: break-word;
    max-height: 5.8em; overflow: hidden; transition: max-height 420ms var(--ease); }
  .tx.fade { -webkit-mask-image: linear-gradient(to bottom, black 50%, transparent); mask-image: linear-gradient(to bottom, black 50%, transparent); }
  .tx.open { max-height: var(--h); }
  .post.off .tx { color: var(--text-3); }
  .more { margin-top: var(--s-1); padding: var(--s-1) 0; font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .mrow + .mrow::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } }
  /* the moderators' rows: the words, whose and why, the answers */
  .mrow { position: relative; display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-3) var(--s-4); }
  .mt { font: 450 var(--fs-body)/1.4 var(--font-text); white-space: pre-line; overflow-wrap: break-word; }
  .mm { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .mb { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  .tail { height: calc(var(--bottom) + var(--s-8)); }
</style>
