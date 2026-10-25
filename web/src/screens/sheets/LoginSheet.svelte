<script lang="ts">
  // KBTU sign-in (SPEC §4.1): Microsoft only. One big button; pressing it accepts the terms, said under
  // it with both links (no checkbox); it opens outside
  // Telegram, comes back by /ms.html, and the app reloads me when it's in sight again; someone new then types only the
  // student ID and year (Microsoft doesn't know them: KBTU leaves employeeId empty). Typed in before Oct 20 (relink)
  // or through the old portal: the same button confirms the row they have.
  import { CONSENT_VERSION } from '../../lib/legal';
  import CircleCheck from '@lucide/svelte/icons/circle-check';
  import Sheet from '../../ui/Sheet.svelte';
  import Emoji from '../../ui/Emoji.svelte';
  import Button from '../../ui/Button.svelte';
  import { api, ApiErr } from '../../lib/api';
  import { close, say, type Overlay } from '../../lib/state/ui.svelte';
  import { session, loadMe } from '../../lib/state/session.svelte';
  import { data, loadAfisha, phrase } from '../../lib/state/data.svelte';
  import { sheets } from '../../lib/state/sheets';
  import { t, i18n } from '../../lib/i18n/index.svelte';
  import { haptic, openLink, on } from '../../lib/tg';
  import { nowTs, parts } from '../../lib/time';

  let { overlay, after }: { overlay: Overlay; after?: () => void; why?: 'go' | 'other' } = $props();

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
  $effect(() => { if (pending) { away = false; m.firstName = pending.first || m.firstName; m.lastName = pending.last || m.lastName; } });
  $effect(() => { if (away && done) { away = false; haptic.ok(); say(t('login.msDone'), 'sparkles_3d'); void loadAfisha().then(offerWeek); close(overlay.id); setTimeout(() => after?.(), 380); } });
  // signed in, no timetable yet, nothing else to do next: "load your schedule? 1 minute", skippable (PLAN 26)
  const offerWeek = () => { if (!after && !data.schedule.length) setTimeout(() => sheets.schedHowTo(true), 500); };

  let m = $state({ lastName: '', firstName: '', studentId: '', course: 0 });
  // the example ID starts with this intake's year, so a first-year sees their own: the year of the last
  // August, as a 26B student still enters in spring 2027
  const yr = parts(nowTs()), sidEx = `${String(yr.m >= 7 ? yr.y : yr.y - 1).slice(2)}B123456`;
  const NAME = /^[\p{L}][\p{L}\-' ]{0,39}$/u, SID = /^\d{2}[A-Z]{1,2}\d{5,7}$/;
  // Microsoft's names are taken as they are (the server uses them); typed only where the account has none
  const mReady = $derived((!!pending?.last || NAME.test(m.lastName.trim())) && (!!pending?.first || NAME.test(m.firstName.trim()))
    && SID.test(m.studentId.trim().toUpperCase()) && !busy);  // the year comes from the ID (audit M3)
  async function submit(ev?: Event) {
    ev?.preventDefault();
    if (!pending || !mReady) return;
    busy = true; error = '';
    try {
      session.me = await api.manualLogin({ lastName: m.lastName.trim(), firstName: m.firstName.trim(), studentId: m.studentId.trim().toUpperCase(), course: m.course }, CONSENT_VERSION);
      haptic.ok();
      say(phrase('say.welcome', { name: session.me.student?.firstName ?? '' }), 'partying_face_3d');
      await loadAfisha();
      close(overlay.id);
      setTimeout(() => after?.(), 380);
      offerWeek();
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

<Sheet {overlay} title={t('login.title')}>
  <form class="wrap" onsubmit={submit}>
    {#if st}
      <!-- confirmed through the old portal: only the Microsoft button, nothing to type -->
      {@render msButton(t('login.msConfirm'))}
      {@render consent()}
    {:else if pending}
      <div class="ok"><CircleCheck size={20} /><span><b>{t('login.msOk')}</b><i class="t-foot">{pending.email} · {t('login.msOkText')}</i></span></div>
      {#if !pending.last || !pending.first}
        <label class="field"><span class="t-cap">{t('login.lastName')}</span>
          <input bind:value={m.lastName} autocomplete="family-name" autocapitalize="words" enterkeyhint="next" maxlength="40" /></label>
        <label class="field"><span class="t-cap">{t('login.firstName')}</span>
          <input bind:value={m.firstName} autocomplete="given-name" autocapitalize="words" enterkeyhint="next" maxlength="40" /></label>
      {/if}
      <label class="field"><span class="t-cap">{t('login.sid')}</span>
        <input class="sid" bind:value={m.studentId} placeholder={sidEx} autocapitalize="characters" autocomplete="off" spellcheck="false" enterkeyhint="done" maxlength="12" />
      </label>
      <p class="t-foot dim">{t('login.manualNote')}</p>
      {#if error}<p class="err t-callout">{error}</p>{/if}
      <Button kind="primary" size="l" full type="submit" disabled={!mReady} loading={busy}>{t('login.submit')}</Button>
      {@render consent()}
    {:else}
      {#if relink}<p class="relink t-callout">{t('login.relink')}</p>{/if}
      <div class="big"><Emoji name="waving_hand_3d_default" size={72} /><b>{t('login.big')}</b></div>
      {@render msButton(t('login.ms'))}
      {@render consent()}
    {/if}
    {#if error && !pending}<p class="err t-callout">{error}</p>{/if}
  </form>
</Sheet>

<style>
  .sid { text-transform: uppercase; } /* a typed "b" shows as "B"; it's sent upper-cased */
  .wrap { display: flex; flex-direction: column; gap: 12px; padding-top: 8px; }
  .err { color: var(--danger-text); }
  .ms { display: flex; align-items: center; justify-content: center; gap: 12px; height: 56px; border-radius: var(--r-l); background: #fff; color: #1b1b1b;
    font: 650 17px/1 var(--font-text); box-shadow: inset 0 0 0 1px rgba(0, 0, 0, 0.12), var(--shadow-card); }
  .ms:active { transform: scale(0.98); }
  .big { display: flex; flex-direction: column; align-items: center; gap: 14px; text-align: center; padding: 8px 12px 10px; }
  .big b { font: 750 26px/1.15 var(--font-display, var(--font-text)); letter-spacing: -0.015em; text-wrap: balance; }
  .relink { padding: 12px 14px; border-radius: var(--r-l); background: var(--surface-3); }
  .center { text-align: center; margin-top: -4px; }
  .ok { display: flex; gap: 12px; align-items: flex-start; padding: 14px; border-radius: var(--r-l); background: var(--success-soft); }
  .ok :global(svg) { flex: none; margin-top: 2px; color: var(--success); }
  .ok span { display: flex; flex-direction: column; gap: 4px; }
  .ok b { font: 680 16px/1.25 var(--font-text); }
  .ok i { font-style: normal; }
  .what { margin: 2px 0 0; text-align: center; color: var(--text-3); line-height: 1.45; }
  .what button { color: var(--accent-text); font-weight: 620; }
</style>
