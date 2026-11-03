<script lang="ts">
  // A list group: Rows on one rounded surface (--r-group), a caption above it, a footnote under it. What needs saying
  // goes in the footnote, under the group, never under a row. The look is Settings' (owner, Nov 3: "very simple but very
  // beautiful"; the glass on groups read as childish): every list moved onto Group and Row looks like it.
  //   caption   Settings' section heading (.set-h): --fs-t3 700 in the display face
  //   --group-bg  the body (default --surface)
  //   footnote  --fs-foot, grey
  //   children  Rows, directly (the lines between them need that)
  import type { Snippet } from 'svelte';

  let { caption, footnote, children }: { caption?: string; footnote?: string; children: Snippet } = $props();
</script>

<section class="grp">
  {#if caption}<h3 class="gcap">{caption}</h3>{/if}
  <div class="box">{@render children()}</div>
  {#if footnote}<p class="foot">{footnote}</p>{/if}
</section>

<style>
  .grp { display: flex; flex-direction: column; }
  .box { display: flex; flex-direction: column; overflow: hidden; border-radius: var(--r-group); background: var(--group-bg, var(--surface)); }
  .gcap { margin: 0 var(--s-1) 10px; font: 700 var(--fs-t3)/1.2 var(--font-display); letter-spacing: -0.016em; color: var(--text); }
  .foot { margin: var(--s-2) var(--s-4) 0; font: 450 var(--fs-sub)/1.4 var(--font-text); color: var(--text-3); }
</style>
