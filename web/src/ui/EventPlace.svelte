<script lang="ts">
  // An event's place inside a line (Afisha, rows, the ticket): a tap opens the room on our map or the venue in 2GIS.
  // The event page's own row is EventPlaceRow.
  import MapPin from '@lucide/svelte/icons/map-pin';
  import VideoCall from '@lucide/svelte/icons/video';
  import type { EventCard } from '../lib/api';
  import { t, placeOf } from '../lib/i18n/index.svelte';
  import { eventPlace } from '../lib/map';
  import { sheets } from '../lib/state/sheets';
  import { openLink } from '../lib/tg';

  let { e, pin = false }: { e: Pick<EventCard, 'place' | 'placeUrl' | 'online'>; pin?: boolean } = $props();
  // a campus spot the map can't point at ("Atrium") stays plain text
  const found = $derived(e.online ? null : eventPlace(e.place, e.placeUrl));
  const target = $derived(found?.kind === 'campus' ? null : found);
  const label = $derived(target && !e.place.trim() ? t('event.route') : placeOf(e.place, e.online));

  function open() {
    if (target?.kind === 'room') sheets.map(e.place);
    else if (target) openLink(target.url);
  }
</script>

{#snippet location()}
  {#if pin}{#if e.online}<VideoCall size={14} strokeWidth={1.75} />{:else}<MapPin size={14} strokeWidth={1.75} />{/if}{/if}
  <span class="ellipsis">{label}</span>
{/snippet}

{#if target}
  <button class="place" type="button" onclick={open}>{@render location()}</button>
{:else}
  <span class="plain">{@render location()}</span>
{/if}

<style>
  .place, .plain { display: inline-flex; align-items: center; vertical-align: middle; gap: 5px; max-width: 100%; min-width: 0; }
  .place { position: relative; z-index: 2; min-height: 24px; min-width: 24px; padding: 0; pointer-events: auto; text-decoration: underline; text-underline-offset: 0.16em; }
  .place:active { opacity: 0.65; }
  .place :global(svg), .plain :global(svg) { flex: none; }
</style>
