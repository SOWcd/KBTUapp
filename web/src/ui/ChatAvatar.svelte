<script lang="ts">
  // A Telegram chat's avatar with the mark of what it is (PLAN 86: an org's chats on its page and in Studio): its own
  // picture, or its letters on a colour of its own; a topics group is a squircle, as Telegram draws it.
  import type { Chat } from '../lib/api';
  import ChatKind from './ChatKind.svelte';
  import { COVERS, initials } from './OrgLogo.svelte';

  let { title, photo, kind, size = 44 }: { title: string; photo: string | null; kind: Chat['kind']; size?: number } = $props();
  const tint = $derived(COVERS[[...title].reduce((h, c) => h + c.charCodeAt(0), 0) % COVERS.length]);
</script>

<span class="ca" class:sq={kind === 'forum'} style="--s:{size}px" style:background={photo ? null : tint}>
  {#if photo}<img src={photo} alt="" loading="lazy" decoding="async" />{:else}<em>{initials(title)}</em>{/if}
  <span class="kind"><ChatKind {kind} size={Math.round(size * 0.4)} /></span>
</span>

<style>
  .ca { position: relative; flex: none; width: var(--s); height: var(--s); border-radius: 50%; display: grid; place-items: center; color: #fff; background: var(--surface-2); }
  .ca.sq { border-radius: 30%; }
  .ca img { width: 100%; height: 100%; border-radius: inherit; object-fit: cover; }
  .ca em { font: 800 calc(var(--s) * 0.34)/1 var(--font-display); font-style: normal; letter-spacing: -0.02em; }
  .kind { position: absolute; right: -3px; bottom: -3px; display: flex; border-radius: 50%; box-shadow: 0 0 0 2px var(--bg-raised); }
  .sq .kind { border-radius: 32%; }
</style>
