<script lang="ts">
  // KBTU sign-in (SPEC §4.1): Microsoft only. One big button; pressing it accepts the terms, said under
  // it with both links (no checkbox); it opens outside
  // Telegram, comes back by /ms.html, and the app reloads me when it's in sight again; someone new then types only the
  // student ID and year (Microsoft doesn't know them: KBTU leaves employeeId empty). Typed in before Oct 20 (relink)
  // or through the old portal: the same button confirms the row they have.
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import Sheet from '../../ui/Sheet.svelte';
  import LogIn from '@lucide/svelte/icons/log-in';
  import Emoji from '../../ui/Emoji.svelte';
  import Button from '../../ui/Button.svelte';
  import Field from '../../ui/Field.svelte';
  import Notice from '../../ui/Notice.svelte';
  import { api, ApiErr } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { loadAfisha, phrase } from '../../lib/state/data.svelte';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { haptic, openLink, on } from '../../lib/tg';
  import { nowTs, parts } from '../../lib/time';

  let { overlay, after, lock = false }: { overlay: Overlay; after?: () => void; why?: 'go' | 'other'; lock?: boolean } = $props();

  const legal = (doc: 'privacy' | 'terms') => { haptic.tap(); openLink(`${location.origin}/${doc}?lang=${i18n.lang}`); };
  const st = session.me?.student, relink = !!session.me?.relink;
  let busy = $state(false);
  let error = $state('');

  // Microsoft: away in the browser; back in sight, ask who I am now (confirmed, or the account's names to fill in)
  let away = $state(false);
  const pending = $derived(session.me?.msPending ?? null), done = $derived(!!session.me?.student?.ms);
  async function microsoft() {
    haptic.tap(); error = '';
    try { const { url } = await api.msStart(); away = true; openLink(url); }
    catch { haptic.error(); error = t('common.error'); }
  }
  $effect(() => {
    if (!away) return;
    const back = () => { if (!document.hidden) void loadMe(); };
    document.addEventListener('visibilitychange', back);
    const off = on('activated', back);
    return () => { document.removeEventListener("visibilitychange", back); off(); };
  });
  // back from Microsoft as someone new: the account's names (they win on the server too), only the ID and year to type
  $effect(() => { if (pending) { away = false; m.firstName = pending.first || m.firstName; m.lastName = pending.last || m.lastName; m.studentId ||= pending.prefill?.studentId ?? ''; } });
  // confirmed by Microsoft while this sheet waits (back from the browser, or the return launch's own sheet): it closes and
  // what I wanted runs; never left open asking a confirmed student for Microsoft again. over: once (submit's own way too)
  let over = false;
  $effect(() => {
    if (!done || over) return;
    over = true;
    if (away) { away = false; haptic.ok(); say(t('login.msDone'), 'sparkles_3d'); void loadAfisha(); }
    close(overlay.id); setTimeout(() => after?.(), 380);
  });

  // engine: ui/Field could take autocapitalize and spellcheck (names in Words, the student ID in capitals)
  const caps = (how: string) => (n: HTMLElement) => { const i = n.querySelector('input'); if (i) { i.autocapitalize = how; if (how === 'characters') i.spellcheck = false; } };

  let m = $state({ lastName: '', firstName: '', studentId: '', course: 0 });
  // the example ID starts with this intake's year, so a first-year sees their own: the year of the last
  // August, as a 26B student still enters in spring 2027
  const yr = parts(nowTs()), sidEx = `${String(yr.m >= 7 ? yr.y : yr.y - 1).slice(2)}B123456`;
  const NAME = /^[\p{L}][\p{L}\-' ]{0,39}$/u, SID = /^\d{2}(?:[A-Z]\d{5,7}|[A-Z]{2}\d{4,7})$/;  // server core.STUDENT_ID (a master's 26MD1234 too)
  // Microsoft's names are taken as they are (the server uses them); typed only where the account has none
  const mReady = $derived((!!pending?.last || NAME.test(m.lastName.trim())) && (!!pending?.first || NAME.test(m.firstName.trim()))
    && SID.test(m.studentId.trim().toUpperCase()) && !busy);  // the year comes from the ID (audit M3)
  async function submit(ev?: Event) {
    ev?.preventDefault();
    if (!pending || !mReady) return;
    busy = true; error = '';
    try {
      const me = await api.manualLogin({ lastName: m.lastName.trim(), firstName: m.firstName.trim(), studentId: m.studentId.trim().toUpperCase(), course: m.course }, session.policy);
      over = true; // the effect above leaves this way to me
      session.me = me;
      haptic.ok();
      try { localStorage.setItem('kb-arrive', String(session.me.id)); } catch { /* blocked: no drop, nothing lost */ } // Profile's first open: the badge drops in (Hero)
      say(phrase('say.welcome', { name: session.me.student?.firstName ?? '' }), 'partying_face_3d');
      await loadAfisha();
      close(overlay.id);
      setTimeout(() => after?.(), 380); // nothing else opens: the timetable's ask is Today's card (onboarding plan)
    } catch (e) {
      haptic.error();
      const why = e instanceof ApiErr ? e.message || e.code : '';
      error = e instanceof ApiErr && e.message === 'consent' ? t('login.reopen') : why === 'bad_input' ? t('login.badManual', { sid: sidEx }) : why === 'sid_taken' ? t('login.sidTaken') : why === 'ms_first' ? t('login.msFirst') : t('common.error');
      if (why === 'ms_first') void loadMe(); // the Microsoft sign-in ran out: the button again
    } finally { busy = false; }
  }
</script>

{#snippet consent()}
  <p class="what t-foot">{t('login.consent')}<br /><button type="button" onclick={() => legal('terms')}>{t('login.terms')}</button> · <button type="button" onclick={() => legal('privacy')}>{t('login.consentLink')}</button></p>
{/snippet}

{#snippet msButton(label: string)}
  <!-- Microsoft's own sign-in button look (their branding: the four squares, "Sign in with Microsoft") -->
  <button type="button" class="ms" onclick={microsoft}>
    <svg viewBox="0 0 21 21" width="21" height="21" aria-hidden="true"><path fill="#f25022" d="M0 0h10v10H0z"/><path fill="#7fba00" d="M11 0h10v10H11z"/><path fill="#00a4ef" d="M0 11h10v10H0z"/><path fill="#ffb900" d="M11 11h10v10H11z"/></svg>
    <span>{label}</span></button>
  {#if away}<p class="t-foot dim center">{t('login.msAway')}</p>{/if}
{/snippet}

<Sheet {overlay} icon={LogIn} title={t('login.title')} full={lock} hold={lock ? () => !session.me?.student : undefined}>
  <form class="wrap" onsubmit={submit}>
    {#if st}
      <!-- confirmed through the old portal: only the Microsoft button, nothing to type -->
      {@render msButton(t('login.msConfirm'))}
      {@render consent()}
    {:else if pending}
      <!-- engine: ui/Notice could have a success tone (Microsoft said yes) -->
      <div class="ok"><CircleCheck size={18} /><span><b>{t('login.msOk')}</b><i>{pending.email} · {t('login.msOkText')}</i></span></div>
      {#if !pending.last || !pending.first}
        <div {@attach caps('words')}><Field label={t('login.lastName')} bind:value={m.lastName} autocomplete="family-name" enterkeyhint="next" maxlength={40} /></div>
        <div {@attach caps('words')}><Field label={t('login.firstName')} bind:value={m.firstName} autocomplete="given-name" enterkeyhint="next" maxlength={40} /></div>
      {/if}
      <div class="sid" {@attach caps('characters')}><Field label={t('login.sid')} bind:value={m.studentId} placeholder={t('login.sidEg', { sid: sidEx })} autocomplete="off" enterkeyhint="done" maxlength={12} /></div>
      <p class="t-foot dim">{t('login.manualNote')}</p>
      {#if error}<Notice tone="danger" text={error} />{/if}
      <Button kind="primary" size="l" full type="submit" disabled={!mReady} loading={busy}>{t('login.submit')}</Button>
      {@render consent()}
    {:else}
      {#if relink}<Notice text={t('login.relink')} />{/if}
      <!-- the hello (owner, Oct 29: the full-screen sign-in after a scan "was right; make it beautiful"): the hand waves,
           the brand's light drifts behind it, the rest comes in after it; still under power saving and reduced motion -->
      <div class="big" class:hero={lock}>
        <span class="aura" aria-hidden="true"><i></i><i></i></span>
        <span class="hand"><Emoji name="waving_hand_3d_default" size={lock ? 96 : 72} /></span>
        <b class="in" style="--d:160ms">{t('login.big')}</b>
      </div>
      <div class="in" style="--d:300ms">{@render msButton(t('login.ms'))}</div>
      <div class="in" style="--d:420ms">{@render consent()}</div>
    {/if}
    {#if error && !pending}<Notice tone="danger" text={error} />{/if}
  </form>
</Sheet>

<style>
  .sid :global(input) { text-transform: uppercase; } /* a typed "b" shows as "B"; it's sent upper-cased */
  .wrap { display: flex; flex-direction: column; gap: var(--s-3); padding-top: var(--s-2); }
  /* Microsoft's own sign-in button (their brand: white, the four squares, near-black ink): not the app's Button */
  .ms { position: relative; overflow: hidden; width: 100%; display: flex; align-items: center; justify-content: center; gap: var(--s-3); height: 56px; border-radius: var(--r-l);
    background: #fff; color: #1b1b1b; font: 600 var(--fs-row)/1 var(--font-text); box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.12), var(--shadow-card);
    transition: transform var(--t-fast) var(--ease); }
  /* a glint crosses the button now and then: the one thing to tap */
  .ms::after { content: ''; position: absolute; inset: 0; background: linear-gradient(105deg, transparent 35%, rgba(255, 255, 255, 0.85) 50%, transparent 65%);
    transform: translateX(-120%); animation: glint 3.6s ease-in-out 1.2s infinite; pointer-events: none; mix-blend-mode: overlay; }
  @keyframes glint { 0%, 70% { transform: translateX(-120%); } 100% { transform: translateX(120%); } }
  .ms:active { transform: scale(0.98); }
  .big { position: relative; display: flex; flex-direction: column; align-items: center; gap: 14px; text-align: center; padding: var(--s-2) var(--s-3) 10px; }
  .big.hero { padding: 6vh var(--s-3) 4vh; gap: 18px; }
  /* the brand's light behind the hello, drifting slowly */
  .aura { position: absolute; inset: -10% -20%; z-index: -1; pointer-events: none; }
  .aura i { position: absolute; width: 60%; aspect-ratio: 1; border-radius: 50%; filter: blur(40px); opacity: 0.55; }
  .aura i:first-child { left: 8%; top: 5%; background: radial-gradient(circle, var(--accent), transparent 70%); opacity: 0.4; animation: drift 9s ease-in-out infinite alternate; }
  .aura i:last-child { right: 4%; top: 25%; background: radial-gradient(circle, rgba(175, 82, 222, 0.55), transparent 70%); animation: drift 11s ease-in-out infinite alternate-reverse; }
  @keyframes drift { to { transform: translate3d(14%, 10%, 0) scale(1.15); } }
  /* the hand: comes up, waves twice from the wrist, then breathes */
  .hand { display: inline-flex; transform-origin: 70% 85%; animation: hand-in 520ms cubic-bezier(.2, 1.4, .4, 1) backwards, wave 1.3s ease-in-out 480ms, bob 3.2s ease-in-out 1.9s infinite; }
  @keyframes hand-in { from { opacity: 0; transform: translateY(18px) scale(0.6); } }
  @keyframes wave { 15% { transform: rotate(16deg); } 30% { transform: rotate(-10deg); } 45% { transform: rotate(14deg); } 60% { transform: rotate(-6deg); } 75% { transform: rotate(8deg); } }
  @keyframes bob { 50% { transform: translateY(-5px) rotate(-3deg); } }
  .in { animation: login-in 480ms cubic-bezier(.2, .9, .25, 1) backwards; animation-delay: var(--d, 0ms); }
  @keyframes login-in { from { opacity: 0; transform: translate3d(0, 12px, 0); } }
  :global(html.lowfx) .aura, :global(html.lowfx) .ms::after { display: none; }
  :global(html.lowfx) .hand { animation: hand-in 520ms cubic-bezier(.2, 1.4, .4, 1) backwards; }
  .big b { font: 700 var(--fs-t1)/1.15 var(--font-display, var(--font-text)); letter-spacing: -0.015em; text-wrap: balance; }
  .center { text-align: center; margin-top: calc(-1 * var(--s-1)); }
  .ok { display: flex; gap: var(--s-3); align-items: flex-start; padding: var(--s-3) var(--s-3) var(--s-3) var(--s-4); border-radius: var(--r-group); background: var(--success-soft); }
  .ok :global(svg) { flex: none; margin-top: 1px; color: var(--success-text); }
  .ok span { display: flex; flex-direction: column; gap: 2px; }
  .ok b { font: 600 var(--fs-body)/1.3 var(--font-text); }
  .ok i { font: 450 var(--fs-body)/1.35 var(--font-text); font-style: normal; color: var(--text-2); }
  .what { margin: 2px 0 0; text-align: center; color: var(--text-3); line-height: 1.45; }
  .what button { color: var(--accent-text); font-weight: 600; }
</style>
