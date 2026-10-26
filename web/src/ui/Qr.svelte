<script lang="ts" module>
  type Code = { text: string; n: number; dots: string; eyes: number[][]; hole: number };
  const made = new Map<string, Code>(); // the same link is the same code: encoded once per launch
</script>

<script lang="ts">
  // A real, styled QR: round dots, rounded ink eyes and a clear square in the middle for the organizer's
  // mark (the owner picked this look from four). Error correction Q (25 %) keeps it readable with the middle
  // (≤ 11 % of the modules) covered; H made the badge's link a busy 41×41, Q draws it 37×37 with bigger dots that also
  // read from further away (checked with zbarimg). All dots are one path: a single DOM node.
  import qrcode from 'qrcode-generator';
  import type { Snippet } from 'svelte';

  // tone: two dark colours for a gradient across the code (both keep ≥ 7:1 against the white plate); lazy: a code that
  // isn't encoded yet comes when the page is idle (the profile card's: encoding held up the tab's first frame)
  let { text, tone, lazy = false, children }: { text: string; tone?: [string, string]; lazy?: boolean; children?: Snippet } = $props();
  const gid = 'qrg' + Math.random().toString(36).slice(2, 8); // gradient ids are page-global

  function make(text: string): Code {
    const had = made.get(text);
    if (had) return had;
    const q = qrcode(0, 'Q');
    q.addData(text, /^[0-9A-Z $%*+\-./:]*$/.test(text) ? 'Alphanumeric' : 'Byte');
    q.make();
    const n = q.getModuleCount(), mid = Math.floor(n / 2), h = n > 29 ? 4 : 3;
    const eye = (x: number, y: number) => (x < 8 && y < 8) || (x >= n - 8 && y < 8) || (x < 8 && y >= n - 8);
    let dots = '';
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
      if (!q.isDark(y, x) || eye(x, y) || (Math.abs(x - mid) <= h && Math.abs(y - mid) <= h)) continue;
      dots += `M${x + 0.07} ${y + 0.5}a.43 .43 0 1 0 .86 0a.43 .43 0 1 0 -.86 0`;
    }
    const c = { text, n, dots, eyes: [[0, 0], [n - 7, 0], [0, n - 7]], hole: ((h * 2 + 1) / n) * 100 };
    made.set(text, c);
    return c;
  }
  const now = $derived(lazy && !made.has(text) ? null : make(text));
  let late = $state<Code | null>(null);
  $effect(() => {
    if (now) return;
    const tx = text, idle = window.requestIdleCallback ?? ((f: () => void) => setTimeout(f, 60));
    const h = idle(() => (late = make(tx)), { timeout: 500 });
    return () => (window.cancelIdleCallback ?? clearTimeout)(h);
  });
  const code = $derived(now ?? (late?.text === text ? late : null));
</script>

<div class="qr">
  {#if code}
  <svg viewBox="0 0 {code.n} {code.n}" aria-hidden="true">
    {#if tone}
      <defs><linearGradient id={gid} gradientUnits="userSpaceOnUse" x1="0" y1="0" x2={code.n} y2={code.n}>
        <stop offset="0" stop-color={tone[0]} /><stop offset="1" stop-color={tone[1]} /></linearGradient></defs>
    {/if}
    <g fill={tone ? `url(#${gid})` : '#0A0F24'}>
      <path d={code.dots} />
      {#each code.eyes as [x, y] (x * 1000 + y)}
        <rect x={x + 0.5} y={y + 0.5} width="6" height="6" rx="2.2" fill="none" stroke={tone ? `url(#${gid})` : '#0A0F24'} stroke-width="1" />
        <rect x={x + 2} y={y + 2} width="3" height="3" rx="1.1" />
      {/each}
    </g>
  </svg>
  {#if children}<div class="mid" style="width:{code.hole}%;height:{code.hole}%">{@render children()}</div>{/if}
  {/if}
</div>

<style>
  .qr { position: relative; width: 100%; aspect-ratio: 1; }
  svg { width: 100%; height: 100%; }
  .mid { position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%); padding: 4%; display: flex; }
</style>
