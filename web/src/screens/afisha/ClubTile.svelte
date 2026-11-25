<script lang="ts">
  // One club in the Clubs tab's catalogue grid: its cover (lanyard art or its colours) with the mark sitting on the
  // edge, the name, and one line of life: what's next (lit), else friends in it, else its people. Opens the club's card.
  import type { Org } from '../../lib/api';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { friendsIn, waitsDmp } from '../../lib/clubs';
  import { artOf, coverOf, mirrors } from '../../lib/covers';
  import { nameOf } from '../../lib/short';
  import { sheets } from '../../lib/state/sheets';
  import { haptic } from '../../lib/tg';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import OfficialMark from '../../ui/OfficialMark.svelte';
  import GovMark from '../../ui/GovMark.svelte';

  let { org: o, next }: { org: Org; next?: string } = $props();
  const art = $derived(artOf(o));
  const line = $derived(waitsDmp(o) ? t('clubs.awaitsDmp') : next ?? (o.friendsN ? friendsIn(o) : o.members ? tn('club.members', o.members) : ''));
  const open = () => { haptic.tap(); sheets.club(o.id); };
</script>

<button class="tile press" onclick={open}>
  <span class="cv" style:background={coverOf(o)}>
    {#if art}<img class={['art', { flip: mirrors(o) }]} src={art} alt="" loading="lazy" decoding="async" draggable="false" />{/if}
    {#if o.recruiting || o.round}<span class="open">{t('clubs.doorOpen')}</span>{/if}
  </span>
  <span class="mk"><OrgLogo org={o} size={44} /></span>
  <span class="tx">
    <b class="clamp-2">{nameOf(o)}{#if o.official && o.kind === 'club'}<OfficialMark size={13} />{/if}{#if o.gov}<GovMark size={12} />{/if}</b>
    {#if line}<small class={['ellipsis', { lit: !!next && !waitsDmp(o) }]}>{line}</small>{/if}
  </span>
</button>

<style>
  .tile { position: relative; display: flex; flex-direction: column; min-width: 0; overflow: hidden; text-align: left; border-radius: var(--r-l); background: var(--surface-solid); box-shadow: var(--card-rim), var(--shadow-card); color: var(--text); }
  .cv { position: relative; display: block; height: 64px; overflow: hidden; }
  .art { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; }
  .flip { scale: -1 1; }
  /* a glass tag on the cover: this club takes people now */
  .open { position: absolute; top: var(--s-2); right: var(--s-2); padding: 3px var(--s-2); border-radius: var(--r-full); background: var(--media-tag); color: var(--on-accent); font: 600 var(--fs-micro)/1.2 var(--font-text); -webkit-backdrop-filter: blur(12px); backdrop-filter: blur(12px); }
  /* the mark sits half on the cover, cut out of it by a ring of the tile's own ground */
  .mk { position: relative; display: flex; margin: -22px 0 0 var(--s-3); }
  .mk :global(.logo) { box-shadow: 0 0 0 3px var(--surface-solid); }
  .tx { display: flex; flex-direction: column; gap: 3px; padding: var(--s-2) var(--s-3) var(--s-3); }
  b { font: 600 var(--fs-body)/1.25 var(--font-text); letter-spacing: -0.01em; overflow-wrap: anywhere; }
  b :global(.om), b :global(.gov) { vertical-align: -1px; margin-left: 3px; }
  small { font: 500 var(--fs-cap)/1.3 var(--font-text); color: var(--text-3); }
  small.lit { color: var(--accent-text); }
</style>
