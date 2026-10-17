<script module lang="ts">
  /** The cover palette, one home (the server's logic.COVERS counts it). */
  export const COVERS = [
    'linear-gradient(135deg,#FF4FA3,#FFB23D)', 'linear-gradient(135deg,#2FD3A0,#35D0FF)', 'linear-gradient(135deg,#3B6BFF,#8B5CFF)',
    'linear-gradient(135deg,#F2542D,#FFB23D)', 'linear-gradient(135deg,#7C4DFF,#B8A6FF)', 'linear-gradient(135deg,#111827,#3B6BFF)',
  ];
  /** A club's two letters, made from its name: the server still wants them, nobody types them (they show nowhere). */
  export const initials = (name: string) => name.trim().split(/\s+/).slice(0, 2).map((w) => Array.from(w)[0] ?? '').join('').toUpperCase();
</script>

<script lang="ts">
  // A club's mark: its uploaded logo (owner, Oct 5), else its 3D emoji on its cover gradient. Without `size` it fills
  // its container (used in the middle of the ticket QR).
  import type { OrgRef } from '../lib/api';
  import Emoji from './Emoji.svelte';

  let { org, size }: { org: OrgRef; size?: number } = $props();
</script>

<span class="logo" class:fill={!size} style="background:{org.logo ? '#fff' : COVERS[org.cover % COVERS.length]}{size ? `;width:${size}px;height:${size}px;border-radius:${Math.round(size * 0.31)}px` : ''}">
  {#if org.logo}<img src={org.logo} alt="" draggable="false" />{:else}<Emoji name={org.emoji} size={size ? Math.round(size * 0.6) : 64} />{/if}
</span>

<style>
  .logo { display: flex; align-items: center; justify-content: center; flex: none; overflow: hidden; }
  .logo img { width: 100%; height: 100%; object-fit: cover; }
  .fill { width: 100%; height: 100%; border-radius: 31%; }
  .fill :global(.emoji) { width: 62%; height: 62%; }
</style>
