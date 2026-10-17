<script lang="ts">
  // Achievement medal. The rim tells the tier: bronze / silver / gold, and Legend is iridescent —
  // iridescence lives inside one object, never smeared over text (owner's taste). "First 500" is a struck coin, its
  // number instead of an emoji (owner, Oct 13: an emoji can't say it; server sends "n500").
  import type { Achievement } from '../lib/api';
  import Emoji from './Emoji.svelte';
  let { a, size = 64 }: { a: Achievement; size?: number } = $props();

  const multi = $derived(a.levels.length > 1);
  const tier = $derived(a.level === 0 ? 'none' : !multi ? 'one' : (['bronze', 'silver', 'gold', 'legend'][a.level - 1] ?? 'legend'));
  const hidden = $derived(a.secret && a.level === 0);
</script>

<span class="medal {tier}" style="width:{size}px;height:{size}px">
  <span class="disc">
    {#if hidden}<span class="q" style="font-size:{Math.round(size * 0.4)}px">?</span>
    {:else if a.emoji === 'n500'}<span class="coin" style="width:{Math.round(size * 0.66)}px;font-size:{Math.round(size * 0.22)}px"><b class="num">500</b></span>
    {:else}<Emoji name={a.emoji} size={Math.round(size * 0.58)} />{/if}
  </span>
</span>

<style>
  .medal { position: relative; flex: none; border-radius: 50%; padding: 3px; display: inline-flex; }
  .disc { width: 100%; height: 100%; border-radius: 50%; display: flex; align-items: center; justify-content: center; background: radial-gradient(70% 70% at 35% 25%, var(--surface-3), var(--surface)); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.12); }
  .q { font-weight: 800; color: var(--text-3); }
  /* a gold coin, the number struck into it: rim light on top, its shadow under, the digits pressed in */
  .coin { aspect-ratio: 1; border-radius: 50%; display: flex; align-items: center; justify-content: center;
    background: radial-gradient(80% 80% at 35% 28%, #FFF1BF, #F5C451 45%, #C98A10 100%);
    box-shadow: inset 0 0 0 1.5px rgba(255, 246, 214, 0.75), inset 0 -3px 5px rgba(120, 70, 0, 0.35), 0 3px 6px rgba(0, 0, 0, 0.35); }
  .coin b { font-family: var(--font-display); font-weight: 900; letter-spacing: -0.04em; line-height: 1; color: #9A6200;
    text-shadow: 0 1px 0 rgba(255, 244, 205, 0.85), 0 -1px 0 rgba(110, 60, 0, 0.45); }
  .none .coin { filter: grayscale(1); opacity: 0.38; }
  .none { background: var(--surface-2); }
  .none .disc :global(img) { filter: grayscale(1); opacity: 0.38; }
  .one { background: var(--grad-accent); }
  .bronze { background: linear-gradient(145deg, #F3BE93, #A5622D 60%, #E0A06A); }
  .silver { background: linear-gradient(145deg, #FFFFFF, #9AA6BF 60%, #E6ECF8); }
  .gold { background: linear-gradient(145deg, #FFE9A8, #D99A16 55%, #FFD45E); }
  .legend { background: conic-gradient(from 210deg, #FF6BD6, #7C4DFF, #35D0FF, #2FD3A0, #FFD23F, #FF6BD6); animation: spin 9s linear infinite; }
  .legend .disc { animation: spin 9s linear infinite reverse; }
  :global(html.lowfx) .legend, :global(html.lowfx) .legend .disc { animation: none; } /* power saving */
  .medal:not(.none) { box-shadow: 0 6px 18px -8px rgba(0, 0, 0, 0.6); }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
