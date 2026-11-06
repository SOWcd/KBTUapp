<script lang="ts">
  // The creator's own lanyard (owner, Nov 6: the holographic one went; in his photo's colours, a halftone hand cut out of
  // white paper on graphite). lib/awards.ts SOWER picks the concept; its layers far to near (assets/lanyards/sower, drawn
  // by .claude/reports/sower-lanyard/gen-sower.py; as pictures: tools/scene-rasters.mjs), the far and near ones moving
  // with the tilt (base.css .z). `wide`: the profile's card and its back; else the full-screen badge (MyQr), the same
  // scene across its top, fading down into the QR's side.
  import { SOWER } from '../lib/awards';
  const PIC = import.meta.glob('../assets/lanyards/sower/*-card.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
  let { wide = false }: { wide?: boolean } = $props();
</script>

<div class="sa {SOWER}" class:wide aria-hidden="true">
  {#each ['far', 'mid', 'near'] as n (n)}<img class="l {n}" class:z={n !== 'mid'} src={PIC[`../assets/lanyards/sower/${SOWER}-${n}-card.webp`]} alt="" />{/each}
  <i class="gloss"></i>
</div>

<style>
  .sa { position: absolute; inset: 0; overflow: hidden; border-radius: inherit; pointer-events: none;
    background: radial-gradient(70% 90% at 92% 0%, rgba(232, 232, 231, 0.12), transparent 70%), linear-gradient(160deg, rgb(46, 46, 46), rgb(30, 30, 30) 50%, rgb(14, 14, 14)); }
  img { position: absolute; inset: 0; width: 100%; height: 100%; object-fit: cover; object-position: 100% 100%; pointer-events: none; user-select: none; -webkit-user-drag: none; }
  .far { --z: -2; --zs: 1.03; }
  .near { --z: 3; --zs: 1.03; }
  /* the badge: the scene a little smaller in its top right corner, so the hand stands whole above the QR */
  .sa:not(.wide) img { left: auto; top: -4px; width: 82%; height: auto; aspect-ratio: 340 / 164; bottom: auto;
    -webkit-mask: linear-gradient(180deg, black 72%, transparent); mask: linear-gradient(180deg, black 72%, transparent); }
  i { position: absolute; display: block; pointer-events: none; }
  .gloss { inset: 0; border-radius: inherit; background: radial-gradient(130% 70% at 30% -18%, rgba(255, 255, 255, 0.1), transparent 65%), linear-gradient(180deg, transparent 65%, rgba(0, 0, 0, 0.18));
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22), inset 0 -2px 8px rgba(0, 0, 0, 0.25); }
</style>
