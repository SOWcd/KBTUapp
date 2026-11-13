// "Solved by your appeals" lines as you type (the SG panel): the server's own (server logic/appeals.solved_line),
// mirrored on the forum channel's checks (forumRules). The server still decides; this says why at the spot.
// The cases both sides agree on: server/tests/solved_rules.json.
import { BRACKET_DOT, HIDDEN, brokenAll } from './forumRules';

export type SolvedWhy = 'length' | 'link' | 'contact' | 'number' | 'name' | 'quote'; // quote: the server alone (it reads the appeals)
const CONTACT = /@|\((?:at|dog)\)|\[(?:at|dog)\]|\p{Nd}(?:[\s().+-]*\p{Nd}){5,}/iu; // mentions, e-mails, phones
// a room, a floor, a date, an id, as the server's _NUMBER, _DATE (no lookbehind: old iOS)
const LOOKS = 'Oo\u041e\u043eIl\u0406\u0417';
const NUMBER = new RegExp(`\\p{Nd}[^\\p{L}\\p{N}]*\\p{Nd}|\\p{Nd}[${LOOKS}]|[${LOOKS}]\\p{Nd}|(?:^|[^\\p{L}\\p{N}_])[IVXLC\u0406\u0425\u0421]{2,}(?![\\p{L}\\p{N}_])`, 'u');
const DATE = new RegExp('\\p{Nd}[^\\p{L}\\p{N}]*(?:(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sep(?:t(?:ember)?)?' +
  '|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)(?![a-z])|\u044f\u043d\u0432\u0430\u0440|\u0444\u0435\u0432\u0440\u0430\u043b|\u043c\u0430\u0440\u0442|\u0430\u043f\u0440\u0435\u043b|\u043c\u0430[\u0439\u044f]|\u0438\u044e\u043d|\u0438\u044e\u043b' +
  '|\u0430\u0432\u0433\u0443\u0441\u0442|\u0441\u0435\u043d\u0442\u044f\u0431\u0440|\u043e\u043a\u0442\u044f\u0431\u0440|\u043d\u043e\u044f\u0431\u0440|\u0434\u0435\u043a\u0430\u0431\u0440|\u049b\u0430\u04a3\u0442\u0430\u0440|\u0430\u049b\u043f\u0430\u043d|\u043d\u0430\u0443\u0440\u044b\u0437|\u0441\u04d9\u0443\u0456\u0440|\u043c\u0430\u043c\u044b\u0440|\u043c\u0430\u0443\u0441\u044b\u043c' +
  '|\u0448\u0456\u043b\u0434\u0435|\u0442\u0430\u043c\u044b\u0437|\u049b\u044b\u0440\u043a\u04af\u0439\u0435\u043a|\u049b\u0430\u0437\u0430\u043d|\u049b\u0430\u0440\u0430\u0448\u0430|\u0436\u0435\u043b\u0442\u043e\u049b\u0441\u0430\u043d)', 'iu');
const INITIALS = /(?:^|[^\p{L}\p{N}_])\p{Lu}\. ?\p{Lu}\./u; // "A. B.": a name's initials

/** invisible and control characters out, whitespace collapsed: the line as the server keeps it */
export const solvedClean = (raw: string): string =>
  raw.replace(HIDDEN, '').replace(/‍|\p{Cc}/gu, (c) => (/\s/.test(c) ? c : '')).split(/\s+/).filter(Boolean).join(' ');

/** why the server would refuse the line, or null */
export function solvedWhy(raw: string): SolvedWhy | null {
  const s = solvedClean(raw), n = [...s].length;
  if (n < 10 || n > 140) return 'length';
  const seen = s.normalize('NFKC').replace(/[。｡．]/g, '.').replace(BRACKET_DOT, '.');
  if (CONTACT.test(seen)) return 'contact';
  if (brokenAll(s).includes('link')) return 'link';
  if (NUMBER.test(seen) || DATE.test(seen)) return 'number';
  return INITIALS.test(seen) ? 'name' : null;
}

/** "2026-11" as "November" (this year) or "November 2025" */
export function monthName(m: string, lang: string, now = new Date()): string {
  const d = new Date(`${m}-15T12:00:00Z`);
  return d.toLocaleDateString(lang, d.getUTCFullYear() === now.getFullYear() ? { month: 'long' } : { month: 'long', year: 'numeric' });
}
