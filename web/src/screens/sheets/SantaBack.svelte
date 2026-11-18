<script lang="ts">
  // Secret Santa's card, its sealed side: the same drawing small on the event's page and large in the reveal
  // (SantaReveal), so the one flies out of the other. Every size is a share of the width.
  import Gift from '@lucide/svelte/icons/gift';
  let { w }: { w: number } = $props();
</script>

<span class="back" style:--w="{w}px"><span class="seal"><Gift size={w * 0.17} strokeWidth={2} /></span></span>

<style>
  .back { position: relative; display: grid; place-items: center; width: var(--w); aspect-ratio: 3 / 4; border-radius: calc(var(--w) * 0.11);
    background: linear-gradient(155deg, #E5414F, #C01F36 55%, #94122A); color: #7A1022;
    box-shadow: inset 0 0 0 0.5px rgba(255, 255, 255, 0.22); }
  /* the gold hairline a card's edge has */
  .back::before { content: ''; position: absolute; inset: calc(var(--w) * 0.055); border-radius: calc(var(--w) * 0.07); border: max(1px, calc(var(--w) * 0.006)) solid rgba(255, 221, 150, 0.5); }
  .seal { position: relative; display: grid; place-items: center; width: 36%; aspect-ratio: 1; border-radius: 50%;
    background: linear-gradient(150deg, #FBE3A6, #E2B052 70%, #C99236); box-shadow: 0 calc(var(--w) * 0.012) calc(var(--w) * 0.04) rgba(60, 0, 12, 0.35), inset 0 0 0 0.5px rgba(255, 255, 255, 0.5); }
</style>
