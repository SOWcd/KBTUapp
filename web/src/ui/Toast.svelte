<script lang="ts">
  // Live phrase: a 3D emoji and a short line, floats over the nav for ~2.5 s. Re-keyed per phrase so a
  // new one replays the entrance even while the old one is visible.
  import { toast } from '../lib/state/ui.svelte';
  import Emoji from './Emoji.svelte';
  import { glass } from './glass';
</script>

{#key toast.id}
  {#if toast.text}
    <div class="toast glass glass-pill" role="status" use:glass>
      <Emoji name={toast.emoji} size={26} />
      <span>{toast.text}</span>
    </div>
  {/if}
{/key}

<style>
  /* width: max-content — with left: 50% the shrink-to-fit width stopped at half the screen and short phrases wrapped */
  .toast {
    position: absolute; left: 50%; bottom: calc(var(--safe-bottom) + 82px); z-index: var(--z-toast);
    display: flex; align-items: center; gap: 10px; width: max-content; max-width: calc(100% - 40px); padding: 9px 16px 9px 10px;
    border-radius: var(--r-full); font: 600 14px/1.25 var(--font-text); letter-spacing: -0.01em;
    transform: translateX(-50%); pointer-events: none;
    animation: pop 420ms var(--ease-spring) both, out 300ms var(--ease-in) 2300ms forwards;
  }
  :global(html[data-sheet]) .toast { bottom: calc(var(--safe-bottom) + 24px); }
  :global(html[data-map]) .toast { bottom: calc(var(--safe-bottom) + 108px); } /* above the map's floors and its note */
  @keyframes pop { from { opacity: 0; transform: translate(-50%, 14px) scale(0.92); } }
  @keyframes out { to { opacity: 0; transform: translate(-50%, 8px) scale(0.96); } }
</style>
