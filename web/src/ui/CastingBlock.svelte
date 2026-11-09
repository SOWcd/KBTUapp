<script lang="ts">
  // What makes a post a casting wherever it's shown: the mark, its state, when and where, and that nobody signs up
  // (the last only while it's on). Spans throughout: it also sits inside a tappable Card. onphoto: over Stories' dark.
  import Clock from '@lucide/svelte/icons/clock';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import type { Casting } from '../lib/api';
  import { t } from '../lib/i18n/index.svelte';
  import { castingOn, castingState, castingStatus, castingWhen } from '../lib/posts';
  import Tag from './Tag.svelte';

  let { casting, onphoto = false }: { casting: Casting; onphoto?: boolean } = $props();
  const TONES = { scheduled: 'accent', open: 'success', ended: 'neutral', cancelled: 'danger' } as const;
  const tone = $derived(onphoto ? 'onphoto' : TONES[castingState(casting)]);
</script>

<span class={['cb', { onphoto, over: !castingOn(casting) }]}>
  <span class="top"><Tag tone={onphoto ? 'onphoto' : 'warning'}>{t('casting.mark')}</Tag><Tag {tone}>{castingStatus(casting)}</Tag></span>
  <span class="ln"><Clock size={16} /><span>{castingWhen(casting)}</span></span>
  <span class="ln"><MapPin size={16} /><span>{casting.place}</span></span>
  {#if castingOn(casting)}<span class="go">{t('casting.walkIn')}</span>{/if}
</span>

<style>
  .cb { display: flex; flex-direction: column; gap: 8px; padding: 12px; border-radius: var(--r-m); background: var(--surface-2); text-align: left; }
  .top { display: flex; flex-wrap: wrap; gap: 6px; }
  .ln { display: flex; align-items: center; gap: 8px; min-width: 0; font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text); overflow-wrap: anywhere; }
  .ln :global(svg) { flex: none; color: var(--text-3); }
  .go { font: 450 var(--fs-sub)/1.3 var(--font-text); color: var(--text-2); }
  .over .ln { font-weight: 450; color: var(--text-3); }
  .onphoto { align-self: stretch; background: rgba(12, 13, 18, 0.62); -webkit-backdrop-filter: blur(22px) saturate(1.4); backdrop-filter: blur(22px) saturate(1.4); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.08); }
  .onphoto .ln { color: var(--on-accent); }
  .onphoto .ln :global(svg) { color: rgba(255, 255, 255, 0.7); }
  .onphoto .go { color: rgba(255, 255, 255, 0.85); }
  .onphoto.over .ln { color: rgba(255, 255, 255, 0.6); }
</style>
