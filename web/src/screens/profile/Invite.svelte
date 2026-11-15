<script lang="ts">
  // My invite (referrals): the row under Friends in the profile's people group, and since Nov 4 my Recruiter's only home
  // on my profile (my own shelf hides it). The medal opens its award view (the levels); the rest of the row opens
  // RefSheet (my profile QR, Share). Under the title: what is left to the next level, and the nine levels as nine small
  // marks in their metals, the next one filling. A student it brings counts once they sign in with KBTU.
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  import type { Achievement, Me } from '../../lib/api';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { sheets } from '../../lib/state/sheets';
  import { achItem, achName, leftLine, metalOf, nextOf } from '../../lib/awards';
  import { glass } from '../../ui/glass';
  import Medal from '../../ui/Medal.svelte';

  let { r, ach }: { r: NonNullable<Me['referrals']>; ach?: Achievement } = $props();
  const LEVELS = [1, 3, 5, 10, 15, 25, 50, 75, 100]; // as the server's ACHIEVEMENTS
  // my card's own Recruiter once it's loaded; until then the same from the count, so the row never waits
  const a = $derived<Achievement>(ach && ach.count === r.count ? ach : {
    code: 'referral', emoji: 'megaphone_3d', secret: false, count: r.count, rarity: 0,
    level: LEVELS.filter((n) => n <= r.count).length, levels: LEVELS.map((need) => ({ need, reached: r.count >= need, rarity: 0 })),
  });
  const next = $derived(nextOf(a)?.need);
  const from = $derived(a.levels[a.level - 1]?.need ?? 0);
  const part = $derived(next ? Math.max(0.06, (r.count - from) / (next - from)) : 1);
  // each mark in its own level's metal: I-III bronze, IV-VI silver, VII-VIII gold, IX legend
  const marks = $derived(a.levels.map((l, i) => ({ m: 'bsgl'[metalOf(i + 1, a.levels.length)], fill: l.reached ? 1 : i === a.level ? part : 0 })));
</script>

<!-- kb-row: Row's own mark, so a Row after it draws its line -->
<div class="inv kb-row">
  <button class="art" use:glass onclick={() => { haptic.tap(); sheets.award(achItem(a), true); }} aria-label={achName(a)}><Medal {a} size={40} /></button>
  <button class="main" onclick={() => { haptic.tap(); sheets.referral(r.code); }}>
    <span class="tx">
      <span class="tt">{t('ref.title')}</span>
      {#if next}<span class="st ellipsis">{leftLine(a)}</span>{/if}
      <span class="marks" aria-hidden="true">{#each marks as k, i (i)}<i class={k.m}><s style:transform="scaleX({k.fill})"></s></i>{/each}</span>
    </span>
    <span class="val"><b class="num">{r.count}</b> <span class="w">{tn('ref.came', r.count)}</span></span>
    <span class="mk"><ChevronRight size={18} /></span>
  </button>
</div>

<style>
  /* Row's metrics (ui/Row.svelte), with two buttons side by side: the medal and the rest */
  .inv { display: flex; align-items: stretch; width: 100%; padding-left: var(--s-4); }
  .art { flex: none; align-self: center; display: flex; border-radius: 50%; }
  .art:active { transform: scale(0.94); }
  .main { position: relative; flex: 1; min-width: 0; display: flex; align-items: center; gap: var(--s-2); min-height: var(--row-h2);
    margin-left: var(--s-3); padding: 10px var(--s-4) 10px 0; text-align: left; color: var(--text); font: var(--fw-row) var(--fs-row)/1.25 var(--font-text); }
  .main::before { content: ''; position: absolute; top: 0; left: 0; right: 0; height: 0.5px; background: var(--separator); }
  .main:active { opacity: 0.6; }
  .tx { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px; }
  .st { font: 450 var(--fs-body)/1.3 var(--font-text); letter-spacing: -0.008em; color: var(--text-3); }
  .val { flex: none; color: var(--text-3); font-weight: 450; white-space: nowrap; }
  .val b { font-weight: 600; color: var(--text-2); }
  @media (max-width: 359px) { .w { display: none; } } /* 320 px: the number alone, the title keeps its line */
  .mk { flex: none; display: inline-flex; margin-right: -4px; color: var(--text-3); opacity: 0.6; }
  /* the nine levels: a mark each, in its metal; the next one fills as friends come */
  .marks { display: flex; gap: 3px; max-width: 150px; margin-top: 5px; }
  .marks i { flex: 1; height: 3px; border-radius: var(--r-full); background: var(--fill); overflow: hidden; }
  .marks s { display: block; height: 100%; border-radius: inherit; transform-origin: left; transition: transform 600ms var(--ease-out, ease); }
  .marks .b s { background: linear-gradient(90deg, rgb(178, 106, 60), rgb(238, 176, 122)); }
  .marks .s s { background: linear-gradient(90deg, rgb(142, 152, 174), rgb(232, 237, 246)); }
  .marks .g s { background: linear-gradient(90deg, rgb(194, 134, 26), rgb(247, 215, 116)); }
  .marks .l s { background: linear-gradient(90deg, rgb(124, 77, 255), rgb(53, 208, 255), rgb(255, 210, 63)); }
</style>
