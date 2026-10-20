<script lang="ts">
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  // The profile hero, shared by Me and the person sheet (owner's pick of three, Oct 4): the profile as a KBTU
  // event badge on a lanyard — clubs print their titles in English on theirs, so this one does too. It hangs
  // from the capsule or the sheet's grip, swings in from the clip, then follows the phone's tilt; the
  // holographic strip is the only iridescence and stays inside the card. Data: lib/awards.ts.
  // Your own badge (`qr`, on Me) carries your QR in the corner, like a conference badge: it holds only a
  // link into the app (your profile; the friend invite once friends exist), never a student ID; a tap shows
  // it full screen. Other people's cards never show it.
  import type { PersonCard } from '../../lib/api';
  import { hero, founderItem, ideaItem } from '../../lib/awards';
  import { glass } from '../../ui/glass';
  import Avatar from '../../ui/Avatar.svelte';
  import Founder from '../../ui/Founder.svelte';
  import Award from '../../ui/Award.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { session } from '../../lib/state/session.svelte';
  import KbtuMark from '../../ui/KbtuMark.svelte';
  import LanyardBand from '../../ui/LanyardBand.svelte';
  import LanyardHolo from '../../ui/LanyardHolo.svelte';
  import { QR_TONE, lookOf, STRAP } from '../../lib/awards';
  import { t } from '../../lib/i18n/index.svelte';
  import { power } from '../../lib/state/power.svelte';

  // qr: my badge QR code (Me only; me.qr), a random code a door scanner checks, so an id can't be turned into a QR.
  // live: the badge's screen is open (Me: the Profile tab; a sheet: always)
  let { p, qr = null, live = true, shelf = true }: { p: PersonCard; qr?: string | null; live?: boolean; shelf?: boolean } = $props();
  const h = $derived(hero(p));
  // the club badge they picked (a skin, owner Oct 13; picked in LookSheet), else the KBTU one
  const sower = $derived(p.skin === 'sower'); // the creator's own (owner, Oct 13)
  const look = $derived(lookOf(p)); // the class and the strap's word
  const mine = $derived(!!qr);
  const link = $derived(`https://t.me/KBTUappBot?startapp=u_${qr}`);
  const encoder = () => import('../../ui/Qr.svelte'); // its own chunk, shared with the ticket

  // a damped pendulum around the clip, like a badge let go (WAAPI frames from the formula, not keyframes by hand)
  const frames = Array.from({ length: 41 }, (_, f) => {
    const s = (f / 40) * 1.4;
    return { transform: `rotate(${f === 40 ? 0 : (-6 * Math.exp(-2.8 * s) * Math.cos(7.5 * s)).toFixed(2)}deg)` };
  });
  let swing: HTMLDivElement;
  const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  // it swings in each time its screen opens (owner, Oct 4: not only when the app opens), never on scroll
  $effect(() => { if (live && !still()) swing.animate(frames, { duration: 1400 }); });

  // On Me it also feels the Profile pages being swiped (owner, Oct 4: the swing-in on paging looked like a jerk):
  // it leans behind a moving page and sways when the page stops. A damped spring (8 rad/s, ζ 0.2) toward a lean
  // set by the page's speed (1e-4 rad per px/s, at most 0.09 rad: 3.5–6°, calm in 2 s), measured from where the badge really is, so a
  // drag, a flick and the capsule's slide all feel the same. CSS `rotate`, so it adds to the swing-in's transform.
  $effect(() => {
    if (!qr || still() || power.lite) return; // power saving: no spring, it reads the layout every frame
    let th = 0, om = 0, vs = 0, lastX = 0, lastT = 0, raf = 0, until = 0;
    const step = (t: number) => {
      const x = swing.getBoundingClientRect().left, dt = lastT ? Math.min(0.034, (t - lastT) / 1000) : 0;
      if (dt) vs += ((x - lastX) / dt - vs) * 0.3;
      lastX = x; lastT = t;
      const lean = Math.max(-0.09, Math.min(0.09, vs * 1e-4));
      om += (64 * (lean - th) - 3.2 * om) * dt; th += om * dt;
      if (t < until || Math.abs(th) > 5e-4 || Math.abs(om) > 5e-3 || Math.abs(vs) > 5) { swing.style.rotate = `${th.toFixed(4)}rad`; raf = requestAnimationFrame(step); }
      else { swing.style.rotate = ''; th = om = vs = raf = lastT = 0; }
    };
    // the pager speaks when a drag moves and when a settle starts (≤ 360 ms): keep watching that long
    const kick = () => { until = performance.now() + 450; if (!raf) raf = requestAnimationFrame(step); };
    addEventListener('kb:pager', kick);
    return () => { removeEventListener('kb:pager', kick); cancelAnimationFrame(raf); };
  });
</script>

<section class="h">
<div class="hang {look}">
  <div class="strap" aria-hidden="true"><span>{STRAP[look]}</span></div>
  <div class="clip" aria-hidden="true"></div>
  <div class="swing" bind:this={swing}>
    <div class="badge" use:glass>
      <LanyardBand {look} wide />
      <span class="slot" aria-hidden="true"></span>
      {#if mine}
        <button class="qr" onclick={() => sheets.myQr(link, p)} aria-label={t('me.qr')}>{#await encoder() then m}<m.default text={link} tone={sower ? undefined : QR_TONE}><span class="appmark"><KbtuMark /></span></m.default>{/await}</button>
      {/if}
      <div class="top" class:mine>
        {#if mine}<button class="photo" onclick={() => sheets.look()} aria-label={t('look.title')}><Avatar person={h.person} size={74} tappable={false} /></button>
        {:else}<span class="photo"><Avatar person={h.person} size={mine ? 74 : 86} tappable={false} /></span>{/if}
        <span class="id">
          <b class="nm"><span class="ellipsis">{h.name}</span>{#if h.status}<button class="seal" onclick={() => sheets.award(p.founder ? founderItem() : ideaItem(), p.id === session.me?.id)} aria-label={h.status}><Founder size={19} idea={!p.founder} /></button>{/if}</b>
          <span class="role">{h.title}</span>
          <span class="meta">{h.line}</span>
        </span>
      </div>
      <span class="foot"><LanyardHolo {look} no={h.no} /></span>
    </div>
  </div>
</div>

{#if h.bio}<p class="t-callout bio">{h.bio}</p>{/if}

<!-- the award shelf (owner, Oct 14): the showcase with empty places to fill, the count, and on mine the closest next
     award; mine opens the whole collection. Someone else's shows only when there's something on it. -->
{#if shelf && (mine || h.shelf.length)}
  <div class="shelf surface" class:wait={!h.loaded}>
    {#if mine}<button class="sh" onclick={() => sheets.awards()}><b>{t('person.awards')}</b><span class="num">{h.loaded ? t('aw.of', { n: h.earned, total: h.total }) : ''}</span><ChevronRight size={16} /></button>
    {:else}<p class="sh"><b>{t('person.awards')}</b><span class="num">{t('aw.of', { n: h.earned, total: h.total })}</span></p>{/if}
    <div class="row">
      {#each h.shelf as it (it.key)}<button onclick={() => sheets.award(it, mine)} aria-label={it.name}><Award {it} size={44} /></button>{/each}
      {#if mine}{#each { length: Math.max(0, 6 - h.shelf.length) } as _, i (i)}<span class="empty" aria-hidden="true"></span>{/each}{/if}
    </div>
    {#if mine && h.next}<button class="nx t-foot ellipsis" onclick={() => sheets.awards()}>{h.next}</button>{/if}
  </div>
{/if}
</section>

<style>
  .hang { display: flex; flex-direction: column; align-items: center; perspective: 900px; margin-top: -14px; }
  /* the word sits clear of the clip (it hid behind it at the bottom: owner, Oct 4) */
  .strap { width: 26px; height: 46px; display: flex; justify-content: center; align-items: center; padding-bottom: 4px; overflow: hidden;
    background: linear-gradient(90deg, #1B36A0, #3B6BFF 50%, #1B36A0); box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25); }
  .strap span { writing-mode: vertical-rl; transform: rotate(180deg); font: 800 7.5px/26px var(--font-text); letter-spacing: 0.22em; color: rgba(255, 255, 255, 0.8); white-space: nowrap; }
  .clip { position: relative; z-index: 2; width: 36px; height: 15px; margin-bottom: -9px; border-radius: 5px;
    background: linear-gradient(180deg, #F4F6FB, #9AA4B8); box-shadow: 0 2px 5px rgba(0, 0, 0, 0.4), inset 0 1px 0 #fff; }
  .swing { width: min(340px, 100%); transform-origin: 50% -16px; }

  .badge {
    position: relative; overflow: hidden; padding-bottom: 14px; border-radius: 22px; color: #fff;
    background: linear-gradient(180deg, #1A2A78, #0E1438);
    box-shadow: 0 30px 50px -26px rgba(0, 0, 0, 0.75), 0 10px 22px -14px rgba(16, 22, 51, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.28);
    transform: rotateX(calc(var(--gy, 0) * -6deg)) rotateY(calc(var(--gx, 0) * 8deg));
    transition: transform 160ms ease-out;
  }
  /* a sheen that slides with the tilt */
  .badge::after { content: ''; position: absolute; inset: 0; pointer-events: none; background: linear-gradient(115deg, transparent 32%, rgba(255, 255, 255, 0.13) 46%, transparent 60%);
    background-size: 260% 100%; background-position: calc(50% + var(--gx, 0) * 45%) 0; }
  .slot { position: absolute; z-index: 1; top: 9px; left: 50%; width: 46px; height: 8px; margin-left: -23px; border-radius: 4px;
    background: rgba(5, 8, 20, 0.55); box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.7), 0 1px 0 rgba(255, 255, 255, 0.16); }
  /* the photo overlaps the band's bottom edge; the name starts below the band */
  .top { position: relative; display: flex; gap: 14px; align-items: flex-start; margin-top: -34px; padding: 0 18px; }
  .id { margin-top: 42px; }
  .foot { display: block; margin: 16px 18px 0; }
  .top.mine .id { padding-right: 62px; } /* the name never runs under the QR */
  .top.mine .nm { font-size: 20px; }
  .qr { position: absolute; z-index: 1; top: 126px; right: 14px; width: 58px; height: 58px; padding: 5px; border-radius: 13px; background: #fff;
    box-shadow: 0 8px 16px -8px rgba(0, 0, 0, 0.55), inset 0 0 0 1px rgba(10, 15, 36, 0.06); transition: transform var(--t-fast) var(--ease); }

  .qr:active { transform: scale(0.92); }
  .photo { position: relative; z-index: 1; flex: none; padding: 3px; border-radius: 21px; background: #fff; box-shadow: 0 8px 18px -8px rgba(0, 0, 0, 0.6); }
  .photo :global(.av), .photo :global(.av img), .photo :global(.ini) { border-radius: 18px; }
  .id { display: flex; flex-direction: column; gap: 4px; min-width: 0; }
  .nm { display: flex; align-items: center; gap: 7px; min-width: 0; font: 780 22px/1.12 var(--font-display); letter-spacing: -0.025em; }
  .nm :global(svg) { flex: none; }
  .seal { flex: none; display: inline-flex; padding: 10px; margin: -10px; transition: transform var(--t-fast) var(--ease); } /* a 39 px target */
  .seal:active { transform: scale(0.88); }
  .role { font: 760 11px/1.25 var(--font-text); letter-spacing: 0.13em; text-transform: uppercase; }
  .meta { font: 550 13px/1.3 var(--font-text); color: rgba(255, 255, 255, 0.72); }

  /* below the band, each look's own body and role colour; the strap's colours (the band and the strip: LanyardBand,
     LanyardHolo) */
  .role { color: var(--role, #A9C0FF); }
  .cheer { --role: #FFC83D; }
  .cheer .badge { background: linear-gradient(180deg, #1D2042, #0A0B17); }
  .cheer .strap { background: linear-gradient(90deg, #1E2140, #3A3F72 50%, #1E2140); }
  .cheer .strap span { color: #FFC83D; }
  .knights { --role: #9CC2FF; }
  .knights .badge { background: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 250 140'%3E%3Cg fill='none' stroke='white' stroke-opacity='.07' stroke-width='2'%3E%3Cpath d='M-20 140A145 145 0 0 1 270 140'/%3E%3Cpath d='M70 140V80H180V140'/%3E%3C/g%3E%3C/svg%3E") center bottom / 100% auto no-repeat,
    linear-gradient(180deg, #0F2B66, #071631); }
  .knights .strap { background: linear-gradient(90deg, #163E7C, #2F6BD0 50%, #163E7C); }
  .knights .strap span { letter-spacing: 0.12em; } /* seven letters on the short strap */
  .studex { --role: #FF8A80; }
  .studex .badge { background: linear-gradient(90deg, #CF3428 0 6px, transparent 6px), linear-gradient(180deg, #14306A, #0A1838); } /* a red edge, the band's cut running down */
  .studex .strap { background: linear-gradient(90deg, #A9271E, #CF3428 50%, #A9271E); }
  /* SOWER, the creator's alone (owner, Oct 13-14): black, the strap white with black letters */
  .sower { --role: rgba(255, 255, 255, 0.92); }
  .sower .badge { background: #000; }
  .sower .strap { background: linear-gradient(90deg, #DCDCE0, #fff 50%, #DCDCE0); }
  .sower .strap span { color: #000; }
  .sower .qr :global(.appmark) { background: #0A0A0A; }
  .sower .meta { color: rgba(255, 255, 255, 0.66); }

  .bio { margin-top: 8px; text-align: center; color: var(--text); }
  /* the award shelf: six places, the empty ones dashed */
  .shelf { margin-top: 14px; padding: 12px 14px 14px; border-radius: var(--r-xl); }
  .shelf.wait { animation: wait 1.2s ease-in-out infinite; }
  @keyframes wait { 50% { opacity: 0.6; } }
  .sh { display: flex; align-items: center; gap: 6px; width: 100%; font: 650 15px/1.2 var(--font-text); color: var(--text); text-align: left; }
  .sh b { flex: 1; font-weight: 650; }
  .sh .num { font: 550 13.5px/1.2 var(--font-text); color: var(--text-2); }
  .sh :global(svg) { color: var(--text-3); }
  .row { display: flex; justify-content: space-between; margin-top: 12px; }
  .row button { display: flex; transition: transform var(--t-fast) var(--ease); }
  .row button:active { transform: scale(0.9); }
  .empty { width: 44px; height: 44px; border-radius: 50%; box-shadow: inset 0 0 0 1.5px var(--line); background: var(--surface-2); }
  .nx { display: block; width: 100%; margin-top: 12px; text-align: left; color: var(--text-2); }
</style>
