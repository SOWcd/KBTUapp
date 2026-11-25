<script lang="ts">
  // The creator's own lanyard, "matte black, one red" (.claude/reports/sower-badge, card C): a graphite card lit from
  // its top right corner, faint tone-on-tone rings spreading from there, a hairline edge. No pictures: the hand is his
  // photo's tile (Hero), the one red is the strap's stitch, the role's dot and the strip's № (Hero, LanyardHolo).
  // `wide`: the profile's card and its back; else the full-screen badge (MyQr), the rings a little smaller.
  let { wide = false }: { wide?: boolean } = $props();
</script>

<div class="sa" class:wide aria-hidden="true"><i class="rings"></i></div>

<style>
  .sa { position: absolute; inset: 0; overflow: hidden; border-radius: inherit; pointer-events: none;
    background: radial-gradient(90% 120% at 100% 0%, rgb(44, 44, 46), transparent 55%), linear-gradient(165deg, rgb(28, 28, 30), rgb(10, 10, 11) 70%);
    box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.07), inset 0 1px 0 rgba(255, 255, 255, 0.16); }
  .rings { position: absolute; right: -90px; top: -90px; width: 380px; height: 380px; border-radius: 50%;
    background: repeating-radial-gradient(circle, transparent 0 13px, rgba(255, 255, 255, 0.035) 13px 14px);
    -webkit-mask: radial-gradient(circle, black 20%, transparent 68%); mask: radial-gradient(circle, black 20%, transparent 68%); }
  .sa:not(.wide) .rings { right: -110px; top: -110px; }
</style>
