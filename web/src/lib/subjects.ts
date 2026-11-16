// The subjects' cards (server logic/subjects.py): a name's folded form, the same as the server's tool makes the cards
// by (tools/subjects.py key), so my timetable's class finds its card: a name with a Latin B for a Cyrillic one, or a space less, is one.
import type { ClassItem, Subject } from './api';

// Cyrillic look-alikes (after lower case; the Kazakh i too) as the Latin letters the timetables mix them with
const FROM = '\u0430\u0435\u043e\u0440\u0441\u0445\u0456\u0443\u043a\u043c\u0442\u043d\u0432', TO = 'aeopcxiykmthb';
export const fold = (s: string): string => s.normalize('NFKC').toLowerCase().replace(/\u0451/g, '\u0435')
  .replace(/[\u0430\u0435\u043e\u0440\u0441\u0445\u0456\u0443\u043a\u043c\u0442\u043d\u0432]/g, (c) => TO[FROM.indexOf(c)]).replace(/[^\p{L}\p{N}]+/gu, '');

/** The cards by their folded names, built once per list. */
export const byName = (list: Subject[]): Map<string, Subject> => new Map(list.map((s) => [fold(s.name), s]));

/** A class's card: its name in any language the timetable has it in. */
export function subjectOf(c: ClassItem, index: Map<string, Subject>): Subject | undefined {
  for (const n of [c.subject, ...Object.values(c.names ?? {})]) {
    const s = n && index.get(fold(n));
    if (s) return s;
  }
  return undefined;
}
