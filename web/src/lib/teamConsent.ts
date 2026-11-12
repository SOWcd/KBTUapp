// Team events' own consent (server evteams.CONSENT): mine, one for every event. Asked the first time I pick a way into
// a team event (a team of my own, a link, "no team": the app or the organizer may place me) and on an invite's Join;
// taken back from a team event's card, which takes me out of my teams on events not started yet.
import { api } from './api';
import { session } from './state/session.svelte';
import { sheets } from './state/sheets';
import { say } from './state/ui.svelte';
import { t, i18n } from './i18n/index.svelte';
import { haptic } from './tg';

export const TEAM_CONSENT = 'tm1';

/** true once it is mine (asked if it wasn't); the answer at once, back if the server says no */
export async function setTeamConsent(on: boolean): Promise<boolean> {
  const me = session.me?.teams;
  if (!me) return false;
  if (me.consent === on) return true;
  const yes = on
    ? await sheets.ask({ title: t('tm.consentT'), text: t('tm.consentText'), ok: t('tm.consentOk'), cancel: t('common.cancel'),
      link: { label: t('tm.consentLink'), url: `${location.origin}/privacy?lang=${i18n.lang}` } })
    : await sheets.ask({ title: t('tm.offT'), text: t('tm.offText'), ok: t('tm.offOk'), cancel: t('common.cancel'), danger: true });
  if (!yes) return false;
  me.consent = on;
  try { me.consent = (await api.teamConsent(on ? TEAM_CONSENT : null)).consent; haptic.ok(); return me.consent === on; }
  catch { me.consent = !on; haptic.error(); say(t('common.error'), 'warning_3d'); return false; }
}

/** before a step into a team: mine already, or asked now */
export const teamConsentOk = (): Promise<boolean> => (session.me?.teams?.consent ? Promise.resolve(true) : setTeamConsent(true));
