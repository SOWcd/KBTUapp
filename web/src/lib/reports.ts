// Clubs' event reports' own consent (server evreports.CONSENT): mine, one for every club. Asked before my first report
// (EventReport) and given or taken back from Studio's row; taking it back takes my marks from every report.
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
