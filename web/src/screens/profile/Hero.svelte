<script lang="ts">
  import { tick, untrack } from 'svelte';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  // The profile hero, shared by Me and the person sheet (owner's pick of three): the profile as a KBTU
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
  import LookMark from '../../ui/LookMark.svelte';
  import LanyardBand from '../../ui/LanyardBand.svelte';
  import LanyardHolo from '../../ui/LanyardHolo.svelte';
  import { QR_LOOK, lookOf, STRAP, banded } from '../../lib/awards';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { api } from '../../lib/api';
  import { say, overlays, moment } from '../../lib/state/ui.svelte';
  import { burst } from '../../ui/burst';

  // qr: my badge QR code (Me only; me.qr), a random code a door scanner checks, so an id can't be turned into a QR.
  // live: the badge's screen is open (Me: the Profile tab; a sheet: always)
  let { p, qr = null, live = true, shelf = true }: { p: PersonCard; qr?: string | null; live?: boolean; shelf?: boolean } = $props();
  const h = $derived(hero(p));
  // the club badge they picked (a skin; picked in LookSheet), else the KBTU one
  const look = $derived(lookOf(p)); // the lanyard picked
  // the one on show: it trails `look` while a new one is put on, so the old face turns away before the new one shows
  let face = $state(untrack(() => look));
  const mine = $derived(!!qr);
  const link = $derived(`https://t.me/KBTUappBot?startapp=u_${qr}`);
  const encoder = () => import('../../ui/Qr.svelte'); // its own chunk, shared with the ticket

  // a damped pendulum from the strap's top, like a badge let go (WAAPI frames from the formula, not keyframes by hand)
  const frames = Array.from({ length: 41 }, (_, f) => {
    const s = (f / 40) * 1.4;
    return { transform: `rotate(${f === 40 ? 0 : (-6 * Math.exp(-2.8 * s) * Math.cos(7.5 * s)).toFixed(2)}deg)` };
  });
  let swing: HTMLDivElement;
  const still = () => matchMedia('(prefers-reduced-motion: reduce)').matches;
  // it swings in each time its screen opens (not only when the app opens), never on scroll
  $effect(() => { if (live) untrack(() => { if (due()) later(); else if (!still()) swing.animate(frames, { duration: 1400 }); }); });
  // signed in from Profile itself: the sign-in sheet is still closing over it, so the drop waits for a free screen
  const later = () => { if (!overlays.some((o) => !o.closing)) { arrive(); return; } swing.style.opacity = '0'; moment(arrive); };
  // the one wow of the first run (onboarding plan, Oct 31): the first Profile open after the sign-in, the badge drops in
  // from above with its number (Unlock's medal curve), lands with a haptic and a burst, then swings as always; one toast.
  // Due: "First 500" not yet celebrated (it has no Unlock of its own now), or the sign-up's mark (LoginSheet: past 500)
  function due(): boolean {
    const me = session.me;
    if (!mine || !me || p.id !== me.id || p.no == null) return false;
    let mark = false;
    try { mark = localStorage.getItem('kb-arrive') === String(me.id); localStorage.removeItem('kb-arrive'); } catch { /* blocked */ }
    return mark || !!me.unlocked?.some((x) => x.code === 'first50');
  }
  function arrive() {
    swing.style.opacity = '';
    const award = session.me?.unlocked?.find((x) => x.code === 'first50');
    if (award) void api.markUnlocked(award.code, award.level).then((r) => { if (session.me) session.me = { ...session.me, unlocked: r.unlocked }; }).catch(() => {});
    const land = () => { const r = swing.getBoundingClientRect(); haptic.ok(); burst(false, { x: r.left + r.width / 2, y: r.top + r.height / 2 }); say(t(p.no! <= 500 ? 'me.arrived' : 'me.arrivedNo', { no: h.no }), 'party_popper_3d'); };
    if (still()) { land(); return; }
    swing.animate([{ transform: 'translateY(-70vh) rotate(-12deg)', opacity: 0 }, { transform: 'translateY(0) rotate(5deg)', opacity: 1, offset: 0.68 },
      { transform: 'none' }], { duration: 880, easing: 'cubic-bezier(.2,.9,.25,1)' }).onfinish = () => swing.animate(frames, { duration: 1400 });
    setTimeout(land, 600);
  }
  // the lanyard's own motion (LanyardBand's loops) runs only while the card is on screen and its tab open: a hidden tab
  // and a card scrolled away would animate for nobody
  let seen = $state(true);
  // and while a full-screen overlay (one with a mark in the capsule: the QR, the map) covers my card
  const covered = $derived(mine && overlays.some((o) => !o.closing && o.icon));
  $effect(() => {
    const io = new IntersectionObserver(([e]) => (seen = e.isIntersecting));
    io.observe(swing);
    return () => io.disconnect();
  });
  // a new lanyard put on: the badge turns over on its strap (owner, Oct 31: the right way, but it jerked and the light
  // stripe looked childish). One continuous half turn: it speeds up to its edge and leaves the edge at that same speed
  // (matched curves, no overshoot, no sway); the new face is put on while edge-on and the turn goes on only a frame
  // later, so the redraw never lands in a moving frame. The light comes from the angle: the face darkens as it turns
  // away, the new one comes out of the shade with a soft sheen. Transform and opacity only, on the compositor.
  let spinning = false, shade: HTMLElement;
  // the edge's speed matched: TURN ends at slope 2 over 170 ms, LAND starts at slope 4.67 over 400 ms, both ~1.05 deg/ms (owner: 240+560 was slow)
  const TURN = 'cubic-bezier(.4, 0, .75, .5)', LAND = 'cubic-bezier(.12, .56, .25, 1)';
  function spin() {
    spinning = true;
    swing.style.willChange = 'transform';
    const out = swing.animate([{ transform: 'none' }, { transform: 'rotateY(90deg)' }], { duration: 170, easing: TURN, fill: 'forwards' });
    shade.animate([{ opacity: 0 }, { opacity: 0.55 }], { duration: 170, easing: TURN, fill: 'forwards' });
    out.onfinish = async () => {
      face = untrack(() => look);
      haptic.soft();
      await tick();
      requestAnimationFrame(() => {
        const back = swing.animate([{ transform: 'rotateY(-90deg)' }, { transform: 'none' }], { duration: 400, easing: LAND });
        out.cancel();
        shade.getAnimations().forEach((x) => x.cancel());
        shade.animate([{ opacity: 0.55, background: 'linear-gradient(100deg, rgba(0, 0, 0, 0.9), rgba(0, 0, 0, 0.5))' },
          { opacity: 0.5, background: 'linear-gradient(100deg, rgba(255, 255, 255, 0.0), rgba(255, 255, 255, 0.22))', offset: 0.45 },
          { opacity: 0, background: 'linear-gradient(100deg, rgba(255, 255, 255, 0), rgba(255, 255, 255, 0.22))' }], { duration: 400, easing: LAND });
        back.onfinish = () => { swing.style.willChange = ''; spinning = false; if (untrack(() => look) !== face) spin(); };
      });
    };
  }
  $effect(() => {
    if (look === untrack(() => face) || spinning) return;
    if (still()) face = look;
    else spin();
  });
</script>

<section class="h">
<div class="hang {face}" class:rest={!live || !seen || covered}>
  <div class="swing" bind:this={swing}>
    <div class="strap" aria-hidden="true"><span>{STRAP[face]}</span></div>
    <div class="badge" use:glass>
      {#if face === 'sower'}<i class="rings z" aria-hidden="true"></i>{/if}
      {#if banded(face)}<LanyardBand look={face} wide qr={mine} />{/if}
      <span class="slot" aria-hidden="true"></span>
      {#if mine}
        <button class="qr" onclick={() => sheets.myQr(link, p)} aria-label={t('me.qr')}>{#await encoder() then m}<m.default text={link} lazy tone={QR_LOOK[face]}><LookMark look={face} /></m.default>{/await}</button>
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
      <span class="foot"><LanyardHolo look={face} no={h.no} /></span>
      <i class="shade" bind:this={shade} aria-hidden="true"></i>
    </div>
    <div class="clip" aria-hidden="true"></div>
  </div>
</div>

{#if h.bio}<p class="t-callout bio">{h.bio}</p>{/if}

<!-- the award shelf: the showcase with empty places to fill, the count, and on mine the closest next
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
  .rest :global(*) { animation-play-state: paused !important; }
  .rest .badge { transform: none; } /* and still: a hidden card, or one under the QR's blur (re-blurred on every move) */
  .hang { display: flex; flex-direction: column; align-items: center; perspective: 900px; margin-top: -14px; padding-top: 52px; }
  /* the word sits clear of the clip (it hid behind it at the bottom) */
  /* the strap swings with the card, from its top (owner, Oct 29: it stood still while the card moved) */
  .strap { position: absolute; top: -52px; left: 50%; margin-left: -13px; width: 26px; height: 52px; display: flex; justify-content: center; align-items: center; padding-bottom: 4px; overflow: hidden;
    background: linear-gradient(90deg, #1B36A0, #3B6BFF 50%, #1B36A0); box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25); }
  .strap span { writing-mode: vertical-rl; transform: rotate(180deg); font: 800 7.5px/26px var(--font-text); letter-spacing: 0.22em; color: rgba(255, 255, 255, 0.8); white-space: nowrap; }
  /* the clip swings with the card, down into its slot (owner, Oct 29: it hung above it) */
  .clip { position: absolute; z-index: 2; top: -1px; left: 50%; width: 36px; height: 15px; margin-left: -18px; border-radius: 5px;
    background: linear-gradient(180deg, #F4F6FB, #9AA4B8); box-shadow: 0 2px 5px rgba(0, 0, 0, 0.4), inset 0 1px 0 #fff; }
  .swing { position: relative; width: min(340px, 100%); transform-origin: 50% -52px; }

  .badge {
    position: relative; overflow: hidden; padding: 26px 0 14px; border-radius: 22px; color: #fff;
    background: radial-gradient(110% 90% at 0% 0%, rgba(124, 77, 255, 0.6), transparent 55%), linear-gradient(155deg, #2A4FD6, #121A3D 72%);
    box-shadow: 0 30px 50px -26px rgba(0, 0, 0, 0.75), 0 10px 22px -14px rgba(16, 22, 51, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.28);
    transform: rotateX(calc(var(--gy, 0) * -6deg)) rotateY(calc(var(--gx, 0) * 8deg));
    transition: transform 160ms ease-out;
  }
  /* the light on a lanyard turning over (the spin above): unseen at rest */
  .shade { position: absolute; inset: 0; z-index: 2; pointer-events: none; opacity: 0; border-radius: inherit;
    background: linear-gradient(100deg, rgba(0, 0, 0, 0.9), rgba(0, 0, 0, 0.5)); }
  /* a sheen that slides with the tilt */
  .badge::after { content: ''; position: absolute; inset: 0; pointer-events: none; background: linear-gradient(115deg, transparent 32%, rgba(255, 255, 255, 0.13) 46%, transparent 60%);
    background-size: 260% 100%; background-position: calc(50% + var(--gx, 0) * 45%) 0; }
  .slot { position: absolute; z-index: 1; top: 9px; left: 50%; width: 46px; height: 8px; margin-left: -23px; border-radius: 4px;
    background: rgba(5, 8, 20, 0.55); box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.7), 0 1px 0 rgba(255, 255, 255, 0.16); }
  .top { position: relative; display: flex; gap: 14px; align-items: center; padding: 0 18px; }
  /* Cheerleading and Knights: their art is the card's background (LanyardBand), under everything here */
  .foot { position: relative; display: block; margin: 16px 18px 0; } /* above the art (LanyardBand) */
  .top.mine .id, .cheer .id, .knights .id { padding-right: 62px; } /* the name never runs under the QR or the club's object */
  .top.mine .nm { font-size: 20px; }
  .qr { position: absolute; z-index: 1; top: 16px; right: 14px; width: 58px; height: 58px; padding: 5px; border-radius: 13px; background: #fff;
    box-shadow: 0 8px 16px -8px rgba(0, 0, 0, 0.55), inset 0 0 0 1px rgba(10, 15, 36, 0.06); transition: transform var(--t-fast) var(--ease); }

  .qr:active { transform: scale(0.92); }
  .photo { position: relative; z-index: 1; flex: none; padding: 3px; border-radius: 21px; background: rgba(255, 255, 255, 0.16); }
  .cheer .photo, .knights .photo, .moments .photo, .faces .photo, .studex .photo, .sower .photo { background: #fff; }
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
  .cheer .strap { background: linear-gradient(90deg, rgb(20, 22, 44), rgb(46, 50, 88) 50%, rgb(20, 22, 44)); box-shadow: inset 1px 0 0 rgba(232, 192, 98, 0.45), inset -1px 0 0 rgba(232, 192, 98, 0.45), 0 2px 6px rgba(0, 0, 0, 0.25); } /* their navy, gold stitches at the edges */
  .cheer .strap span { color: rgb(255, 200, 61); }
  .knights { --role: #9CC2FF; }
  .knights .strap { background: linear-gradient(90deg, #163E7C, #2F6BD0 50%, #163E7C); }
  .knights .strap span { letter-spacing: 0.12em; } /* seven letters on the short strap */
  .moments { --role: #F4D9BE; }
  .moments .meta { color: rgba(255, 255, 255, 0.84); } /* with the darker column behind it (LanyardBand), 4.5:1 */
  .moments .strap { background: linear-gradient(90deg, #7A321F, #B5603F 50%, #7A321F); }
  .moments .strap span { color: #F4D9BE; letter-spacing: 0.12em; }
  .faces { --role: #FF9BD6; }
  .faces .strap { background: linear-gradient(90deg, rgba(0, 0, 0, 0.3), transparent 35% 65%, rgba(0, 0, 0, 0.3)), linear-gradient(180deg, #6E7BFF, #C04BFF 55%, #FF4F9A); } /* shaded round like the others */
  .faces .strap span { color: #fff; }
  /* StudEx (kept over the band on Oct 20): red, a white cut, navy, the logo's arrow a faint watermark */
  .studex { --role: rgba(255, 255, 255, 0.92); }
  /* a soft shadow under the text where the art runs behind it (owner, Oct 31: a dark patch behind the column was crude) */
  .studex .id { text-shadow: 0 1px 2px rgba(6, 18, 48, 0.6), 0 0 14px rgba(6, 18, 48, 0.55); }
  .moments .id { text-shadow: 0 1px 2px rgba(40, 16, 8, 0.6), 0 0 14px rgba(40, 16, 8, 0.55); }
  .studex .meta { color: rgba(255, 255, 255, 0.8); }
  .studex .strap { background: linear-gradient(90deg, #A9271E, #CF3428 50%, #A9271E); }
  /* SOWER, the creator's alone (Oct 14 after four drafts): black, rings spreading from behind the QR's corner; the strap white with black letters */
  .sower { --role: rgba(255, 255, 255, 0.92); }
  .sower .badge { background: radial-gradient(90% 120% at 0% 0%, #26262B, #000 62%); }
  .rings { position: absolute; right: -120px; top: -120px; width: 300px; height: 300px; border-radius: 50%; pointer-events: none; --z: -2; /* depth: base.css */
    background: repeating-radial-gradient(circle, transparent 0 17px, rgba(255, 255, 255, 0.12) 17px 18.5px); }
  .sower .strap { background: linear-gradient(90deg, #DCDCE0, #fff 50%, #DCDCE0); }
  .sower .strap span { color: #000; }
  .sower .meta { color: rgba(255, 255, 255, 0.66); }

  .bio { margin-top: 8px; text-align: center; color: var(--text); }
  /* the award shelf: six places, the empty ones dashed */
  .shelf { margin-top: 14px; padding: 12px 14px 14px; border-radius: var(--r-xl); }
  .shelf.wait { animation: wait 1.2s ease-in-out infinite; }
  @keyframes wait { 50% { opacity: 0.6; } }
  .sh { display: flex; align-items: center; gap: 6px; width: 100%; padding: 6px 0; margin: -6px 0; /* a taller target, same place */ font: 650 15px/1.2 var(--font-text); color: var(--text); text-align: left; }
  .sh b { flex: 1; font-weight: 650; }
  .sh .num { font: 550 13.5px/1.2 var(--font-text); color: var(--text-2); }
  .sh :global(svg) { color: var(--text-3); }
  .row { display: flex; justify-content: space-between; margin-top: 12px; }
  .row button { display: flex; transition: transform var(--t-fast) var(--ease); }
  .row button:active { transform: scale(0.9); }
  .empty { width: 44px; height: 44px; border-radius: 50%; box-shadow: inset 0 0 0 1.5px var(--line); background: var(--surface-2); }
  .nx { display: block; width: 100%; padding: 6px 0; margin: 6px 0 -6px; /* a taller target, same place */ text-align: left; color: var(--text-2); }
</style>
