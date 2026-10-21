<script lang="ts">
  // KBTU sign-in (SPEC §4.1): Microsoft only (owner, Oct 20). One big button, consent ticked above it; it opens outside
  // Telegram, comes back by /ms.html, and the app reloads me when it's in sight again; someone new then types only the
  // student ID and year (Microsoft doesn't know them: KBTU leaves employeeId empty). Typed in before Oct 20 (relink)
  // or through the old portal: the same button confirms the row they have.
  import { CONSENT_VERSION } from '../../lib/legal';
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
  const st = session.me?.student, relink = !!session.me?.relink;
  let agree = $state(!!st);
  let busy = $state(false);
  let error = $state('');

  // Microsoft: away in the browser; back in sight, ask who I am now (confirmed, or the account's names to fill in)
  let away = $state(false);
  const pending = $derived(session.me?.msPending ?? null), done = $derived(!!session.me?.student?.ms);
  // back from Microsoft, its page shows a code to type here (audit M6): a sign-in link someone else sent can't take
  // your KBTU account to their Telegram without it
  const waiting = $derived(!!session.me?.msCode);
  let code = $state('');
  async function confirmCode() {
    if (busy || code.trim().length !== 6) return;
    busy = true; error = '';
    away = true; // a confirmed student closes the sheet below (also after a reload lost `away`)
    try { session.me = await api.msConfirm(code.trim()); code = ''; }
    catch (e) {
      haptic.error();
      const why = e instanceof ApiErr ? (e.code === 'conflict' ? e.message : e.code) : '';
      error = why === 'bad_input' ? t('login.codeWrong') : why === 'linked' ? t('login.msTaken') : why === 'other_ms' ? t('login.msOther') : t('login.codeExpired');
      if (why !== 'bad_input') void loadMe();
    } finally { busy = false; }
  }
  async function microsoft() {
    if (!agree) return;
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
  $effect(() => { if (away && done) { away = false; haptic.ok(); say(t('login.msDone'), 'sparkles_3d'); void loadAfisha(); close(overlay.id); setTimeout(() => after?.(), 380); } });

  let m = $state({ lastName: '', firstName: '', studentId: '', course: 0 });
  const NAME = /^[\p{L}][\p{L}\-' ]{0,39}$/u, SID = /^\d{2}[A-Z]{1,2}\d{5,7}$/;
  // Microsoft's names are taken as they are (the server uses them); typed only where the account has none
  const mReady = $derived((!!pending?.last || NAME.test(m.lastName.trim())) && (!!pending?.first || NAME.test(m.firstName.trim()))
    && SID.test(m.studentId.trim().toUpperCase()) && agree && !busy);  // the year comes from the ID (audit M3)
  async function submit(ev?: Event) {
    ev?.preventDefault();
    if (waiting) return void confirmCode();
    if (!pending || !mReady) return;
    busy = true; error = '';
    try {
      session.me = await api.manualLogin({ lastName: m.lastName.trim(), firstName: m.firstName.trim(), studentId: m.studentId.trim().toUpperCase(), course: m.course }, CONSENT_VERSION);
      haptic.ok();
      say(phrase('say.welcome', { name: session.me.student?.firstName ?? '' }), 'partying_face_3d'); void requestWriteAccess();
      await loadAfisha();
      close(overlay.id);
      setTimeout(() => after?.(), 380);
    } catch (e) {
      haptic.error();
      const why = e instanceof ApiErr ? e.message || e.code : '';
      error = e instanceof ApiErr && e.message === 'consent' ? t('login.reopen') : why === 'bad_input' ? t('login.badManual') : why === 'sid_taken' ? t('login.sidTaken') : why === 'ms_first' ? t('login.msFirst') : t('common.error');
      if (why === 'ms_first') void loadMe(); // the Microsoft sign-in ran out: the button again
    } finally { busy = false; }
  }
</script>

{#snippet consent()}
  <label class="agree">
    <input type="checkbox" bind:checked={agree} />
    <span class="box" aria-hidden="true"></span>
    <span class="t-callout">{t('login.consent')}</span>
  </label>
  <span class="what t-foot"><button type="button" onclick={() => legal('terms')}>{t('login.terms')}</button> · <button type="button" onclick={() => legal('privacy')}>{t('login.consentLink')}</button></span>
{/snippet}

{#snippet msButton(label: string)}
  <!-- Microsoft's own sign-in button look (their branding: the four squares, "Sign in with Microsoft") -->
  <button type="button" class="ms" onclick={microsoft} disabled={!agree}>
    <svg viewBox="0 0 21 21" width="21" height="21" aria-hidden="true"><path fill="#f25022" d="M0 0h10v10H0z"/><path fill="#7fba00" d="M11 0h10v10H11z"/><path fill="#00a4ef" d="M0 11h10v10H0z"/><path fill="#ffb900" d="M11 11h10v10H11z"/></svg>
    <span>{label}</span></button>
  <p class="t-foot dim center">{away ? t('login.msAway') : t('login.msNote')}</p>
{/snippet}

<Sheet {overlay} title={t('login.title')}>
  <form class="wrap" onsubmit={submit}>
    {#if waiting}
      <div class="big"><b>{t('login.codeTitle')}</b><span class="t-foot">{t('login.codeHint')}</span></div>
      <input class="code" bind:value={code} inputmode="numeric" autocomplete="one-time-code" maxlength="6" placeholder="000000" enterkeyhint="done" />
      {#if error}<p class="err t-callout">{error}</p>{/if}
      <Button kind="primary" size="l" full type="submit" disabled={code.trim().length !== 6} loading={busy}>{t('login.codeGo')}</Button>
    {:else if st}
      <!-- confirmed through the old portal: only the Microsoft button, nothing to type -->
      {@render msButton(t('login.msConfirm'))}
    {:else if pending}
      <div class="ok"><CircleCheck size={20} /><span><b>{t('login.msOk')}</b><i class="t-foot">{pending.email} · {t('login.msOkText')}</i></span></div>
      {#if !pending.last || !pending.first}
        <label class="field"><span class="t-cap">{t('login.lastName')}</span>
          <input bind:value={m.lastName} autocomplete="family-name" autocapitalize="words" enterkeyhint="next" maxlength="40" /></label>
        <label class="field"><span class="t-cap">{t('login.firstName')}</span>
          <input bind:value={m.firstName} autocomplete="given-name" autocapitalize="words" enterkeyhint="next" maxlength="40" /></label>
      {/if}
      <label class="field"><span class="t-cap">{t('login.sid')}</span>
        <input bind:value={m.studentId} placeholder="24B031234" autocapitalize="characters" autocomplete="off" spellcheck="false" enterkeyhint="done" maxlength="12" />
      </label>
      <p class="t-foot dim">{t('login.manualNote')}</p>
      {#if !agree}{@render consent()}{/if}
      {#if error}<p class="err t-callout">{error}</p>{/if}
      <Button kind="primary" size="l" full type="submit" disabled={!mReady} loading={busy}>{t('login.submit')}</Button>
    {:else}
      {#if relink}<p class="relink t-callout">{t('login.relink')}</p>{/if}
      <div class="big"><b>{t('login.big')}</b><span class="t-foot">{t('login.bigSub')}</span></div>
      {@render consent()}
      {@render msButton(t('login.ms'))}
    {/if}
    {#if error && !pending && !waiting}<p class="err t-callout">{error}</p>{/if}
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
  .ms:disabled { opacity: 0.45; }
  .big { display: flex; flex-direction: column; gap: 6px; text-align: center; padding: 6px 0 4px; }
  .big b { font: 750 24px/1.2 var(--font-display, var(--font-text)); letter-spacing: -0.01em; }
  .big span { color: var(--text-2); }
  .relink { padding: 12px 14px; border-radius: var(--r-l); background: var(--surface-3); }
  .center { text-align: center; margin-top: -4px; }
  .ok { display: flex; gap: 12px; align-items: flex-start; padding: 14px; border-radius: var(--r-l); background: var(--success-soft); }
  .ok :global(svg) { flex: none; margin-top: 2px; color: var(--success); }
  .ok span { display: flex; flex-direction: column; gap: 4px; }
  .ok b { font: 680 16px/1.25 var(--font-text); }
  .ok i { font-style: normal; }
  .code { height: 64px; border-radius: var(--r-l); background: var(--surface-2); text-align: center; color: var(--text);
    font: 760 32px/1 ui-monospace, 'SF Mono', Menlo, monospace; letter-spacing: 0.3em; }
  .what { align-self: flex-start; margin: -6px 0 0 34px; color: var(--text-3); }
  .what button { color: var(--accent-text); font-weight: 620; }
</style>
