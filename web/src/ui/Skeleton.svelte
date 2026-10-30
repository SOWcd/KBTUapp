<script lang="ts">
  // What's loading, in the shape it will have: grey blocks that pulse slowly (still under power saving and reduced
  // motion). Use it only where the store has nothing yet (a page never waits for its data when the store has it).
  //   kind  rows (a Group's rows: a tile and two lines) | cards (event cards: a poster and three lines) | lines (text)
  //   n     how many
  let { kind = 'rows', n = 3 }: { kind?: 'rows' | 'cards' | 'lines'; n?: number } = $props();
</script>

<div class="sk {kind}" aria-busy="true" aria-hidden="true">
  {#each Array.from({ length: n }, (_, i) => i) as i (i)}
    {#if kind === 'lines'}<span class="bar" style:width="{92 - ((i * 23) % 40)}%"></span>
    {:else}
      <div class="it"><span class="pic"></span><span class="txt"><span class="bar"></span><span class="bar short"></span>{#if kind === 'cards'}<span class="bar tiny"></span>{/if}</span></div>
    {/if}
  {/each}
</div>

<style>
  .sk { display: flex; flex-direction: column; }
  .rows { border-radius: var(--r-group); background: var(--surface); overflow: hidden; }
  .cards { gap: var(--s-3); }
  .lines { gap: 10px; }
  .it { display: flex; align-items: center; gap: var(--s-3); padding: 10px var(--s-4); min-height: var(--row-h); }
  .cards .it { padding: 10px; border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-card); }
  .pic { flex: none; width: 30px; height: 30px; border-radius: var(--r-xs); }
  .cards .pic { width: 68px; height: 68px; border-radius: var(--r-m); }
  .txt { flex: 1; display: flex; flex-direction: column; gap: 8px; }
  .bar { display: block; height: 12px; border-radius: var(--r-full); width: 70%; }
  .short { width: 45%; }
  .tiny { width: 30%; }
  .pic, .bar { background: var(--fill); animation: breathe 1.4s ease-in-out infinite alternate; }
  @keyframes breathe { from { opacity: 1; } to { opacity: 0.45; } }
  :global(html.lowfx) .pic, :global(html.lowfx) .bar { animation: none; }
</style>
