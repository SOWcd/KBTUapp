<script lang="ts">
  // A list group: Rows on one rounded surface (--r-group), a caption above it, a footnote under it. What needs saying
  // goes in the footnote, under the group, never under a row. The look is Settings' (simple; glass on groups
  // reads as childish): every list on Group and Row looks like it.
  //   caption   Settings' section heading (.set-h): --fs-t3 700 in the display face
  //   --group-bg  the body (default --surface)
  //   note      grey after the caption ("3 of 5"), kept whole
  //   aside     at the caption's end (the list's SortChip)
  //   footnote  --fs-foot, grey
  //   children  Rows, directly (the lines between them need that)
  import type { Snippet } from 'svelte';

  let { caption, note, footnote, aside, children }: { caption?: string; note?: string; footnote?: string; aside?: Snippet; children: Snippet } = $props();
</script>

<section class="grp">
  {#if caption}<header class="ghd"><h3 class="gcap">{caption}{#if note}<span class="note">{note}</span>{/if}</h3>{@render aside?.()}</header>{/if}
  <div class="box">{@render children()}</div>
  {#if footnote}<p class="foot">{footnote}</p>{/if}
</section>

<style>
  .grp { display: flex; flex-direction: column; }
  .box { display: flex; flex-direction: column; overflow: hidden; border-radius: var(--r-group); background: var(--group-bg, var(--surface)); box-shadow: var(--elev-1); }
  .ghd { display: flex; align-items: baseline; gap: var(--s-3); margin: 0 var(--s-1) 10px; }
  .gcap { min-width: 0; margin: 0; font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; color: var(--text); }
  .note { margin-left: 0.3em; white-space: nowrap; color: var(--text-3); font-weight: 600; }
  .foot { margin: var(--s-2) var(--s-4) 0; font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
</style>
