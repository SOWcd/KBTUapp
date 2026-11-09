<script lang="ts">
  // The search at the top of a tab, the Telegram/iOS way: it scrolls with the page, sticks under the capsule, slides away
  // as the list goes on and comes back the moment the list is pulled down. Stays put while it's in use. Goes directly in
  // a tab's .scroll page (the sticky top counts from that page's padding edge).
  import SearchField from './SearchField.svelte';

  let { value = $bindable(''), placeholder }: { value?: string; placeholder: string } = $props();
  let stuck = $state(false), away = $state(false);

  function track(sent: HTMLElement) {
    const page = sent.closest('.scroll');
    if (!page) return;
    let line = 0, last = page.scrollTop, run = 0; // run: how far the list has gone in one direction
    const onscroll = () => {
      line ||= Math.round((document.querySelector('.cap.glass')?.getBoundingClientRect().bottom ?? 46) + 8);
      const d = page.scrollTop - last;
      last = page.scrollTop;
      run = d * run > 0 ? run + d : d;
      stuck = sent.getBoundingClientRect().top < line;
      if (!stuck || value || sent.nextElementSibling?.contains(document.activeElement)) away = false;
      else if (run > 24) away = true;
      else if (run < -8) away = false;
    };
    page.addEventListener('scroll', onscroll, { passive: true });
    return () => page.removeEventListener('scroll', onscroll);
  }
</script>

<i class="sent" {@attach track} aria-hidden="true"></i>
<div class={['find', { stuck, away }]} inert={away}><SearchField bind:value {placeholder} /></div>

<style>
  .sent { display: block; height: 0; }
  .find { position: sticky; top: calc(var(--head-bottom) + var(--s-2) - var(--page-top)); z-index: var(--z-sticky); margin: var(--s-6) calc(-1 * var(--gutter)) 0;
    padding: 0 var(--gutter) var(--s-2); background: var(--bg); transition: translate 280ms var(--ease); }
  .sent:first-child + .find { margin-top: var(--s-1); }
  /* stuck: the bar's ground reaches up to the capsule, so no row shows between them */
  .find::before { content: ''; position: absolute; left: 0; right: 0; bottom: 100%; height: calc(var(--head-bottom) + var(--s-2)); background: var(--bg);
    opacity: 0; transition: opacity var(--t-fast) var(--ease); pointer-events: none; }
  .find.stuck::before { opacity: 1; }
  .find.stuck { box-shadow: 0 0.5px 0 var(--separator); }
  /* translate, not transform: the page's stagger animates transform */
  .find.away { translate: 0 calc(-100% - var(--head-bottom) - var(--s-2)); box-shadow: none; }
</style>
