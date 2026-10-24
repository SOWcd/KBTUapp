<script lang="ts" module>
  /** a named place on the "Place" side: a hall, the canteen, an entrance */
  export type PadTile = { v: string; label: string; sub?: string; door?: boolean; off?: boolean };
  export type PadCheck = { ok: boolean; hint: string; tone?: 'ok' | 'no' };
  import { t as tr } from '../../lib/i18n/index.svelte';
  import { SPOTS, floorOf, normRoom } from '../../lib/map';
  import uniqRooms from '../../assets/map/uniq-rooms.json';
  const fl = (n: number) => (n ? tr('route.floor', { n }) : tr('route.basement'));
  /** the places people know by name, with where they are */
  export function placeTiles(): PadTile[] {
    return SPOTS.map((s) => { const name = tr(`route.spot.${s.k}` as 'route.spot.canteen'); return { v: name, label: name, sub: s.room ? `${s.room} \u00b7 ${fl(floorOf(s.room) ?? 0)}` : fl(s.f ?? 0) }; });
  }
  // every number the main map prints, for "rooms that start so"
  const ALL = [...new Set((uniqRooms as unknown as Record<string, unknown>[]).flatMap((f) => Object.keys(f)))]
    .sort((a, b) => parseInt(a) - parseInt(b) || a.localeCompare(b));
  // a real room as the example, a new one each time (owner, Oct 24: not always 305)
  const EX = ALL.filter((r) => /^[1-5]\d\d$/.test(r));
  const suggest = (typed: string) => { const q = normRoom(typed); return q.length < 2 ? [] : ALL.filter((r) => r.startsWith(q) && r !== q); };
</script>

<script lang="ts">
  // The map's own keypad (owner, Oct 24, mockup design/mock/map.html): every input on the map is a room number or a
  // named place, so no system keyboard at all (B7: the iOS keyboard jerked the route card). A big number that pops in
  // digit by digit, the rooms that start so under it (five, one row, no scrolling), round keys that flash under the
  // finger, a letter key cycling a-b-v-g (251a); the named places on a second side as tiles, not a sideways row (owner:
  // "scrolling left and right to find one is bad").
  import { untrack } from 'svelte';
  import X from '@lucide/svelte/icons/x';
  import Delete from '@lucide/svelte/icons/delete';
  import MapPin from '@lucide/svelte/icons/map-pin';
  import DoorOpen from '@lucide/svelte/icons/door-open';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';

  let { title, go, point, placeTab, groups, check, onsubmit, onclose, start = '' }: {
    title: string; go: string; point: 'a' | 'b'; placeTab: string; groups: { title?: string; tiles: PadTile[] }[];
    check: (text: string) => PadCheck; onsubmit: (text: string) => void; onclose: () => void; start?: string;
  } = $props();

  const example = EX[Math.floor(Math.random() * EX.length)] ?? '305';
  const LET = ['\u0430', '\u0431', '\u0432', '\u0433']; // a, b, v, g as typed on a door
  let typed = $state(untrack(() => start)), fresh = $state(-1), side = $state<'num' | 'place'>('num'), shook = $state(0);
  const word = $derived(/[^\d\u0430-\u0433]/.test(typed));
  const res = $derived(check(typed));
  const sug = $derived(word || !typed ? [] : suggest(typed).slice(0, 5));
  const letter = $derived(LET.includes(typed.slice(-1)) ? (LET[LET.indexOf(typed.slice(-1)) + 1] ?? '–') : LET[0]);
  const letterOn = $derived(!word && /[\d\u0430-\u0433]$/.test(typed));

  function deny() { haptic.error(); shook++; }
  function key(k: string) {
    if (word) typed = '';
    side = 'num';
    if (k === 'del') { if (!typed) return deny(); typed = typed.slice(0, -1); fresh = -1; }
    else if (k === 'l') { // after a number "a", again "b", "v", "g", then off
      const i = LET.indexOf(typed.slice(-1));
      if (i >= 0) typed = typed.slice(0, -1) + (LET[i + 1] ?? '');
      else if (/\d$/.test(typed)) typed += LET[0];
      else return deny();
      fresh = typed.length - 1;
    } else if (typed.length < 4 && !LET.includes(typed.slice(-1))) { typed += k; fresh = typed.length - 1; }
    else return deny();
    haptic.tap();
  }
  /** a room as typed on the keypad: the maps' Latin a, b, v back to the Cyrillic the letter key shows */
  const asTyped = (r: string) => r.replace(/[abvc]/g, (c) => '\u0430\u0431\u0432\u0441'['abvc'.indexOf(c)]);
  function take(v: string) { haptic.select(); typed = v; fresh = -1; }
  function flip(s: 'num' | 'place') { if (s !== side) { haptic.select(); side = s; } }
  function submit() { if (res.ok) onsubmit(typed); else deny(); }

  // the key under the finger lights at once (pointerdown), not on release
  function press(node: HTMLButtonElement, k: string) {
    const down = () => { node.classList.add('hit'); setTimeout(() => node.classList.remove('hit'), 140); key(k); };
    node.addEventListener('pointerdown', down);
    return { destroy: () => node.removeEventListener('pointerdown', down) };
  }
</script>

<div class="scrim" onclick={onclose} aria-hidden="true"></div>
<!-- the point being set shows by its colour (owner, Oct 24: "which one am I setting now?"): A green, B blue -->
<div class="msheet pt-{point}" data-cover role="dialog" aria-label={title}>
  <span class="grab" aria-hidden="true"></span>
  <div class="head"><h2><span class="pt" aria-hidden="true">{point === 'a' ? t('pad.a') : t('pad.b')}</span>{title}</h2><button class="xb" onclick={onclose} aria-label={t('common.close')}><X size={18} /></button></div>
  <div class="vseg" class:r={side === 'place'} role="tablist">
    <span class="knob" aria-hidden="true"></span>
    <button role="tab" aria-selected={side === 'num'} class:on={side === 'num'} onclick={() => flip('num')}>{t('pad.number')}</button>
    <button role="tab" aria-selected={side === 'place'} class:on={side === 'place'} onclick={() => flip('place')}><MapPin size={16} />{placeTab}</button>
  </div>
  {#key shook}
    <div class="disp" class:word class:shake={shook > 0} role="status">
      {#if !typed}<span class="ph">{example}</span><i class="caret"></i>
      {:else if word}<span>{typed}</span>
      {:else}{#each [...typed] as c, i (i + c)}<span class="d" class:new={i === fresh}>{c}</span>{/each}<i class="caret"></i>{/if}
    </div>
  {/key}
  <p class="hint" class:ok={res.tone === 'ok'} class:no={res.tone === 'no'}>{res.hint}</p>
  {#if side === 'num'}
    <div class="sug">{#each sug as r, i (r)}<button class:on={asTyped(r) === typed} style:animation-delay="{i * 25}ms" onclick={() => take(asTyped(r))}>{asTyped(r)}</button>{/each}</div>
  {/if}
  <div class="body" class:tall={side === 'place'}>
    <div class="pad" class:hide={side !== 'num'} inert={side !== 'num'}>
      {#each ['1', '2', '3', '4', '5', '6', '7', '8', '9'] as k (k)}<button use:press={k}>{k}</button>{/each}
      <button class="x l" class:off={!letterOn} use:press={'l'} aria-label={letter}>{letter}</button>
      <button use:press={'0'}>0</button>
      <button class="x" use:press={'del'} aria-label={t('route.erase')}><Delete size={28} strokeWidth={1.8} /></button>
    </div>
    <div class="tiles" class:hide={side !== 'place'} inert={side !== 'place'}>
      {#each groups as g, gi (gi)}
        {#if g.title}<p class="cap">{g.title}</p>{/if}
        {#each g.tiles as tl (tl.v)}
          <button class="tile" class:door={tl.door} class:off={tl.off} class:on={tl.v === typed} disabled={tl.off} onclick={() => take(tl.v)}>
            <span class="ti">{#if tl.door}<DoorOpen size={18} />{:else}<MapPin size={18} />{/if}</span>
            <span><b>{tl.label}</b>{#if tl.sub}<small>{tl.sub}</small>{/if}</span>
          </button>
        {/each}
      {/each}
    </div>
  </div>
  <button class="go" disabled={!res.ok} onclick={submit}>{go}</button>
</div>

<style>
  .scrim { position: absolute; inset: 0; z-index: 5; background: rgba(2, 3, 8, 0.45); animation: fade 0.4s ease; }
  @keyframes fade { from { opacity: 0; } }
  .msheet { --k: clamp(52px, calc((100dvh - 430px) / 4.6), 72px); --pt: #3b6bff; --pt-text: var(--accent-text);
    position: absolute; z-index: 6; left: 0; right: 0; bottom: 0; padding: 8px 16px calc(var(--safe-bottom) + 14px); border-radius: 36px 36px 0 0;
    background: radial-gradient(120% 50% at 50% 0%, color-mix(in srgb, var(--pt) 22%, transparent), transparent 70%), var(--surface-solid); color: var(--text);
    box-shadow: 0 -20px 60px -20px rgba(0, 0, 0, 0.8), inset 0 1.5px 0 color-mix(in srgb, var(--pt) 70%, transparent);
    animation: rise 0.6s var(--ease-spring); }
  .msheet.pt-a { --pt: #2fc277; --pt-text: var(--success); }
  .head h2 { display: flex; align-items: center; gap: 10px; }
  .pt { width: 30px; height: 30px; border-radius: 50%; display: grid; place-items: center; flex: none; background: var(--pt); color: #fff;
    font: 800 16px/1 var(--font-display); box-shadow: 0 0 0 4px color-mix(in srgb, var(--pt) 25%, transparent), 0 4px 14px color-mix(in srgb, var(--pt) 60%, transparent); }
  @keyframes rise { from { transform: translate3d(0, 105%, 0); } }
  .grab { display: block; width: 38px; height: 5px; border-radius: 3px; background: var(--line-2); margin: 0 auto 8px; }
  .head { display: flex; align-items: center; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
  .head h2 { margin-block: 0; font: 800 24px/1.15 var(--font-display); letter-spacing: -0.01em; }
  .xb { width: 36px; height: 36px; border-radius: 50%; background: var(--surface-2); display: grid; place-items: center; color: var(--text-2); flex: none; }
  .vseg { position: relative; display: flex; padding: 3px; border-radius: 15px; background: var(--surface); }
  .vseg .knob { position: absolute; top: 3px; bottom: 3px; left: 3px; width: calc(50% - 3px); border-radius: 12px; transition: transform 0.5s var(--ease-spring);
    background: linear-gradient(180deg, #fff, #e1e7ff); box-shadow: inset 0 -2px 5px rgba(80, 100, 200, 0.22), inset 0 1px 0 #fff, 0 6px 16px -6px rgba(140, 170, 255, 0.7); }
  .vseg.r .knob { transform: translateX(100%); }
  .vseg button { position: relative; flex: 1; height: 36px; display: flex; align-items: center; justify-content: center; gap: 6px; font: 650 14px/1 var(--font-text); color: var(--text-2); transition: color 0.25s; }
  .vseg button.on { color: #0a0f24; }
  .disp { height: 66px; margin-top: 6px; display: flex; align-items: center; justify-content: center; font: 800 56px/1 var(--font-display); letter-spacing: 0.02em; font-variant-numeric: tabular-nums; }
  .disp.word { font-size: 28px; letter-spacing: -0.01em; }
  .disp .d { display: inline-block; }
  .disp .d.new { animation: pop 0.5s var(--ease-bounce); }
  @keyframes pop { from { transform: translateY(40%) scale(0.5); opacity: 0; filter: blur(6px); } }
  .ph { color: var(--text-3); opacity: 0.45; }
  .caret { width: 3px; height: 48px; border-radius: 2px; margin-left: 4px; background: var(--pt-text); box-shadow: 0 0 10px var(--pt-text); animation: blink 1s steps(2) infinite; }
  @keyframes blink { 50% { opacity: 0; } }
  .disp.shake { animation: shake 0.4s; }
  @keyframes shake { 20%, 60% { transform: translateX(-8px); } 40%, 80% { transform: translateX(8px); } }
  .hint { height: 22px; margin: 0; text-align: center; font: 600 14px/22px var(--font-text); color: var(--text-3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .hint::first-letter { text-transform: uppercase; }
  .hint.ok { color: var(--success); }
  .hint.no { color: var(--danger-text, var(--danger)); }
  .sug { display: grid; grid-template-columns: repeat(5, 1fr); gap: 6px; height: 36px; margin-top: 8px; }
  .sug button { height: 36px; display: grid; place-items: center; border-radius: 18px; background: var(--surface-2); font: 650 15px/1 var(--font-text); animation: chip 0.4s var(--ease-spring) backwards; }
  .sug button.on { background: var(--pt); color: #fff; }
  @keyframes chip { from { opacity: 0; transform: translateY(8px) scale(0.9); } }
  .body { position: relative; height: calc(var(--k) * 4 + 30px); margin-top: 10px; transition: height 0.5s var(--ease-spring); }
  .body.tall { height: calc(var(--k) * 4 + 80px); }
  .body > div { position: absolute; inset: 0; transition: opacity 0.3s, transform 0.5s var(--ease-spring); }
  .body .hide { opacity: 0; pointer-events: none; transform: scale(0.96); }
  .pad { display: grid; grid-template-columns: repeat(3, 1fr); grid-auto-rows: var(--k); align-content: start; gap: 10px; }
  .pad button { width: 100%; height: var(--k); border-radius: calc(var(--k) / 2); display: grid; place-items: center; font: 550 32px/1 var(--font-display); color: var(--text);
    background: radial-gradient(120% 100% at 50% 0%, rgba(255, 255, 255, 0.16), rgba(255, 255, 255, 0.045) 70%);
    box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.22), inset 0 -1px 0 rgba(255, 255, 255, 0.04);
    transition: background 0.45s ease, color 0.45s ease, transform 0.45s var(--ease-bounce); touch-action: manipulation; }
  .pad button:global(.hit) { background: rgba(255, 255, 255, 0.92); color: #0a0f24; transform: scale(0.96); transition-duration: 40ms; }
  .pad button.x { background: none; box-shadow: none; color: var(--text-2); }
  .pad button.x:global(.hit) { background: var(--surface-2); color: var(--text); }
  .pad button.l { font: 650 22px/1 var(--font-text); }
  .pad button.l.off { opacity: 0.25; }
  .tiles { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; align-content: start; overflow-y: auto; scrollbar-width: none; overscroll-behavior: contain; }
  .tiles::-webkit-scrollbar { display: none; }
  .cap { grid-column: 1 / -1; margin: 4px 2px 0; font: 650 12px/1 var(--font-text); color: var(--text-3); text-transform: uppercase; letter-spacing: 0.06em; }
  .tile { min-height: 58px; padding: 8px 12px; border-radius: 18px; background: var(--surface); display: flex; align-items: center; gap: 10px; text-align: left;
    font: 620 13.5px/1.2 var(--font-text); color: var(--text); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.06); }
  .tile b { font-weight: 640; }
  .tile small::first-letter { text-transform: uppercase; }
  .tile small { display: block; margin-top: 2px; color: var(--text-3); font: 500 12px/1.2 var(--font-text); }
  .ti { width: 34px; height: 34px; border-radius: 11px; display: grid; place-items: center; flex: none; background: var(--accent-soft); color: var(--accent-text); }
  .tile.door .ti { background: rgba(63, 214, 138, 0.15); color: var(--success); }
  .tile.off { opacity: 0.4; }
  .tile.off b { text-decoration: line-through; }
  .tile.on { background: var(--pt); color: #fff; }
  .tile.on .ti { background: rgba(255, 255, 255, 0.2); color: #fff; }
  .tile.on small { color: rgba(255, 255, 255, 0.7); }
  .go { width: 100%; height: 56px; margin-top: 10px; border-radius: 28px; display: flex; align-items: center; justify-content: center; font: 750 17px/1 var(--font-text); color: #fff;
    background: linear-gradient(180deg, #5c85ff, #3b6bff 55%, #3457e0); box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.35), 0 10px 24px -8px rgba(59, 107, 255, 0.8);
    transition: opacity 0.25s, filter 0.25s; }
  .pt-a .go { background: linear-gradient(180deg, #55e29c, #2fc277 60%, #22a866); color: #04140b; box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.45), 0 10px 24px -8px rgba(63, 214, 138, 0.7); }
  .go:disabled { opacity: 0.35; filter: saturate(0.4); }
  :global(.theme-light) .pad button:not(.x) { background: radial-gradient(120% 100% at 50% 0%, rgba(11, 20, 51, 0.04), rgba(11, 20, 51, 0.08) 70%); box-shadow: inset 0 0 0 1px rgba(11, 20, 51, 0.06); }
  :global(.theme-light) .pad button:global(.hit) { background: #0b1433; color: #fff; }
  :global(html.lowfx) .caret { animation: none; }
  @media (prefers-reduced-motion: reduce) { .msheet, .disp .d.new, .sug button, .disp.shake { animation: none; } }
</style>
