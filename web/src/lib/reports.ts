// Clubs' event reports' own consent (server evreports.CONSENT): mine, one for every club. Asked once after my first team
// check-in mark (askAfterTeamMark), before my first report (EventReport), and given or taken back in Settings → Privacy;
// taking it back takes my marks from every report.
import { api } from './api';
import { session } from './state/session.svelte';
import { sheets } from './state/sheets';
import { say } from './state/ui.svelte';
import { t, i18n } from './i18n/index.svelte';
import { haptic } from './tg';

export const REPORT_CONSENT = 'evr1';

/** true once it is mine (asked if it wasn't); the switch answers at once, back if the server says no */
export async function setReportConsent(on: boolean): Promise<boolean> {
  const me = session.me?.reports;
  if (!me) return false;
  if (me.consent === on) return true;
  const yes = on
    ? await sheets.ask({ title: t('evr.consentT'), text: t('evr.consentText'), ok: t('evr.consentOk'), cancel: t('common.cancel'),
      link: { label: t('evr.consentLink'), url: `${location.origin}/privacy?lang=${i18n.lang}` } })
    : await sheets.ask({ title: t('evr.offT'), text: t('evr.offText'), ok: t('evr.offOk'), cancel: t('common.cancel'), danger: true });
  if (!yes) return false;
  me.consent = on;
  try { me.consent = (await api.reportConsent(on ? REPORT_CONSENT : null)).consent; haptic.ok(); return me.consent === on; }
  catch { me.consent = !on; haptic.error(); say(t('common.error'), 'warning_3d'); return false; }
}

/** after a team check-in mark (the mark already kept): the question once ever, whatever the answer (Settings has the switch) */
export function askAfterTeamMark(): void {
  const me = session.me;
  if (!me?.reports || me.reports.consent) return;
  // ponytail: "asked" lives on this phone only (another phone asks once more); a server flag if that annoys
  const key = `evr.asked.${me.id}`;
  try { if (localStorage.getItem(key)) return; localStorage.setItem(key, '1'); } catch { return; /* blocked: never nag */ }
  void setReportConsent(true);
}
