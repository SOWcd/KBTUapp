<script lang="ts">
  // The news on top of Afisha's List, as a row of circles (PLAN 46): the broadcasts (DMP, KBTU App),
  // every club I'm in or follow that posted in the last 30 days, and every club with a new event (lib/posts.ts); a ring while something is unread. A tap plays that
  // club's posts full screen (Stories.svelte), then the next clubs'. The first circle, "News", opens every post (News).
  import Newspaper from '@lucide/svelte/icons/newspaper';
  import { t } from '../../lib/i18n/index.svelte';
  import { untrack } from 'svelte';
  import { SvelteSet } from 'svelte/reactivity';
  import type { OrgRef } from '../../lib/api';
  import { data, loadNews } from '../../lib/state/data.svelte';
  import { ui } from '../../lib/state/ui.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { nowTs } from '../../lib/time';
  import { storyGroups, seenEv } from '../../lib/posts';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import { nameOf } from '../../lib/short'; // a school by its abbreviation, a club in full ("EC" looked like a bug)

  // fresh each time List comes into view, quietly (the last copy shows meanwhile)
  $effect(() => { if (ui.tab === 'afisha') void untrack(loadNews); });
  // a club whose full name runs past its circle ("Club Fem...") goes by its short name (owner, Nov 3); measured, once each
  const tight = new SvelteSet<number>();
  // (by the text's own width, so a row laid out on a hidden tab measures right too; 66: the circle's width, .s)
  let pen: CanvasRenderingContext2D | null = null;
  function fit(node: HTMLElement, o: OrgRef) {
    if (!o.abbr) return;
    pen ??= document.createElement('canvas').getContext('2d');
    if (!pen) return;
    pen.font = getComputedStyle(node).font;
    if (pen.measureText(nameOf(o)).width > 66) tight.add(o.id);
  }
  // a new event earns a circle only from an official organization or one I'm in or follow (owner, Nov 9), as the posts do (server _REACH)
  const reach = $derived(new Set(data.orgs.filter((o) => o.official || o.kind !== 'club' || o.top || o.myRole || o.subscribed).map((o) => o.id)));
  const groups = $derived(storyGroups(data.news?.casts ?? [], data.news?.posts ?? [], nowTs(), data.events.filter((e) => reach.has(e.org.id)), seenEv));
</script>

<div class="row hscroll">
  <!-- the whole news feed first and by its name (owner, Nov 11: as the last circle "All" nobody found it) -->
  <button class="s news" onclick={() => sheets.news()}>
    <span class="ring"><span class="in all"><Newspaper size={24} strokeWidth={2} /></span></span>
    <b class="ellipsis">{t('page.news')}</b>
  </button>
  {#each groups as g, i (g.org.id)}
    <button class="s" class:new={g.unread} onclick={() => sheets.stories(groups, i)}>
      <span class="ring"><span class="in"><OrgLogo org={g.org} size={54} /></span></span>
      <b class="ellipsis" use:fit={g.org}>{tight.has(g.org.id) ? g.org.abbr : nameOf(g.org)}</b>
    </button>
  {/each}
</div>

<style>
  .row { display: flex; gap: 12px; margin: 0 calc(-1 * var(--gutter)) 16px; padding: 2px var(--gutter); overflow-x: auto; scrollbar-width: none; }
  .s { flex: none; width: 66px; display: flex; flex-direction: column; align-items: center; gap: 6px; }
  .s:active .ring { transform: scale(0.94); }
  .ring { display: block; box-sizing: border-box; width: 64px; height: 64px; padding: 2px; border-radius: 50%; background: var(--line-2); transition: transform var(--t-fast) var(--ease); }
  .new .ring { padding: 2.5px; background: conic-gradient(from 200deg, var(--accent), var(--accent-2), var(--accent)); }
  .in { box-sizing: border-box; display: grid; place-items: center; width: 100%; height: 100%; border-radius: 50%; border: 2.5px solid var(--bg); overflow: hidden; }
  .all { background: var(--accent-soft); color: var(--accent); }
  .news b { color: var(--text); }
  b { max-width: 100%; font: 600 var(--fs-micro)/1.2 var(--font-text); color: var(--text-2); }
  .new b { color: var(--text); }
</style>
