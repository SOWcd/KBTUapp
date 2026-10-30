<script lang="ts">
  // A round button with an icon alone: 44 (gray, or glass over photos, the map and full-screen layers; plain inside a
  // Toolbar; filled for a composer's send).
  //   icon     a lucide component, drawn at 20 (24 for size l)
  //   label    what it does, for screen readers (required: there is no text)
  //   kind     gray | glass | plain | filled | tinted;  size m 44 | s 36 (a 44 px hit area) | l 50
  //   badge    a red count on its corner;  on / disabled / loading / destructive: as Button
  import type { Component } from 'svelte';
  import Button, { type Kind } from './Button.svelte';
  import Badge from './Badge.svelte';

  type Props = { icon: Component<any>; label: string; kind?: Kind; size?: 'l' | 'm' | 's'; badge?: number; on?: boolean; disabled?: boolean;
    loading?: boolean; destructive?: boolean; onclick?: (e: MouseEvent) => void };
  let { icon: Icon, label, kind = 'gray', size = 'm', badge = 0, on = false, disabled = false, loading = false, destructive = false, onclick }: Props = $props();
</script>

<span class="ib">
  <Button {kind} {size} round {label} {on} {disabled} {loading} {destructive} {onclick}>
    {#snippet icon()}<Icon size={size === 'l' ? 24 : size === 's' ? 18 : 20} strokeWidth={2} />{/snippet}
  </Button>
  {#if badge > 0}<span class="bd"><Badge n={badge} /></span>{/if}
</span>

<style>
  .ib { position: relative; display: inline-flex; flex: none; }
  .bd { position: absolute; top: -3px; right: -3px; pointer-events: none; }
</style>
