<script lang="ts">
  import CloseX from '../../ui/CloseX.svelte';
  // The ticket: a pass in the event's colour with the entry QR (KBTU<code>, the organizer's mark in the
  // middle). Opens from the event sheet, Profile → Me, the live capsule and t.me links (tk_<id>).
  // Telegram's Back, a tap outside or Close dismisses it. The pass is lit like the glass: its light and
  // a slight 3D tilt follow the phone, and it leans toward a pressing finger, like a card in Wallet.
  // A real ticket (owner, Nov 3: the flat red card with a huge sparse code was weak): a club with a lanyard of its own
  // prints it in its lanyard's art and colours (lib/awards.ts skinOf, ui/LanyardBand), its medallion top right; the rest
  // in their colour on a security print. The stub tears off at notches and a perforation; its QR is a finer 33×33
  // (Qr minVersion), as dense as the badge's.
  import { onMount } from 'svelte';
  import type { Id } from '../../lib/api';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { eventById, toggleGoing, declineInvite, askDm } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, money, placeOf } from '../../lib/i18n/index.svelte';
  import Ticket from '@lucide/svelte/icons/ticket';
  import { relDay, time, nowTs, multiDay, daySpan } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import { calendarUrl } from '../../lib/calendar';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import Bell from '@lucide/svelte/icons/bell';
  import { glass, recenter } from '../../ui/glass';
  import Qr from '../../ui/Qr.svelte';
  import '../../lib/qrnow'; // its code in the first frame (lib/qr.svelte.ts)
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import OrgMedal from '../../ui/OrgMedal.svelte';
  import LanyardBand from '../../ui/LanyardBand.svelte';
  import LookMark from '../../ui/LookMark.svelte';
  import { skinOf, clubLook, lookVars, QR_LOOK } from '../../lib/awards';
  import guilloche from '../../assets/lanyards/kbtu-guilloche.svg?url';
  import { nameOf } from '../../lib/short';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();

  const e = $derived(eventById(id));
  $effect(() => { overlay.title = t('cap.ticket'); overlay.icon = Ticket; overlay.theme = 'dark'; }); // the capsule (SPEC §8.2), dark as the scrim
  const my = $derived(e?.my);
  const valid = $derived(!!e && e.status !== 'cancelled' && my?.status === 'going' && !!my.ticketCode);
  const started = $derived(!!e && e.startsAt <= nowTs());
  const st = $derived(session.me?.student);
  const holder = $derived(st ? `${st.lastName} ${st.firstName}` : session.me?.name ?? '');
  const skin = $derived(skinOf(e?.org)); // the club's (or school's) lanyard, if it has one

  let wrap: HTMLDivElement;
  let scrim: HTMLDivElement;
  let pass = $state<HTMLDivElement>();
  let gone = false;

  onMount(() => {
    recenter(); // the card opens face on, however the phone is held
    haptic.soft();
    wrap.animate([{ opacity: 0, transform: 'translate3d(0,70px,0) scale(0.92)' }, { opacity: 1, transform: 'none' }],
      { duration: 480, easing: 'cubic-bezier(.2,.9,.25,1.1)' });
    scrim.animate([{ opacity: 0 }, { opacity: 1 }], { duration: 240, easing: 'ease-out' });
    return hideChrome();
  });

  function leave() {
    if (gone) return;
    gone = true;
    wrap.animate([{ opacity: 1, transform: 'none' }, { opacity: 0, transform: 'translate3d(0,60px,0) scale(0.94)' }],
      { duration: 240, easing: 'cubic-bezier(.4,0,1,1)', fill: 'forwards' });
    const a = scrim.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 240, easing: 'ease-in', fill: 'forwards' });
    a.onfinish = () => removeOverlay(overlay.id);
  }
  $effect(() => { if (overlay.closing) leave(); });

  // the pass leans toward the finger (≤ 5°) and gives a little; it springs back on release
  function press(ev: PointerEvent) {
    if (!pass) return;
    const r = pass.getBoundingClientRect();
    pass.style.setProperty('--px', (((ev.clientX - r.left) / r.width) * 2 - 1).toFixed(2));
    pass.style.setProperty('--py', (((ev.clientY - r.top) / r.height) * 2 - 1).toFixed(2));
    pass.style.setProperty('--ps', '0.985');
  }
  function release() {
    if (!pass) return;
    for (const v of ['--px', '--py']) pass.style.setProperty(v, '0');
    pass.style.setProperty('--ps', '1');
  }

  async function cancelReg() {
    if (e?.meeting) { // a club meeting (§2b): "can't make it" says why
      const why = await sheets.askText({ title: t('meet.whyTitle'), text: t('meet.whyText'), ok: t('meet.send'), cancel: t('common.cancel'),
        placeholder: t('meet.whyPh'), max: 140 });
      if (!why) return;
      declineInvite(id, why);
      close(overlay.id);
      return;
    }
    const yes = await sheets.ask({ title: t('tk.cancelAsk'), text: t('tk.cancelText'), ok: t('tk.cancelGo'), cancel: t('tk.keep'), danger: true });
    if (!yes) return;
    toggleGoing(id);
    close(overlay.id);
  }
</script>

<div class="scrim" bind:this={scrim} style="--tint:{e?.tint ?? '#3B6BFF'}" onclick={() => close(overlay.id)} role="presentation"></div>
<div class="wrap" bind:this={wrap}>
  <div class="page">
  {#if e}
    <div class="stage">
      <div class="pass {skin ?? 'plain'}" class:club={!!skin && !!clubLook(skin)} bind:this={pass} style="--tint:{e.tint}; {skin ? lookVars(skin) : ''}" use:glass role="group" aria-label={t('event.ticket')}
           onpointerdown={press} onpointerup={release} onpointercancel={release} onpointerleave={release}>
        <div class="main">
          {#if skin}<LanyardBand look={skin} wide qr />{:else}<img class="gl" src={guilloche} alt="" />{/if}
          <span class="medal">{#if skin}<OrgMedal look={skin} logo={e.org.logo ?? null} />{:else}<span class="rim"><OrgLogo org={e.org} size={44} /></span>{/if}</span>
          <button class="head" onclick={() => sheets.event(id)}>
            <span class="org ellipsis">{nameOf(e.org)}</span>
            <span class="ttl clamp-2">{e.title}</span>
          </button>
          <div class="facts">
            <div><i>{t('tk.when')}</i><b>{multiDay(e.startsAt, e.endsAt) ? daySpan(e.startsAt, e.endsAt) : relDay(e.startsAt) + ', ' + time(e.startsAt)}</b></div>
            <div><i>{t('tk.where')}</i><b>{placeOf(e.place)}{e.price ? ' · ' + (e.my?.free ? t('event.freeMine') : money(e.price)) : ''}</b></div>
          </div>
        </div>
        <!-- the stub: torn off at the notches along the perforation -->
        <div class="stub">
          <i class="perf" aria-hidden="true"></i>
          {#if valid && my?.ticketCode}
            <div class="qrbox" class:used={!!my.checkedInAt}>
              <Qr text={'KBTU' + my.ticketCode} minVersion={4} tone={skin ? QR_LOOK[skin] : undefined}>{#if skin}<LookMark look={skin} />{:else}<OrgLogo org={e.org} />{/if}</Qr>
              {#if my.checkedInAt}<span class="stamp">✓ {t('tk.checkedIn', { time: time(my.checkedInAt) })}</span>{/if}
            </div>
            <div class="facts foot">
              <div><i>{t('tk.holder')}</i><b class="ellipsis">{holder}</b></div>
              <div class="code"><i>{t('tk.code')}</i><b class="num">{my.ticketCode.replace(/^(\w{3})(\w{3})$/, '$1 $2')}</b></div>
            </div>
          {:else}
            <p class="void">{e.status === 'cancelled' ? t('event.cancelledLong') : t('tk.none')}</p>
          {/if}
        </div>
      </div>
    </div>

    {#if valid && !my?.checkedInAt}<p class="hint">{t('tk.hint')}</p>{/if}
    <!-- the receipt looks wrong (§4.3): why, and another file in its place, in the pay sheet -->
    {#if valid && my?.receiptFlags?.length}<button class="pill glass glass-pill doubt" use:glass onclick={() => { close(overlay.id); sheets.pay(id); }}><TriangleAlert size={17} />{t('tk.receiptDoubt')}</button>{/if}
    <!-- the bot may not write yet: no reminders, no ticket in the chat -->
    {#if valid && !started && session.me && !session.me.canDm}<button class="pill glass glass-pill" use:glass onclick={() => askDm(id, true)}><Bell size={17} />{t('tk.dmOn')}</button>{/if}
    <div class="acts">
      {#if valid && !started}
        <button class="pill glass glass-pill" use:glass onclick={() => openLink(calendarUrl(e))}><CalendarPlus size={18} />{t('tk.calendar')}</button>
        <button class="pill glass glass-pill danger" use:glass onclick={cancelReg}>{t('event.cancelReg')}</button>
      {/if}
    </div>
  {/if}
  </div>
  <CloseX onclick={() => close(overlay.id)} />
</div>

<style>
  /* the blur turns whatever is underneath (usually the event sheet's text) into soft colour */
  .scrim {
    --dim: rgba(3, 4, 10, 0.78);
    position: absolute; inset: 0; z-index: var(--z-sheet);
    background: radial-gradient(70% 45% at 50% 40%, color-mix(in srgb, var(--tint) 38%, transparent), transparent 72%), var(--dim);
    -webkit-backdrop-filter: blur(18px) saturate(120%); backdrop-filter: blur(18px) saturate(120%);
  }
  :global(html.lowfx) .scrim { --dim: rgba(3, 4, 10, 0.92); -webkit-backdrop-filter: none; backdrop-filter: none; }
  @supports not (background: color-mix(in srgb, red 50%, blue)) {
    .scrim { background: var(--dim); }
  }
  .wrap { position: absolute; inset: 0; z-index: var(--z-sheet); pointer-events: none; display: flex; flex-direction: column; padding-bottom: var(--close-room); }
  /* the content scrolls in a box that ends above the × (--close-room): a long text or a short phone never puts a
     button under it; it fades out above it. Taps on its empty space still reach the scrim (closes) */
  .page { flex: 1; min-height: 0; overflow-x: hidden; overflow-y: auto; scrollbar-width: none; pointer-events: none; display: flex; flex-direction: column; align-items: center;
    gap: 14px; padding: calc(var(--top) + 8px) 20px 20px;
    -webkit-mask-image: linear-gradient(black calc(100% - 20px), transparent); mask-image: linear-gradient(black calc(100% - 20px), transparent); }
  .page::-webkit-scrollbar { display: none; }
  .page > :global(*) { pointer-events: auto; }
  .page > :global(:first-child) { margin-top: auto; }
  .page > :global(:last-child) { margin-bottom: auto; }
  .stage { perspective: 900px; }

  /* the ticket: the main part over the stub, one material; each part cut by its own mask (half a notch each side of the
     perforation), the shadow on the pass round both. Its colour is --base: the club's lanyard, else the event's tint */
  .pass {
    --base: var(--tint); --r: 26px; --notch: 12px;
    /* the text's colours: white on the colour; a lanyard's own (lookVars: dark on Shade's paper) below */
    --t1: white; --t2: rgba(255, 255, 255, 0.72); --t3: rgba(255, 255, 255, 0.86); --tsh: 0 1px 2px rgba(0, 0, 0, 0.3);
    position: relative; width: min(340px, calc(100vw - 40px)); border-radius: var(--r); color: var(--t1);
    box-shadow: 0 34px 60px -22px rgba(0, 0, 0, 0.75), 0 10px 24px -12px rgba(0, 0, 0, 0.45);
    transform: rotateX(calc(var(--gy, 0) * -7deg + var(--py, 0) * 5deg)) rotateY(calc(var(--gx, 0) * 9deg - var(--px, 0) * 5deg)) scale(var(--ps, 1));
    transition: transform 160ms ease-out;
    touch-action: manipulation;
  }
  .main, .stub { position: relative; overflow: hidden; isolation: isolate; }
  .main { min-height: 178px; padding: 26px 18px 18px; border-radius: var(--r) var(--r) 0 0;
    background: radial-gradient(110% 80% at 0% 0%, rgba(255, 255, 255, 0.24), transparent 55%), radial-gradient(80% 90% at 100% 100%, rgba(0, 0, 0, 0.3), transparent 65%),
      linear-gradient(155deg, rgba(255, 255, 255, 0.16), transparent 45%, rgba(0, 0, 0, 0.36)), var(--base);
    -webkit-mask: radial-gradient(circle at 0 100%, transparent var(--notch), black calc(var(--notch) + 0.5px)) left / 51% 100% no-repeat,
      radial-gradient(circle at 100% 100%, transparent var(--notch), black calc(var(--notch) + 0.5px)) right / 51% 100% no-repeat;
    mask: radial-gradient(circle at 0 100%, transparent var(--notch), black calc(var(--notch) + 0.5px)) left / 51% 100% no-repeat,
      radial-gradient(circle at 100% 100%, transparent var(--notch), black calc(var(--notch) + 0.5px)) right / 51% 100% no-repeat; }
  .stub { padding: 20px 18px 16px; border-radius: 0 0 var(--r) var(--r);
    background: radial-gradient(90% 60% at 50% 0%, rgba(255, 255, 255, 0.08), transparent 70%),
      linear-gradient(180deg, rgba(0, 0, 0, 0.22), rgba(0, 0, 0, 0.45)), var(--base);
    -webkit-mask: radial-gradient(circle at 0 0, transparent var(--notch), black calc(var(--notch) + 0.5px)) left / 51% 100% no-repeat,
      radial-gradient(circle at 100% 0, transparent var(--notch), black calc(var(--notch) + 0.5px)) right / 51% 100% no-repeat;
    mask: radial-gradient(circle at 0 0, transparent var(--notch), black calc(var(--notch) + 0.5px)) left / 51% 100% no-repeat,
      radial-gradient(circle at 100% 0, transparent var(--notch), black calc(var(--notch) + 0.5px)) right / 51% 100% no-repeat; }
  /* the perforation: round holes punched between the notches */
  .perf { position: absolute; top: -1.5px; left: calc(var(--notch) + 8px); right: calc(var(--notch) + 8px); height: 3px;
    background: radial-gradient(circle, rgba(0, 0, 0, 0.55) 1.3px, transparent 1.6px) 0 50% / 9px 3px repeat-x; }
  /* a sheen across both parts that slides with the tilt (the badge's) */
  .main::after, .stub::after { content: ''; position: absolute; top: 0; bottom: 0; left: 0; width: 260%; z-index: 4; pointer-events: none;
    background: linear-gradient(115deg, transparent 32%, rgba(255, 255, 255, 0.12) 46%, transparent 60%);
    transform: translateX(calc(-30.769% - var(--gx, 0) * 27.692%)); }

  /* a club's lanyard: its art under the text (LanyardBand), its card's colours (lookVars) */
  .club { --base: var(--c2); --t1: var(--ink); --t2: var(--ink2); --t3: var(--role); }
  .club .main { background: linear-gradient(155deg, var(--c1), var(--c2) 55%, var(--c3)); }
  .club .stub { background: radial-gradient(90% 60% at 50% 0%, rgba(255, 255, 255, 0.1), transparent 70%), linear-gradient(180deg, var(--c2), var(--c3)); }
  .cheer { --base: rgb(24, 26, 52); --t3: rgb(255, 200, 61); }
  .knights { --base: rgb(20, 50, 112); --t3: rgb(232, 196, 120); }
  .moments { --base: rgb(58, 33, 22); --t3: rgb(244, 217, 190); }
  .faces { --base: rgb(22, 12, 34); --t3: rgb(255, 155, 214); }
  .studex { --base: rgb(16, 39, 90); }
  .gl { position: absolute; inset: 0; z-index: -1; width: 100%; height: 100%; opacity: 0.16; mix-blend-mode: screen; pointer-events: none; }

  .medal { position: absolute; z-index: 3; top: 16px; right: 16px; width: 52px; height: 52px; }
  /* a club without a lanyard: its logo set in a silver rim, as a medallion */
  .rim { display: block; padding: 3px; border-radius: var(--r-m); background: linear-gradient(145deg, white, rgb(176, 184, 202) 42%, rgb(244, 246, 251) 62%, rgb(140, 150, 172));
    box-shadow: 0 12px 20px -10px rgba(0, 0, 0, 0.7), 0 2px 5px rgba(0, 0, 0, 0.28); }
  .rim :global(.logo) { border-radius: var(--r-s) !important; }
  .head, .main .facts { position: relative; z-index: 3; text-shadow: var(--tsh); }
  .head { display: flex; flex-direction: column; gap: 6px; width: 100%; padding-right: 60px; text-align: left; }
  .org { display: block; font: 760 var(--fs-tab)/1.3 var(--font-text); letter-spacing: 0.12em; text-transform: uppercase; color: var(--t3); }
  .ttl { font: 780 var(--fs-sec)/1.12 var(--font-display); letter-spacing: -0.025em; }

  .facts { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 16px; }
  .facts div { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .facts i { font: 650 var(--fs-tab)/1.2 var(--font-text); font-style: normal; letter-spacing: 0.08em; text-transform: uppercase; color: var(--t2); }
  .facts b { font: 640 var(--fs-body)/1.3 var(--font-text); }
  .foot { margin-top: 14px; }
  .code { text-align: right; }
  .code b { letter-spacing: 0.08em; }

  /* the QR on its white plate, the code's own quiet zone in it */
  .qrbox { position: relative; width: min(232px, 100%); margin: 0 auto; padding: 12px; border-radius: var(--r-l); background: white;
    box-shadow: 0 16px 30px -18px rgba(0, 0, 0, 0.7), inset 0 0 0 1px rgba(0, 0, 0, 0.05); }
  .qrbox.used :global(.qr) { opacity: 0.25; }
  .stamp {
    position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%) rotate(-8deg); white-space: nowrap;
    padding: 8px 14px; border-radius: 12px; border: 2px solid var(--success); color: #13884A; background: rgba(255, 255, 255, 0.92);
    font: 750 15px/1 var(--font-text);
  }
  .void { padding: 22px 0 8px; text-align: center; font: 620 var(--fs-body)/1.35 var(--font-text); color: var(--t2); }
  @media (max-width: 359px) { .main, .stub { padding-left: 16px; padding-right: 16px; } .ttl { font-size: var(--fs-t3); } .qrbox { width: 210px; } }

  .hint { font: 550 13px/1.3 var(--font-text); color: rgba(255, 255, 255, 0.62); }
  .acts { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }
  .pill { position: relative; display: inline-flex; align-items: center; gap: 8px; height: 44px; padding: 0 24px; border-radius: var(--r-full); color: #fff; font: 650 15px/1 var(--font-text); background-color: rgba(255, 255, 255, 0.1); }
  .pill:active { transform: scale(0.96); }
  .danger { color: #FF8A80; background-color: rgba(255, 69, 58, 0.16); }
  .doubt { height: 40px; padding: 0 18px; color: #FFD27A; background-color: rgba(255, 176, 32, 0.18); font-size: 14px; }
</style>
