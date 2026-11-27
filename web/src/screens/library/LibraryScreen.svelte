<script lang="ts">
  // A library room's big screen (/show?lib=<key>, Admin → Library copies the link): its tables and seats as free or
  // taken, the free count in big. Nothing else: no names, no codes; the room's key is all it needs (server library.screen).
  import { onMount } from 'svelte';
  import { api, type LibWall } from '../../lib/api';
  import { t } from '../../lib/i18n/index.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';

  const key = new URLSearchParams(location.search).get('lib') ?? '';
  let wall = $state<LibWall | null>(null), gone = $state(false);
  onMount(() => {
    let stop = false, timer: ReturnType<typeof setTimeout> | undefined;
    // ponytail: read again every 5 s, like /show's check-in screen (no push channel to a signed-out page exists).
    // Upgrade: a server-sent stream for both
    const poll = async () => {
      const w = await api.libWall(key);
      if (stop) return;
      if (w) { wall = w; gone = false; } else if (!wall) gone = true;
      timer = setTimeout(poll, 5000);
    };
    void poll();
    return () => { stop = true; clearTimeout(timer); };
  });
</script>

<main class="wall">
  <header>
    <span class="mark"><KbtuMark size={44} /></span>
    {#if wall}<h1>{wall.name}</h1>{/if}
  </header>
  {#if wall}
    <p class="free"><b>{wall.free}</b><span>{t('lib.wallFree', { total: wall.total })}</span></p>
    <section class="tables">
      {#each wall.tables as x, i (i)}
        <div class="table">
          <span class="label">{x.label}</span>
          <span class="seats">{#each x.seats as s, j (j)}<i class={s}></i>{/each}</span>
        </div>
      {/each}
    </section>
    <p class="how">{t('lib.wallHow')}</p>
  {:else if gone}
    <p class="how">{t('lib.wallGone')}</p>
  {/if}
</main>

<style>
  :global(body) { margin: 0; background: var(--bg); color: var(--text); }
  .wall { min-height: 100vh; box-sizing: border-box; padding: 4vh 5vw; display: flex; flex-direction: column; gap: 3vh; font-family: var(--font-text); }
  header { display: flex; align-items: center; gap: 20px; }
  .mark { display: inline-flex; color: var(--accent); }
  /* a wall's sizes: from the screen's width, in rem (a laptop on a TV) */
  h1 { margin: 0; font: 800 clamp(1.75rem, 4vw, 3.5rem)/1.1 var(--font-display); letter-spacing: -0.03em; }
  .free { margin: 0; display: flex; align-items: baseline; gap: 18px; }
  .free b { font: 800 clamp(4rem, 12vw, 11rem)/0.9 var(--font-display); color: var(--success); letter-spacing: -0.05em; font-variant-numeric: tabular-nums; }
  .free span { font: 600 clamp(1.25rem, 2.4vw, 2.1rem)/1.2 var(--font-text); color: var(--text-2); }
  .tables { display: grid; grid-template-columns: repeat(auto-fill, minmax(170px, 1fr)); gap: 16px; }
  .table { display: grid; gap: 12px; padding: 18px; border-radius: var(--r-l); background: var(--surface); box-shadow: var(--shadow-card); }
  .label { font: 700 clamp(1.1rem, 1.6vw, 1.6rem)/1 var(--font-display); }
  .seats { display: flex; flex-wrap: wrap; gap: 10px; }
  .seats i { width: 26px; height: 26px; border-radius: 50%; background: var(--success); transition: background var(--t-fast) var(--ease); }
  .seats i.taken { background: var(--fill-2); }
  .how { margin: auto 0 0; font: 500 clamp(1rem, 1.6vw, 1.5rem)/1.4 var(--font-text); color: var(--text-2); }
</style>
