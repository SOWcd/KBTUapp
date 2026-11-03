<script lang="ts">
  // One award on a shelf: a medal (round) or a pin (a shield), an event's too (awards plan: the shape tells the kind).
  import { yearOf, type ShelfItem } from '../lib/awards';
  import Medal from './Medal.svelte';
  import Pin from './Pin.svelte';
  import Founder from './Founder.svelte';
  let { it, size = 56 }: { it: ShelfItem; size?: number } = $props();
</script>

{#if it.founder || it.idea}<Founder {size} idea={it.idea} />{:else if it.ach}<Medal a={it.ach} {size} />{:else if it.badge}<Pin emoji={it.badge.emoji} color={it.badge.color} year={yearOf(it.badge.at)} {size} />{/if}
