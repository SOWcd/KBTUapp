<script lang="ts">
  // KBTU sign-in (SPEC §4.1). The portal-password way is off since Oct 19 (KBTU blocked it and made its students
  // change their passwords): a student types their name, student ID and year, marked manual (no card number nor
  // First 500 until the KBTU account is confirmed, PLAN item 25). Consent is mandatory.
  import Info from '@lucide/svelte/icons/info';
  import Sheet from '../../ui/Sheet.svelte';
  import Button from '../../ui/Button.svelte';
  import { api, ApiErr } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { session } from '../../lib/state/session.svelte';
  import { loadAfisha, phrase } from '../../lib/state/data.svelte';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { haptic, requestWriteAccess, openLink } from '../../lib/tg';

  let { overlay, after }: { overlay: Overlay; after?: () => void; why?: 'go' | 'other' } = $props();

  const legal = (doc: 'privacy' | 'terms') => { haptic.tap(); openLink(`${location.origin}/${doc}?lang=${i18n.lang}`); };
  const CONSENT_VERSION = '2026-10-v2'; // v2 (Oct 16): the full privacy policy and the terms, kbtu.sow.kz/privacy and /terms
  const st = session.me?.student;
  let agree = $state(!!st);
  let busy = $state(false);
  let error = $state('');

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
      error = why === 'bad_input' ? t('login.badManual') : why === 'linked' ? t('login.sidTaken') : t('common.error');
    } finally { busy = false; }
  }
</script>

<Sheet {overlay} title={t('login.title')}>
  <form class="wrap" onsubmit={submitManual}>
    <div class="down"><Info size={20} /><span><b>{t('login.offTitle')}</b><i class="t-foot">{t('login.offText')}</i></span></div>

    <label class="field"><span class="t-cap">{t('login.lastName')}</span>
      <input bind:value={m.lastName} autocomplete="family-name" autocapitalize="words" enterkeyhint="next" maxlength="40" />
    </label>
    <label class="field"><span class="t-cap">{t('login.firstName')}</span>
      <input bind:value={m.firstName} autocomplete="given-name" autocapitalize="words" enterkeyhint="next" maxlength="40" />
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
  </form>
</Sheet>

<style>
  .wrap { display: flex; flex-direction: column; gap: 12px; padding-top: 8px; }
  .agree { position: relative; display: flex; gap: 10px; align-items: center; padding: 6px 2px; }
  .agree input { position: absolute; opacity: 0; width: 1px; height: 1px; }
  .box { width: 22px; height: 22px; border-radius: 7px; border: 2px solid var(--line-2); flex: none; transition: background-color var(--t-fast), border-color var(--t-fast); }
  .agree input:checked + .box { background: var(--accent) url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24' fill='none' stroke='white' stroke-width='3.2' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='M5 12.5l4.5 4.5L19 7.5'/%3E%3C/svg%3E") center/16px no-repeat; border-color: var(--accent); }
  .err { color: var(--danger-text); }
  .down { display: flex; gap: 12px; align-items: flex-start; padding: 14px; border-radius: var(--r-l); background: var(--warning-soft); }
  .down :global(svg) { flex: none; margin-top: 2px; color: var(--warning-text); }
  .down span { display: flex; flex-direction: column; gap: 4px; }
  .down b { font: 680 16px/1.25 var(--font-text); }
  .down i { font-style: normal; }
  .years { display: flex; gap: 6px; }
  .years button { flex: 1; height: 40px; border-radius: 12px; text-align: center; background: var(--surface-3); font: 650 17px/1 var(--font-text); color: var(--text); transition: background-color var(--t-fast), color var(--t-fast); }
  .years button.on { background: var(--accent); color: #fff; }
  .what { align-self: flex-start; margin: -6px 0 0 34px; color: var(--text-3); }
  .what button { color: var(--accent-text); font-weight: 620; }
</style>
