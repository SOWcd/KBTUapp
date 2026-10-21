<script lang="ts">
  // The unlock moment (SPEC §4.11): a new achievement level, celebrated once. The medal drops in and lands with a glow in
  // its tier's colour, the confetti flies from it; its name, tier, what it took and how rare it is. Share sends our bot's
  // card (aw_<code>), "Great!" closes; the next new level, if any, comes after.
  import { onMount } from 'svelte';
  import Trophy from '@lucide/svelte/icons/trophy';
  import type { Achievement } from '../../lib/api';
  import { close, removeOverlay, hideChrome, say, type Overlay } from '../../lib/state/ui.svelte';
  import { phrase } from '../../lib/state/data.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { achName, tierName } from '../../lib/awards';
  import { haptic, shareCard } from '../../lib/tg';
  import { burst } from '../../ui/burst';
  import { glass } from '../../ui/glass';
  import Medal from '../../ui/Medal.svelte';

  let { overlay, a, ondone }: { overlay: Overlay; a: Achievement; ondone?: () => void } = $props();
  const GLOW = ['#7C4DFF', '#E0A06A', '#C8D2E6', '#FFD45E', '#B07CFF']; // one-level, bronze, silver, gold, legend
  const glow = $derived(a.levels.length > 1 ? GLOW[Math.min(a.level, 4)] : GLOW[0]);
  const tier = $derived(a.levels.length > 1 ? tierName(a) : '');
  const rare = $derived.by(() => { const x = a.levels[Math.max(0, a.level - 1)]?.rarity ?? a.rarity; return x > 0 && x < 0.01 ? '<1' : String(Math.round(x * 100)); });
  $effect(() => { overlay.title = t('unlock.kicker'); overlay.icon = Trophy; });

  let scrim: HTMLDivElement;
  let wrap: HTMLDivElement;
  let medal: HTMLSpanElement;
  let gone = false;
  onMount(() => {
    haptic.soft();
    scrim.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 320, easing: 'ease-out' });
    for (const [i, el] of [...wrap.querySelectorAll('.up')].entries())
      el.animate([{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }], { duration: 420, delay: 520 + i * 70, easing: 'cubic-bezier(.2,.9,.25,1)', fill: 'backwards' });
    medal.animate([{ transform: 'translateY(-55vh) scale(0.45) rotate(-35deg)', opacity: 0 }, { transform: 'translateY(0) scale(1.14) rotate(6deg)', opacity: 1, offset: 0.68 },
      { transform: 'none' }], { duration: 880, easing: 'cubic-bezier(.2,.9,.25,1)' });
    const land = setTimeout(() => { const r = medal.getBoundingClientRect(); haptic.ok(); burst(false, { x: r.left + r.width / 2, y: r.top + r.height / 2 }); }, 600);
    const off = hideChrome();
    return () => { clearTimeout(land); off(); };
  });
  function leave() {
    if (gone) return;
    gone = true;
    wrap.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(0.96)' }], { duration: 220, easing: 'ease-in', fill: 'forwards' });
    const x = scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 240, easing: 'ease-in', fill: 'forwards' });
    x.onfinish = () => { removeOverlay(overlay.id); ondone?.(); };
  }
  $effect(() => { if (overlay.closing) leave(); });

  let sharing = $state(false);
  async function share() {
    sharing = true; haptic.tap();
    try { if (await shareCard({ kind: 'aw', code: a.code }, 'https://t.me/KBTUappBot?startapp=aw_' + a.code, t('aw.shareText', { name: achName(a) }))) say(phrase('say.shared'), 'party_popper_3d'); }
    catch { haptic.error(); say(t('common.error'), 'pleading_face_3d'); }
    finally { sharing = false; }
  }
</script>

<div class="scrim" bind:this={scrim} style="--glow:{glow}" onclick={() => close(overlay.id)} role="presentation"></div>
<div class="wrap" bind:this={wrap} style="--glow:{glow}">
  <p class="kicker up">{t('unlock.kicker')}</p>
  <span class="medal" bind:this={medal}><Medal {a} size={168} /><span class="shine"></span></span>
  <h2 class="name up">{achName(a)}</h2>
  {#if tier}<p class="tier up">{t('aw.level', { tier })}</p>{/if}
  <p class="how up">{t(`ach.${a.code}.how` as 'ach.regular.how')}</p>
  <p class="rare up">{t('person.rarity', { p: rare })}</p>
  <div class="acts up">
    <button class="pill glass glass-pill main" use:glass disabled={sharing} onclick={share}>{t('aw.share')}</button>
    <button class="pill glass glass-pill" use:glass onclick={() => close(overlay.id)}>{t('unlock.ok')}</button>
  </div>
</div>

<style>
  .scrim { position: absolute; inset: 0; z-index: var(--z-sheet);
    background: radial-gradient(60% 40% at 50% 38%, color-mix(in srgb, var(--glow) 45%, transparent), transparent 70%), rgba(3, 4, 10, 0.86);
    -webkit-backdrop-filter: blur(16px); backdrop-filter: blur(16px); }
  :global(html.lowfx) .scrim { -webkit-backdrop-filter: none; backdrop-filter: none; background: radial-gradient(60% 40% at 50% 38%, color-mix(in srgb, var(--glow) 45%, transparent), transparent 70%), rgba(3, 4, 10, 0.95); }
  .wrap { position: absolute; inset: 0; z-index: var(--z-sheet); pointer-events: none; display: flex; flex-direction: column; align-items: center; justify-content: center;
    gap: 8px; padding: calc(var(--top) + 8px) 28px calc(var(--safe-bottom) + 20px); color: #fff; text-align: center; }
  .wrap > * { pointer-events: auto; }
  .kicker { font: 700 13px/1 var(--font-text); letter-spacing: 0.14em; text-transform: uppercase; color: color-mix(in srgb, var(--glow) 70%, #fff); }
  .medal { position: relative; display: inline-flex; margin: 14px 0 10px; border-radius: 50%;
    filter: drop-shadow(0 0 34px color-mix(in srgb, var(--glow) 70%, transparent)) drop-shadow(0 20px 30px rgba(0, 0, 0, 0.5)); }
  .shine { position: absolute; inset: 0; border-radius: 50%; pointer-events: none; mix-blend-mode: soft-light; overflow: hidden; }
  .shine::after { content: ''; position: absolute; inset: -30%; background: linear-gradient(115deg, transparent 38%, rgba(255, 255, 255, 0.85) 50%, transparent 62%);
    transform: translateX(-120%); animation: sweep 2.6s 1.1s ease-in-out infinite; }
  @keyframes sweep { 55%, 100% { transform: translateX(120%); } }
  .name { font: 800 30px/1.1 var(--font-display); letter-spacing: -0.03em; }
  .tier { font: 650 15px/1.2 var(--font-text); color: color-mix(in srgb, var(--glow) 65%, #fff); }
  .how { max-width: 320px; margin-top: 6px; font: 500 15px/1.4 var(--font-text); color: rgba(255, 255, 255, 0.78); text-wrap: balance; }
  .rare { font: 600 13px/1.3 var(--font-text); color: rgba(255, 255, 255, 0.55); }
  .acts { display: flex; gap: 10px; margin-top: 22px; }
  .pill { position: relative; height: 48px; padding: 0 26px; border-radius: var(--r-full); color: #fff; font: 680 16px/1 var(--font-text); background-color: rgba(255, 255, 255, 0.12); }
  .pill.main { background-color: color-mix(in srgb, var(--glow) 55%, rgba(255, 255, 255, 0.1)); }
  .pill:active { transform: scale(0.96); }
  @media (prefers-reduced-motion: reduce) { .shine::after { animation: none; } }
  :global(html.lowfx) .shine::after { animation: none; } /* power saving: a sweep under a blend mode */
</style>
