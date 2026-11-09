<script lang="ts">
  // My friends in a club, on one line: a face or two and "Ali and 3 more". Only for a club with friends in it.
  import type { Org } from '../lib/api';
  import { friendsIn } from '../lib/clubs';
  import Avatar from './Avatar.svelte';

  let { org, max = 2 }: { org: Org; max?: number } = $props();
</script>

<span class="fl">
  <span class="fc">{#each org.friends.slice(0, max) as p (p.id)}<Avatar person={p} size={18} tappable={false} />{/each}</span>
  <span class="clamp-2">{friendsIn(org)}</span>
</span>

<style>
  .fl { display: flex; align-items: center; gap: 6px; min-width: 0; }
  .fc { flex: none; display: flex; }
  .fc > :global(* + *) { margin-left: -6px; }
</style>
