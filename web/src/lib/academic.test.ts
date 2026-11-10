import { expect, test } from 'vitest';
import { MASTER, noClasses, nextUp, semester, span, termsOf, TERMS } from './academic';

test("master's calendar: picked by the ID's letter M, its own term strip, the same days off", () => {
  expect(termsOf('26MD0335')).toBe(MASTER);
  for (const sid of ['24B031234', '25E01', '', null, undefined]) expect(termsOf(sid)).toBe(TERMS);
  expect(semester('2026-09-07', MASTER)).toMatchObject({ week: 1, weeks: 15, mid: [8, 8] });
  expect(semester('2026-09-01', MASTER)).toBeNull();                        // orientation, before classes
  expect(semester('2027-01-05', MASTER)).toMatchObject({ exams: true });     // master's exams run into January
  expect(nextUp('2026-10-20', MASTER)?.key).toBe('holiday');                 // Oct 25, then their midterm from the 26th
  expect(nextUp('2026-11-10', MASTER)?.key).toBe('thesis');
  for (const r of MASTER.flatMap((x) => x.rows)) { const [a, b] = span(r); expect(a <= b && /^\d{4}-\d\d-\d\d$/.test(a)).toBe(true); }
  // the timetable keeps the default calendar: both must agree on every day off
  for (let d = Date.parse('2026-08-15'); d <= Date.parse('2027-08-31'); d += 864e5) {
    const day = new Date(d).toISOString().slice(0, 10);
    expect(noClasses(day, MASTER)).toBe(noClasses(day));
  }
});

test('academic calendar: spans, and what comes next', () => {
  expect(span({ key: 'withdraw', at: '/2026-09-28' })).toEqual(['2026-09-28', '2026-09-28']);
  expect(span({ key: 'holiday', at: '2026-10-25' })).toEqual(['2026-10-25', '2026-10-25']);
  expect(nextUp('2026-10-07')?.key).toBe('midterm');    // the owner's day: midterms from the 12th
  expect(nextUp('2026-10-20')?.key).toBe('midterm');    // still on
  expect(nextUp('2026-10-25')?.key).toBe('holiday');
  expect(nextUp('2027-08-01')).toBeUndefined();         // the year is over: the row just names the calendar
  for (const r of TERMS.flatMap((x) => x.rows)) { const [a, b] = span(r); expect(a <= b && /^\d{4}-\d\d-\d\d$/.test(a)).toBe(true); }
});

test('semester strip: week of the term, midterm weeks, weeks to the exams', () => {
  expect(semester('2026-09-01')).toMatchObject({ week: 1, weeks: 15, mid: [7, 8], toExams: 14 });
  expect(semester('2026-10-21')).toMatchObject({ week: 8, toExams: 7 });
  expect(semester('2026-12-13')).toMatchObject({ week: 15, toExams: 0, over: true, exams: false }); // the Sunday before
  expect(semester('2026-12-20')).toMatchObject({ week: 15, toExams: 0, exams: true });
  expect(semester('2027-01-10')).toBeNull();                               // the break
  expect(semester('2027-01-18')).toMatchObject({ week: 1, weeks: 15 });    // spring
});
