import { expect, test } from 'vitest';
import { nextUp, semester, span, TERMS } from './academic';

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
  expect(semester('2026-12-13')).toMatchObject({ week: 15, toExams: 0, exams: false }); // the Sunday before
  expect(semester('2026-12-20')).toMatchObject({ week: 15, toExams: 0, exams: true });
  expect(semester('2027-01-10')).toBeNull();                               // the break
  expect(semester('2027-01-18')).toMatchObject({ week: 1, weeks: 15 });    // spring
});
