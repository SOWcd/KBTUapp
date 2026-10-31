<script lang="ts">
  // The Knights' helmet and plume, hand-traced from their logo (design/brand/knights/logo.png) without the building,
  // wordmark and ball: big shapes that hold up small (the QR's mark) and faint behind text (the profile's card).
  // `emboss`: pressed into the card, a light edge on top and a shadow below, drawn here (no CSS filter or blend: both
  // force offscreen passes inside the tilted 3D card on old WebKit).
  let { emboss = false }: { emboss?: boolean } = $props();
  const D = [
    'M246 113C232 98 222 78 222 58C222 30 248 10 284 10C330 10 368 38 388 78C398 98 412 112 432 122C410 126 392 120 378 108C362 92 350 76 330 70C306 62 284 70 274 86C268 96 266 104 266 113ZM236 76C236 46 262 26 300 26C338 26 366 50 382 88C362 60 336 42 304 40C272 38 248 52 236 76ZM246 98C248 82 262 64 290 60C266 66 254 80 246 98Z',
    'M256 112C216 112 189 146 189 190C189 230 216 260 256 266C296 260 323 230 323 190C323 146 296 112 256 112ZM204 177Q256 167 309 175L309 186Q256 178 204 188ZM254 122H258V170H254ZM254 191H258V256H254ZM224 204H230V244H224ZM238 204H244V250H238ZM268 204H274V250H268ZM282 204H288V244H282Z',
  ];
  const id = 'kh' + Math.random().toString(36).slice(2, 8); // mask ids are page-global: the picker draws several
</script>

<svg viewBox="184 6 252 264" fill-rule="evenodd" aria-hidden="true">
  {#if emboss}
    <!-- the shape moved 1.5 up (or down) minus the shape itself: a 1 px sliver along its top (or bottom) edges -->
    {#each [['u', -1.5], ['d', 1.5]] as [k, dy] (k)}
      <mask id="{id}{k}" maskUnits="userSpaceOnUse" x="180" y="0" width="260" height="280">
        {#each D as d (d)}<path {d} fill="white" transform="translate(0 {dy})" />{/each}
        {#each D as d (d)}<path {d} fill="black" />{/each}
      </mask>
    {/each}
    <rect x="180" y="0" width="260" height="280" fill="rgba(255, 255, 255, 0.28)" mask="url(#{id}u)" />
    <rect x="180" y="0" width="260" height="280" fill="rgba(0, 0, 0, 0.22)" mask="url(#{id}d)" />
    {#each D as d (d)}<path {d} fill="rgba(255, 255, 255, 0.13)" />{/each}
  {:else}
    {#each D as d (d)}<path {d} fill="white" />{/each}
  {/if}
</svg>

<style>
  svg { display: block; width: 100%; height: 100%; }
</style>
