// KBTU's academic calendar for 2026-2027, bachelor's (SPEC §4.11): the owner's PDF (Oct 7), approved by the Academic
// Council on 23 April 2026. `at`: Almaty days, 'from/to', one day, or '/to' for "until". `who`: whom a row is for when
// it isn't everyone (the PDF's ISE cells, a year of study, SITE). Names: i18n 'acad.<key>'. A new year: a new PDF, new rows.
import { t } from './i18n/index.svelte';
import { dateInput, dayRange, nowTs } from './time';

export type Row = { key: string; at: string; who?: 'ise' | 'y1' | 'y12' | 'y24' | 'site' };

export const TERMS: { key: 'fall' | 'spring' | 'summer'; rows: Row[] }[] = [
  { key: 'fall', rows: [
    { key: 'schedule', at: '2026-08-17/2026-08-29' }, { key: 'orientation', at: '2026-08-17/2026-08-31', who: 'y1' },
    { key: 'adddrop', at: '2026-08-31/2026-09-04' }, { key: 'study', at: '2026-09-01/2026-12-12' },
    { key: 'late', at: '2026-09-07/2026-09-11' }, { key: 'withdraw', at: '/2026-09-28' },
    { key: 'midterm', at: '2026-10-12/2026-10-24' }, { key: 'holiday', at: '2026-10-25' },
    { key: 'regSpring', at: '2026-10-27/2026-11-08', who: 'y1' },
    { key: 'exams', at: '2026-12-14/2026-12-30' }, { key: 'exams', at: '2026-12-14/2026-12-26', who: 'ise' }, { key: 'holiday', at: '2026-12-16' },
    { key: 'break', at: '2026-12-31/2027-01-17' }, { key: 'break', at: '2026-12-28/2027-01-04', who: 'ise' },
    { key: 'fx', at: '2027-01-05/2027-01-08' }, { key: 'final', at: '2027-01-11/2027-02-05' },
  ] },
  { key: 'spring', rows: [
    { key: 'schedule', at: '2027-01-08/2027-01-17' }, { key: 'schedule', at: '2027-01-05/2027-01-11', who: 'ise' },
    { key: 'adddrop', at: '2027-01-18/2027-01-22' }, { key: 'adddrop', at: '2027-01-05/2027-01-11', who: 'ise' },
    { key: 'study', at: '2027-01-18/2027-05-01' }, { key: 'study', at: '2027-01-04/2027-04-17', who: 'ise' },
    { key: 'late', at: '2027-01-25/2027-01-29' }, { key: 'withdraw', at: '/2027-02-12' }, { key: 'withdraw', at: '/2027-01-31', who: 'ise' },
    { key: 'midterm', at: '2027-03-01/2027-03-13' }, { key: 'midterm', at: '2027-02-22/2027-02-27', who: 'ise' },
    { key: 'regYear', at: '2027-03-01/2027-03-31' },
    { key: 'holiday', at: '2027-01-01/2027-01-02' }, { key: 'holiday', at: '2027-01-07' }, { key: 'holiday', at: '2027-03-08' },
    { key: 'holiday', at: '2027-03-15' }, { key: 'holiday', at: '2027-03-22/2027-03-24' }, { key: 'holiday', at: '2027-05-01' },
    { key: 'holiday', at: '2027-05-07' }, { key: 'holiday', at: '2027-05-09' },
    { key: 'exams', at: '2027-05-11/2027-05-28' }, { key: 'exams', at: '2027-04-19/2027-04-24', who: 'ise' },
    { key: 'fx', at: '2027-05-31/2027-06-04' }, { key: 'fx', at: '2027-04-26/2027-05-22', who: 'ise' },
    { key: 'practice', at: '2027-05-31/2027-06-11', who: 'y12' },
    { key: 'final', at: '2027-05-31/2027-06-19' }, { key: 'final', at: '2027-05-31/2027-06-25', who: 'site' },
    { key: 'break', at: '2027-05-31/2027-08-31', who: 'y24' }, { key: 'break', at: '2027-06-14/2027-08-31', who: 'y1' },
  ] },
  { key: 'summer', rows: [
    { key: 'reg', at: '2027-05-11/2027-05-23' }, { key: 'study', at: '2027-06-07/2027-07-17' },
    { key: 'holiday', at: '2027-07-06' }, { key: 'fx', at: '2027-07-19/2027-07-22' },
  ] },
];

/** classes on these days are held online, asynchronously (the PDF's footnote) */
export const ONLINE = ['2026-10-26', '2026-12-16', '2027-01-07', '2027-03-08', '2027-03-15', '2027-03-22/2027-03-24', '2027-05-01', '2027-07-06'];

/** first and last day of a row (both the deadline for "until") */
export const span = (r: Row): [string, string] => { const [a, b = a] = r.at.split('/'); return [a || b, b]; };
// a day off by its name (owner, Oct 25: "not 'Day off', the real holiday"): the dates are fixed by the Labour Code
// (art. 84), so a list beats an API that missed Christmas; a day KBTU moved (Mar 15) stays "Day off"
const HOLIDAYS: Record<string, string> = { '01-01': 'newYear', '01-07': 'christmas', '03-08': 'women', '03-21': 'nauryz', '03-22': 'nauryz',
  '05-01': 'unity', '05-07': 'defender', '05-09': 'victory', '07-06': 'capital', '08-30': 'constitution', '10-25': 'republic', '12-16': 'independence' };
export const nameOf = (r: Row): string => {
  const h = r.key === 'holiday' && HOLIDAYS[span(r)[0].slice(5)];
  return h ? t(`hol.${h}` as 'hol.republic') : t(`acad.${r.key}` as 'acad.midterm');
};
export function whenOf(r: Row): string { const [a, b] = span(r); return r.at.startsWith('/') ? t('acad.until', { date: dayRange(b, b) }) : dayRange(a, b); }
/** what is on now or comes next for everyone, past the long teaching period: the line under the row in Me */
export const nextUp = (today = dateInput(nowTs())): Row | undefined =>
  TERMS.flatMap((x) => x.rows).filter((r) => !r.who && r.key !== 'study' && span(r)[1] >= today).sort((a, b) => span(a)[0].localeCompare(span(b)[0]))[0];

const days = (a: string, b: string): number => (Date.parse(b) - Date.parse(a)) / 864e5;
/** Where today is in a fall or spring term, for the strip in Me: teaching weeks (Monday to Sunday, week 1 holds the first
 *  day of "study"), the midterm weeks, how many weeks to the exams; from the first day of study to the last day of exams. */
export function semester(today = dateInput(nowTs())) {
  for (const x of TERMS) {
    if (x.key === 'summer') continue;
    const row = (k: string) => x.rows.find((r) => r.key === k && !r.who);
    const study = row('study'), exams = row('exams'), mid = row('midterm');
    if (!study || !exams || !mid) continue;
    const [a, b] = span(study), [ea, eb] = span(exams), [ma, mb] = span(mid);
    if (today < a || today > eb) continue;
    const mon = (Date.parse(a) / 864e5 - (new Date(a).getUTCDay() + 6) % 7) * 864e5; // the Monday of the first week
    const wk = (d: string) => Math.floor((Date.parse(d) - mon) / 864e5 / 7) + 1, weeks = wk(b);
    // whole weeks left: the weekend before the exams already says "exams"
    return { week: Math.min(weeks, wk(today)), weeks, mid: [wk(ma), wk(mb)] as [number, number], over: today > b, exams: today >= ea,
      toExams: Math.max(0, Math.floor(days(today, ea) / 7)), start: a };
  }
  return null;
}

// KBTU's psychological service: its Microsoft Bookings page, no sign-in (Me, and quietly under "Delete account")
export const PSYCHOLOGIST = 'https://outlook.office365.com/book/Bookings7@kbtu.kz/';

/** the first three weeks of a fall or spring term: Studio asks a closed club to open recruitment */
export const termJustStarted = (now = nowTs()): boolean =>
  TERMS.some((x) => x.key !== 'summer' && x.rows.some((r) => r.key === 'study' && !r.who && span(r)[0] <= dateInput(now) && span(r)[0] >= dateInput(now - 21 * 86400)));
