<script lang="ts">
  // Where I've been in the last 30 days, in Awards (the "N events" number opens it; My events page gone):
  // in the week after one, its faces ask how it was, one tap rates it here.
  import { FACES } from '../../lib/faces';
  import { data, canAskRating, ratingBusy, rateFromPrompt } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { relDay } from '../../lib/time';
  import EventRow from '../../ui/EventRow.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import Button from '../../ui/Button.svelte';
  import Section from '../../ui/Section.svelte';

  const recent = $derived((data.myPast ?? data.past.filter((e) => e.my?.checkedInAt != null)).slice(0, 5));
</script>

{#if recent.length}
  <Section title={t('me.recent')}>
  <div class="list">
    {#each recent as e (e.id)}
      <div class="past">
        <EventRow {e} showDate dateLine={relDay(e.startsAt)} />
        {#if canAskRating(e) && !ratingBusy.has(e.id)}
          <div class="ask"><b>{t('rate.ask')}</b><span class="faces">{#each FACES as f, i (i)}<Button kind="secondary" size="m" full round label={t('rate.score', { n: i + 1 })} onclick={() => void rateFromPrompt(e.id, i + 1)}>{#snippet icon()}<Emoji name={f} size={28} />{/snippet}</Button>{/each}</span></div>
        {/if}
      </div>
    {/each}
  </div>
  </Section>
{/if}

<style>
  .list { display: flex; flex-direction: column; gap: 8px; }
  .past { border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-card); }
  .past :global(.row) { box-shadow: none; background: none; }
  .ask { display: grid; gap: 8px; padding: 0 10px 12px; }
  .ask b { padding-left: 4px; font: 600 var(--fs-body)/1.2 var(--font-text); }
  .faces { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; }
  .faces > :global(.btn) { width: 100%; } /* round, as wide as its fifth */
</style>
