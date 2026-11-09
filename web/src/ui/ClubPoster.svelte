<script lang="ts">
  // A club as a poster, the shelves of the Clubs tab and an interest's page: its cover, its big mark, the name on it and
  // one line. wide: the page's first, the whole row. A tap opens the club.
  import type { Org } from '../lib/api';
  import { artOf } from '../lib/covers';
  import { sheets } from '../lib/state/sheets';
  import { lastWord, nameOf } from '../lib/short';
  import Emoji from './Emoji.svelte';
  import FriendsLine from './FriendsLine.svelte';
  import GovMark from './GovMark.svelte';
  import OfficialMark from './OfficialMark.svelte';
  import { COVERS } from './OrgLogo.svelte';

  let { org: o, sub, wide = false }: { org: Org; sub: string; wide?: boolean } = $props();
  const size = $derived(wide ? 128 : 88);
  const [head, tail] = $derived(lastWord(nameOf(o)));
  const art = $derived(artOf(o));
</script>

<button class={['poster', { wide }]} style:background={COVERS[o.cover % COVERS.length]} onclick={() => sheets.club(o.id)}>
  {#if art}<img class="art" src={art} alt="" loading="lazy" decoding="async" draggable="false" />{/if}
  <span class="mark">{#if o.logo}<img src={o.logo} alt="" width={size} height={size} draggable="false" />{:else}<Emoji name={o.emoji} {size} />{/if}</span>
  <span class="tx">
    <b class="clamp-2">{head}<span class="nb">{tail}{#if o.official && o.kind === 'club'}<OfficialMark size={15} />{/if}{#if o.gov}<GovMark size={14} />{/if}</span></b>
    {#if o.friends.length}<small><FriendsLine org={o} max={1} /></small>{:else if sub}<small class="clamp-2">{sub}</small>{/if}
  </span>
</button>

<style>
  .poster { position: relative; flex: none; width: 148px; height: 184px; overflow: hidden; border-radius: var(--r-l); color: var(--on-accent); text-align: left; scroll-snap-align: start; }
  .poster.wide { width: 100%; height: 164px; }
  .poster::after { content: ''; position: absolute; inset: 45% 0 0; background: linear-gradient(transparent, rgba(0, 0, 0, 0.55)); }
  .art { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .mark { position: absolute; left: 50%; top: 16px; translate: -50% 0; rotate: -5deg; display: flex; filter: drop-shadow(0 12px 16px rgba(0, 0, 0, 0.3)); }
  .wide .mark { left: auto; right: 10px; top: 6px; translate: none; rotate: -8deg; }
  .mark img { border-radius: var(--r-l); object-fit: cover; }
  .tx { position: absolute; z-index: 1; left: 12px; right: 12px; bottom: 11px; display: flex; flex-direction: column; gap: 2px; }
  .wide .tx { right: 150px; left: 16px; bottom: 14px; }
  b { min-width: 0; font: 700 var(--fs-body)/1.15 var(--font-text); letter-spacing: -0.012em; }
  .wide b { font: 800 var(--fs-sec)/1.12 var(--font-display); letter-spacing: -0.02em; }
  small { font: 500 var(--fs-cap)/1.2 var(--font-text); opacity: 0.85; }
  b :global(.om), b :global(.gov) { vertical-align: -2px; margin-left: 3px; color: var(--on-accent); }
  .nb { white-space: nowrap; } /* a mark never sits alone on a line: it stays with the last word */
  b :global(.om .tick) { stroke: var(--accent); }
</style>
