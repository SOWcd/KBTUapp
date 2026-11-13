<script lang="ts" module>
  type Code = { text: string; n: number; dots: string; eyes: number[][]; hole: number };
  const made = new Map<string, Code>(); // the same link is the same code: encoded once per launch
</script>

<script lang="ts">
  // A real, styled QR: round dots, rounded ink eyes and a clear square in the middle for the organizer's
  // mark (the owner picked this look from four). Error correction Q (25 %) keeps it readable with the middle
  // (≤ 11 % of the modules) covered; H made the badge's link a busy 41×41, Q draws it 37×37 with bigger dots that also
  // read from further away (checked with zbarimg). All dots are one path: a single DOM node.
  import type { Snippet } from 'svelte';
  import { qr, loadQr } from '../lib/qr.svelte';

  // tone: two dark colours for a gradient across the code (both keep ≥ 7:1 against the white plate); lazy: a code that
  // isn't encoded yet comes when the page is idle (the profile card's: encoding held up the tab's first frame);
  // minVersion: a short text drawn as a bigger, finer code (the ticket's 10 characters: 33×33, as dense as the badge's,
  // not a coarse 21×21; read by zbarimg with the middle covered), a text too long for it takes the size it needs
  let { text, tone, lazy = false, minVersion = 0, children }: { text: string; tone?: [string, string]; lazy?: boolean; minVersion?: number; children?: Snippet } = $props();
  const gid = 'qrg' + Math.random().toString(36).slice(2, 8); // gradient ids are page-global

  function encode(text: string, v: number) {
    const q = qr.enc!(v as Parameters<NonNullable<typeof qr.enc>>[0], 'Q');
    q.addData(text, /^[0-9A-Z $%*+\-./:]*$/.test(text) ? 'Alphanumeric' : 'Byte');
    q.make(); // throws when the text doesn't fit version v
    return q;
  }
  function make(text: string, minV: number): Code {
    const key = minV + ':' + text, had = made.get(key);
    if (had) return had;
    let q;
    try { q = encode(text, minV); } catch { q = encode(text, 0); }
    // the middle's size follows the code's: a ticket's short code is a 21×21, where a 7×7 hole lost too much to read
    // (zbarimg: none of five tickets read, all with 5×5; owner, Nov 3)
    const n = q.getModuleCount(), mid = Math.floor(n / 2), h = n > 29 ? 4 : n > 21 ? 3 : 2;
    const eye = (x: number, y: number) => (x < 8 && y < 8) || (x >= n - 8 && y < 8) || (x < 8 && y >= n - 8);
    let dots = '';
    for (let y = 0; y < n; y++) for (let x = 0; x < n; x++) {
      if (!q.isDark(y, x) || eye(x, y) || (Math.abs(x - mid) <= h && Math.abs(y - mid) <= h)) continue;
      dots += `M${x + 0.07} ${y + 0.5}a.43 .43 0 1 0 .86 0a.43 .43 0 1 0 -.86 0`;
    }
    const c = { text, n, dots, eyes: [[0, 0], [n - 7, 0], [0, n - 7]], hole: ((h * 2 + 1) / n) * 100 };
    made.set(key, c);
    return c;
  }
  // (a code shown at once has the encoder already: its screen imports lib/qrnow.ts)
  const now = $derived((lazy && !made.has(minVersion + ':' + text)) || !qr.enc ? null : make(text, minVersion));
  let late = $state<Code | null>(null);
  $effect(() => {
    if (now) return;
    if (!lazy) { void loadQr().catch(() => {}); return; }
    const tx = text, mv = minVersion, idle = window.requestIdleCallback ?? ((f: () => void) => setTimeout(f, 60));
    const h = idle(() => void loadQr().then(() => (late = make(tx, mv))).catch(() => {}), { timeout: 500 });
    return () => (window.cancelIdleCallback ?? clearTimeout)(h);
  });
  // a new text (a rotating check-in code) keeps the last code drawn until its own is ready: never a blank frame
  let last: Code | null = null;
  const code = $derived((last = now ?? (late?.text === text ? late : null) ?? last));
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
