<script lang="ts">
  // Admin → Forum posts (owner, Nov 1: staff tools live in Admin alone; the Forum tab looks the same for everyone).
  // The channel's posts waiting for a moderator (Publish / Remove), this week's live ones (Take down; Publish again for
  // one whose message someone deleted in Telegram by hand), and this week's
  // take-downs with Bring back (published anew); the owner alone reveals an anonymous author, each look audited.
  // Every removal asks first. Below, the find-people forum's own queue and skills catalog (silent when it's off).
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import { api, type ChannelMod, type ChannelModPost } from '../../lib/api';
  import { session } from '../../lib/state/session.svelte';
  import { loadChannel } from '../../lib/state/channel.svelte';
  import { say, type Overlay } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, type Key } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { ago } from '../../lib/time';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import Group from '../../ui/Group.svelte';
  import ForumMod from '../forum/ForumMod.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const owner = $derived(session.me?.role === 'admin' && !!session.me?.founder);
  let mod = $state<ChannelMod | null>(null);
  const load = () => api.channelMod().then((m) => (mod = m)).catch(() => {});
  $effect(() => { void load(); });
  const WHY: Record<string, Key> = { ai: 'fc.whyAi', person: 'fc.whyPerson', check: 'fc.whyCheck', busy: 'fc.whyBusy', lost: 'fc.whyLost' };

  function fail() { haptic.error(); say(t('common.error'), 'warning_3d'); }

  async function decide(p: ChannelModPost, ok: boolean, held: boolean) {
    if (!ok && !(await sheets.ask({ title: t(held ? 'fc.removeAsk' : 'fc.takeDownAsk'), text: t(held ? 'fc.removeText' : 'fc.takeDownText'),
      ok: t('fc.takeDown'), cancel: t('common.cancel'), danger: true }))) return;
    const before = mod;
    // a live one keeps its channel message for the server's minute: Undo till then, Bring back after (a reload then)
    if (mod) mod = { held: mod.held.filter((x) => x.id !== p.id), live: ok ? [p, ...mod.live] : mod.live.filter((x) => x.id !== p.id),
      removed: ok ? mod.removed : [{ ...p, undo: !held }, ...mod.removed] };
    haptic.ok();
    try { await api.channelModDecide(p.id, ok); void load(); void loadChannel(); if (!ok && !held) setTimeout(load, 61_000); }
    catch { mod = before; fail(); }
  }

  async function restore(p: ChannelModPost) {
    const before = mod;
    if (mod) mod = { ...mod, removed: mod.removed.filter((x) => x.id !== p.id) };
    haptic.ok();
    try { await api.channelModRestore(p.id); say(t(p.undo ? 'fc.undoneSay' : 'fc.restoredSay'), 'raising_hands_3d_default'); void load(); void loadChannel(); }
    catch { mod = before; fail(); }
  }

  // a live post whose channel message someone deleted in Telegram (the bot is never told): sent anew, same post
  async function republish(p: ChannelModPost) {
    if (!(await sheets.ask({ title: t('fc.republishAsk'), text: t('fc.republishText'), ok: t('fc.republish'), cancel: t('common.cancel') }))) return;
    haptic.ok();
    try { await api.channelModRepublish(p.id); say(t('fc.republishedSay'), 'raising_hands_3d_default'); setTimeout(loadChannel, 5000); }
    catch { fail(); }
  }

  async function reveal(p: ChannelModPost) {
    if (!(await sheets.ask({ title: t('fc.revealAsk'), text: t('fc.revealText'), ok: t('fc.reveal'), cancel: t('common.cancel') }))) return;
    try { const who = await api.revealChannelPost(p.id); say(t('fc.wrote', { name: who.name }), 'locked_3d'); } catch { fail(); }
  }
</script>

{#snippet row(p: ChannelModPost, kind: 'held' | 'live' | 'removed')}
  <div class="mrow">
    <p class="mt selectable">{p.body}</p>
    <span class="mm">{p.anon ? t('fc.anon') : p.author?.name ?? ''} · {ago(p.at)}{kind === 'held' && p.why ? ' · ' + t(WHY[p.why] ?? 'fc.whyCheck') : ''}</span>
    <span class="mb">
      {#if kind === 'held'}<Button kind="tinted" size="s" onclick={() => decide(p, true, true)}>{t('fc.release')}</Button>{/if}
      {#if kind === 'removed'}<Button kind="tinted" size="s" onclick={() => restore(p)}>{t(p.undo ? 'fc.undo' : 'fc.restore')}</Button>
      {:else}<Button kind="gray" size="s" onclick={() => decide(p, false, kind === 'held')}>{t('fc.takeDown')}</Button>{/if}
      {#if kind === 'live'}<Button kind="gray" size="s" onclick={() => republish(p)}>{t('fc.republish')}</Button>{/if}
      {#if owner && p.anon}<Button kind="plain" size="s" onclick={() => reveal(p)}>{t('fc.reveal')}</Button>{/if}
    </span>
  </div>
{/snippet}

<Sheet {overlay} full title={t('fc.modAdmin')} icon={MessagesSquare}>
  {#if mod}
    <div class="col">
      <Group caption={t('fc.modTitle')}>
        {#each mod.held as p (p.id)}{@render row(p, 'held')}{:else}<p class="none">{t('fc.modEmpty')}</p>{/each}
      </Group>
      {#if mod.live.length}<Group caption={t('fc.modLive')}>{#each mod.live as p (p.id)}{@render row(p, 'live')}{/each}</Group>{/if}
      {#if mod.removed.length}<Group caption={t('fc.modRemoved')}>{#each mod.removed as p (p.id)}{@render row(p, 'removed')}{/each}</Group>{/if}
    </div>
  {/if}
  <ForumMod changed={() => {}} />
</Sheet>

<style>
  .col { display: flex; flex-direction: column; gap: var(--s-4); }
  /* a post: the words, whose and why, the answers */
  .mrow { position: relative; display: flex; flex-direction: column; gap: var(--s-2); padding: var(--s-3) var(--s-4); }
  .mrow + .mrow::before { content: ''; position: absolute; top: 0; left: var(--s-4); right: 0; height: 0.5px; background: var(--separator); }
  .mt { font: 450 var(--fs-body)/1.4 var(--font-text); white-space: pre-line; overflow-wrap: break-word; }
  .mm { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  .mb { display: flex; flex-wrap: wrap; gap: var(--s-2); }
  .none { padding: var(--s-3) var(--s-4); font: 450 var(--fs-body)/1.4 var(--font-text); color: var(--text-3); }
</style>
