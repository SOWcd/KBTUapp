<script lang="ts">
  // Where I've been in the last 30 days, in Awards (the "N events" number opens it; My events page gone):
  // in the week after one, its faces ask how it was, one tap rates it here.
  import { api, type EventCard } from '../../lib/api';
  import { FACES } from '../../lib/faces';
  import { burst } from '../../ui/burst';
  import { say } from '../../lib/state/ui.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { relDay, nowTs } from '../../lib/time';
  import { haptic } from '../../lib/tg';
  import EventRow from '../../ui/EventRow.svelte';
  import Emoji from '../../ui/Emoji.svelte';

  let recent = $state<EventCard[]>([]);
  $effect(() => { api.pastEvents().then((l) => (recent = l.filter((e) => e.my?.checkedInAt && e.startsAt > nowTs() - 30 * 86400).slice(0, 5))).catch(() => {}); });
  const askable = (e: EventCard) => { const end = e.endsAt ?? e.startsAt + 3 * 3600, now = nowTs(); return e.my?.rating == null && end <= now && now <= end + 7 * 86400; };
  async function rate(e: EventCard, score: number) {
    haptic.select();
    try {
      await api.rate(e.id, score);
      recent = recent.map((x) => (x.id === e.id && x.my ? { ...x, my: { ...x.my, rating: score } } : x));
      haptic.ok(); burst(); say(t('rate.thanks'), 'sparkles_3d');
    } catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
  }
</script>

{#if recent.length}
  <h2 class="sh">{t('me.recent')}</h2>
  <div class="list">
    {#each recent as e (e.id)}
      <div class="past">
        <EventRow {e} showDate dateLine={relDay(e.startsAt)} />
        {#if askable(e)}
          <div class="ask"><b>{t('rate.ask')}</b><span class="faces">{#each FACES as f, i (i)}<button onclick={() => rate(e, i + 1)} aria-label={String(i + 1)}><Emoji name={f} size={28} /></button>{/each}</span></div>
        {/if}
      </div>
    {/each}
  </div>
{/if}

<style>
  .sh { font: 750 19px/1.2 var(--font-display); letter-spacing: -0.025em; margin-top: 6px; }
  .list { display: flex; flex-direction: column; gap: 8px; }
  .past { border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-card); }
  .past :global(.row) { box-shadow: none; background: none; }
  .ask { display: grid; gap: 8px; padding: 0 10px 12px; }
  .ask b { padding-left: 4px; font: 680 14px/1.2 var(--font-text); }
  .faces { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; }
  .faces button { height: 42px; border-radius: 13px; background: var(--surface-2); display: flex; align-items: center; justify-content: center; }
  .faces button:active { transform: scale(0.88); }
</style>
