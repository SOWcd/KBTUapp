<script lang="ts">
  // One notice box for the whole app (was EventEditor's .note / .cast / .sug, SettingsSheet's .once, the red warning
  // cards): calm, in Settings' grammar: a flat tinted card shaped like a group, an icon, the text, an optional action.
  //   tone      neutral | warning | danger | accent (the icon's colour and the tint)
  //   icon      a lucide component (default by tone: info, a triangle, a triangle, sparkles)
  //   title     a bold first line (optional);  text: the words;  children: anything else under them (the AI's suggestion)
  //   action    { label, onclick }: an S button at its end (primary for warning and danger, secondary otherwise)
  //   stack     the action under the text, full width (an M button), for a text too long to share its line
  import type { Component, Snippet } from 'svelte';
  import Info from '@lucide/svelte/icons/info';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import Sparkles from '@lucide/svelte/icons/sparkles';
  import Button from './Button.svelte';

  type Props = { tone?: 'neutral' | 'warning' | 'danger' | 'accent'; icon?: Component<any>; title?: string; text?: string;
    action?: { label: string; onclick: () => void }; children?: Snippet; stack?: boolean };
  let { tone = 'neutral', icon, title, text, action, children, stack = false }: Props = $props();
  const Icon = $derived(icon ?? (tone === 'accent' ? Sparkles : tone === 'neutral' ? Info : TriangleAlert));
</script>

<div class="ntc {tone}" role={tone === 'danger' ? 'alert' : 'note'}>
  <span class="ni"><Icon size={18} strokeWidth={2} /></span>
  <div class="nb">
    {#if title}<b class="nh">{title}</b>{/if}
    {#if text}<p class="nt">{text}</p>{/if}
    {#if children}{@render children()}{/if}
  </div>
  {#if action}<span class={['na', { stack }]}><Button kind={tone === 'warning' || tone === 'danger' ? 'primary' : 'secondary'} size={stack ? 'm' : 's'} full={stack} onclick={action.onclick}>{action.label}</Button></span>{/if}
</div>

<style>
  .ntc { --tint: var(--surface); position: relative; display: flex; flex-wrap: wrap; align-items: center; gap: var(--s-2) var(--s-3);
    padding: var(--s-3) var(--s-3) var(--s-3) var(--s-4); border-radius: var(--r-group); background: var(--tint);
    animation: note-in 300ms var(--ease-spring) backwards; }
  @keyframes note-in { from { opacity: 0; transform: translateY(-4px); } }
  .warning { --tint: var(--warning-soft); }
  .danger { --tint: var(--danger-soft); }
  .accent { --tint: var(--accent-soft); }
  .ni { flex: none; align-self: flex-start; display: inline-flex; padding-top: 1px; color: var(--text-3); }
  .warning .ni { color: var(--warning-text); }
  .danger .ni { color: var(--danger-text); }
  .accent .ni { color: var(--accent-text); }
  .nb { flex: 1 1 160px; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .nh { font: 600 var(--fs-body)/1.3 var(--font-text); }
  .nt { font: 450 var(--fs-body)/1.35 var(--font-text); color: var(--text); }
  .na { flex: none; margin-left: auto; }
  .na.stack { flex: 0 0 100%; margin-left: 0; }
</style>
