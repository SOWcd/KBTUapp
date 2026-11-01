<script lang="ts">
  // The Forum tab (Nov 1: the in-app forum became the public channel @KBTUappForum). A student writes a post here,
  // under their name or anonymously; the AI looks, its OK publishes at once, anything else waits for a moderator.
  // Comments live in Telegram. Below: the way to the channel and "My posts" with their status and a delete. Every tap
  // answers at once (the post shows "under review" while the AI looks; a delete leaves the list before the server
  // says so). Moderators see what waits, and this week's posts to take one down; the owner alone can reveal a mask.
  import { untrack } from 'svelte';
  import Send from '@lucide/svelte/icons/send';
  import Trash2 from '@lucide/svelte/icons/trash-2';
  import VenetianMask from '@lucide/svelte/icons/venetian-mask';
  import { api, ApiErr, type ChannelMod, type ChannelPost, type ChannelModPost } from '../../lib/api';
  import { session, asStudent } from '../../lib/state/session.svelte';
  import { channel, loadChannel } from '../../lib/state/channel.svelte';
  import { ui, say } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, type Key } from '../../lib/i18n/index.svelte';
  import { haptic, openLink } from '../../lib/tg';
  import { ago, nowTs } from '../../lib/time';
  import { burst } from '../../ui/burst';
  import { grow } from '../../ui/grow';
  import { fitTitle, largeTitle } from '../../ui/title';
  import { TAB_ICON } from '../../ui/icons';
  import Button from '../../ui/Button.svelte';
  import Card from '../../ui/Card.svelte';
  import Group from '../../ui/Group.svelte';
  import Row from '../../ui/Row.svelte';
  import Tag from '../../ui/Tag.svelte';
  import IconButton from '../../ui/IconButton.svelte';
  import EmptyState from '../../ui/EmptyState.svelte';

  const CHANNEL = 'https://t.me/KBTUappForum';
  const me = $derived(session.me);
  const student = $derived(!!me?.student);
  const staff = $derived(me?.role === 'admin' || me?.role === 'moderator');
  const owner = $derived(me?.role === 'admin' && !!me?.founder);
  const here = $derived(ui.tab === 'forum');
  $effect(() => { if (here && student) untrack(() => void loadChannel()); });
  let mod = $state<ChannelMod | null>(null);
  const loadMod = () => api.channelMod().then((m) => (mod = m)).catch(() => {});
  $effect(() => { if (here && staff) untrack(loadMod); });

  let body = $state(''), anon = $state(false), busy = $state(false);
  const ready = $derived(body.trim().length >= 2 && !busy);
  const TAG = { live: 'success', held: 'warning', hidden: 'neutral' } as const;
  const WHY: Record<string, Key> = { ai: 'fc.whyAi', person: 'fc.whyPerson', check: 'fc.whyCheck', busy: 'fc.whyBusy' };

  function fail(e: unknown, fallback: Key = 'common.error') {
    haptic.error();
    const why = e instanceof ApiErr ? (e.code === 'rate_limited' ? 'fc.slow' : e.message === 'links' ? 'fc.links' : fallback) : fallback;
    say(t(why), 'pleading_face_3d');
  }

  async function post() {
    if (!ready) return;
    const text = body.trim(), was = anon, temp: ChannelPost = { id: -Date.now(), body: text, anon: was, status: 'held', at: nowTs() };
    // at once: in my list "under review" (the AI is looking), the field empty again
    channel.mine = [temp, ...(channel.mine ?? [])]; body = ''; busy = true; haptic.select();
    try {
      const p = await api.newChannelPost(text, was);
      channel.mine = (channel.mine ?? []).map((x) => (x.id === temp.id ? p : x));
      haptic.ok();
      if (p.status === 'live') { burst(); say(t('fc.postedSay'), 'party_popper_3d'); } else say(t('fc.heldSay'), 'thinking_face_3d');
    } catch (e) {
      channel.mine = (channel.mine ?? []).filter((x) => x.id !== temp.id);
      if (!body) body = text; // the words come back to fix
      fail(e);
    } finally { busy = false; }
  }

  async function drop(p: ChannelPost) {
    if (!(await sheets.ask({ title: t('fc.deleteAsk'), text: t('fc.deleteText'), ok: t('fc.delete'), cancel: t('common.cancel'), danger: true }))) return;
    const before = channel.mine;
    channel.mine = (channel.mine ?? []).filter((x) => x.id !== p.id); haptic.ok();
    try { await api.deleteChannelPost(p.id); } catch (e) { channel.mine = before; fail(e); }
  }

  async function decide(p: ChannelModPost, ok: boolean) {
    const before = mod;
    if (mod) mod = { held: mod.held.filter((x) => x.id !== p.id), live: ok ? [p, ...mod.live] : mod.live.filter((x) => x.id !== p.id) };
    haptic.ok();
    try { await api.channelModDecide(p.id, ok); void loadMod(); } catch (e) { mod = before; fail(e); }
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
  <h1 class="fs-title ttl" use:fitTitle use:largeTitle={'forum'}>{t('page.forum')}</h1>

  {#if !student}
    <EmptyState icon={TAB_ICON.forum} title={t('fc.guestTitle')} text={t('fc.guestText')} action={{ label: t('fc.signIn'), onclick: () => asStudent(() => void loadChannel()) }} />
  {:else}
    <Card>
      <textarea class="text" bind:value={body} maxlength="1000" rows="3" placeholder={t('fc.ph')} aria-label={t('fc.ph')} use:grow={280}></textarea>
      <p class="rules">{t('fc.rules')}</p>
    </Card>
    <Group footnote={anon ? t('fc.asAnon') : t('fc.as', { name: me?.name ?? '' })}>
      <Row title={t('fc.anon')} icon={VenetianMask} tile="gray" accessory="switch" checked={anon} onchange={(v) => { anon = v; haptic.select(); }} />
    </Group>
    <Button kind="filled" size="l" full disabled={!ready} onclick={post}>{t('fc.post')}</Button>

    <Group>
      <Row title={t('fc.open')} icon={Send} tile="blue" accessory="external" onclick={() => openLink(CHANNEL)} />
    </Group>

    {#if staff && mod && (mod.held.length || mod.live.length)}
      {#if mod.held.length}<Group caption={t('fc.modTitle')}>{#each mod.held as p (p.id)}{@render modRow(p, true)}{/each}</Group>{/if}
      {#if mod.live.length}<Group caption={t('fc.modLive')}>{#each mod.live as p (p.id)}{@render modRow(p, false)}{/each}</Group>{/if}
    {/if}

    {#if channel.mine?.length}
      <Group caption={t('fc.mine')}>
        {#each channel.mine as p (p.id)}
          <div class="mine" class:off={p.status === 'hidden'}>
            <div class="mx">
              <p class="mtx">{p.body}</p>
              <span class="meta"><Tag tone={TAG[p.status]}>{t(`fc.${p.status}`)}</Tag>
                {#if p.anon}<VenetianMask size={14} strokeWidth={2} aria-label={t('fc.anon')} />{/if}<span class="when">{ago(p.at)}</span></span>
            </div>
            {#if p.id > 0}<IconButton icon={Trash2} label={t('fc.delete')} kind="plain" size="s" onclick={() => drop(p)} />{/if}
          </div>
        {/each}
      </Group>
    {/if}
  {/if}
  <div class="tail"></div>
</div>

<style>
  .page { position: absolute; inset: 0; padding: var(--page-top) var(--gutter) 0; display: flex; flex-direction: column; gap: var(--s-4); }
  .page > :global(*) { flex-shrink: 0; }
  .ttl { margin: 0 var(--s-1); }
  /* the words: no box of their own inside the card, the card is the field */
  .text { display: block; width: 100%; min-height: 84px; padding: 0; border: 0; resize: none; background: none; color: var(--text);
    font: 450 var(--fs-row)/1.4 var(--font-text); letter-spacing: -0.012em; }
  .text::placeholder { color: var(--text-3); }
  .text:focus { outline: none; }
  .rules { margin-top: var(--s-3); padding-top: var(--s-3); border-top: 0.5px solid var(--separator); font: 450 var(--fs-sub)/1.35 var(--font-text); color: var(--text-3); }
  /* my posts: the words (three lines at most), then the status and when; the delete at the row's end */
  .mine { position: relative; display: flex; align-items: center; gap: var(--s-2); padding: var(--s-3) var(--s-2) var(--s-3) var(--s-4); animation: rise 360ms cubic-bezier(.2, .9, .25, 1.05) backwards; }
  .mine + .mine::before, .mrow + .mrow::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .mine.off .mtx { color: var(--text-3); }
  .mx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: var(--s-2); }
  .mtx { font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text); white-space: pre-line; overflow-wrap: break-word;
    display: -webkit-box; -webkit-line-clamp: 3; line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; }
  .meta { display: flex; align-items: center; gap: var(--s-2); color: var(--text-3); }
  .when { font: 450 var(--fs-sub)/1.2 var(--font-text); }
  @keyframes rise { from { opacity: 0; transform: translateY(8px); } }
  /* the moderators' rows: the words, whose and why, the answers */
  .mrow { position: relative; display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-3) var(--s-4); }
  .mt { font: 450 var(--fs-body)/1.4 var(--font-text); white-space: pre-line; overflow-wrap: break-word; }
  .mm { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .mb { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  .tail { height: calc(var(--bottom) + var(--s-8)); }
</style>
