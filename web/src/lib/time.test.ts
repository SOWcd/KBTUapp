import { expect, test } from 'vitest';
import { at, daySpan, endTime, fromInputs, multiDay } from './time';

test('multi-day events: past 24 h the span of days, an overnight one stays one evening', () => {
  const start = at(2026, 10, 2, 10), end = at(2026, 10, 12, 18); // a casting, 2-12 November
  expect(multiDay(start, end)).toBe(true);
  expect(multiDay(start, null)).toBe(false);
  expect(multiDay(at(2026, 10, 2, 20), at(2026, 10, 3, 8))).toBe(false); // a night hackathon
  expect(multiDay(start, start + 86400)).toBe(false);                    // exactly a day: still expressible by time alone
  expect(daySpan(start, end)).toMatch(/^2\s?[–-]\s?12 \D+$/);
  expect(daySpan(at(2026, 9, 31, 10), at(2026, 10, 2, 10))).toMatch(/31\s\D+?\s?[–-]\s?2\s\D+/);
});

test('a last day with no time shows no end (stored as 23:59)', () => {
  const start = fromInputs('2026-11-21', '10:00');
  expect(endTime(start, fromInputs('2026-11-22', '23:59'))).toBe('');
  expect(endTime(start, fromInputs('2026-11-22', '18:00'))).toBe('18:00');
  expect(endTime(start, fromInputs('2026-11-21', '23:59'))).toBe('23:59'); // one day: typed by hand
  expect(endTime(start, null)).toBe('');
});
