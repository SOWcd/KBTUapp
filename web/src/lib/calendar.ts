// "To calendar" on the ticket (SPEC §4.2): Google Calendar's own new-event page on every phone, iPhone too (owner,
// Nov 27: our students live in Google Calendar; Apple's was the iPhone default before). It needs no file.
import type { EventCard } from './api';

const utc = (ts: number) => new Date(ts * 1000).toISOString().replace(/[-:]|\.\d{3}/g, '');

export function calendarUrl(e: EventCard): string {
  const end = e.endsAt ?? e.startsAt + 3 * 3600; // no end: three hours, as everywhere (§4.9)
  const q = new URLSearchParams({ action: 'TEMPLATE', text: e.title, dates: `${utc(e.startsAt)}/${utc(end)}`, location: e.place,
    details: `${e.org.name}\nhttps://t.me/KBTUappBot?startapp=ev_${e.id}` });
  return 'https://calendar.google.com/calendar/render?' + q;
}
