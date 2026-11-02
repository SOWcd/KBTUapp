<script lang="ts">
  // A frame drawn over a photo on the lanyard (flowers, space, ...), picked apart from the lanyard so any two combine
  // (owner, Nov 2). Each is an SVG whose 0..100 box is the photo, drawn 25% past it on every side; the parent is the
  // photo's positioned box. Never on small avatars in lists: there it would cover the face.
  let { id }: { id: string | null | undefined } = $props();
</script>

{#if id}<img class="frame" src="frames/{id}.svg" alt="" aria-hidden="true" draggable="false" />{/if}

<style>
  .frame { position: absolute; inset: -25%; width: 150%; height: 150%; max-width: none; z-index: 2; pointer-events: none; user-select: none; -webkit-user-select: none; }
</style>
