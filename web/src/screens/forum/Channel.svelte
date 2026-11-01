<script lang="ts">
  // The Forum tab (Nov 1: the in-app forum became the public channel @KBTUappForum). Posts only: the channel's feed,
  // newest first; a tap opens the post in Telegram, its Comments row the comments. My own posts are
  // marked (on their way, under review, removed) and can be deleted. No large title (the capsule names the tab, Nov 2):
  // the feed starts with a Threads-like "Share with KBTU…" row that opens the new post screen (ChannelCompose). A signed
  // post shows its author as the app does (his nick if he has one, else the short name; his profile on a tap), while the
  // channel signs it with the short name; an anonymous one a mask, nobody behind it (the API sends no one). Every tap answers at once (a new post stands at the top "checking"; a delete leaves the list before the
  // server says so). It looks the same for every viewer, staff too: the channel's moderation lives in Admin alone.
  // A card mirrors Telegram, read-only: the post's top reactions and its newest commenters' faces (Nov 2).
  import { tick, untrack } from 'svelte';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import SquarePen from '@lucide/svelte/icons/square-pen';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import Avatar from '../../ui/Avatar.svelte';
  import { initials } from '../../ui/OrgLogo.svelte';
  import Card from '../../ui/Card.svelte';
  import { api, ApiErr, type ChannelFeedPost } from '../../lib/api';
  import { session, asStudent } from '../../lib/state/session.svelte';
  import { channel, loadChannel } from '../../lib/state/channel.svelte';
  import { ui, say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { ago } from '../../lib/time';
  import { TAB_ICON } from '../../ui/icons';
  import Tag from '../../ui/Tag.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  const CHANNEL = 'https://t.me/KBTUappForum';
  const me = $derived(session.me);
  const here = $derived(ui.tab === 'forum');
  $effect(() => { if (here) untrack(() => void loadChannel().then(seek)); });

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
  // a reaction as plain text: a custom emoji (only its id comes) and a paid star as their nearest plain ones
  const glyph = (e: string) => e.startsWith('custom:') ? '✨' : e === 'paid' ? '⭐' : e;

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
</script>

<div class="page scroll">
  <!-- the way to write: my face and a quiet prompt, the whole row a tap (Threads' composer) -->
  <Card onclick={write}>
    <div class="who compose">
      {#if me}<Avatar person={me} size={32} tappable={false} />{:else}<span class="av" aria-hidden="true"><SquarePen size={16} strokeWidth={2} /></span>{/if}
      <span class="prompt">{t('fc.share')}</span>
    </div>
  </Card>

  {#if channel.feed?.length}
    <div class="feed">
      {#each channel.feed as p (p.id)}
        {@const m = p.mine ? mark(p) : null}
        {#snippet post()}
          <div class="who">
            {#if p.person}
              <Avatar person={p.person} size={32} />
              <span class="nm"><button class="name" onclick={() => { haptic.tap(); sheets.person(p.person!.id); }}><b class="ellipsis">{p.person.name}</b></button><span class="when">{ago(p.at)}</span></span>
            {:else}
              <!-- anonymous: the mask; an author no longer here (a deleted account): the signature's initials -->
              <span class="av" aria-hidden="true">{#if p.anon}<VenetianMask size={16} strokeWidth={2} />{:else}{initials(p.sign)}{/if}</span>
              <span class="nm"><b class="ellipsis">{p.sign}</b><span class="when">{ago(p.at)}</span></span>
            {/if}
            {#if m}<Tag tone={m.tone}>{t(m.key)}</Tag>{/if}
            {#if p.mine && p.id > 0}<IconButton icon={Trash2} label={t('fc.delete')} kind="plain" size="s" onclick={() => drop(p)} />{/if}
          </div>
          <p class="tx" class:fade={long[p.id] && !open[p.id]} class:open={open[p.id]} style:--h="{full[p.id] ?? 0}px" use:measure={p.id}>{p.body}</p>
          {#if long[p.id] && !open[p.id]}<button class="more" onclick={() => { haptic.tap(); open[p.id] = true; }}>{t('common.more')}</button>{/if}
          {#if p.msg && p.status === 'live'}
            <!-- Telegram's reactions, read-only (the whole card opens the post, where they are left) -->
            {#if p.reactions.length}
              <div class="rx">{#each p.reactions as r (r.emoji)}<span class="chip"><span class="e">{glyph(r.emoji)}</span>{r.n}</span>{/each}</div>
            {/if}
            <button class="cm" onclick={() => { haptic.tap(); openLink(comments(p)); }}>
              <MessageCircle size={18} strokeWidth={2} /><span>{t('fc.comments')}</span>
              <!-- who is talking there: the newest commenters' faces (app students only), then the count -->
              {#if p.faces.length}<span class="faces">{#each p.faces as f (f.id)}<Avatar person={f} size={20} tappable={false} />{/each}</span>{/if}
              {#if p.comments}<span class="n" class:after={p.faces.length}>{p.comments}</span>{/if}
            </button>
          {/if}
        {/snippet}
        <div class="post" class:off={p.status === 'hidden'} class:lit={lit === p.id} data-post={p.id}>
          {#if p.msg}<Card onclick={() => { haptic.tap(); openLink(`${CHANNEL}/${p.msg}`); }}>{@render post()}</Card>
          {:else}<Card>{@render post()}</Card>{/if}
        </div>
      {/each}
    </div>
  {:else if channel.feed}
    <EmptyState icon={TAB_ICON.forum} title={t('fc.emptyTitle')} text={t('fc.emptyText')} />
  {/if}

  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: var(--s-4); }
  .page > :global(*) { flex-shrink: 0; }
  /* the composer row: a post's header line, the words a quiet prompt */
  .who.compose { margin: calc(-1 * var(--s-1)) 0; }
  .prompt { flex: 1; min-width: 0; font: 450 var(--fs-body)/1.2 var(--font-text); color: var(--text-3); }
  /* the feed: a card per post, air between them */
  .feed { display: flex; flex-direction: column; gap: var(--s-3); }
  .post { animation: rise 360ms cubic-bezier(.2, .9, .25, 1.05) backwards; }
  /* the post the bot's button pointed at: an accent ring that fades */
  .post.lit :global(.card) { animation: lit 1.8s var(--ease); }
  @keyframes lit { 0%, 45% { box-shadow: 0 0 0 2px var(--accent), var(--shadow-card); } }
  .name { display: flex; min-width: 0; padding: 0; text-align: left; }
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
  /* the way to the comments: a full-width row under the words, a hairline above it */
  .cm { display: flex; align-items: center; gap: var(--s-2); width: 100%; min-height: 44px; margin: var(--s-3) 0 calc(-1 * var(--s-2));
    padding: var(--s-2) 0 0; border-top: 0.5px solid var(--separator); font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .cm:active { opacity: 0.6; }
  .cm .n { margin-left: auto; color: var(--text-3); font-variant-numeric: tabular-nums; }
  .cm .n.after { margin-left: 0; }
  /* the faces: overlapping, each cut out of the card by a ring of its colour */
  .faces { margin-left: auto; display: flex; }
  .faces :global(.av) { box-shadow: 0 0 0 1.5px var(--surface); }
  .faces :global(.av + .av) { margin-left: -6px; }
  /* reactions: small quiet pills under the words, as Telegram shows them */
  .rx { display: flex; flex-wrap: wrap; gap: var(--s-1); margin-top: var(--s-3); }
  .chip { display: inline-flex; align-items: center; gap: 4px; height: 26px; padding: 0 var(--s-2); border-radius: var(--r-full); background: var(--surface-2);
    font: 600 var(--fs-cap)/1 var(--font-text); color: var(--text-2); font-variant-numeric: tabular-nums; }
  .chip .e { font-size: var(--fs-sub); line-height: 1; }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } }
  .tail { height: calc(var(--bottom) + var(--s-8)); }
</style>
