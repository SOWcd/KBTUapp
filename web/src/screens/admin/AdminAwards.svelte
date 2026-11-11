<script lang="ts">
  // Admin → Awards (pushed from the right; owner, Nov 3: "one Initiation 2026 medal as three buttons is dumb"): one card
  // per award in a two-column grid (owner, Nov 10) with its real medal and how many hold it; a card opens the award's
  // page (its variant, Scan, Link, the links, who has it). A person's awards are given from the person (Admin's search →
  // a person).
  import { api } from '../../lib/api';
  import { CATALOG, manualMedal, manualTitle } from '../../lib/awards';
  import { session } from '../../lib/state/session.svelte';
  import { open, type Overlay } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import Pane from '../../ui/Pane.svelte';
  import Medal from '../../ui/Medal.svelte';
  import AwardPane from './AwardPane.svelte';

  let { overlay }: { overlay: Overlay } = $props();
  const list = $derived(CATALOG.filter((a) => !a.creator || !!session.me?.founder));
  let counts = $state<Record<string, number>>({});
  const load = () => api.awardCounts().then((c) => (counts = c)).catch(() => {});
  void load();
</script>

<Pane {overlay} title={t('aw.title')}>
  <div class="grid">
    {#each list as a, i (a.code)}
      <button class="card" style="--i:{i}" onclick={() => { haptic.tap(); open(AwardPane, { award: a, onchange: load }); }}>
        <Medal a={manualMedal(a.code, a.emoji)} size={64} />
        <b class="nm">{manualTitle(a)}</b>
        <span class="n num">{counts[a.code] != null ? tn('aw.n', counts[a.code]) : '\u00a0'}</span>
      </button>
    {/each}
  </div>
</Pane>

<style>
  .grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
  .card { display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 18px 10px 14px; border-radius: var(--r-l); text-align: center;
    background: var(--surface); box-shadow: inset 0 0 0 1px var(--line); animation: rise 440ms cubic-bezier(.2, .9, .25, 1.05) backwards;
    animation-delay: calc(var(--i) * 40ms); transition: transform var(--t-fast) var(--ease); }
  .card:active { transform: scale(0.97); }
  .nm { max-width: 100%; font: 600 var(--fs-body)/1.2 var(--font-text); letter-spacing: -0.01em; overflow-wrap: break-word; hyphens: auto; }
  .n { font: 500 var(--fs-sub)/1.2 var(--font-text); color: var(--text-2); }
  @keyframes rise { from { opacity: 0; transform: translate3d(0, 8px, 0); } }
  :global(html.lowfx) .card { animation: none; }
</style>
