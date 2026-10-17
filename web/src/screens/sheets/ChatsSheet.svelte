<script lang="ts">
  // Every chat in the directory (SPEC §4.11), grouped: for everyone, then by school and course. A tap opens it in
  // Telegram and ticks it.
  import Check from '@lucide/svelte/icons/check';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import UsersRound from '@lucide/svelte/icons/users-round';
  import type { Chat } from '../../lib/api';
  import type { Overlay } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { openChat, compact } from '../../lib/chats';
  import Sheet from '../../ui/Sheet.svelte';

  let { overlay, chats }: { overlay: Overlay; chats: Chat[] } = $props();
  let list = $state<Chat[]>([]);
  $effect.pre(() => { if (!list.length) list = chats; });
  const label = (c: Chat) => c.school && c.course ? `${c.school} · ${t('chats.course', { n: c.course })}` : c.school ?? (c.course ? t('chats.course', { n: c.course }) : t('chats.everyone'));
  const groups = $derived.by(() => {
    const m = new Map<string, Chat[]>();
    for (const c of list) { const k = label(c); if (!m.has(k)) m.set(k, []); m.get(k)!.push(c); }
    return [...m];
  });
  function tap(c: Chat) { void openChat(c).then(() => { list = list.map((x) => (x.id === c.id ? { ...x, opened: true } : x)); }); }
</script>

<Sheet {overlay} tall title={t('chats.sheet')}>
  <h2 class="t-h2 hd">{t('chats.sheet')}</h2>
  <p class="t-foot sub">{t('chats.note')}</p>
  {#each groups as [g, items] (g)}
    <h3 class="t-cap gh">{g}</h3>
    <div class="list surface">
      {#each items as c (c.id)}
        <button class="row" onclick={() => tap(c)}>
          <span class="ci" class:ch={c.kind === 'channel'} class:sq={c.kind === 'forum'}>{#if c.photo}<img src={c.photo} alt="" />{:else if c.kind === 'channel'}<Megaphone size={18} />{:else}<UsersRound size={18} />{/if}</span>
          <span class="tx"><b class="ellipsis">{c.title}</b><i>{t(`chats.${c.kind}`)}{c.members ? ' · ' + tn('chats.members', c.members).replace(String(c.members), compact(c.members)) : ''}</i></span>
          {#if c.opened}<span class="tick"><Check size={14} strokeWidth={3} /></span>{/if}
        </button>
      {/each}
    </div>
  {/each}
</Sheet>

<style>
  .hd { margin: 4px 0 4px; }
  .sub { margin-bottom: 14px; }
  .gh { margin: 14px 4px 8px; }
  .list { display: flex; flex-direction: column; padding: 4px 0; }
  .row { display: flex; align-items: center; gap: 12px; width: 100%; padding: 10px 14px; text-align: left; }
  .row + .row { border-top: 1px solid var(--line); }
  .row:active { background: var(--surface-2); }
  .ci { flex: none; width: 40px; height: 40px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--accent-soft); color: var(--accent-text); }
  .ci.ch { background: color-mix(in srgb, #2AABEE 18%, transparent); color: #2AABEE; }
  /* the chat's own avatar; a topics group is a squircle, as Telegram draws it */
  .ci.sq { border-radius: 30%; }
  .ci img { width: 100%; height: 100%; border-radius: inherit; object-fit: cover; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .tx b { font: 640 15px/1.25 var(--font-text); }
  .tx i { font: 500 12.5px/1.25 var(--font-text); font-style: normal; color: var(--text-2); }
  .tick { flex: none; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: var(--success); color: #fff; }
</style>
