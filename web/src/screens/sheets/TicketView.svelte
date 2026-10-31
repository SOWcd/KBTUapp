<script lang="ts">
  import CloseX from '../../ui/CloseX.svelte';
  // The ticket: a pass in the event's colour with the entry QR (KBTU<code>, the organizer's mark in the
  // middle). Opens from the event sheet, Profile → Me, the live capsule and t.me links (tk_<id>).
  // Telegram's Back, a tap outside or Close dismisses it. The pass is lit like the glass: its light and
  // a slight 3D tilt follow the phone, and it leans toward a pressing finger, like a card in Wallet.
  import { onMount } from 'svelte';
  import type { Id } from '../../lib/api';
  import { close, removeOverlay, hideChrome, type Overlay } from '../../lib/state/ui.svelte';
  import { eventById, toggleGoing, declineInvite, askDm } from '../../lib/state/data.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, money, placeOf } from '../../lib/i18n/index.svelte';
  import Ticket from '@lucide/svelte/icons/ticket';
  import { relDay, time, nowTs } from '../../lib/time';
  import { haptic, openLink } from '../../lib/tg';
  import { calendarUrl } from '../../lib/calendar';
  import CalendarPlus from '@lucide/svelte/icons/calendar-plus';
  import TriangleAlert from '@lucide/svelte/icons/triangle-alert';
  import Bell from '@lucide/svelte/icons/bell';
  import { glass } from '../../ui/glass';
  import Qr from '../../ui/Qr.svelte';
  import OrgLogo from '../../ui/OrgLogo.svelte';
  import { nameOf } from '../../lib/short';

  let { overlay, id }: { overlay: Overlay; id: Id } = $props();

  const e = $derived(eventById(id));
  $effect(() => { overlay.title = t('cap.ticket'); overlay.icon = Ticket; overlay.theme = 'dark'; }); // the capsule (SPEC §8.2), dark as the scrim
  const my = $derived(e?.my);
  const valid = $derived(!!e && e.status !== 'cancelled' && my?.status === 'going' && !!my.ticketCode);
  const started = $derived(!!e && e.startsAt <= nowTs());
  const st = $derived(session.me?.student);
  const holder = $derived(st ? `${st.lastName} ${st.firstName}` : session.me?.name ?? '');

  let wrap: HTMLDivElement;
  let scrim: HTMLDivElement;
  let pass = $state<HTMLDivElement>();
  let gone = false;

  onMount(() => {
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
  {#if e}
    <div class="stage">
      <div class="pass glass" bind:this={pass} style="--tint:{e.tint}" use:glass role="group" aria-label={t('event.ticket')}
           onpointerdown={press} onpointerup={release} onpointercancel={release} onpointerleave={release}>
        <button class="head" onclick={() => sheets.event(id)}>
          <span class="org"><OrgLogo org={e.org} size={24} /><span class="ellipsis">{nameOf(e.org)}</span></span>
          <span class="ttl clamp-2">{e.title}</span>
        </button>
        <div class="facts">
          <div><i>{t('tk.when')}</i><b>{relDay(e.startsAt)}, {time(e.startsAt)}</b></div>
          <div><i>{t('tk.where')}</i><b>{placeOf(e.place)}{e.price ? ' · ' + (e.my?.free ? t('event.freeMine') : money(e.price)) : ''}</b></div>
        </div>
        <div class="cut" aria-hidden="true"></div>
        {#if valid && my?.ticketCode}
          <div class="qrbox" class:used={!!my.checkedInAt}>
            <Qr text={'KBTU' + my.ticketCode}><OrgLogo org={e.org} /></Qr>
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
  .wrap {
    position: absolute; inset: 0; z-index: var(--z-sheet); pointer-events: none;
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 14px;
    padding: calc(var(--top) + 8px) 20px calc(var(--safe-bottom) + 84px);
  }
  .wrap > :global(*) { pointer-events: auto; }
  .stage { perspective: 900px; }

  .pass {
    position: relative; width: min(340px, calc(100vw - 40px)); padding: 16px 18px 16px; border-radius: 26px; color: #fff;
    background-color: var(--tint);
    background-image: radial-gradient(120% 70% at 15% 0%, rgba(255, 255, 255, 0.22), transparent 60%), linear-gradient(180deg, transparent 35%, rgba(0, 0, 0, 0.3));
    -webkit-backdrop-filter: none; backdrop-filter: none;
    box-shadow: 0 34px 60px -22px rgba(0, 0, 0, 0.7), 0 10px 24px -12px rgba(0, 0, 0, 0.45);
    transform: rotateX(calc(var(--gy, 0) * -7deg + var(--py, 0) * 5deg)) rotateY(calc(var(--gx, 0) * 9deg - var(--px, 0) * 5deg)) scale(var(--ps, 1));
    transition: transform 160ms ease-out;
    touch-action: manipulation;
  }
  .head { display: flex; flex-direction: column; gap: 8px; width: 100%; text-align: left; }
  .org { display: inline-flex; align-items: center; gap: 8px; min-width: 0; font: 620 13px/1.2 var(--font-text); color: rgba(255, 255, 255, 0.86); }
  .ttl { font: 780 21px/1.15 var(--font-display); letter-spacing: -0.025em; }

  .facts { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 14px; }
  .facts div { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .facts i { font: 650 10.5px/1.2 var(--font-text); font-style: normal; letter-spacing: 0.08em; text-transform: uppercase; color: rgba(255, 255, 255, 0.6); }
  .facts b { font: 640 14.5px/1.3 var(--font-text); }
  .foot { margin-top: 12px; }
  .code { text-align: right; }
  .code b { letter-spacing: 0.06em; }

  .cut { height: 0; margin: 16px -18px 16px; border-top: 1.5px dashed rgba(255, 255, 255, 0.28); }
  .qrbox { position: relative; padding: 14px; border-radius: 20px; background: #fff; box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.04); }
  .qrbox.used :global(.qr) { opacity: 0.25; }
  .stamp {
    position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%) rotate(-8deg); white-space: nowrap;
    padding: 8px 14px; border-radius: 12px; border: 2px solid var(--success); color: #13884A; background: rgba(255, 255, 255, 0.92);
    font: 750 15px/1 var(--font-text);
  }
  .void { padding: 26px 0 10px; text-align: center; font: 620 15px/1.35 var(--font-text); color: rgba(255, 255, 255, 0.8); }

  .hint { font: 550 13px/1.3 var(--font-text); color: rgba(255, 255, 255, 0.62); }
  .acts { display: flex; flex-wrap: wrap; justify-content: center; gap: 10px; }
  .pill { position: relative; display: inline-flex; align-items: center; gap: 8px; height: 44px; padding: 0 24px; border-radius: var(--r-full); color: #fff; font: 650 15px/1 var(--font-text); background-color: rgba(255, 255, 255, 0.1); }
  .pill:active { transform: scale(0.96); }
  .danger { color: #FF8A80; background-color: rgba(255, 69, 58, 0.16); }
  .doubt { height: 40px; padding: 0 18px; color: #FFD27A; background-color: rgba(255, 176, 32, 0.18); font-size: 14px; }
</style>
