<script lang="ts">
  // Who puts an event on, on a photo (the Feed, the event sheet's header): the club's own mark and name; StudEx as its
  // wordmark, the one on its lanyard (a microphone emoji isn't StudEx).
  import type { OrgRef } from '../lib/api';
  import { skinOf } from '../lib/awards';
  import OrgLogo from './OrgLogo.svelte';
  import { nameOf } from '../lib/short';
  let { org }: { org: OrgRef } = $props();
</script>

{#if skinOf(org) === 'studex'}<span class="tag sx" aria-label={org.name}><b><i>STUD</i>EX</b></span>
{:else}<span class="tag"><OrgLogo {org} size={20} /><span class="ellipsis">{nameOf(org)}</span></span>{/if}

<style>
  .tag { display: inline-flex; align-items: center; gap: 7px; max-width: 100%; height: 30px; padding: 0 12px 0 5px; border-radius: var(--r-full);
    background: rgba(12, 14, 24, 0.42); color: #fff; font: 620 13px/1 var(--font-text); }
  .tag :global(.logo) { border-radius: 50% !important; }
  .sx { padding: 0 13px; background: #fff; box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25); }
  .sx b { font: 900 15px/1 var(--font-display); letter-spacing: -0.02em; color: #173064; }
  .sx i { font-style: normal; color: #CF3428; }
</style>
