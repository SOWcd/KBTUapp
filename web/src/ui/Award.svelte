<script lang="ts">
  // One award on a shelf: an achievement medal or a badge pin (SPEC §4.11: different shapes on purpose).
  import type { ShelfItem } from '../lib/awards';
  import Medal from './Medal.svelte';
  import Pin from './Pin.svelte';
  import Founder from './Founder.svelte';
  import Shield from './Shield.svelte';
  let { it, size = 56, deep = false }: { it: ShelfItem; size?: number; deep?: boolean } = $props(); // deep: the shield's tilt layers (AwardSheet)
</script>

{#if it.founder || it.idea}<Founder {size} idea={it.idea} />{:else if it.staff}<Shield role={it.staff} {size} {deep} />{:else if it.ach}<Medal a={it.ach} {size} />{:else if it.badge}<Pin emoji={it.badge.emoji} color={it.badge.color} {size} />{/if}
