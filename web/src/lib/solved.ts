// "Solved by your appeals" lines as you type (the SG panel): the server's own (server logic/appeals.solved_line),
// mirrored on the forum channel's checks (forumRules). The server still decides; this says why at the spot.
// The cases both sides agree on: server/tests/solved_rules.json.
import { BRACKET_DOT, HIDDEN, brokenAll } from './forumRules';

export type SolvedWhy = 'length' | 'link' | 'contact' | 'number';
const CONTACT = /@|\((?:at|dog)\)|\[(?:at|dog)\]|\p{Nd}(?:[\s().+-]*\p{Nd}){5,}/iu; // mentions, e-mails, phones
const NUMBER = /\p{Nd}{2}/u; // a room, a floor, a date, an id

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
  return NUMBER.test(seen) ? 'number' : null;
}

/** "2026-11" as "November" (this year) or "November 2025" */
export function monthName(m: string, lang: string, now = new Date()): string {
  const d = new Date(`${m}-15T12:00:00Z`);
  return d.toLocaleDateString(lang, d.getUTCFullYear() === now.getFullYear() ? { month: 'long' } : { month: 'long', year: 'numeric' });
}
