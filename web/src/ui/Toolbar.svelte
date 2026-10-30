<script lang="ts" module>
  import type { Component } from 'svelte';
  /** onclick gets the tap: a ⋯ opens its Menu at e.currentTarget */
  export type Tool = { icon: Component<any>; label: string; onclick: (e: MouseEvent) => void; badge?: number; on?: boolean };
</script>

<script lang="ts">
  // A screen's or a sheet's 1-3 icon actions in one capsule, on the title's line at the right: gray (--fill), the way
  // a header that scrolls with the page or sits in a sheet should look; glass only when it is pinned over scrolling
  // content (photos, the map). Telegram's own ⋯ owns the very top right corner in full screen: keep it under there.
  //   items  1-3 tools { icon, label (for screen readers), onclick, badge, on };  glass
  import IconButton from './IconButton.svelte';

  let { items, glass = false }: { items: Tool[]; glass?: boolean } = $props();
</script>

<div class="bar" class:glass class:glass-pill={glass} role="toolbar">
  {#each items as it (it.label)}
    <IconButton kind="plain" icon={it.icon} label={it.label} onclick={it.onclick} badge={it.badge} on={it.on} />
  {/each}
</div>

<style>
  /* the tools are plain inside (the capsule is their one surface), their icons in text colour, not accent */
  .bar { position: relative; display: inline-flex; flex: none; height: var(--ctl-m); border-radius: var(--r-full); background: var(--fill); --plain-ink: var(--text); }
  .bar.glass { background: var(--glass-pill-bg); } /* the capsule's pill glass (base.css .glass .glass-pill) */
</style>
