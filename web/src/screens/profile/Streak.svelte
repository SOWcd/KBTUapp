<script lang="ts">
  // The weeks-in-a-row flame (§4.11, a student's idea, Nov 27): the current run of weeks with a check-in, the number big
  // by a flame; on my Profile my friends' flames beside mine (the Friends page's rows carry them: no request of its own).
  // A tap opens the Streak medal. Nothing shows at zero: an empty flame reads as a reproach.
  import type { Achievement, FriendRow } from '../../lib/api';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { achItem } from '../../lib/awards';
  import { sheets } from '../../lib/state/sheets';
  import { haptic } from '../../lib/tg';
  import Avatar from '../../ui/Avatar.svelte';
  import Emoji from '../../ui/Emoji.svelte';

  let { a, mine = false, friends = [] }: { a: Achievement; mine?: boolean; friends?: FriendRow[] } = $props();
  const now = $derived(a.now ?? 0);
  // the longest runs first, three at most: the card stays one line on a 320 px phone
  const lit = $derived(friends.filter((f) => (f.streak ?? 0) > 0).sort((x, y) => y.streak! - x.streak!).slice(0, 3));
</script>

{#if now > 0 || lit.length}
  <button class="streak surface" data-away onclick={() => { haptic.tap(); sheets.award(achItem(a), mine); }}
    aria-label={`${t('ach.streak.name')}: ${now} ${tn('streak.weeks', now)}${lit.length ? ` · ${t('streak.friends')}: ${lit.map((f) => f.streak).join(', ')}` : ''}`}>
    <span class="me" class:off={!now}>
      <span class="fl" aria-hidden="true"><Emoji name="fire_3d" size={30} /></span>
      <b class="n num">{now}</b>
      <span class="lb">{tn('streak.weeks', now)}</span>
    </span>
    {#if lit.length}
      <span class="fr" aria-hidden="true">
        {#each lit as f (f.person.id)}
          <span class="f"><Avatar person={f.person} size={28} tappable={false} /><i class="num">{f.streak}</i></span>
        {/each}
      </span>
    {/if}
  </button>
{/if}

<style>
  .streak { display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; padding: 12px 14px; border-radius: var(--r-l); text-align: left;
    background: radial-gradient(70% 120% at 0% 50%, var(--warning-soft), transparent 70%), var(--surface); }
  .streak:active { transform: scale(0.98); }
  .me { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .fl { display: flex; animation: flicker 2.8s ease-in-out infinite; transform-origin: 50% 90%; }
  .off .fl { animation: none; opacity: 0.45; filter: grayscale(1); }
  .n { font: 800 var(--fs-t1)/1 var(--font-display); letter-spacing: -0.03em; }
  .lb { font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .fr { display: flex; gap: 10px; flex-shrink: 0; }
  .f { position: relative; display: flex; }
  .f i { position: absolute; right: -6px; bottom: -4px; display: flex; align-items: center; justify-content: center; min-width: 18px; height: 18px; padding: 0 5px;
    border-radius: var(--r-full); background: var(--warning); color: var(--ink); font: 700 var(--fs-micro)/1 var(--font-text); font-style: normal;
    box-shadow: 0 0 0 2px var(--surface-solid); }
  @keyframes flicker { 0%, 100% { transform: none; } 50% { transform: scale(1.06) rotate(-2deg); } }
  @media (prefers-reduced-motion: reduce) { .fl { animation: none; } }
  :global(html.lowfx) .fl { animation: none; }
</style>
