// My own upcoming tickets kept on the phone for the door without the network (the shell offline: sw.ts). Only what the
// QR and its card need, nothing about anyone else. They live in the account's recovery scope (state/recovery.ts): signing
// out, a ban, deleting the account or another account on this phone drops them with the rest; a ticket goes as its event ends.
import type { EventCard } from './api';
import { ApiErr } from './api/errors';
import { recovery, TICKETS_AGE } from './state/recovery';

export interface OfflineTicket { id: number; title: string; startsAt: number; endsAt: number | null; place: string; online: boolean; code: string }
export const TICKETS = 'tickets'; // (recovery's sweep knows this key: TICKETS_AGE, not a draft's week)
const MAX = 20;
const CODE = /^[A-Z0-9]{4,8}$/; // server seats._ticket_code: 4 characters, the QR is 'KBTU' + it

/** An event's end as the ticket counts it: its own, else three hours after the start (as TicketView's late sign-up). */
export const endOf = (t: { startsAt: number; endsAt: number | null }): number => t.endsAt ?? t.startsAt + 3 * 3600;

/** Only well-formed tickets not over yet, soonest first, one per event: what was kept may be anything (an older
 *  build's, a storage edited by hand). Field by field, so nothing else ever rides along. */
export function sanitize(raw: unknown, now: number): OfflineTicket[] {
  if (!Array.isArray(raw)) return [];
  const out = new Map<number, OfflineTicket>();
  for (const x of raw as Partial<Record<keyof OfflineTicket, unknown>>[]) {
    if (!x || typeof x !== 'object') continue;
    const { id, title, startsAt, endsAt, place, online, code } = x;
    if (typeof id !== 'number' || !Number.isSafeInteger(id) || id <= 0 || out.has(id)) continue;
    if (typeof title !== 'string' || typeof place !== 'string' || typeof online !== 'boolean') continue;
    if (typeof startsAt !== 'number' || !Number.isFinite(startsAt) || !(endsAt === null || typeof endsAt === 'number' && Number.isFinite(endsAt))) continue;
    if (typeof code !== 'string' || !CODE.test(code)) continue;
    const t: OfflineTicket = { id, title: title.slice(0, 200), startsAt, endsAt, place: place.slice(0, 200), online, code };
    if (endOf(t) > now) out.set(id, t);
  }
  return [...out.values()].sort((a, b) => a.startsAt - b.startsAt).slice(0, MAX);
}

/** My tickets in the events the server sent: going (not a hold, a waitlist or cancelled), with a code, not over. */
export const ticketsOf = (events: EventCard[], now: number): OfflineTicket[] => sanitize(events.flatMap((e) =>
  e.status !== 'cancelled' && e.my?.status === 'going' && e.my.ticketCode
    ? [{ id: e.id, title: e.title, startsAt: e.startsAt, endsAt: e.endsAt, place: e.place, online: e.online, code: e.my.ticketCode }] : []), now);

/** Kept after each verified load (App's keep): an empty list removes the record. */
export function keepTickets(events: EventCard[], now = Date.now() / 1000): void {
  const list = ticketsOf(events, now), owner = recovery.scope();
  if (list.length) recovery.write(owner, TICKETS, JSON.stringify(list));
  else recovery.clear(owner, TICKETS);
}

/** The kept tickets of this phone's account (tgId: Telegram's user; outside Telegram the last signed-in account). */
export function keptTickets(tgId?: number, now = Date.now() / 1000): OfflineTicket[] {
  return sanitize(recovery.read<unknown>(recovery.scope() ?? recovery.last(tgId), TICKETS, TICKETS_AGE), now);
}

/** Signed out elsewhere (the server no longer knows this browser): its tickets go before anyone else sees them. */
export const dropTickets = (): void => recovery.drop(TICKETS);

/** The request never reached the server (no network, the server down): not an answer from it. */
export const unreachable = (e: unknown): boolean => e instanceof ApiErr && e.code === 'unavailable' && e.message === 'network';
