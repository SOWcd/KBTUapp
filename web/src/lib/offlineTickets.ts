// My own upcoming tickets kept on the phone for the door without the network (the shell offline: sw.ts). Only what the
// QR and its card need, nothing about anyone else. They live in the account's recovery scope (state/recovery.ts): signing
// out, a ban, deleting the account or another account on this phone drops them with the rest; a ticket goes as its event ends.
import type { EventCard } from './api';
import { recovery, TICKETS_AGE } from './state/recovery';
import { lookArt, QR_LOOK, skinOf, type Look } from './awards';

export interface OfflineTicket { id: number; title: string; startsAt: number; endsAt: number | null; place: string; online: boolean; code: string; look: Look; logo: string | null }
export const TICKETS = 'tickets'; // (recovery's sweep knows this key: TICKETS_AGE, not a draft's week)
const MAX = 20;
const CODE = /^[A-Z0-9]{4,8}$/; // server seats._ticket_code: 4 characters, the QR is 'KBTU' + it
// Only our small raster copy: a stored URL must never make an offline screen ask the network (or load an SVG).
const logoOf = (x: unknown): string | null => typeof x === 'string' && x.length <= 32_768
  && /^data:image\/png;base64,iVBORw0KGgo[A-Za-z0-9+/]*={0,2}$/.test(x) ? x : null;

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
    const look = typeof x.look === 'string' && Object.prototype.hasOwnProperty.call(QR_LOOK, x.look) ? x.look as Look : 'kbtu';
    const t: OfflineTicket = { id, title: title.slice(0, 200), startsAt, endsAt, place: place.slice(0, 200), online, code,
      look, logo: lookArt(look) ? logoOf(x.logo) : null };
    if (endOf(t) > now) out.set(id, t);
  }
  return [...out.values()].sort((a, b) => a.startsAt - b.startsAt).slice(0, MAX);
}

/** My tickets in the events the server sent: going (not a hold, a waitlist or cancelled), with a code, not over. */
export const ticketsOf = (events: EventCard[], now: number): OfflineTicket[] => sanitize(events.flatMap((e) =>
  e.status !== 'cancelled' && e.my?.status === 'going' && e.my.ticketCode
    ? [{ id: e.id, title: e.title, startsAt: e.startsAt, endsAt: e.endsAt, place: e.place, online: e.online, code: e.my.ticketCode,
      look: skinOf(e.org) ?? 'kbtu' }] : []), now);

const logos = new Map<string, Promise<string | null>>();
/** A look's own bundled art, decoded once while online and kept at 64 px (the QR's centre is about 40 px). */
function smallLogo(src: string): Promise<string | null> {
  const had = logos.get(src);
  if (had) return had;
  const made = new Promise<string | null>((resolve) => {
    const img = new Image();
    const done = (logo: string | null) => { clearTimeout(timer); img.onload = img.onerror = null; resolve(logo); };
    const timer = setTimeout(() => done(null), 5000);
    img.onerror = () => done(null);
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        const scale = 64 / Math.max(img.naturalWidth, img.naturalHeight);
        canvas.width = Math.max(1, Math.round(img.naturalWidth * scale));
        canvas.height = Math.max(1, Math.round(img.naturalHeight * scale));
        const ctx = canvas.getContext('2d');
        if (!ctx) { done(null); return; }
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        done(logoOf(canvas.toDataURL('image/png')));
      } catch { done(null); }
    };
    img.src = src;
  }).catch(() => null);
  logos.set(src, made);
  void made.then((logo) => { if (!logo) logos.delete(src); }); // a failed load can retry at the next save
  return made;
}

/** Kept after each verified load (App's idle keep): save codes immediately, then fill in missing marks while online. */
export async function keepTickets(events: EventCard[], online: boolean, now = Date.now() / 1000): Promise<void> {
  const list = ticketsOf(events, now), owner = recovery.scope();
  if (!owner) return;
  if (!list.length) { recovery.clear(owner, TICKETS); return; }
  const previous = new Map(sanitize(recovery.read(owner, TICKETS, TICKETS_AGE), now).filter((t) => t.logo).map((t) => [t.look, t.logo]));
  for (const t of list) t.logo = previous.get(t.look) ?? null;
  const json = JSON.stringify(list), at = recovery.now();
  recovery.write(owner, TICKETS, json, at);
  if (!online) return;
  const pending = list.flatMap((t) => {
    const src = t.logo ? undefined : lookArt(t.look);
    return src ? [smallLogo(src).then((logo) => t.logo = logo)] : [];
  });
  if (!pending.length || !(await Promise.all(pending)).some(Boolean)) return;
  // A later save, cancellation, sign-out or account change wins over an image that arrived late, even in another tab.
  if (JSON.stringify(recovery.read(owner, TICKETS, TICKETS_AGE)) === json)
    recovery.write(owner, TICKETS, JSON.stringify(list), at);
}

/** The kept tickets of this phone's account (tgId: Telegram's user; outside Telegram the last signed-in account). */
export function keptTickets(tgId?: number, now = Date.now() / 1000): OfflineTicket[] {
  return sanitize(recovery.read<unknown>(recovery.scope() ?? recovery.last(tgId), TICKETS, TICKETS_AGE), now);
}

/** Signed out elsewhere (the server no longer knows this browser): its tickets go before anyone else sees them. */
export const dropTickets = (): void => recovery.drop(TICKETS);
