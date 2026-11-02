// "Check my event" before publishing (the editor redesign, stage 1): contradictions and gaps found on the phone, at
// once, no model needed. A club once published a trip as free while its text said 7500 tenge: the price in the text is
// the first thing looked for. Cyrillic as \u escapes (the repo's rule).
// ponytail: regexes over the text; a model pass on the server (dates and places the text names) when these miss real cases

export type Finding =
  | { id: 'priceText'; n: number }   // the text names a price, the event is free
  | { id: 'priceDiff'; n: number }   // the text's price is not the ticket's
  | { id: 'past' }
  | { id: 'noPlace' }
  | { id: 'seatsText'; n: number }   // the text names a number of places, the event has no limit
  | { id: 'noCover' }
  | { id: 'noAbout' }
  | { id: 'longTitle' }
  | { id: 'clubInTitle'; clean: string };   // "TSS by BCL": the card names the club already

const MONEY = /(\d{1,3}(?:[ .\u00a0\u202f]\d{3})+|\d{3,7})\s*(?:\u20b8|\u0442\u0433|\u0442\u0435\u043d\u0433|tg\b|kzt|tenge)/i;
const SEATS = /(\d{1,4})\s*(?:\u043c\u0435\u0441\u0442|\u043e\u0440\u044b\u043d|seats|spots|places)/i;
export const LONG_TITLE = 48;
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** the title without the club's own name around it ("TSS by BCL", "BCL | TSS", "TSS x KBTU"), or null when there's none:
 * the club is on every card, so a name in the title says it twice (owner, Nov 2) */
export function titleWithoutClub(title: string, names: string[]): string | null {
  const ns = [...new Set([...names, 'KBTU', '\u041a\u0411\u0422\u0423', '\u049a\u0411\u0422\u0423'].map((n) => n.trim()).filter((n) => n.length >= 2))]
    .sort((a, b) => b.length - a.length).map(esc).join('|');
  if (!ns) return null;
  const word = `(?:${ns})(?![\\p{L}\\p{N}])`;
  let t = title.trim();
  for (let i = 0; i < 2; i++) {
    t = t.replace(new RegExp(`(?:\\s+(?:by|from|\\u043e\\u0442|x|\\u00d7|-)\\s+|\\s*[|\\u2013\\u2014:]\\s*)${word}\\s*$`, 'iu'), '')
      .replace(new RegExp(`^${word}(?:\\s*[|\\u2013\\u2014:]\\s*|\\s+(?:x|\\u00d7|-|presents|\\u043f\\u0440\\u0435\\u0434\\u0441\\u0442\\u0430\\u0432\\u043b\\u044f\\u0435\\u0442)\\s+)`, 'iu'), '').trim();
  }
  return t !== title.trim() && t.length >= 2 ? t : null;
}

/** the first price the text names, in tenge */
export function priceIn(text: string): number | null {
  const m = text.match(MONEY);
  const n = m ? +m[1].replace(/\D/g, '') : 0;
  return n >= 100 && n <= 1_000_000 ? n : null;
}

export function check(x: { title: string; description: string; paid: boolean; price: number | null; tba: boolean; place: string;
  startTs: number; now: number; live: boolean; cover: boolean; seats: number | null; club?: string[] }): Finding[] {
  const out: Finding[] = [], said = priceIn(x.description);
  if (said && !x.paid) out.push({ id: 'priceText', n: said });
  if (said && x.paid && x.price && said !== x.price) out.push({ id: 'priceDiff', n: said });
  if (!x.live && Number.isFinite(x.startTs) && x.startTs <= x.now) out.push({ id: 'past' });
  if (x.tba || !x.place.trim()) out.push({ id: 'noPlace' });
  const seats = x.description.match(SEATS);
  if (seats && !x.seats && +seats[1] > 0) out.push({ id: 'seatsText', n: +seats[1] });
  if (!x.cover) out.push({ id: 'noCover' });
  if (x.description.trim().length < 20) out.push({ id: 'noAbout' });
  const clean = titleWithoutClub(x.title, x.club ?? []);
  if (clean) out.push({ id: 'clubInTitle', clean });
  else if (x.title.trim().length > LONG_TITLE) out.push({ id: 'longTitle' });
  return out;
}
