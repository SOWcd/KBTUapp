<script lang="ts">
  // KBTU sign-in (SPEC §4.1). The portal-password way is gone since Oct 19 (KBTU blocked it). The KBTU Microsoft
  // account first (PLAN item 44, owner: "one big button"): it opens outside Telegram, comes back by /ms.html, and
  // the app reloads me when it's in sight again; then the student ID and year are typed (Microsoft doesn't know
  // them). Typing everything by hand stays as the other way, marked manual until Microsoft confirms. Consent is mandatory.
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import { api, ApiErr } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { loadAfisha, phrase } from '../../lib/state/data.svelte';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { haptic, requestWriteAccess, openLink, on } from '../../lib/tg';

  let { overlay, after }: { overlay: Overlay; after?: () => void; why?: 'go' | 'other' } = $props();

  const legal = (doc: 'privacy' | 'terms') => { haptic.tap(); openLink(`${location.origin}/${doc}?lang=${i18n.lang}`); };
  const CONSENT_VERSION = '2026-10-v2'; // v2 (Oct 16): the full privacy policy and the terms, kbtu.sow.kz/privacy and /terms
  const st = session.me?.student;
  let agree = $state(!!st);
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
  $effect(() => { if (pending) { away = false; m.firstName = pending.first || m.firstName; m.lastName = pending.last || m.lastName; } });
  $effect(() => { if (away && done) { away = false; haptic.ok(); say(t('login.msDone'), 'sparkles_3d'); void loadAfisha(); close(overlay.id); } });

  let m = $state({ lastName: st?.lastName ?? '', firstName: st?.firstName ?? '', studentId: st?.manual ? st.studentId : '', course: st?.course ?? 0 });
  const NAME = /^[\p{L}][\p{L}\-' ]{0,39}$/u, SID = /^\d{2}[A-Z]{1,2}\d{5,7}$/;
  const mReady = $derived(NAME.test(m.lastName.trim()) && NAME.test(m.firstName.trim()) && SID.test(m.studentId.trim().toUpperCase()) && m.course > 0 && agree && !busy);
  async function submitManual(ev?: Event) {
    ev?.preventDefault();
    if (!mReady) return;
    busy = true; error = '';
    try {
      session.me = await api.manualLogin({ lastName: m.lastName.trim(), firstName: m.firstName.trim(), studentId: m.studentId.trim().toUpperCase(), course: m.course }, CONSENT_VERSION);
      haptic.ok();
      if (st) say(t('mg.saved'), 'sparkles_3d');
      else { say(phrase('say.welcome', { name: session.me.student?.firstName ?? '' }), 'partying_face_3d'); void requestWriteAccess(); }
      await loadAfisha();
      close(overlay.id);
      setTimeout(() => after?.(), 380);
    } catch (e) {
      haptic.error();
      const why = e instanceof ApiErr ? e.message || e.code : '';
      error = why === 'bad_input' ? t('login.badManual') : why === 'linked' ? t('login.sidTaken') : why === 'sid_mismatch' ? t('login.sidMismatch') : t('common.error');
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} title={t('login.title')}>
  <form class="wrap" onsubmit={submitManual}>
    {#if st && !st.manual}
      <!-- confirmed through the old portal: only the Microsoft button, nothing to type -->
      <button type="button" class="ms" onclick={microsoft}>
        <svg viewBox="0 0 21 21" width="21" height="21" aria-hidden="true"><path fill="#f25022" d="M0 0h10v10H0z"/><path fill="#7fba00" d="M11 0h10v10H11z"/><path fill="#00a4ef" d="M0 11h10v10H0z"/><path fill="#ffb900" d="M11 11h10v10H11z"/></svg>
        <span>{t('login.msConfirm')}</span></button>
      <p class="t-foot dim center">{away ? t('login.msAway') : t('login.msNote')}</p>
      {#if error}<p class="err t-callout">{error}</p>{/if}
    {:else if pending}
      <div class="ok"><CircleCheck size={20} /><span><b>{t('login.msOk')}</b><i class="t-foot">{pending.email} · {t('login.msOkText')}</i></span></div>
    {:else}
      <!-- Microsoft's own sign-in button look (their branding: the four squares, "Sign in with Microsoft") -->
      <button type="button" class="ms" onclick={microsoft}>
        <svg viewBox="0 0 21 21" width="21" height="21" aria-hidden="true"><path fill="#f25022" d="M0 0h10v10H0z"/><path fill="#7fba00" d="M11 0h10v10H11z"/><path fill="#00a4ef" d="M0 11h10v10H0z"/><path fill="#ffb900" d="M11 11h10v10H11z"/></svg>
        <span>{st ? t('login.msConfirm') : t('login.ms')}</span></button>
      <p class="t-foot dim center">{away ? t('login.msAway') : t('login.msNote')}</p>
      <div class="or t-foot"><span>{t('login.orHand')}</span></div>
    {/if}

    {#if !st || st.manual}
    <label class="field"><span class="t-cap">{t('login.lastName')}</span>
      <input bind:value={m.lastName} readonly={!!pending?.last} autocomplete="family-name" autocapitalize="words" enterkeyhint="next" maxlength="40" />
    </label>
    <label class="field"><span class="t-cap">{t('login.firstName')}</span>
      <input bind:value={m.firstName} readonly={!!pending?.first} autocomplete="given-name" autocapitalize="words" enterkeyhint="next" maxlength="40" />
    </label>
    <label class="field"><span class="t-cap">{t('login.sid')}</span>
      <input bind:value={m.studentId} placeholder="24B031234" autocapitalize="characters" autocomplete="off" spellcheck="false" enterkeyhint="done" maxlength="12" />
    </label>
    <div class="field"><span class="t-cap">{t('login.course')}</span>
      <div class="years" role="radiogroup" aria-label={t('login.course')}>
        {#each [1, 2, 3, 4, 5, 6] as n (n)}
          <button type="button" role="radio" aria-checked={m.course === n} class:on={m.course === n} onclick={() => { haptic.select(); m.course = n; }}>{n}</button>
        {/each}
      </div>
    </div>
    <p class="t-foot dim">{t('login.manualNote')}</p>

    <label class="agree">
      <input type="checkbox" bind:checked={agree} />
      <span class="box" aria-hidden="true"></span>
      <span class="t-callout">{t('login.consent')}</span>
    </label>
    <span class="what t-foot"><button type="button" onclick={() => legal('terms')}>{t('login.terms')}</button> · <button type="button" onclick={() => legal('privacy')}>{t('login.consentLink')}</button></span>

    {#if error}<p class="err t-callout">{error}</p>{/if}
    <Button kind="primary" size="l" full type="submit" disabled={!mReady} loading={busy}>{st?.manual ? t('login.manualAgain') : t('login.submit')}</Button>
    {/if}
  </form>
</Sheet>

<style>
  .wrap { display: flex; flex-direction: column; gap: 12px; padding-top: 8px; }
  .agree { position: relative; display: flex; gap: 10px; align-items: center; padding: 6px 2px; }
  .agree input { position: absolute; opacity: 0; width: 1px; height: 1px; }
  .box { width: 22px; height: 22px; border-radius: 7px; border: 2px solid var(--line-2); flex: none; transition: background-color var(--t-fast), border-color var(--t-fast); }
  .agree input:checked + .box { background: var(--accent) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M5 12.5l4.5 4.5L19 7.5'/%3E%3C/svg%3E") center/16px no-repeat; border-color: var(--accent); }
  .err { color: var(--danger-text); }
  .ms { display: flex; align-items: center; justify-content: center; gap: 12px; height: 56px; border-radius: var(--r-l); background: #fff; color: #1b1b1b;
    font: 650 17px/1 var(--font-text); box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.12), var(--shadow-card); }
  .ms:active { transform: scale(0.98); }
  .center { text-align: center; margin-top: -4px; }
  .or { display: flex; align-items: center; gap: 10px; color: var(--text-3); margin: 4px 0; }
  .or::before, .or::after { content: ''; flex: 1; height: 1px; background: var(--line); }
  .ok { display: flex; gap: 12px; align-items: flex-start; padding: 14px; border-radius: var(--r-l); background: var(--success-soft); }
  .ok :global(svg) { flex: none; margin-top: 2px; color: var(--success); }
  .ok span { display: flex; flex-direction: column; gap: 4px; }
  .ok b { font: 680 16px/1.25 var(--font-text); }
  .ok i { font-style: normal; }
  .years { display: flex; gap: 6px; }
  .years button { flex: 1; height: 40px; border-radius: 12px; text-align: center; background: var(--surface-3); font: 650 17px/1 var(--font-text); color: var(--text); transition: background-color var(--t-fast), color var(--t-fast); }
  .years button.on { background: var(--accent); color: #fff; }
  .what { align-self: flex-start; margin: -6px 0 0 34px; color: var(--text-3); }
  .what button { color: var(--accent-text); font-weight: 620; }
</style>
