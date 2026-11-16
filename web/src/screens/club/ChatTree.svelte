<script lang="ts">
  // One organisation's groups as a tree (lib/chattree.ts), rows for a Group's box: Studio → Chats and DMP's panel.
  // Thin connectors in CSS, each row ending in its count and state. onplace: the club's own people place a group (a label).
  import MessagesSquare from '@lucide/svelte/icons/messages-square';
  import MessageCircle from '@lucide/svelte/icons/message-circle';
  import Folder from '@lucide/svelte/icons/folder';
  import type { ChatTree, TreeChat } from '../../lib/api';
  import { treeRows, type TreeRow } from '../../lib/chattree';
  import { compact } from '../../lib/chats';
  import { t } from '../../lib/i18n/index.svelte';

  let { tree, base = 0, onplace }: { tree: ChatTree; base?: number; onplace?: (c: TreeChat, at: Element) => void } = $props();
  const rows = $derived(treeRows(tree, base));
  const state = (c: TreeChat) => (c.sync === 'on' ? 'on' : c.sync === 'paused' ? 'paused' : c.bot ? null : 'noBot');
  const movable = (c: TreeChat | null): c is TreeChat => !!onplace && !!c && c.id != null && c.by !== 'sync';
</script>

{#snippet end(c: TreeChat)}
  <span class="end">
    {#if c.members != null}<span class="num">{compact(c.members)}</span>{/if}
    {#if state(c)}<span class="st {state(c)}">{t(`ct.${state(c)!}`)}</span>{/if}
  </span>
{/snippet}

{#snippet row(r: TreeRow)}
  {#each r.rails as on, i (i)}{#if on}<i class="rail" style:--l={base + 1 + i}></i>{/if}{/each}
  {#if r.depth > base}<i class="elbow" class:last={r.last} style:--l={r.depth}></i>{/if}
  {#if r.kind === 'main'}
    <span class="ic main"><MessagesSquare size={16} strokeWidth={2.2} /></span>
    <span class="txt"><span class="tt" class:muted={!r.chat}>{r.chat ? (r.chat.title ?? t('ct.untitled')) : t('ct.noMain')}</span></span>
    {#if r.chat}{@render end(r.chat)}{/if}
  {:else if r.kind === 'dept'}
    <span class="ic"><i class="dot" style:background={r.dept.color}></i></span>
    <span class="txt"><span class="tt">{r.dept.name}</span></span>
    {#if !r.dept.chats.length}<span class="end"><span class="st">{t('ct.noGroup')}</span></span>{/if}
  {:else if r.kind === 'head'}
    <span class="ic"><Folder size={16} /></span>
    <span class="txt"><span class="tt">{t(r.head === 'other' ? 'ct.other' : 'ct.loose')}</span></span>
    <span class="end"><span class="num">{r.n}</span></span>
  {:else}
    <span class="ic"><MessageCircle size={16} /></span>
    <span class="txt"><span class="tt">{r.chat.title ?? t('ct.untitled')}</span>{#if r.loose && onplace}<span class="ask">{t('ct.where')}</span>{/if}</span>
    {@render end(r.chat)}
  {/if}
{/snippet}

{#each rows as r (r.key)}
  {@const chat = r.kind === 'main' || r.kind === 'chat' ? r.chat : null}
  {#if movable(chat)}
    <button class="tr" class:top={r.depth === base} style:--d={r.depth} onclick={(e) => onplace?.(chat, e.currentTarget)}>{@render row(r)}</button>
  {:else}
    <div class="tr" class:top={r.depth === base} style:--d={r.depth}>{@render row(r)}</div>
  {/if}
{/each}

<style>
  /* a level is 20 px; level L's line runs at 16 + (L - 1) * 20 + 9 */
  .tr { position: relative; display: flex; align-items: center; gap: var(--s-2); width: 100%; min-height: var(--row-dense); margin: 0; border: 0; background: none;
    padding: 6px var(--s-4) 6px calc(16px + var(--d) * 20px); text-align: start; color: var(--text); font: 600 var(--fs-body)/1.3 var(--font-text); letter-spacing: -0.008em; }
  .tr:not(.top)::after { content: ''; position: absolute; left: calc(16px + var(--d) * 20px + 26px); right: 0; top: 0; height: 0.5px; background: var(--separator); opacity: 0.6; }
  button.tr { cursor: pointer; }
  button.tr:active { background: var(--fill); }
  .rail, .elbow { position: absolute; top: 0; bottom: 0; left: calc(16px + (var(--l) - 1) * 20px + 9px); width: 1px; background: var(--line-2); }
  .elbow.last { bottom: 50%; }
  .elbow::after { content: ''; position: absolute; left: 0; top: 50%; width: 8px; height: 1px; background: var(--line-2); }
  .elbow.last::after { top: auto; bottom: 0; }
  .ic { flex: none; display: inline-grid; place-items: center; width: 22px; height: 22px; color: var(--text-3); }
  .ic.main { border-radius: var(--r-xs); background: var(--accent-soft); color: var(--accent-text); }
  .dot { width: 10px; height: 10px; border-radius: 50%; }
  .txt { flex: 1; min-width: 0; display: flex; flex-direction: column; }
  .tt { overflow-wrap: anywhere; }
  .muted { color: var(--text-3); font-weight: 450; }
  .ask { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--accent-text); }
  .end { flex: none; display: inline-flex; align-items: center; gap: var(--s-2); font: 450 var(--fs-sub)/1 var(--font-text); color: var(--text-3); white-space: nowrap; }
  .st.on { color: var(--success-text); }
  .st.paused { color: var(--warning-text); }
</style>
