// Admissions (server logic/ako.py): the team's desk in Studio, its own module so the start bundle doesn't carry it
// (only the desk's chunk imports it). Head and up change things, a named reviewer reads. The applicant's calls: ako.ts.
import { call } from './client';
import type { AkoDesk, AkoPackage, AkoStatus, Id } from './types';

const query = (q: Record<string, string | undefined>) => {
  const s = Object.entries(q).filter(([, v]) => v != null).map(([k, v]) => `${k}=${encodeURIComponent(v!)}`).join('&');
  return s ? '?' + s : '';
};

export const akoTeam = {
  akoDesk: (org: Id): Promise<AkoDesk> => call('GET', `/orgs/${org}/ako`),
  akoPackage: (org: Id, app: Id): Promise<AkoPackage> => call('GET', `/orgs/${org}/ako/apps/${app}`),
  /** after a consultation: a prefilled package and its link's secret (shown once: /ako/<token>) */
  akoNew: (org: Id, x: { program: string; name: string; phone: string; lang?: 'ru' | 'kk' | 'en' }): Promise<{ id: Id; token: string }> => call('POST', `/orgs/${org}/ako/apps`, x),
  /** status (review: passed to Academic Programs), note, program, the interview moved or taken back (reason), a new link (the old stops) */
  akoUpdate: (org: Id, app: Id, x: { status?: AkoStatus; note?: string; program?: string; slot?: Id | null; reason?: string; newLink?: true }): Promise<{ token?: string }> => call('PATCH', `/orgs/${org}/ako/apps/${app}`, x),
  akoDrop: (org: Id, app: Id): Promise<void> => call('DELETE', `/orgs/${org}/ako/apps/${app}`),
  /** a day's times in one go; teams: the day's meeting link */
  akoAddSlots: (org: Id, x: { day: string; times: string[]; minutes: number; cap?: number; who?: string; teams?: string }): Promise<void> => call('POST', `/orgs/${org}/ako/slots`, x),
  akoSetDay: (org: Id, day: string, teams: string): Promise<void> => call('PUT', `/orgs/${org}/ako/days`, { day, teams }),
  akoUpdateSlot: (org: Id, slot: Id, x: { teams?: string; who?: string; cap?: number }): Promise<void> => call('PATCH', `/orgs/${org}/ako/slots/${slot}`, x),
  /** a booked time only with force (conflict 'ako_slot_booked' first): its people read the reason and pick again */
  akoDropSlot: (org: Id, slot: Id, force = false, reason = ''): Promise<{ booked: number }> => call('DELETE', `/orgs/${org}/ako/slots/${slot}${query({ force: force ? 'true' : undefined, reason: reason || undefined })}`),
  /** a document, or the whole package as a ZIP: a signed five-minute link to open at once (tg.downloadFile or a tab) */
  akoFileLink: (org: Id, file: Id): Promise<{ url: string }> => call('GET', `/orgs/${org}/ako/files/${file}/link`),
  akoZipLink: (org: Id, app: Id): Promise<{ url: string }> => call('GET', `/orgs/${org}/ako/apps/${app}/link`),
};
