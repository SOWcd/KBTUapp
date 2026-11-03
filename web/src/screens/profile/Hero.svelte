<script lang="ts">
  import { tick, untrack } from 'svelte';
  import ChevronRight from '@lucide/svelte/icons/chevron-right';
  // The profile hero, shared by Me and the person sheet (owner's pick of three): the profile as a KBTU
  // event badge on a lanyard — clubs print their titles in English on theirs, so this one does too. It hangs
  // from the capsule or the sheet's grip, swings in from the clip, then follows the phone's tilt; the
  // holographic strip is the only iridescence and stays inside the card. Data: lib/awards.ts.
  // Every card carries its organisation's medallion in the corner (OrgMedal). Your own badge (`qr`, on Me) has its QR
  // on the back: a tap on the card or the medallion turns it over to the full-screen QR (MyQr). The code holds only a
  // link into the app (your profile), never a student ID. Other people's cards never show it.
  import type { PersonCard } from '../../lib/api';
  import { hero, founderItem, ideaItem } from '../../lib/awards';
  import { glass } from '../../ui/glass';
  import Avatar from '../../ui/Avatar.svelte';
  import Frame from '../../ui/Frame.svelte';
  import Founder from '../../ui/Founder.svelte';
  import Award from '../../ui/Award.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { session } from '../../lib/state/session.svelte';
  import OrgMedal from '../../ui/OrgMedal.svelte';
  import QrCode from '@lucide/svelte/icons/qr-code';
  import LanyardBand from '../../ui/LanyardBand.svelte';
  import LanyardHolo from '../../ui/LanyardHolo.svelte';
  import { lookOf, STRAP, banded, clubLook, lookVars, orgOfLook, SOWER } from '../../lib/awards';
  import SowerArt from '../../ui/SowerArt.svelte';
  import { t } from '../../lib/i18n/index.svelte';
  import { haptic } from '../../lib/tg';
  import { api } from '../../lib/api';
  import { say, overlays, moment, backTo } from '../../lib/state/ui.svelte';
  import CardBack from '../../ui/CardBack.svelte';
  import { burst } from '../../ui/burst';
  import jccPhoto from '../../assets/lanyards/jcc-top-photo.webp';
  import jccLeft from '../../assets/lanyards/jcc-top-left.webp';
  import jccRight from '../../assets/lanyards/jcc-top-right.webp';

  // qr: my badge QR code (Me only; me.qr), a random code a door scanner checks, so an id can't be turned into a QR.
  // live: the badge's screen is open (Me: the Profile tab; a sheet: always). onphoto: my photo tapped (Me: settings, or
  // the photo's menu at it while they're open)
  let { p, qr = null, live = true, shelf = true, onphoto }: { p: PersonCard; qr?: string | null; live?: boolean; shelf?: boolean; onphoto?: (el: Element) => void } = $props();
  const h = $derived(hero(p));
  // the club badge they picked (a skin; picked in Me's settings), else the KBTU one
  const look = $derived(lookOf(p)); // the lanyard picked
  // the one on show: it trails `look` while a new one is put on, so the old face turns away before the new one shows
  let face = $state(untrack(() => look));
  const club = $derived(clubLook(face)); // a template club's lanyard: its colours ride in CSS variables (lookVars)
  const mine = $derived(!!qr);
  const medalLogo = $derived(orgOfLook(p, face)?.logo ?? null); // the medallion: the org's own avatar (OrgMedal decides)
  const link = $derived(`https://t.me/KBTUappBot?startapp=u_${qr}`);

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
  // the card's back (round 5, owner: the edge-on turn into the full-screen QR was flat and empty in the middle): a real
  // two-sided badge. A tap turns it a whole half turn in 3D, lifted toward you at the edge, the face darkening as it turns
  // away and the back coming out of the shade with a sheen; the back carries my QR big enough to scan on the card. A tap
  // on the code opens the full-screen one (MyQr) for a door's scanner; a tap elsewhere on the back, or Back, turns it face
  // on. The resting pose is the class (.flipped), the motion only a WAAPI layer over it, so a cancelled or interrupted
  // turn always lands face on or back on, never edge-on (53a0929's lesson).
  let flipped = $state(false), side = $state(false), card: HTMLDivElement, bshade = $state<HTMLElement>(), strap: HTMLDivElement, clipEl: HTMLDivElement; // the back is mine only
  const DARK = 'linear-gradient(100deg, rgba(0, 0, 0, 0.9), rgba(0, 0, 0, 0.5))', LIGHT = 'linear-gradient(100deg, rgba(255, 255, 255, 0), rgba(255, 255, 255, 0.24))';
  function flip(to: boolean) {
    if (spinning || flipped === to) return;
    haptic.soft();
    flipped = to;
    // which side is drawn: switched at the edge-on moment (45% in), when neither shows
    clearTimeout(sideAt);
    if (still()) { side = to; return; }
    sideAt = setTimeout(() => (side = to), 720 * 0.45);
    spinning = true;
    const from = to ? 0 : 180, end = to ? 180 : 0;
    card.style.willChange = 'transform';
    // a little past the end and back, as a badge on a strap settles (owner, Nov 3: the turn wants finishing); the strap
    // and the clip twist with it, edge-on at the half turn (they hung still while the card turned under them)
    const over = to ? 8 : -8;
    const turn = card.animate([{ transform: `rotateY(${from}deg)` }, { transform: `translateZ(46px) rotateY(${(from + end) / 2}deg) scale(1.02)`, offset: 0.45 },
      { transform: `rotateY(${end + over}deg)`, offset: 0.8 }, { transform: `rotateY(${end}deg)` }], { duration: 720, easing: 'cubic-bezier(.45, .05, .25, 1)' });
    for (const el of [strap, clipEl]) el.animate([{ transform: 'scaleX(1)' }, { transform: 'scaleX(0.12)', offset: 0.45 }, { transform: 'scaleX(1)', offset: 0.8 }, { transform: 'scaleX(1)' }],
      { duration: 720, easing: 'cubic-bezier(.45, .05, .25, 1)' });
    const [gone, come] = to ? [shade, bshade!] : [bshade!, shade];
    gone.animate([{ opacity: 0 }, { opacity: 0.6, offset: 0.45 }, { opacity: 0.6 }], { duration: 720, easing: 'ease-in' });
    come.animate([{ opacity: 0.6, background: DARK }, { opacity: 0.6, background: DARK, offset: 0.45 }, { opacity: 0.5, background: LIGHT, offset: 0.7 },
      { opacity: 0, background: LIGHT }], { duration: 720 });
    const done = () => { card.style.willChange = ''; spinning = false; clearTimeout(sideAt); side = flipped; };
    turn.onfinish = done;
    turn.oncancel = done;
  }
  let sideAt: ReturnType<typeof setTimeout> | undefined;
  const toBack = () => flip(true);
  function cardTap(e: MouseEvent) {
    if (!(e.target as Element).closest('button')) toBack(); // the photo, the seal and the medallion have their own
  }
  function backTap(e: MouseEvent) {
    if (!(e.target as Element).closest('button')) flip(false); // the code opens the full-screen one
  }
  // Back turns it face on; leaving the screen does too, at once
  $effect(() => {
    if (!flipped) return;
    const f = () => flip(false);
    backTo.fn = f;
    return () => { if (backTo.fn === f) backTo.fn = null; };
  });
  $effect(() => { if (!live) untrack(() => { if (flipped) { card.getAnimations().forEach((x) => x.cancel()); flipped = side = false; } }); });
  $effect(() => {
    if (look === untrack(() => face) || spinning) return;
    if (still()) face = look;
    else spin();
  });
</script>

<!-- JCC's top layer (round 5, their own split): their sakura over the photo, its frame and the strip, where their mock puts
     it; part of their lanyard, not a frame (a frame worn with it stays under it) -->
{#snippet sakura()}{#if face === 'japanesecultureclub'}<img class="jt jp" src={jccPhoto} alt="" />{/if}{/snippet}

<section class="h">
<div class="hang {face} {face === 'sower' ? 'sw-' + SOWER : ''}" class:club={!!club} style={lookVars(face)} class:rest={!live || !seen || covered}>
  <div class="swing" bind:this={swing}>
    <div class="strap" bind:this={strap} aria-hidden="true"><span>{STRAP[face]}</span></div>
    <!-- on mine a tap on the card shows its back (the medallion is the button for screen readers and keyboards) -->
    <div class="card" class:flipped class:sb={side} bind:this={card}>
    <div class="badge" use:glass onclick={mine ? cardTap : undefined} role="presentation" inert={flipped}>
      {#if face === 'sower'}<SowerArt wide />{/if}
      {#if banded(face)}<LanyardBand look={face} wide qr />{/if}
      <span class="slot" aria-hidden="true"></span>
      <!-- the organisation's medallion where the QR was (owner, Nov 2); on mine it turns the card over to its back, the
           full-screen QR (MyQr), as a tap anywhere on the card does -->
      {#if mine}<button class="medal" onclick={toBack} aria-label={t('me.qr')}><OrgMedal look={face} logo={medalLogo} /><span class="qrhint"><QrCode size={10} strokeWidth={2.4} /></span></button>
      {:else}<span class="medal"><OrgMedal look={face} logo={medalLogo} /></span>{/if}
      <div class="top" class:mine>
        {#if mine}<button class="photo" onclick={(e) => onphoto?.(e.currentTarget)} aria-label={t('look.photo')}><Avatar person={h.person} size={74} tappable={false} /><Frame id={h.frame} />{@render sakura()}</button>
        {:else}<span class="photo"><Avatar person={h.person} size={86} tappable={false} /><Frame id={h.frame} />{@render sakura()}</span>{/if}
        <span class="id">
          <b class="nm"><span class="ellipsis">{h.name}</span>{#if h.status}<button class="seal" onclick={() => sheets.award(p.founder ? founderItem() : ideaItem(), p.id === session.me?.id)} aria-label={h.status}><Founder size={19} idea={!p.founder} /></button>{/if}</b>
          {#if h.nick}<span class="meta nick ellipsis">{h.nick}</span>{/if}<!-- the real name first, the nick under it (owner, Nov 2) -->
          <span class="role clamp">{h.title}</span>
          <span class="meta clamp">{h.line}</span>
        </span>
      </div>
      <span class="foot"><LanyardHolo look={face} no={h.no} />{#if face === 'japanesecultureclub'}<img class="jt jl" src={jccLeft} alt="" /><img class="jt jr" src={jccRight} alt="" />{/if}</span>
      <i class="shade" bind:this={shade} aria-hidden="true"></i>
    </div>
    <!-- the back, mine only (ui/CardBack): my QR on a white plate, big enough to scan here; my name and number beside it,
         the medallion the button that turns the card face on -->
    {#if mine}
      <div class="back" onclick={backTap} role="presentation" inert={!flipped}>
        <CardBack look={face} name={h.name} title={h.title} line={h.line} no={h.no} text={link} lazy logo={medalLogo}
          onplate={() => sheets.myQr(link, p)} plateLabel={t('me.qr')} onmedal={() => flip(false)} medalLabel={t('me.cardFront')} />
        <i class="bshade" bind:this={bshade} aria-hidden="true"></i>
      </div>
    {/if}
    </div>
    <div class="clip" bind:this={clipEl} aria-hidden="true"></div>
  </div>
</div>

<!-- data-away: these leave while Me's settings are open -->
{#if h.bio}<p class="t-callout bio" data-away>{h.bio}</p>{/if}

<!-- the award shelf: the showcase with empty places to fill, the count, and on mine the closest next
     award; mine opens the whole collection. Someone else's shows only when there's something on it. -->
{#if shelf && (mine || h.shelf.length)}
  <div class="shelf surface" class:wait={!h.loaded} data-away>
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
  .hang { --kb: linear-gradient(155deg, #2A4FD6, #121A3D 72%); display: flex; flex-direction: column; align-items: center; perspective: 900px; margin-top: -14px; padding-top: 52px; }
  /* the word sits clear of the clip (it hid behind it at the bottom) */
  /* the strap swings with the card, from its top (owner, Oct 29: it stood still while the card moved) */
  .strap { position: absolute; top: -52px; left: 50%; margin-left: -13px; width: 26px; height: 52px; display: flex; justify-content: center; align-items: center; padding-bottom: 4px; overflow: hidden;
    background: linear-gradient(90deg, #1B36A0, #3B6BFF 50%, #1B36A0); box-shadow: 0 2px 6px rgba(0, 0, 0, 0.25); }
  .strap span { writing-mode: vertical-rl; transform: rotate(180deg); font: 800 7.5px/26px var(--font-text); letter-spacing: 0.22em; color: rgba(255, 255, 255, 0.8); white-space: nowrap; }
  /* the clip swings with the card, down into its slot (owner, Oct 29: it hung above it) */
  .clip { position: absolute; z-index: 2; top: -1px; left: 50%; width: 36px; height: 15px; margin-left: -18px; border-radius: 5px;
    background: linear-gradient(180deg, #F4F6FB, #9AA4B8); box-shadow: 0 2px 5px rgba(0, 0, 0, 0.4), inset 0 1px 0 #fff; }
  .swing { position: relative; width: min(340px, 100%); transform-origin: 50% -52px; perspective: 1100px; } /* the card's turn in depth */

  /* the two-sided card: the face and the back share one 3D turn; each hides its own back side */
  .card { position: relative; transform-style: preserve-3d; }
  .card.flipped { transform: rotateY(180deg); }
  .badge, .back { backface-visibility: hidden; -webkit-backface-visibility: hidden; }
  /* the face turned away also goes invisible at the half turn: WebKit draws a layered child (JCC's sakura, the art's
     parallax) through its parent's hidden backface, mirrored over the other side (JCC, Nov 3) */
  .card.sb .badge, .card:not(.sb) .back { visibility: hidden; }
  .back { position: absolute; inset: 0; z-index: 1; overflow: hidden; border-radius: 22px; transform: rotateY(180deg);
    box-shadow: 0 30px 50px -26px rgba(0, 0, 0, 0.75); }
  .bshade { position: absolute; inset: 0; z-index: 4; pointer-events: none; opacity: 0; border-radius: inherit; background: linear-gradient(100deg, rgba(0, 0, 0, 0.9), rgba(0, 0, 0, 0.5)); }
  .badge {
    position: relative; overflow: hidden; padding: 26px 0 14px; border-radius: 22px; color: #fff;
    background: radial-gradient(110% 90% at 0% 0%, rgba(124, 77, 255, 0.6), transparent 55%), var(--kb);
    box-shadow: 0 30px 50px -26px rgba(0, 0, 0, 0.75), 0 10px 22px -14px rgba(16, 22, 51, 0.6), inset 0 1px 0 rgba(255, 255, 255, 0.28);
    transform: rotateX(calc(var(--gy, 0) * -6deg)) rotateY(calc(var(--gx, 0) * 8deg));
    transition: transform 160ms ease-out;
  }
  /* the light on a lanyard turning over (the spin above): unseen at rest */
  .shade { position: absolute; inset: 0; z-index: 2; pointer-events: none; opacity: 0; border-radius: inherit;
    background: linear-gradient(100deg, rgba(0, 0, 0, 0.9), rgba(0, 0, 0, 0.5)); }
  /* a sheen that slides with the tilt */
  /* moved, not repainted: the band is its own layer 260% wide, slid by transform exactly where background-position
     50% + gx * 45% put it (a 260% background at p sits at -1.6 widths * p). Painted into the card, it re-rasterised the
     whole card with its art on every tilt frame */
  .badge::after { content: ''; position: absolute; top: 0; bottom: 0; left: 0; width: 260%; pointer-events: none;
    background: linear-gradient(115deg, transparent 32%, rgba(255, 255, 255, 0.13) 46%, transparent 60%);
    transform: translateX(calc(-30.769% - var(--gx, 0) * 27.692%)); will-change: transform; }
  .slot { position: absolute; z-index: 1; top: 9px; left: 50%; width: 46px; height: 8px; margin-left: -23px; border-radius: 4px;
    background: rgba(5, 8, 20, 0.55); box-shadow: inset 0 1px 2px rgba(0, 0, 0, 0.7), 0 1px 0 rgba(255, 255, 255, 0.16); }
  /* round 5: the name and the role give way to the medallion (its 66 px corner; 52 px, was 58: it outweighed the photo),
     the course line has the card's width; the role and the course line wrap to two lines at most (owner: long names fit) */
  .top { position: relative; display: flex; gap: 14px; align-items: center; padding: 0 18px; }
  /* Cheerleading and Knights: their art is the card's background (LanyardBand), under everything here */
  .foot { position: relative; display: block; margin: 16px 18px 0; } /* above the art (LanyardBand) */
  .medal { position: absolute; z-index: 1; top: 14px; right: 14px; width: 52px; height: 52px; transition: transform var(--t-fast) var(--ease); }
  button.medal:active { transform: scale(0.92); }
  /* the back is a QR: a small chip on the medallion's corner says so */
  .qrhint { position: absolute; right: -5px; bottom: -5px; display: grid; place-items: center; width: 18px; height: 18px; border-radius: 50%;
    background: white; color: rgb(14, 20, 48); box-shadow: 0 2px 6px rgba(0, 0, 0, 0.35); }

  .photo { position: relative; z-index: 1; flex: none; padding: 3px; border-radius: 21px; background: rgba(255, 255, 255, 0.16); }
  .cheer .photo, .knights .photo, .moments .photo, .faces .photo, .studex .photo, .sower .photo { background: #fff; }
  .photo :global(.av), .photo :global(.av img), .photo :global(.ini) { border-radius: 18px; }
  .id { display: block; flex: 1; min-width: 0; }
  .nm, .id > .role { padding-right: 54px; } /* the medallion: 14 + 52 in from the edge, less the row's 18 px, and a gap */
  .nm { display: flex; align-items: center; gap: 7px; min-width: 0; font: 780 22px/1.12 var(--font-display); letter-spacing: -0.025em; }
  .nick, .role, .meta { display: block; }
  .role { margin-top: 6px; }
  .meta { margin-top: 3px; }
  .clamp { display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; overflow: hidden; overflow-wrap: anywhere; }
  .nm :global(svg) { flex: none; }
  .seal { flex: none; display: inline-flex; padding: 10px; margin: -10px; transition: transform var(--t-fast) var(--ease); } /* a 39 px target */
  .seal:active { transform: scale(0.88); }
  .role { font: 760 10.5px/1.3 var(--font-text); letter-spacing: 0.12em; text-transform: uppercase; }
  .meta { font: 550 13px/1.3 var(--font-text); color: rgba(255, 255, 255, 0.72); }
  .meta.nick { margin-top: 1px; font-weight: 650; }
  .top.mine .nm { font-size: 20px; }
  @media (max-width: 359px) { .nm { font-size: 20px; } }

  /* below the band, each look's own body and role colour; the strap's colours (the band and the strip: LanyardBand,
     LanyardHolo) */
  .role { color: var(--role, #A9C0FF); }
  .cheer { --role: #FFC83D; }
  .cheer .strap { background: linear-gradient(90deg, rgb(20, 22, 44), rgb(46, 50, 88) 50%, rgb(20, 22, 44)); box-shadow: inset 1px 0 0 rgba(232, 192, 98, 0.45), inset -1px 0 0 rgba(232, 192, 98, 0.45), 0 2px 6px rgba(0, 0, 0, 0.25); } /* their navy, gold stitches at the edges */
  .cheer .strap span { color: rgb(255, 200, 61); }
  .knights { --role: rgb(232, 196, 120); } /* round 5b: their navy, a knight's gold */
  .knights .strap { background: linear-gradient(90deg, rgb(11, 29, 68), rgb(30, 74, 158) 50%, rgb(11, 29, 68)); box-shadow: inset 1px 0 0 rgba(232, 196, 120, 0.6), inset -1px 0 0 rgba(232, 196, 120, 0.6), 0 2px 6px rgba(0, 0, 0, 0.25); }
  .knights .strap span { letter-spacing: 0.12em; color: rgb(232, 196, 120); } /* seven letters on the short strap */
  .moments { --role: #F4D9BE; }
  .moments .meta { color: rgba(255, 255, 255, 0.84); } /* with the darker column behind it (LanyardBand), 4.5:1 */
  .moments .strap { background: repeating-linear-gradient(180deg, transparent 0 3px, rgba(233, 210, 186, 0.8) 3px 6px, transparent 6px 8px) 3px 0 / 3px 100% no-repeat, repeating-linear-gradient(180deg, transparent 0 3px, rgba(233, 210, 186, 0.8) 3px 6px, transparent 6px 8px) calc(100% - 3px) 0 / 3px 100% no-repeat, rgb(27, 19, 16); } /* round 5b: a strip of film */
  .moments .strap span { color: rgb(242, 179, 92); letter-spacing: 0.12em; }
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
  /* SOWER, the creator's alone (round 5b, owner: "redo everything"; ui/SowerArt, lib/awards.ts SOWER): holo, black titanium
     and holographic foil; gold, black lacquer and gold leaf */
  .sower { --role: rgb(212, 218, 232); }
  .sower .meta { color: rgba(255, 255, 255, 0.66); }
  .sower .badge { background: rgb(0, 0, 0); }
  .sower .strap { background: linear-gradient(90deg, rgb(18, 18, 22), rgb(42, 42, 49) 50%, rgb(18, 18, 22)); box-shadow: inset 1px 0 0 rgba(199, 166, 255, 0.7), inset -1px 0 0 rgba(166, 255, 224, 0.6), 0 2px 6px rgba(0, 0, 0, 0.3); }
  .sower .strap span { color: rgb(232, 234, 240); letter-spacing: 0.3em; }
  .sw-gold { --role: rgb(232, 196, 120); }
  .sw-gold .strap { background: linear-gradient(90deg, rgb(10, 8, 6), rgb(30, 26, 18) 50%, rgb(10, 8, 6)); box-shadow: inset 1px 0 0 rgba(232, 196, 120, 0.75), inset -1px 0 0 rgba(232, 196, 120, 0.75), 0 2px 6px rgba(0, 0, 0, 0.3); }
  .sw-gold .strap span { color: rgb(232, 196, 120); }
  /* the template's clubs (lib/awards.ts CLUB_LOOKS, as CSS variables): the card under the band, the strap, the photo's
     ring; the role's colour comes as --role itself */
  .club .badge { background: linear-gradient(155deg, var(--c1), var(--c2) 55%, var(--c3)); }
  .club .strap { background: linear-gradient(90deg, var(--s1), var(--s2) 50%, var(--s1)); }
  .club .strap span { color: var(--s3); letter-spacing: var(--sl); font-size: var(--sf); font-weight: var(--sfw); line-height: var(--slh); white-space: pre; text-align: center; } /* lookVars: two lines, or a long word a size smaller */
  .club .photo { background: var(--ring); }
  .club .badge { color: var(--ink); } /* dark on a light card (Shade's paper) */
  .club .id { text-shadow: var(--tsh); }
  .club .meta { color: var(--ink2); }
  /* JCC's sakura, cut from their 1712 px card (.claude/reports/club-lanyards/cut-jcc-r5.py): placed by their mock's photo
     (124..500 x 183..558) and strip (80..1610 x 738..868), at the strip's 28 px / 130 = 0.2154 px per art px */
  .jt { position: absolute; z-index: 3; max-width: none; pointer-events: none; user-select: none; -webkit-user-select: none; }
  .jp { left: -33%; top: -30.05%; width: 164.9%; height: 162.2%; }
  .jl { left: -10.8px; top: -2.8px; width: 34.5px; height: 36px; }
  .jr { right: -17.2px; top: -35.1px; width: 58.2px; height: 71.1px; }
  .japanesecultureclub .id { position: relative; z-index: 2; } /* the name over the petals */

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
