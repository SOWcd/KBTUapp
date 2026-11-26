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
  // the medal's tier (0..4) lights the card only while the run is alive: a dead flame has no glow
  const tier = $derived(now ? Math.min(a.level ?? 0, a.levels.length) : 0);
  // the longest runs first, three at most: the card stays one line on a 320 px phone
  const lit = $derived(friends.filter((f) => (f.streak ?? 0) > 0).sort((x, y) => y.streak! - x.streak!).slice(0, 3));
</script>

{#if now > 0 || lit.length}
  <button class="streak surface" data-away data-tier={tier} onclick={() => { haptic.tap(); sheets.award(achItem(a), mine); }}
    aria-label={`${t('ach.streak.name')}: ${now} ${tn('streak.weeks', now)}${lit.length ? ` · ${t('streak.friends')}: ${lit.map((f) => f.streak).join(', ')}` : ''}`}>
    <span class="me" class:off={!now}>
      <span class="fl" aria-hidden="true"><Emoji name="fire_3d" size={30} /></span>
      <b class="n num">{now}</b>
      <span class="tx">
        <span class="lb">{tn('streak.weeks', now)}</span>
        <!-- the medal's ladder (2, 4, 8, 16 weeks): the tier reads without relying on colour -->
        <span class="pips" aria-hidden="true">{#each a.levels as _, i (i)}<i class:on={i < tier}></i>{/each}</span>
      </span>
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
  /* the tier's light: --tc its colour, --tc2 the halo's outer ring and the card's wash, --ta the halo's strength, --tr its reach */
  .streak { --tc: var(--warning); --tc2: var(--tc); --ta: 0.18; --tr: -3px; position: relative; isolation: isolate;
    display: flex; align-items: center; justify-content: space-between; gap: 12px; width: 100%; padding: 12px 14px; border-radius: var(--r-l); text-align: left; white-space: nowrap;
    background: var(--surface); }
  /* the card's tier-tinted wash: opacity over a token, no colour mixing (iOS before 16.2 drops it) */
  .streak::before { content: ''; position: absolute; inset: 0; z-index: -1; border-radius: inherit; opacity: 0.12; pointer-events: none;
    background: radial-gradient(70% 120% at 0% 50%, var(--tc2), transparent 70%); }
  .streak[data-tier='1'] { --tc: var(--tile-orange); --ta: 0.3; --tr: -5px; } /* copper */
  .streak[data-tier='2'] { --tc: var(--tile-gray); --ta: 0.36; --tr: -7px; }  /* steel */
  .streak[data-tier='3'] { --tc: var(--gold); --ta: 0.46; --tr: -9px; }
  .streak[data-tier='4'] { --tc: var(--gold); --tc2: var(--accent-2); --ta: 0.56; --tr: -12px; }                     /* legend: gold into violet */
  .streak:active { transform: scale(0.98); }

  .me { display: flex; align-items: center; gap: 8px; min-width: 0; }
  .fl { position: relative; isolation: isolate; display: flex; flex: none; animation: sway 4.6s ease-in-out infinite; transform-origin: 50% 90%; }
  /* the halo: a static gradient, only its scale moves */
  .fl::before { content: ''; position: absolute; inset: var(--tr); z-index: -1; opacity: var(--ta);
    background: radial-gradient(closest-side, var(--tc), var(--tc2) 35%, transparent 75%);
    animation: breathe 6s ease-in-out infinite; }
  .off .fl { animation: none; opacity: 0.45; filter: grayscale(1); }
  .off .fl::before { display: none; }
  .n { flex: none; font: 800 var(--fs-t1)/1 var(--font-display); letter-spacing: -0.03em; }
  .tx { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
  .lb { overflow: hidden; text-overflow: ellipsis; font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  .pips { display: flex; gap: 3px; }
  .pips i { width: 8px; height: 3px; border-radius: var(--r-full); background: var(--fill-2); }
  .pips i.on { background: var(--tc); }

  .fr { display: flex; gap: 10px; flex-shrink: 0; }
  .f { position: relative; display: flex; }
  /* a neutral chip: the flame stays the only warm thing on the card */
  .f i { position: absolute; right: -6px; bottom: -4px; display: flex; align-items: center; justify-content: center; min-width: 18px; height: 18px; padding: 0 5px;
    border-radius: var(--r-full); background: var(--surface-3); color: var(--text); font: 700 var(--fs-micro)/1 var(--font-text); font-style: normal;
    box-shadow: 0 0 0 2px var(--surface-solid); }

  @keyframes sway { 0%, 100% { transform: none; } 50% { transform: scale(1.03) rotate(-1.5deg); } }
  @keyframes breathe { 0%, 100% { transform: scale(0.92); } 50% { transform: scale(1.08); } }
  @media (prefers-reduced-motion: reduce) { .fl, .fl::before { animation: none; } }
  :global(html.lowfx) .fl, :global(html.lowfx) .fl::before { animation: none; }
</style>
