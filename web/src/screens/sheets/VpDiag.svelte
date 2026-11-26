<script lang="ts">
  // ponytail: a throwaway diagnostic (deep link startapp=vp) to measure the Android bottom inset before fixing the
  // tab bar (owner, Nov 27); delete it with the fix.
  import { onMount } from 'svelte';
  import { close } from '../../lib/state/ui.svelte';
  import { tgTry } from '../../lib/tg';

  let { overlay }: { overlay: number } = $props();
  let probeEnv = $state<HTMLDivElement>(), probeSafe = $state<HTMLDivElement>(), probeTg = $state<HTMLDivElement>();
  let lines = $state<string[]>([]);

  function read() {
    const out: string[] = [];
    const j = (v: unknown) => JSON.stringify(v);
    tgTry((w) => {
      const x = w as unknown as Record<string, unknown>;
      for (const k of ['platform', 'version', 'isFullscreen', 'isExpanded', 'viewportHeight', 'viewportStableHeight', 'safeAreaInset', 'contentSafeAreaInset'])
        out.push(`${k}: ${j(x[k])}`);
    });
    if (!out.length) out.push('Telegram.WebApp: none');
    const css = getComputedStyle(document.documentElement);
    for (const v of ['--tg-safe-area-inset-bottom', '--tg-content-safe-area-inset-bottom', '--tg-viewport-height', '--tg-viewport-stable-height'])
      out.push(`${v}: ${css.getPropertyValue(v).trim() || '-'}`);
    out.push(`env(safe-area-inset-bottom): ${probeEnv?.offsetHeight ?? '?'}px`);
    out.push(`--safe-bottom (computed): ${probeSafe?.offsetHeight ?? '?'}px`);
    out.push(`--tg-safe-area-inset-bottom (resolved): ${probeTg?.offsetHeight ?? '?'}px`);
    out.push(`innerHeight: ${innerHeight}, innerWidth: ${innerWidth}`);
    out.push(`visualViewport: ${visualViewport ? `${Math.round(visualViewport.height)} (offsetTop ${Math.round(visualViewport.offsetTop)})` : '-'}`);
    out.push(`documentElement.clientHeight: ${document.documentElement.clientHeight}`);
    out.push(`screen: ${screen.width}x${screen.height}, avail ${screen.availHeight}, dpr ${devicePixelRatio}`);
    const dock = document.querySelector('.dock')?.getBoundingClientRect();
    out.push(`.dock rect: ${dock ? `top ${Math.round(dock.top)}, bottom ${Math.round(dock.bottom)}` : '-'}`);
    out.push(`ua: ${navigator.userAgent}`);
    lines = out;
  }

  onMount(() => {
    read();
    const t = setInterval(read, 1000); // live: rotate, expand, the keyboard
    return () => clearInterval(t);
  });
</script>

<div class="probe" style="height: env(safe-area-inset-bottom, 0px)" bind:this={probeEnv}></div>
<div class="probe" style="height: var(--safe-bottom)" bind:this={probeSafe}></div>
<div class="probe" style="height: var(--tg-safe-area-inset-bottom, 0px)" bind:this={probeTg}></div>
<button class="panel" type="button" onclick={() => close(overlay)}>
  {#each lines as l, i (i)}<span>{l}</span>{/each}
  <span class="hint">tap to close</span>
</button>
<div class="line"></div>

<style>
  .probe { position: fixed; left: 0; top: 0; width: 1px; visibility: hidden; pointer-events: none; }
  .panel { position: fixed; z-index: 9999; left: 8px; right: 8px; top: 30%; padding: 10px; border: 0; border-radius: var(--r-s); text-align: left;
    background: rgb(0 0 0 / 0.82); color: white; font: var(--fs-micro)/1.35 ui-monospace, monospace; word-break: break-all; }
  .panel span { display: block; }
  .hint { margin-top: 6px; opacity: 0.6; }
  .line { position: fixed; z-index: 10000; left: 0; right: 0; bottom: 0; height: 6px; background: lime; pointer-events: none; }
</style>
