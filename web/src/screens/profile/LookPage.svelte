<script lang="ts">
  // The lanyard's editor: Settings' first row opens it in place under my badge (Me), the lanyards and frames in rows
  // that swipe sideways. A tap puts it on the badge above at once as a draft (ui.look); Me's check saves it, Back drops it.
  import Lock from '@lucide/svelte/icons/lock';
  import { onDestroy } from 'svelte';
  import { session } from '../../lib/state/session.svelte';
  import { ui } from '../../lib/state/ui.svelte';
  import { lookData } from '../../lib/state/looks.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { banded, clubLook, lookVars, type Look } from '../../lib/awards';
  // each lanyard's card art at the swatch's size, one small picture (tools/scene-rasters.mjs draws them from LanyardBand)
  const MINI = import.meta.glob('../../assets/lanyards/minis/*.webp', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;

  const me = $derived(session.me);
  const L = $derived(lookData());
  const frame = $derived(ui.look ? ui.look.frame : me?.frame ?? null);
  onDestroy(() => { ui.tryOn = null; });

  const pickSkin = (id: number | 'sower' | null) => { if (ui.look) ui.look = { ...ui.look, skin: id }; };
  const pickFrame = (f: string | null) => { if (ui.look) ui.look = { ...ui.look, frame: f }; };
  const FRAMES = [null, 'flowers', 'space', 'hearts', 'sparkles', 'laurel', 'leaves', 'snow', 'notes', 'neon', 'blossom', 'gold'] as const;
</script>

{#if me}
  <div class="looks">
    {#if L.skins.length || me.founder}
      <!-- each lanyard drawn small, as it hangs above (names alone said nothing; with many clubs the row scrolls) -->
      {#each L.rows as [label, ks], r (label)}
        <h3 class="sub" class:first={r === 0}>{t(label)}</h3>
        <div class="skins" role="radiogroup" aria-label={t(label)}>
          {#each ks as k (k.id ?? 'kbtu')}
            <button class="ly {k.kind}" class:club={!!clubLook(k.kind as Look)} style={lookVars(k.kind as Look)} role="radio" aria-checked={L.worn === k.id} class:on={L.worn === k.id} class:locked={'locked' in k && k.locked}
                    onclick={() => { haptic.select(); if ('locked' in k && k.locked) ui.tryOn = { id: k.id as number, name: k.name, school: L.kindOf(k) === 'school' }; else { ui.tryOn = null; pickSkin(k.id); } }}>
              <span class="st"><i>{k.word}</i></span><span class="cl"></span>
              <!-- a scene for mine only: every club's full scene at once (20+) left the whole list unpainted on iPhones (Nov 2);
                   now a picture each (perf round 3), the locked ones keep their plain colours as before -->
              <span class="cd">{#if banded(k.kind as Look) && !('locked' in k && k.locked)}<img class="mini" src={MINI[`../../assets/lanyards/minis/${k.kind}.webp`]} alt="" loading="lazy" decoding="async" />{/if}<span class="ph"></span><span class="ln"></span><span class="ln s"></span><span class="hl"></span></span>
              {#if 'locked' in k && k.locked}<span class="lk"><Lock size={12} strokeWidth={2.4} /></span>{/if}
              <b>{k.name}</b>
            </button>
          {/each}
        </div>
      {/each}
    {/if}
    <!-- a frame over the photo, apart from the lanyard: any frame with any lanyard (owner, Nov 2) -->
    <h3 class="sub">{t('look.frame')}</h3>
    <div class="frames" role="radiogroup" aria-label={t('look.frame')}>
      {#each FRAMES as f (f ?? 'none')}
        <button class="fr" role="radio" aria-checked={frame === f} class:on={frame === f} onclick={() => { haptic.select(); pickFrame(f); }}>
          <span class="fb"><span class="fp"></span>{#if f}<img src="frames/{f}.svg" alt="" draggable="false" />{/if}</span>
          <b class="ellipsis">{t(f ? `look.frame.${f}` : 'look.frameNone')}</b>
        </button>
      {/each}
    </div>
  </div>
{/if}

<style>
  /* the lanyards, small: strap, clip and card in each one's colours (Hero.svelte's, scaled down); bleeds to the edges */
  .sub { margin: var(--s-2) 0 var(--s-1); font: 600 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); text-transform: uppercase; letter-spacing: 0.04em; }
  .sub.first { margin-top: 0; }
  .skins { display: flex; gap: 10px; overflow-x: auto; margin: 0 calc(-1 * var(--gutter)) 8px; padding: 4px var(--gutter) 6px; scrollbar-width: none; }
  .skins::-webkit-scrollbar { display: none; }
  .frames { display: flex; gap: 10px; overflow-x: auto; margin: 0 calc(-1 * var(--gutter)) 8px; padding: 4px var(--gutter) 6px; scrollbar-width: none; }
  .frames::-webkit-scrollbar { display: none; }
  .fr { flex: none; display: flex; flex-direction: column; align-items: center; gap: 6px; width: 76px; color: var(--text-2); }
  .fr b { max-width: 100%; font: 600 var(--fs-cap)/1.2 var(--font-text); }
  .fb { position: relative; display: grid; place-items: center; width: 76px; height: 76px; border-radius: var(--r-l); background: var(--surface-2); box-shadow: inset 0 0 0 1px var(--line); overflow: hidden; }
  .fp { width: 40px; height: 40px; border-radius: var(--r-s); background: var(--grad-accent); opacity: 0.55; }
  .fb img { position: absolute; left: 8px; top: 8px; width: 60px; height: 60px; }
  .fr.on .fb { box-shadow: inset 0 0 0 2px var(--accent); }
  .fr.on b { color: var(--text); }
  .ly { flex: none; width: 92px; display: flex; flex-direction: column; align-items: center; padding: 8px 6px 8px; border-radius: 16px; background: var(--surface);
    box-shadow: inset 0 0 0 2px transparent; transition: box-shadow var(--t-fast), transform var(--t-fast) var(--ease); }
  .ly:active { transform: scale(0.95); }
  .ly.on { box-shadow: inset 0 0 0 2px var(--accent); }
  /* someone else's club: seen, not worn; a small lock on the card's corner */
  .ly { position: relative; }
  .ly.locked .st, .ly.locked .cl, .ly.locked .cd { opacity: 0.45; filter: saturate(0.4); }
  .ly .lk { position: absolute; top: 6px; right: 6px; width: 22px; height: 22px; border-radius: 50%; display: grid; place-items: center; background: var(--text); color: var(--bg); }
  .ly .st { width: 12px; height: 26px; display: flex; justify-content: center; overflow: hidden; background: linear-gradient(90deg, #1B36A0, #3B6BFF 50%, #1B36A0); }
  .ly .st i { writing-mode: vertical-rl; transform: rotate(180deg); font: 800 4.5px/12px var(--font-text); font-style: normal; letter-spacing: 0.2em; color: rgba(255, 255, 255, 0.85); white-space: nowrap; }
  .ly .cl { width: 18px; height: 7px; margin-bottom: -4px; z-index: 1; border-radius: 3px; background: linear-gradient(180deg, #F4F6FB, #9AA4B8); }
  .ly .cd { position: relative; width: 74px; height: 48px; padding: 9px 7px 6px; border-radius: 9px; display: grid; grid-template-columns: 16px 1fr; grid-template-rows: 6px 6px 1fr; gap: 3px 5px; overflow: hidden;
    background: radial-gradient(110% 90% at 0% 0%, rgba(124, 77, 255, 0.6), transparent 55%), linear-gradient(155deg, #2A4FD6, #121A3D 72%); }
  .ly .ph { grid-row: 1 / 3; width: 16px; height: 16px; border-radius: 5px; background: rgba(255, 255, 255, 0.85); }
  .ly .ln { height: 4px; border-radius: 2px; background: rgba(255, 255, 255, 0.85); }
  .ly .ln.s { width: 60%; opacity: 0.6; }
  .ly .hl { grid-column: 1 / 3; align-self: end; height: 7px; border-radius: 3px; background: linear-gradient(100deg, #FFA6DA, #B9A3FF, #86E3FF, #A6FFD6, #FFE69A); }
  .ly b { max-width: 100%; margin-top: 7px; font: 620 12px/1.2 var(--font-text); text-align: center; overflow-wrap: anywhere; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; }  /* whole names on two lines (owner: "Big City Lig..." cut) */
  .ly .ph { z-index: 1; }
  .ly .ln, .ly .hl { position: relative; z-index: 1; }
  /* the club's real card art, the profile's (LanyardBand wide) shrunk to the swatch, still and flat: its picture */
  .mini { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
  .ly.studex .st { background: linear-gradient(90deg, #A9271E, #CF3428 50%, #A9271E); }
  .ly.studex .hl { background: #fff; }
  .ly.cheer .st { background: linear-gradient(90deg, rgb(20, 22, 44), rgb(46, 50, 88) 50%, rgb(20, 22, 44)); }
  .ly.cheer .hl { background: linear-gradient(100deg, rgb(196, 154, 64), rgb(236, 204, 128), rgb(190, 148, 60)); }
  .ly.knights .st { background: linear-gradient(90deg, #163E7C, #2F6BD0 50%, #163E7C); }
  .ly.knights .hl { background: linear-gradient(90deg, #1C4C94, #2F6BD0); box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.35); }
  .ly.moments .st { background: linear-gradient(90deg, #7A321F, #B5603F 50%, #7A321F); }
  .ly.moments .st i { color: #F4D9BE; }
  .ly.moments .hl { background: linear-gradient(100deg, #F2DEC8, #E3A985, #C9C391); }
  .ly.faces .st { background: linear-gradient(90deg, rgba(0, 0, 0, 0.3), transparent 35% 65%, rgba(0, 0, 0, 0.3)), linear-gradient(180deg, #6E7BFF, #C04BFF 55%, #FF4F9A); } /* shaded round like the others */
  .ly.faces .hl { background: linear-gradient(100deg, #6E7BFF, #C04BFF, #FF4F9A, #FFA43D); }
  .ly.sower .st { background: linear-gradient(90deg, #CECECA, #F6F6F4 50%, #CECECA); }
  .ly.sower .st i { color: #1E1E1E; }
  .ly.sower .cd { background: radial-gradient(90% 120% at 100% 0%, #5E5E5D, #2E2E2E 62%); }
  .ly.sower .cd::before { content: ''; position: absolute; right: -30px; top: -30px; width: 76px; height: 76px; border-radius: 50%;
    background: radial-gradient(circle, rgba(232, 232, 231, 0.3) 1px, transparent 1.5px) 0 0 / 5px 5px; } /* his photo's halftone */
  .ly.sower .hl { background: #E8E8E7; }
  .ly.locked .cd { background: linear-gradient(135deg, var(--c1, rgb(58, 66, 110)), var(--c2, rgb(22, 26, 48))); }
  .ly.club .st { background: linear-gradient(90deg, var(--s1), var(--s2) 50%, var(--s1)); }
  .ly.club .st i { color: var(--s3); font-size: calc(var(--sf) * 0.6); font-weight: var(--sfw); letter-spacing: var(--sl); line-height: calc(var(--slh) * 0.6); white-space: pre; text-align: center; }
  .ly.club .hl { background: linear-gradient(100deg, var(--h1), var(--h2)); }
</style>
