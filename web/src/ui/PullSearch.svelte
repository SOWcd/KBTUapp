<script lang="ts" module>
  /** How far a tab's page starts scrolled: the field's height and its gap. A tab's own "at the top" counts from here. */
  export const PULL = 56;
</script>

<script lang="ts">
  // A tab's search, hidden until the list is pulled down, the Telegram/iOS way: the field is the page's first child and
  // the page opens scrolled just past it, so the pull is the browser's own scroll, no touch handling. Stopped halfway, it
  // settles open or shut. Goes directly in a tab's .scroll page (position: absolute).
  import SearchField from './SearchField.svelte';

  let { value = $bindable(''), placeholder }: { value?: string; placeholder: string } = $props();
  let seen = $state(0); // fades in with the pull: shut, it would show under the capsule and Telegram's buttons

  function track(field: HTMLElement) {
    const page = field.closest('.scroll');
    if (!page) return;
    let touching = false, timer: ReturnType<typeof setTimeout> | undefined;
    // set in the next frame's own layout, not here mid-mount: written now it laid out the half-built tab once more
    // inside the start's first task (perf, Nov 10: ~85 ms at 4x CPU on the Afisha); the frame isn't painted before it
    const raf = requestAnimationFrame(() => { if (!page.scrollTop) page.scrollTop = PULL; }); // unless scrolled since
    // a tab built while away has no layout yet: shut it the first time it is on screen
    const io = new IntersectionObserver(([e]) => { if (!e.isIntersecting) return; io.disconnect(); if (!value) page.scrollTop = PULL; });
    io.observe(field);
    const settle = () => {
      const y = page.scrollTop;
      if (!touching && y > 0 && y < PULL) page.scrollTo({ top: y < PULL / 2 ? 0 : PULL, behavior: 'smooth' });
    };
    const later = () => { clearTimeout(timer); timer = setTimeout(settle, 120); };
    const onscroll = () => { seen = Math.max(0, 1 - page.scrollTop / PULL); later(); };
    const down = () => { touching = true; };
    const up = () => { touching = false; later(); };
    page.addEventListener('scroll', onscroll, { passive: true });
    page.addEventListener('touchstart', down, { passive: true });
    page.addEventListener('touchend', up, { passive: true });
    return () => {
      cancelAnimationFrame(raf); io.disconnect(); clearTimeout(timer);
      page.removeEventListener('scroll', onscroll);
      page.removeEventListener('touchstart', down);
      page.removeEventListener('touchend', up);
    };
  }
</script>

<div class="pull" style:opacity={seen} inert={seen === 0} {@attach track}><SearchField bind:value {placeholder} /></div>
<!-- a short list still scrolls by PULL, so the field can hide -->
<i class="hold" aria-hidden="true"></i>

<style>
  .pull { margin-bottom: var(--s-3); }
  .hold { position: absolute; top: 0; left: 0; width: 1px; height: calc(100% + var(--ctl-m) + var(--s-3)); visibility: hidden; pointer-events: none; }
</style>
