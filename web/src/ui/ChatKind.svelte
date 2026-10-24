<script lang="ts">
  // What a chat is, Telegram's three kinds, as a small lit badge on its avatar (owner, Oct 25: the stock line icons
  // looked default). Filled glyphs drawn for this app, a glossy gradient chip; a forum's chip is a squircle like its avatar.
  import type { Chat } from '../lib/api';
  import { t } from '../lib/i18n/index.svelte';

  let { kind, size = 22 }: { kind: Chat['kind']; size?: number } = $props();
</script>

<i class="ck {kind}" style="--s:{size}px" title={t(`chats.${kind}`)}>
  <svg viewBox="0 0 24 24" aria-hidden="true">
    {#if kind === 'channel'}
      <!-- a megaphone, Telegram's own sign for a channel (owner, Oct 25: the speaker read as "sound") -->
      <path d="M3.5 9.7c0-1 .8-1.7 1.7-1.7h2.6l8.9-4.3c.9-.4 1.8.2 1.8 1.1v14.4c0 1-.9 1.5-1.8 1.1L7.8 16H5.2c-1 0-1.7-.8-1.7-1.7Z" />
      <path class="bk" d="M6.4 16.6h3.3l1 3.3c.2.7-.3 1.4-1 1.4h-.9c-.6 0-1-.4-1.2-.9Z" />
      <path class="ln" d="M20.8 9.6v4.8" />
    {:else if kind === 'forum'}
      <!-- two bubbles: threads talking -->
      <path class="bk" d="M10 15.6h5l3.2 2.6c.5.4 1.2 0 1.2-.6v-2.1a2.3 2.3 0 0 0 1.6-2.2V9.5a2.3 2.3 0 0 0-2.3-2.3h-.4v3.6a4.6 4.6 0 0 1-4.6 4.6H10Z" />
      <path d="M3 6.4A2.9 2.9 0 0 1 5.9 3.5h7.4a2.9 2.9 0 0 1 2.9 2.9v4.4a2.9 2.9 0 0 1-2.9 2.9H8.6l-3.5 2.7c-.5.4-1.3 0-1.3-.6v-2.2A2.9 2.9 0 0 1 3 10.8Z" />
    {:else}
      <!-- two people, the nearer one in front -->
      <circle class="bk" cx="16.6" cy="8.4" r="2.8" />
      <path class="bk" d="M15.6 13.4a5 5 0 0 1 1.5-.2c2.5 0 4.4 1.8 4.4 4.3 0 .6-.4 1-1 1h-3.1a7 7 0 0 0-1.8-5.1Z" />
      <circle cx="9" cy="7.8" r="3.4" />
      <path d="M2.5 18.4c0-3.3 2.9-5.6 6.5-5.6s6.5 2.3 6.5 5.6c0 .6-.5 1.1-1.1 1.1H3.6c-.6 0-1.1-.5-1.1-1.1Z" />
    {/if}
  </svg>
</i>

<style>
  .ck {
    display: grid; place-items: center; width: var(--s); height: var(--s); border-radius: 50%; color: #fff;
    background: linear-gradient(160deg, #6fd0ff, #1f8fe6 70%);
    box-shadow: inset 0 1px 0.5px rgba(255, 255, 255, 0.6), inset 0 -2px 4px rgba(0, 0, 0, 0.18);
  }
  .ck.group { background: linear-gradient(160deg, #b59cff, #6c3ff2 70%); }
  .ck.forum { border-radius: 32%; background: linear-gradient(160deg, #ffc072, #f06b2a 70%); }
  svg { width: 64%; height: 64%; fill: currentColor; filter: drop-shadow(0 1px 1px rgba(0, 0, 0, 0.18)); }
  .ln { fill: none; stroke: currentColor; stroke-width: 2.2; stroke-linecap: round; }
  .bk { opacity: 0.62; }
</style>
