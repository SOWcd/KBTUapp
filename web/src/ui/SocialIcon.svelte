<script lang="ts">
  // Networks as one-colour line marks in the icon set's stroke (Lucide has no brand icons); Telegram is its own mark, as
  // everywhere in the app (the paper plane "is some strange icon").
  import type { SocialKind } from '../lib/social';
  import TelegramMark from './TelegramMark.svelte';
  let { kind, size = 20 }: { kind: SocialKind; size?: number } = $props();
</script>

{#if kind === 'telegram'}<TelegramMark {size} />{:else}
<svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
  {#if kind === 'instagram'}
    <rect x="3" y="3" width="18" height="18" rx="5.5" /><circle cx="12" cy="12" r="4.2" /><circle cx="17.4" cy="6.6" r="0.4" fill="currentColor" />
  {:else if kind === 'tiktok'}
    <path d="M14 3v11.6a3.6 3.6 0 1 1-3.6-3.6" /><path d="M14 3c.5 2.7 2.4 4.6 5.2 4.8" />
  {:else if kind === 'youtube'}
    <rect x="2.5" y="5.5" width="19" height="13" rx="4" /><path d="M10.2 9.4v5.2l4.4-2.6z" fill="currentColor" />
  {:else if kind === 'github'}
    <path d="M15 22v-4a4.8 4.8 0 0 0-1-3.5c3 0 6-2 6-5.5.08-1.25-.27-2.48-1-3.5.28-1.15.28-2.35 0-3.5 0 0-1 0-3 1.5-2.64-.5-5.36-.5-8 0C6 2 5 2 5 2c-.3 1.15-.3 2.35 0 3.5A5.403 5.403 0 0 0 4 9c0 3.5 3 5.5 6 5.5-.39.49-.68 1.05-.85 1.65-.17.6-.22 1.23-.15 1.85v4" /><path d="M9 18c-4.51 2-5-2-7-2" />
  {:else}
    <circle cx="12" cy="12" r="10" /><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20" /><path d="M2 12h20" />
  {/if}
</svg>
{/if}
