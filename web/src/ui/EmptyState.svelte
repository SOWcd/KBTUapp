<script lang="ts">
  // Nothing here, or it failed to load. Three shapes:
  //   full     the orb (ui/Orb) with the state's light (tone) and a lucide icon held inside its glass, a light title,
  //            one line, at most one tinted button. Centred, no box, no emoji: icon, title, text,
  //            action { label, onclick }, tone neutral | success ("all sorted") | danger
  //   inline   one grey line inside a Group or a list ("no new applications", "a free day"): inline + text
  //   error    onretry given: the failure's icon, "Something went wrong" (or your title/text) and "Try again"
  import type { Component } from 'svelte';
  import CloudOff from '@lucide/svelte/icons/cloud-off';
  import Button from './Button.svelte';
  import Orb from './Orb.svelte';
  import { t } from '../lib/i18n/index.svelte';

  type Props = { icon?: Component<any>; title?: string; text?: string; action?: { label: string; onclick: () => void };
    tone?: 'neutral' | 'success' | 'danger'; inline?: boolean; onretry?: () => void };
  let { icon, title, text, action, tone = 'neutral', inline = false, onretry }: Props = $props();
  const Icon = $derived(icon ?? (onretry ? CloudOff : null));
</script>

{#if inline}
  <p class="line">{text ?? title}</p>
{:else}
  <div class="empty" role={onretry ? 'alert' : undefined}>
    {#if Icon}<span class="ic"><Orb size={112} tone={onretry ? 'danger' : tone}><Icon size={48} strokeWidth={1.25} /></Orb></span>{/if}
    <p class="tt">{title ?? (onretry ? t('common.error') : '')}</p>
    {#if text}<p class="tx">{text}</p>{/if}
    {#if onretry}<span class="act"><Button kind="tinted" onclick={onretry}>{t('common.retry')}</Button></span>
    {:else if action}<span class="act"><Button kind="tinted" onclick={action.onclick}>{action.label}</Button></span>{/if}
  </div>
{/if}

<style>
  .empty { display: flex; flex-direction: column; align-items: center; gap: var(--s-2); padding: var(--s-8) var(--s-6); text-align: center; }
  /* room under the orb for its shadow; the icon is inside the glass (large, thin, under the grains): a picture, not a button */
  .ic { display: block; margin: var(--s-2) 0 var(--s-8); }
  .ic :global(svg) { opacity: 0.8; }
  .tt { font: 600 var(--fs-row)/1.3 var(--font-text); letter-spacing: -0.012em; overflow-wrap: break-word; }
  .ic + .tt { font: var(--fw-light) var(--fs-t1)/1.1 var(--font-display); letter-spacing: -0.04em; } /* under the orb: display type, light */
  .tx { max-width: 270px; font: 450 var(--fs-body)/1.35 var(--font-text); color: var(--text-3); overflow-wrap: break-word; }
  .act { margin-top: 12px; }
  .line { padding: 14px var(--s-4); font: 450 var(--fs-body)/1.35 var(--font-text); color: var(--text-3); }
</style>
