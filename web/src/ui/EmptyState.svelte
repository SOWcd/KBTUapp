<script lang="ts">
  // Nothing here, or it failed to load. Three shapes:
  //   full     a lucide icon (44, in the state's tone), a title, one line, at most one tinted button. Centred, no box,
  //            no emoji: icon, title, text, action { label, onclick }, tone neutral | success ("all sorted") | danger
  //   inline   one grey line inside a Group or a list ("no new applications", "a free day"): inline + text
  //   error    onretry given: the failure's icon, "Something went wrong" (or your title/text) and "Try again"
  import type { Component } from 'svelte';
  import CloudOff from '@lucide/svelte/icons/cloud-off';
  import Button from './Button.svelte';
  import { t } from '../lib/i18n/index.svelte';

  type Props = { icon?: Component<any>; title?: string; text?: string; action?: { label: string; onclick: () => void };
    tone?: 'neutral' | 'success' | 'danger'; inline?: boolean; onretry?: () => void };
  let { icon, title, text, action, tone = 'neutral', inline = false, onretry }: Props = $props();
  const Icon = $derived(icon ?? (onretry ? CloudOff : null));
</script>

{#if inline}
  <p class="line">{text ?? title}</p>
{:else}
  <div class="empty {onretry ? 'danger' : tone}" role={onretry ? 'alert' : undefined}>
    {#if Icon}<span class="ic"><Icon size={44} strokeWidth={2} /></span>{/if}
    <p class="tt">{title ?? (onretry ? t('common.error') : '')}</p>
    {#if text}<p class="tx">{text}</p>{/if}
    {#if onretry}<span class="act"><Button kind="tinted" onclick={onretry}>{t('common.retry')}</Button></span>
    {:else if action}<span class="act"><Button kind="tinted" onclick={action.onclick}>{action.label}</Button></span>{/if}
  </div>
{/if}

<style>
  .empty { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: var(--s-8) var(--s-6); text-align: center; }
  .ic { display: inline-flex; margin-bottom: 8px; color: var(--text-3); }
  .success .ic { color: var(--success-text); }
  .danger .ic { color: var(--danger-text); }
  .tt { font: 600 var(--fs-row)/1.3 var(--font-text); letter-spacing: -0.012em; overflow-wrap: break-word; }
  .tx { max-width: 300px; font: 450 var(--fs-body)/1.35 var(--font-text); color: var(--text-2); overflow-wrap: break-word; }
  .act { margin-top: 12px; }
  .line { padding: 14px var(--s-4); font: 450 var(--fs-body)/1.35 var(--font-text); color: var(--text-3); }
</style>
