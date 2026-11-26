<script lang="ts">
  // The event page's place row: a room opens our map, the rest leaves for 2GIS (its mark, an arrow out), a campus spot
  // the map can't point at stays plain. Apart from EventPlace so the 2GIS mark stays out of the start chunk.
  import MapPin from '@lucide/svelte/icons/map-pin';
  import MapIcon from '@lucide/svelte/icons/map';
  import type { EventCard } from '../lib/api';
  import { campusPlace } from '../lib/campusPlace';
  import { t, placeOf } from '../lib/i18n/index.svelte';
  import { eventPlace } from '../lib/map';
  import { sheets } from '../lib/state/sheets';
  import { openLink } from '../lib/tg';
  import Row from './Row.svelte';
  import TwoGisMark from './TwoGisMark.svelte';

  let { e }: { e: Pick<EventCard, 'place' | 'placeUrl'> } = $props();
  const found = $derived(eventPlace(e.place, e.placeUrl));
  const hasText = $derived(!!e.place.trim());
</script>

{#if found?.kind === 'room'}
  <Row icon={MapIcon} title={placeOf(e.place)} whole value={campusPlace(e.place) ? undefined : found.floor ? t('route.floor', { n: found.floor }) : t('route.basement')}
    accessory="chevron" onclick={() => sheets.map(e.place)} />
{:else if found && found.kind !== 'campus'}
  {@const url = found.url}
  <Row title={hasText ? placeOf(e.place) : t('event.route')} subtitle={hasText ? t('event.route') : undefined} accessory="external" onclick={() => openLink(url)}>
    {#snippet lead()}<span class="gis"><TwoGisMark size={22} /></span>{/snippet}
  </Row>
{:else}
  <Row icon={MapPin} title={placeOf(e.place)} />
{/if}

<style>
  .gis { width: 24px; display: grid; place-items: center; }
</style>
