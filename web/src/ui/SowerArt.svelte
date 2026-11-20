<script lang="ts">
  // The creator's own lanyard (from scratch, his avatar itself): the photo's horns hand screened again at
  // the card's size on its torn white paper, the creator's seal held between its two fingers (Hero: .sower .medal), on
  // the avatar's charcoal checker that turns into a print's halftone behind it; crop marks, one red dot. Layers far to
  // near (assets/lanyards/sower, made by .claude/reports/club-lanyards/owner/round1/gen/gen-owner.py; as pictures:
  // tools/scene-rasters.mjs): the checker moving with the tilt (base.css .z), the marks still, the hand moving the
  // most. `wide`: the profile's card and its back; else the full-screen badge (MyQr).
  import far from '../assets/lanyards/sower/far-card.webp';
  import mid from '../assets/lanyards/sower/mid-card.webp';
  import near from '../assets/lanyards/sower/near-card.webp';
  let { wide = false }: { wide?: boolean } = $props();
</script>

<div class="sa" class:wide aria-hidden="true">
  <img class="far z" src={far} alt="" /><img src={mid} alt="" /><img class="near z" src={near} alt="" />
  <i class="gloss"></i>
</div>

<style>
  .sa { position: absolute; inset: 0; overflow: hidden; border-radius: inherit; pointer-events: none;
    background: linear-gradient(160deg, rgb(46, 46, 46), rgb(28, 28, 28) 50%, rgb(14, 14, 14)); }
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
