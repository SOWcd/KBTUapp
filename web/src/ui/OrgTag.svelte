<script lang="ts">
  // Who puts an event on, on a photo (the Feed, the event sheet's header): the club's own mark and name; StudEx as its
  // wordmark, the one on its lanyard (a microphone emoji isn't StudEx). Co-hosted: both marks, "Crystal × JCC"; with
  // `onpick` each name opens its own club.
  import type { Id, OrgRef } from '../lib/api';
  import { skinOf } from '../lib/awards';
  import OrgLogo from './OrgLogo.svelte';
  import { nameOf } from '../lib/short';
  let { org, co = null, onpick }: { org: OrgRef; co?: OrgRef | null; onpick?: (id: Id) => void } = $props();
</script>

{#if co}
  <span class="tag">
    <span class="pair"><OrgLogo {org} size={20} /><OrgLogo org={co} size={20} /></span>
    {#if onpick}
      <button class="nm ellipsis" onclick={() => onpick(org.id)}>{nameOf(org)}</button><span class="x" aria-hidden="true">×</span><button class="nm ellipsis" onclick={() => onpick(co.id)}>{nameOf(co)}</button>
    {:else}<span class="ellipsis">{nameOf(org)} × {nameOf(co)}</span>{/if}
  </span>
{:else if skinOf(org) === 'studex'}<span class="tag sx" aria-label={org.name}><b><i>STUD</i>EX</b></span>
{:else}<span class="tag"><OrgLogo {org} size={20} /><span class="ellipsis">{nameOf(org)}</span></span>{/if}

<style>
  .tag { display: inline-flex; align-items: center; gap: 7px; max-width: 100%; height: 30px; padding: 0 12px 0 5px; border-radius: var(--r-full);
    background: rgba(12, 14, 24, 0.42); color: #fff; font: 620 13px/1 var(--font-text); }
  .tag :global(.logo) { border-radius: 50% !important; }
  /* two marks, the second over the first's edge */
  .pair { display: flex; flex: none; }
  .pair :global(.logo + .logo) { margin-left: -6px; box-shadow: 0 0 0 1.5px rgba(12, 14, 24, 0.42); }
  .nm { min-width: 0; color: inherit; font: inherit; }
  .nm:active { opacity: 0.7; transform: none; }
  .x { flex: none; opacity: 0.7; margin: 0 -2px; }
  .sx { padding: 0 13px; background: #fff; box-shadow: 0 4px 14px rgba(0, 0, 0, 0.25); }
  .sx b { font: 900 15px/1 var(--font-display); letter-spacing: -0.02em; color: #173064; }
  .sx i { font-style: normal; color: #CF3428; }
</style>
