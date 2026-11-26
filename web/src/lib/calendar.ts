// "To calendar" on the ticket (SPEC §4.2): Apple devices choose Apple's Calendar (the event file, Safari hands it over)
// or Google's; the rest go straight to Google Calendar's own new-event page, which needs no file.
import type { EventCard } from './api';
import { tg } from './tg';

const utc = (ts: number) => new Date(ts * 1000).toISOString().replace(/[-:]|\.\d{3}/g, '');

/** Apple's Calendar: the event file, on Apple devices only (null elsewhere) */
export const appleCalendarUrl = (e: EventCard): string | null =>
  e.my?.ics && /^(ios|macos)$/.test(tg.platform) ? location.origin + e.my.ics : null;

export function googleCalendarUrl(e: EventCard): string {
  const end = e.endsAt ?? e.startsAt + 3 * 3600; // no end: three hours, as everywhere (§4.9)
  const q = new URLSearchParams({ action: 'TEMPLATE', text: e.title, dates: `${utc(e.startsAt)}/${utc(end)}`, location: e.place,
    details: `${e.org.name}\nhttps://t.me/KBTUappBot?startapp=ev_${e.id}` });
  return 'https://calendar.google.com/calendar/render?' + q;
}
