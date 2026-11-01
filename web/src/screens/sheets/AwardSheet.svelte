<script lang="ts">
  // One award up close (SPEC §4.11), full screen over a dimmed profile (owner, Nov 1: the sheet's top cut the light
  // behind the medal). An achievement: the medal big with the
  // tilt light, what it takes, the way to the next level and how rare every level is; a secret one shows only its
  // hint until earned. A badge: the event it came from. The Creator's seal: what it is, in the words everyone
  // reads, the creator included.
  // Mine and earned: Share sends our bot's card (aw_<code>: the reader sees their own way to it).
  // ponytail: no earned date (nothing records it until the unlock moment ships).
  import { onMount } from 'svelte';
  import Check from '@lucide/svelte/icons/check';
  import { achHow, variantHow, variantName, type ShelfItem } from '../../lib/awards';
  import { removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { t, tn } from '../../lib/i18n/index.svelte';
  import { dayMonth } from '../../lib/time';
  import Share from '@lucide/svelte/icons/share';
  import { haptic, shareCard } from '../../lib/tg';
  import { shareInvite } from '../../lib/friends';
  import { say } from '../../lib/state/ui.svelte';
  import { phrase } from '../../lib/state/data.svelte';
  import { glass, recenter } from '../../ui/glass';
  import CloseX from '../../ui/CloseX.svelte';
  import Award from '../../ui/Award.svelte';
  import { nameOf } from '../../lib/short';
  import { session } from '../../lib/state/session.svelte';
  import Megaphone from '@lucide/svelte/icons/megaphone';
  import Medal from '@lucide/svelte/icons/medal';
  import Crown from '@lucide/svelte/icons/crown';
  import Lightbulb from '@lucide/svelte/icons/lightbulb';
  import BadgeCheck from '@lucide/svelte/icons/badge-check';

  let { overlay, it, mine = false }: { overlay: Overlay; it: ShelfItem; mine?: boolean } = $props();
  let sharing = $state(false);
  async function shareIt() {
    if (!it.ach) return;
    sharing = true; haptic.tap();
    try { if (await shareCard({ kind: 'aw', code: it.ach.code }, 'https://t.me/KBTUappBot?startapp=aw_' + it.ach.code, t('aw.shareText', { name: it.name }))) say(phrase('say.shared'), 'party_popper_3d'); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { sharing = false; }
  }
  // "Recruiter" is earned by my invite link: the link right here (owner, Oct 29: no hunting for it on Me)
  let inviting = $state(false);
  const ref = $derived(mine && it.ach?.code === 'referral' ? session.me?.referrals : null);
  async function invite() {
    if (!ref) return;
    inviting = true; haptic.tap();
    try { await shareInvite(ref.code, () => (inviting = false)); }
    catch { haptic.error(); say(t('common.error'), 'warning_3d'); }
    finally { inviting = false; }
  }
  const a = $derived(it.ach), b = $derived(it.badge);
  let seen = $state<string | null>(null); // a variant tapped to read what it means (null: mine)
  const hidden = $derived(!!a && a.secret && a.level === 0);
  const tiers = $derived(!!a && a.levels.length > 1);
  const next = $derived(a?.levels.find((l) => !l.reached));
  const pct = $derived(a && next ? Math.min(100, Math.max(3, (a.count / next.need) * 100)) : 100); // as the words say: 6 of 15
  const share = (x: number) => (x > 0 && x < 0.01 ? '<1' : String(Math.round(x * 100)));
  const tierOf = (i: number) => t(`ach.tier.${i + 1}` as 'ach.tier.1');
  // the stage's light: the metal's own colour (one-level accent, bronze, silver, gold, legend; a drawn medal its metal);
  // none on a medal not earned yet. The rays and halo only behind a round one (a pin's corners stay clean)
  const GLOW = ['124, 77, 255', '224, 160, 106', '200, 210, 230', '255, 196, 80', '176, 124, 255']; // r, g, b: rgba() below (no color-mix on old iOS)
  const ROSE = '226, 152, 124'; // the performer's rose gold
  const DRAWN: Record<string, string> = { medal_init26_2: GLOW[3], medal_init26f_2: GLOW[2], medal_init26p_2: ROSE, medal_first500: GLOW[3] }; // a new art gets a new name: phones keep the old file for hours
  // the 3D medal's ribbon, stripes left to right (r, g, b): its own palette per drawn medal, else its metal on deep blue
  const GOLD = '214, 170, 72', SILVER = '206, 212, 224', NAVY = '18, 22, 82', VIOLET = '62, 32, 146', ROYAL = '30, 64, 196', WHITE = '238, 240, 246', AMETHYST = '88, 34, 150';
  const RIBBON: Record<string, string[]> = {
    medal_init26p_2: [ROSE, AMETHYST, AMETHYST, WHITE, AMETHYST, AMETHYST, ROSE, AMETHYST, AMETHYST, WHITE, AMETHYST, AMETHYST, ROSE],
    medal_first500: [GOLD, VIOLET, VIOLET, NAVY, NAVY, GOLD, NAVY, NAVY, VIOLET, VIOLET, GOLD],
    medal_init26_2: [GOLD, ROYAL, ROYAL, WHITE, ROYAL, ROYAL, GOLD, ROYAL, ROYAL, WHITE, ROYAL, ROYAL, GOLD],
    medal_init26f_2: [SILVER, ROYAL, ROYAL, WHITE, ROYAL, ROYAL, SILVER, ROYAL, ROYAL, WHITE, ROYAL, ROYAL, SILVER],
  };
  const round = $derived(!!a || !!it.founder || !!it.idea);
  const glow = $derived(it.founder || it.idea ? GLOW[0] : !a || !a.level ? '' : DRAWN[a.emoji] ?? (tiers ? GLOW[Math.min(a.level, 4)] : GLOW[0]));
  // the coin's edge (owner, Nov 1: "a real coin"): its metal; the seals' silver rim, the idea's blue. None on a medal
  // not earned yet: its face is see-through, the edge would show through it
  const edge = $derived(!round || !glow ? '' : it.founder ? GLOW[2] : it.idea ? '47, 91, 234' : glow);
  const EDGE = Array.from({ length: 22 }, (_, i) => i + 1); // 22 discs 1 px apart: ~10% of the 220 px coin, a real coin's thickness
  const SIZE = 220;

  // a finger turns the coin round its upright axis, a flick spins it past its back, then it settles face up (Apple's
  // award view); on top of the tilt. --spin is written straight on .big: no re-render per frame
  let big = $state<HTMLSpanElement>();
  let spin = 0, vel = 0, raf = 0, drag: { x: number; a: number; t: number; id: number } | null = null;
  const put = () => big?.style.setProperty('--spin', spin.toFixed(2) + 'deg');
  function coast() {
    if (Math.abs(vel) > 0.35) { spin += vel; vel *= 0.955; }
    else {
      const to = Math.round(spin / 360) * 360; // the nearest face-up
      spin += (to - spin) * 0.14;
      if (Math.abs(to - spin) < 0.2) { spin = 0; vel = 0; put(); raf = 0; return; }
    }
    put(); raf = requestAnimationFrame(coast);
  }
  function grab(e: PointerEvent) {
    if (!edge || matchMedia('(prefers-reduced-motion: reduce)').matches || document.documentElement.classList.contains('lowfx')) return;
    cancelAnimationFrame(raf); raf = 0;
    drag = { x: e.clientX, a: spin, t: e.timeStamp, id: e.pointerId }; vel = 0;
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  }
  function move(e: PointerEvent) {
    if (!drag || e.pointerId !== drag.id) return;
    const was = spin;
    spin = drag.a + (e.clientX - drag.x) * 0.9; // 0.9 deg a pixel: a swipe across the coin is about half a turn
    const dt = Math.max(1, e.timeStamp - drag.t);
    vel = ((spin - was) / dt) * 16.7; drag.t = e.timeStamp; // deg a frame
    put();
  }
  function drop() {
    if (!drag) return;
    drag = null; vel = Math.max(-40, Math.min(40, vel));
    if (Math.abs(vel) > 6) haptic.tap();
    raf = requestAnimationFrame(coast);
  }
  // a drawn medal is a real 3D coin (WebGL, three.js in its own lazy chunk; owner, Nov 1: the CSS layers read cheap).
  // The flat art shows until the first frame is drawn, and stays when there is no WebGL, under power saving or reduced
  // motion. ponytail: the tier medals and seals keep the CSS coin; a canvas-painted face for them is the upgrade
  const art = $derived(a && a.level && a.emoji.startsWith('medal_') ? a.emoji : '');
  let gl = $state<'' | 'wait' | 'on'>('');
  let landed = $state(true); // the 3D entrance: the light behind fades up as the medal arrives
  let host: HTMLSpanElement, stage: HTMLDivElement;
  const tiltOf = (k: string) => parseFloat(stage?.style.getPropertyValue(k)) || 0; // glass.ts writes --gx/--gy here
  onMount(() => {
    let off: (() => void) | undefined, dead = false;
    if (art && edge && !matchMedia('(prefers-reduced-motion: reduce)').matches && !document.documentElement.classList.contains('lowfx')) {
      gl = 'wait'; landed = false;
      import('../../ui/coin3d')
        .then((m) => m.mountCoin(host, { src: `emoji/${art}.webp`, tint: edge, ribbon: RIBBON[art] ?? [edge, NAVY, NAVY, edge, NAVY, NAVY, edge], size: SIZE, state: () => ({ x: tiltOf('--gx'), y: tiltOf('--gy'), spin }), onLand: () => { landed = true; haptic.soft(); } }))
        .then((f) => { if (dead) f(); else { off = f; gl = 'on'; } })
        .catch(() => { gl = ''; landed = true; }); // no WebGL: the flat medal
    }
    return () => { dead = true; cancelAnimationFrame(raf); off?.(); };
  });
  // the line over the name: the event a medal is from, else the level reached; a badge: its club and day
  const kicker = $derived(a?.code === 'init26' ? (a.variant ? t('aw.init26', { variant: variantName(a.code, a.variant) }) : '') : a?.level && tiers ? t('aw.level', { tier: tierOf(a.level - 1) })
    : b ? `${nameOf(b.org)} · ${dayMonth(b.at)}` : '');

  $effect(() => { overlay.title = it.ach ? t('cap.achievement') : it.founder ? t('cap.founder') : it.idea ? t('cap.idea') : t('cap.badge');
    overlay.icon = it.ach ? Medal : it.founder ? Crown : it.idea ? Lightbulb : BadgeCheck; });

  // the entry pop runs on .pop, the tilt on .big inside it: a WAAPI transform on the tilted element itself hid the tilt
  // for the whole 620 ms and then jumped (owner, Nov 1: "the medal follows the phone only after a while")
  let medal: HTMLSpanElement, scrim: HTMLDivElement, wrap: HTMLDivElement;
  let gone = false;
  onMount(() => {
    recenter(); // it opens face on, however the phone is held (owner, Nov 1: lying on his side it opened turned away)
    haptic.soft();
    scrim.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 280, easing: 'ease-out' });
    if (!matchMedia('(prefers-reduced-motion: reduce)').matches) {
      if (!gl) medal.animate([{ transform: 'scale(0.55) rotate(-14deg)', opacity: 0 }, { transform: 'scale(1.06) rotate(3deg)', opacity: 1, offset: 0.62 }, { transform: 'none' }],
        { duration: 620, easing: 'cubic-bezier(.2,.9,.25,1)' });
      wrap.querySelector('.shade')?.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 620, easing: 'ease-out' });
      for (const [i, el] of [...wrap.querySelectorAll('.up')].entries())
        el.animate([{ opacity: 0, transform: 'translateY(12px)' }, { opacity: 1, transform: 'none' }], { duration: 400, delay: 260 + i * 60, easing: 'cubic-bezier(.2,.9,.25,1)', fill: 'backwards' });
    }
    return hideChrome();
  });
  function leave() {
    if (gone) return;
    gone = true;
    wrap.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'scale(0.96)' }], { duration: 200, easing: 'ease-in', fill: 'forwards' });
    scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 220, easing: 'ease-in', fill: 'forwards' }).onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });
</script>

<div class="scrim" bind:this={scrim} style:--glow={glow || GLOW[0]} onclick={() => leave()} role="presentation"></div>
<div class="wrap theme-dark" bind:this={wrap}>
  <div class="page">
  <div class="stage" bind:this={stage} class:dim={!landed} class:hangs={!!gl} class:lit={round && !!glow} class:spins={!!edge} style:--glow={glow} use:glass role="presentation" onpointerdown={grab} onpointermove={move} onpointerup={drop} onpointercancel={drop}>
    {#if round && glow}<span class="rays" aria-hidden="true"></span><span class="halo" aria-hidden="true"></span>{/if}
    {#if round}<span class="shade" aria-hidden="true"></span>{/if}
    <span class="pop" bind:this={medal}><span class="big" class:round class:coin={!!edge && !gl} class:flat={!!gl} style:--edge={edge || null} bind:this={big}>{#if edge && !gl}{#each EDGE as z (z)}<i class="edge" style:--z={z}></i>{/each}<span class="back" aria-hidden="true"><Award {it} size={SIZE} /></span>{/if}<span class="face" class:hid={!!gl}><Award {it} size={round ? SIZE : 132} /><span class="shine"></span>{#if round && glow}<span class="sweep"></span>{/if}</span></span><span class="gl" bind:this={host}></span></span>
  </div>
  <h2 class="name up">{it.name}</h2>
  {#if kicker}<p class="kick up">{kicker}</p>{/if}

  {#if a}
    {#if a.now}<p class="tier">{tn('ach.streakNow', a.now)}</p>{/if}
    <p class="t-callout how up">{seen ? variantHow(a.code, seen) : achHow(a)}</p>
    {#if a.variants}
      <!-- one badge, its variants side by side: mine lit, the others dim; a tap tells what each one means -->
      <div class="vars up">
        {#each a.variants as x (x.code)}
          <button class="var" class:have={x.have} class:mine={x.code === a.variant} class:on={x.code === (seen ?? a.variant)} onclick={() => { haptic.select(); seen = x.code === a.variant ? null : x.code; }}>
            <img src={`emoji/${x.emoji}.webp`} alt="" draggable="false" />
            <span>{variantName(a.code, x.code)}</span>
          </button>
        {/each}
      </div>
    {/if}
    {#if a.level && a.at && tiers}<p class="t-foot got">{t('aw.earned', { date: dayMonth(a.at) })}</p>{/if}
    {#if !hidden}
      {#if a.level && !tiers}
        <!-- earned, one level: the day and how rare, one quiet line (owner, Nov 1: the boxed card looked clunky) -->
        <p class="meta up">{a.at ? dayMonth(a.at) : t('aw.have')} · {t('person.rarity', { p: share(Math.max(a.levels[0].rarity, 0.001)) })}</p>
      {:else if next}
        <div class="prog up">
          <div class="row"><b>{t('ach.progress', { count: a.count, need: next.need })}</b>{#if tiers}<span>{t('aw.toLevel', { tier: tierOf(a.levels.indexOf(next)) })}</span>{/if}</div>
          <div class="bar"><span style="width:{pct}%"></span></div>
        </div>
      {:else}
        <p class="top">{t('aw.topCount', { count: a.count })}</p>
      {/if}
      {#if tiers}
        <div class="ladder up">
          <div class="lh t-cap"><span>{t('aw.levels')}</span><span>{t('aw.need')}</span><span>{t('aw.students')}</span></div>
          {#each a.levels as l, i (i)}
            <div class="lv" class:got={l.reached}>
              <span class="ln">{#if l.reached}<Check size={15} strokeWidth={2.6} />{/if}{tierOf(i)}</span>
              <span>{l.need}</span><span>{share(l.rarity)}%</span>
            </div>
          {/each}
        </div>
      {:else if !a.level}
        <p class="t-foot rar">{t('person.rarity', { p: share(a.levels[0].rarity) })}</p>
      {/if}
    {/if}
  {:else if b}
    <p class="t-callout how">{t('aw.badgeHow')}</p>
  {:else if it.founder || it.idea}
    <p class="t-callout how">{t('seal.one')}</p>
  {/if}

  <!-- small glass pills in the medal's metal, right under it (owner, Nov 1: the wide blue button at the bottom was ugly) -->
  {#if ref || (mine && a && a.level > 0)}
    <div class="acts up" style:--glow={glow || GLOW[0]}>
      {#if ref}<button class="pill glass glass-pill main" use:glass disabled={inviting} onclick={invite}><Megaphone size={17} />{t('ref.invite')}</button>{/if}
      {#if mine && a && a.level > 0}
        <button class="pill glass glass-pill" class:main={!ref} use:glass disabled={sharing} onclick={shareIt}><Share size={17} />{t('aw.share')}</button>
      {/if}
    </div>
  {/if}
  </div>
  <CloseX onclick={() => leave()} />
</div>

<style>
  /* full screen: the profile dimmed and blurred, a faint wash of the medal's metal from above */
  .scrim { position: absolute; inset: 0; z-index: var(--z-sheet);
    background: radial-gradient(70% 45% at 50% 30%, rgba(var(--glow), 0.1), transparent 70%), rgba(3, 4, 10, 0.88);
    -webkit-backdrop-filter: blur(18px); backdrop-filter: blur(18px); }
  :global(html.lowfx) .scrim { -webkit-backdrop-filter: none; backdrop-filter: none; background: radial-gradient(70% 45% at 50% 30%, rgba(var(--glow), 0.1), transparent 70%), rgba(3, 4, 10, 0.96); }
  .wrap { position: absolute; inset: 0; z-index: var(--z-sheet); pointer-events: none; display: flex; flex-direction: column; background: none; padding-bottom: var(--close-room); }
  .wrap > :global(*) { pointer-events: auto; }
  /* the scroll ends above the × and fades out into it: Share never slides under it */
  .page { flex: 1; min-height: 0; overflow-x: hidden; overflow-y: auto; scrollbar-width: none; padding: calc(var(--top) + 8px) 20px 20px; display: flex; flex-direction: column;
    -webkit-mask-image: linear-gradient(black calc(100% - 20px), transparent); mask-image: linear-gradient(black calc(100% - 20px), transparent); }
  .page::-webkit-scrollbar { display: none; }
  .page > :first-child { margin-top: auto; }
  .page > :last-child { margin-bottom: auto; }
  .acts { display: flex; justify-content: center; flex-wrap: wrap; gap: 10px; margin-top: 24px; }
  .pill { position: relative; height: 46px; padding: 0 22px; display: inline-flex; align-items: center; gap: 8px; border-radius: var(--r-full);
    color: var(--text); font: 650 var(--fs-body)/1 var(--font-text); background-color: rgba(255, 255, 255, 0.1); }
  .pill.main { background-color: rgba(var(--glow), 0.32); }
  .pill > :global(svg) { position: relative; }
  .pill:active { transform: scale(0.96); }
  .pill:disabled { opacity: 0.6; }
  .stage { position: relative; display: flex; justify-content: center; padding: 10px 0 6px; }
  .lit { padding: 56px 0 44px; }
  .lit.hangs { padding-top: 140px; } /* the 3D medal's ribbon needs the room above, clear of the capsule */
  .spins { touch-action: pan-y; cursor: grab; user-select: none; -webkit-user-select: none; }
  /* behind the coin, still, like a medal in a display case: a very faint wash of its metal round it and a soft, low
     pool of light on the "shelf" under it (owner, Nov 1: the old wide rays read childish; then the halo and hairline
     rays still read as a glow: quieter, more refined). Both sit on the medal's centre, whatever room the ribbon takes */
  .lit { --below: 44px; } /* under the coin: its padding below; its centre is 110 px (SIZE / 2) above that */
  .halo, .rays { position: absolute; left: 50%; bottom: calc(var(--below) + 110px); border-radius: 50%; pointer-events: none; translate: -50% 50%; }
  .rays { width: 480px; aspect-ratio: 1; background: radial-gradient(closest-side, rgba(var(--glow), 0.07), rgba(var(--glow), 0.025) 55%, transparent); }
  .halo { bottom: calc(var(--below) - 36px); translate: -50% 0; width: 300px; height: 64px;
    background: radial-gradient(closest-side, rgba(var(--glow), 0.2), rgba(var(--glow), 0.06) 60%, transparent); }
  /* the halo, rays and shadow stay put: only the coin turns (owner, Nov 1: the glow moving with the coin looked strange) */
  .shade { position: absolute; left: 50%; top: 50%; width: 196px; aspect-ratio: 1; border-radius: 50%; pointer-events: none; translate: -50% -50%;
    background: radial-gradient(closest-side, rgba(0, 0, 0, 0.55), rgba(0, 0, 0, 0.22) 62%, transparent);
    transform: translateY(18px); }
  .lit .shade { top: auto; bottom: calc(var(--below) + 110px); translate: -50% 50%; }
  .pop { position: relative; z-index: 1; display: inline-flex; perspective: 700px; }
  /* power saving stops the gyro (--gx would freeze off-centre): flat; reduced motion never starts it */
  :global(html.lowfx) .big { transform: none; }
  :global(html.lowfx) .edge { display: none; }
  @media (prefers-reduced-motion: reduce) { .sweep { animation: none; } .big { transform: none; } .edge { display: none; } }
  /* one narrow pass of light across the metal as it lands */
  .sweep { position: absolute; inset: 0; border-radius: 50%; pointer-events: none; mix-blend-mode: overlay; background-size: 300% 100%;
    background-image: linear-gradient(115deg, transparent 46%, rgba(255, 255, 255, 0.55) 50%, transparent 54%); background-position: 130% 0;
    animation: sweep 1.4s 0.55s cubic-bezier(0.4, 0, 0.2, 1) both; }
  @keyframes sweep { to { background-position: -30% 0; } }
  /* under the coin, Apple's award view: the name large, one quiet line, the words, a quiet meta line */
  .kick { text-align: center; margin-top: 6px; font: 600 var(--fs-body)/1.3 var(--font-text); color: var(--text-2); }
  .meta { text-align: center; margin-top: 14px; font: 560 var(--fs-sub)/1.3 var(--font-text); color: var(--text-3); }
  /* the coin only turns, it never slides (owner, Nov 1). No transition: glass.ts's lerp already smooths --gx/--gy */
  .big { position: relative; display: inline-flex; will-change: transform; transform-style: preserve-3d;
    transform: rotateX(calc(var(--gy, 0) * -22deg)) rotateY(calc(var(--gx, 0) * 26deg + var(--spin, 0deg))); }
  .big.flat { transform: none; }
  .hid { visibility: hidden; }
  .halo, .rays, .shade { transition: opacity 0.9s cubic-bezier(0.2, 0.8, 0.2, 1); }
  .dim :is(.halo, .rays, .shade) { opacity: 0; }
  .gl { position: absolute; inset: 0; pointer-events: none; }
  /* the face hides when it turns away; the back is the same disc, mirrored, darker and flatter, like a struck reverse */
  .face { position: relative; display: inline-flex; }
  .coin .face { -webkit-backface-visibility: hidden; backface-visibility: hidden; }
  .back { position: absolute; inset: 0; display: inline-flex; -webkit-backface-visibility: hidden; backface-visibility: hidden;
    transform: translateZ(-23px) rotateY(180deg) scaleX(-1); }
  .coin .back > :global(:first-child) { filter: grayscale(0.55) brightness(0.62) contrast(1.15); }
  .back::after { content: ''; position: absolute; inset: 0; border-radius: 50%; box-shadow: inset 0 2px 3px rgba(0, 0, 0, 0.5), inset 0 -1px 2px rgba(255, 255, 255, 0.18); }
  /* the edge: discs of the metal stacked 1 px apart behind the face (at 26 deg a step projects to under 0.5 px: no gaps);
     the rim shows on the side the coin turns away from, as on a real coin. Darker than the face's rim, lit from above,
     with fine radial ridges (a conic stripe on every disc lines up into the milled edge). The face's own drop shadow
     would fall on its edge: off here */
  .edge { position: absolute; inset: 0; border-radius: 50%; pointer-events: none; transform: translateZ(calc(var(--z) * -1px));
    background: repeating-conic-gradient(rgba(0, 0, 0, 0.32) 0 0.9deg, rgba(255, 255, 255, 0.14) 0.9deg 1.8deg),
      linear-gradient(180deg, rgba(255, 255, 255, 0.12), rgba(0, 0, 0, 0.55)), linear-gradient(rgba(0, 0, 0, 0.42), rgba(0, 0, 0, 0.42)), rgb(var(--edge)); }
  .coin .face > :global(:first-child), .coin :is(.face, .back) :global(img) { box-shadow: none; filter: none; }
  /* the light slides over the metal with the tilt (round medals only: a pin's corners stay clean) */
  .shine { display: none; }
  /* a soft specular band that slides with the tilt, as on polished metal (owner, Nov 1: the white spot was so-so) */
  .round .shine { display: block; position: absolute; inset: 0; border-radius: 50%; pointer-events: none; mix-blend-mode: soft-light;
    background: linear-gradient(125deg, transparent calc(28% + var(--gx, 0) * 34% + var(--gy, 0) * 14%), rgba(255, 255, 255, 0.5) calc(40% + var(--gx, 0) * 34% + var(--gy, 0) * 14%), transparent calc(54% + var(--gx, 0) * 34% + var(--gy, 0) * 14%)); }
  .name { text-align: center; margin-top: 10px; color: var(--text); font: 750 var(--fs-title)/1.12 var(--font-display); letter-spacing: -0.02em; }
  .got { text-align: center; margin-top: 2px; }
  .tier { text-align: center; margin-top: 4px; font: 650 14px/1.3 var(--font-text); color: var(--accent-text); }
  .how { text-align: center; margin: 14px 12px 0; color: var(--text-2); }

  .vars { display: flex; justify-content: center; gap: 8px; margin-top: 16px; }
  .var { flex: 0 1 104px; min-width: 0; display: flex; flex-direction: column; align-items: center; gap: 6px; padding: 10px 4px 8px; border-radius: var(--r-m);
    font: 600 var(--fs-sub)/1.2 var(--font-text); color: var(--text-3); transition: background-color .2s; }
  .var img { width: 56px; height: 56px; object-fit: contain; filter: grayscale(1) brightness(0.7); opacity: 0.4; transition: filter .2s, opacity .2s; }
  .var span { max-width: 100%; text-align: center; }
  .var.have img { filter: grayscale(0.6) brightness(0.85); opacity: 0.7; }
  .var.mine img { filter: drop-shadow(0 4px 10px rgba(0, 0, 0, 0.5)); opacity: 1; }
  .var.mine { color: var(--text); }
  .var.on { background: rgba(255, 255, 255, 0.08); }
  .var:active { transform: scale(0.96); }
  .prog { margin-top: 16px; padding: 12px 14px; border-radius: var(--r-m); background: var(--surface-2); }
  .prog .row { display: flex; justify-content: space-between; align-items: baseline; gap: 8px; }
  .prog b { font: 720 17px/1.2 var(--font-display); }
  .prog .row span { font: 560 13px/1.2 var(--font-text); color: var(--text-2); }
  .bar { height: 8px; margin-top: 10px; border-radius: 4px; background: var(--surface-3); overflow: hidden; }
  .bar span { display: block; height: 100%; border-radius: 4px; background: var(--grad-accent); }
  .rar { text-align: center; margin-top: 8px; }
  .top { text-align: center; margin-top: 14px; font: 650 14px/1.3 var(--font-text); color: var(--success-text); }

  .ladder { margin-top: 14px; display: flex; flex-direction: column; border-radius: var(--r-m); background: var(--surface-2); padding: 4px 0; }
  .lh, .lv { display: grid; grid-template-columns: 1fr 70px 90px; align-items: center; padding: 8px 14px; }
  .lh { color: var(--text-3); padding-bottom: 4px; }
  .lh span:not(:first-child), .lv span:not(:first-child) { text-align: right; }
  .lv { font: 600 14.5px/1.2 var(--font-text); color: var(--text-2); }
  .lv + .lv { box-shadow: inset 0 1px 0 var(--line); }
  .lv.got { color: var(--text); }
  .ln { display: inline-flex; align-items: center; gap: 6px; }
  .lv.got .ln { color: var(--success-text); }
</style>
