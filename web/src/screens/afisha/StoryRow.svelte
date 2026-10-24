<script lang="ts">
  // The news on top of Afisha's List, as a row of circles (owner, Oct 24; PLAN 46): the broadcasts (DMP, KBTU App) and
  // every club I'm in or follow that posted in the last 30 days; a ring while something is unread. A tap plays that
  // club's posts full screen (Stories.svelte), then the next clubs'.
  import { untrack } from 'svelte';
  import { data, loadNews } from '../../lib/state/data.svelte';
  import { ui } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { nowTs } from '../../lib/time';
  import { storyGroups } from '../../lib/posts';
  import OrgLogo from '../../ui/OrgLogo.svelte';

  // fresh each time List comes into view, quietly (the last copy shows meanwhile)
  $effect(() => { if (ui.tab === 'afisha' && ui.page.afisha === 1) void untrack(loadNews); });
  const groups = $derived(data.news ? storyGroups(data.news.casts, data.news.posts, nowTs()) : []);
</script>

{#if groups.length}
  <div class="row hscroll" data-noswipe>
    {#each groups as g, i (g.org.id)}
      <button class="s" class:new={g.unread} onclick={() => sheets.stories(groups, i)}>
        <span class="ring"><span class="in"><OrgLogo org={g.org} size={54} /></span></span>
        <b class="ellipsis">{g.org.abbr ?? g.org.name}</b>
      </button>
    {/each}
  </div>
{/if}

<style>
  .row { display: flex; gap: 12px; margin: 0 calc(-1 * var(--gutter)) 16px; padding: 2px var(--gutter); overflow-x: auto; scrollbar-width: none; }
  .s { flex: none; width: 66px; display: flex; flex-direction: column; align-items: center; gap: 6px; }
  .s:active .ring { transform: scale(0.94); }
  .ring { display: block; box-sizing: border-box; width: 64px; height: 64px; padding: 2px; border-radius: 50%; background: var(--line-2); transition: transform var(--t-fast) var(--ease); }
  .new .ring { padding: 2.5px; background: conic-gradient(from 200deg, var(--accent), var(--accent-2), var(--accent)); }
  .in { box-sizing: border-box; display: grid; place-items: center; width: 100%; height: 100%; border-radius: 50%; border: 2.5px solid var(--bg); overflow: hidden; }
  b { max-width: 100%; font: 600 11.5px/1.2 var(--font-text); color: var(--text-2); }
  .new b { color: var(--text); }
</style>
