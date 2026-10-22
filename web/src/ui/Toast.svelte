<script lang="ts">
  // Live phrase: a 3D emoji and a short line, floats over the nav for ~2.5 s. Re-keyed per phrase so a
  // new one replays the entrance even while the old one is visible.
  import { toast } from '../lib/state/ui.svelte';
  import Emoji from './Emoji.svelte';
  import { glass } from './glass';
  // read once per phrase, not live: a sheet closing right after say() must not move the toast mid-way (review, Oct 22);
  // the map hides the chrome too but keeps its toast low, above its floors
  const atTop = () => { const d = document.documentElement.dataset; return 'sheet' in d && !('map' in d); };
</script>

{#key toast.id}
  {#if toast.text}
    <div class="toast glass glass-pill" class:top={atTop()} role="status" use:glass>
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
  /* a sheet's footer holds its buttons: there the toast drops from the top, under Telegram's header, like an iOS push (owner, Oct 22) */
  .toast.top { bottom: auto; top: calc(var(--safe-top) + max(var(--tg-head), 46px) + 8px); animation-name: drop, rise; }
  :global(html[data-map]) .toast { bottom: calc(var(--safe-bottom) + 108px); } /* above the map's floors and its note */
  @keyframes pop { from { opacity: 0; transform: translate(-50%, 14px) scale(0.92); } }
  @keyframes drop { from { opacity: 0; transform: translate(-50%, -14px) scale(0.92); } }
  @keyframes rise { to { opacity: 0; transform: translate(-50%, -8px) scale(0.96); } }
  @keyframes out { to { opacity: 0; transform: translate(-50%, 8px) scale(0.96); } }
</style>
