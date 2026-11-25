<script lang="ts">
  import { CAMPUS_SIDES, campusPlace, campusSides, type CampusSide } from '../../lib/campusPlace';
  import { campusPlaceLabel, t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Chip from '../../ui/Chip.svelte';
  import Field from '../../ui/Field.svelte';

  let { value = $bindable(''), placeholder, error }: {
    value: string; placeholder: string; error?: string;
  } = $props();

  let pending = $state<CampusSide | null>(null);
  let roomInput = $state<string | null>(null);
  const campus = $derived(campusPlace(value));
  const side = $derived(pending ?? campus?.side);
  const floors = $derived.by(() => {
    if (!side) return [];
    const { min, max } = CAMPUS_SIDES[side];
    return Array.from({ length: max - min + 1 }, (_, i) => min + i);
  });
  const sideName = (key: CampusSide) => t(key === 'panfilov' ? 'campus.side.panfilov' : `memo.side.${key}`);

  function typePlace(text: string) {
    pending = null;
    roomInput = null;
    value = text;
  }

  function pickPlace(side: CampusSide, floor: number, room: string) {
    value = campusPlaceLabel({ side, floor, room: room.trim().replace(/\s+/g, ' ') });
    pending = null;
  }
</script>

<Field label={t('ed.place')} bind:value={() => value, typePlace}
  {placeholder} {error} maxlength={400} enterkeyhint="done" />

<div class="picker">
  <div class="choices" role="group" aria-label={t('ed.campusSide')}>
    <span class="label" aria-hidden="true">{t('ed.campusSide')}</span>
    <div class="chips">
      {#each campusSides as key (key)}
        <Chip full selected={side === key} onclick={() => { haptic.tap(); pending = key; }}>
          <abbr title={sideName(key)}>{t(`campus.code.${key}`)}</abbr>
        </Chip>
      {/each}
    </div>
  </div>
  {#if side}
    {@const selected = campus?.side === side ? campus : null}
    <div class="choices" role="group" aria-label={`${sideName(side)} · ${t('ed.campusFloor')}`}>
      <span class="label" aria-hidden="true">{t('ed.campusFloor')}</span>
      <div class="chips">
        {#each floors as floor (floor)}
          <Chip full selected={selected?.floor === floor} onclick={() => {
            haptic.tap(); roomInput = null; pickPlace(side, floor, selected?.floor === floor ? selected.room : '');
          }}>{floor}</Chip>
        {/each}
      </div>
    </div>
    {#if selected}
      <Field label={t('ed.campusRoom')} maxlength={60} enterkeyhint="done"
        bind:value={() => roomInput ?? selected.room, (room) => { roomInput = room; pickPlace(side, selected.floor, room); }} />
    {/if}
  {/if}
</div>

<style>
  .picker, .choices { display: grid; gap: var(--s-2); }
  .picker { gap: var(--s-3); }
  .label { padding-inline: var(--s-4); color: var(--text-3); font: 450 var(--fs-sub)/1.2 var(--font-text); }
  .chips { display: grid; grid-auto-flow: column; grid-auto-columns: minmax(0, 1fr); gap: var(--s-1); padding-block: 4px; }
  abbr { text-decoration: none; }
</style>
