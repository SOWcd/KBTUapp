// Clubs' event reports' own consent (server evreports.CONSENT): mine, one for every club. Asked once after my first team
// check-in mark (askAfterTeamMark), before my first report (EventReport), and given or taken back in Settings → Privacy;
// taking it back takes my marks from every report.
import { api, ApiErr } from './api';
import { session } from './state/session.svelte';
import { sheets } from './state/sheets';
import { say } from './state/ui.svelte';
import { t, i18n } from './i18n/index.svelte';
import { haptic } from './tg';

export const REPORT_CONSENT = 'evr2';

/** true once it is mine (asked if it wasn't); the switch answers at once, back if the server says no */
export async function setReportConsent(on: boolean): Promise<boolean> {
  const owner = session.me?.id;
  if (owner == null || !session.me?.reports || session.reportConsentBusy) return false;
  if (session.me.reports.consent === on && (on || !session.me.reports.legacy)) return true;
  const yes = on
    ? await sheets.ask({ title: t('evr.consentT'), text: t('evr.consentText'), ok: t('evr.consentOk'), cancel: t('common.cancel'),
      link: { label: t('evr.consentLink'), url: `${location.origin}/privacy?lang=${i18n.lang}` } })
    : await sheets.ask({ title: t('evr.offT'), text: t('evr.offText'), ok: t('evr.offOk'), cancel: t('common.cancel'), danger: true });
  const me = session.me?.reports;
  if (!yes || session.me?.id !== owner || !me || session.reportConsentBusy) return false;
  const previous = me.consent;
  session.reportConsentBusy = true;
  session.reportConsentRevision++;
  me.consent = on;
  try {
    const result = await api.reportConsent(on ? REPORT_CONSENT : null);
    if (session.me?.id !== owner || !session.me.reports) return false;
    session.me.reports = { consent: result.consent };
    session.reportLog = result.consent && result.reportLog ? { owner, entries: result.reportLog } : null;
    haptic.ok();
    return result.consent === on;
  } catch {
    if (session.me?.id === owner && session.me.reports) session.me.reports.consent = previous;
    haptic.error(); say(t('common.error'), 'warning_3d'); return false;
  } finally {
    session.reportConsentRevision++;
    session.reportConsentBusy = false;
  }
}

/** Report actions ask here if the server has a newer consent state than this app. */
export async function withReportConsent<T>(action: () => Promise<T>): Promise<T | undefined> {
  if (!(await setReportConsent(true))) return;
  try { return await action(); }
  catch (e) {
    if (!(e instanceof ApiErr) || e.message !== 'report_consent') throw e;
    if (!session.me?.reports || session.reportConsentBusy) return;
    session.me.reports.consent = false;
    session.reportLog = null;
    session.reportConsentRevision++;
    if (await setReportConsent(true)) return action();
  }
}

/** After a team check-in mark: ask once per consent version. Settings has the switch. */
export function askAfterTeamMark(): void {
  const me = session.me;
  if (!me?.reports || me.reports.consent) return;
  // ponytail: "asked" lives on this phone only (another phone asks once more); a server flag if that annoys
  const key = `evr.asked.${REPORT_CONSENT}.${me.id}`;
  try { if (localStorage.getItem(key)) return; localStorage.setItem(key, '1'); } catch { return; /* blocked: never nag */ }
  void setReportConsent(true);
}
