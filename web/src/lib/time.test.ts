import { expect, test } from 'vitest';
import { at, daySpan, multiDay } from './time';

test('multi-day events: past 24 h the span of days, an overnight one stays one evening', () => {
  const start = at(2026, 10, 2, 10), end = at(2026, 10, 12, 18); // a casting, 2-12 November
  expect(multiDay(start, end)).toBe(true);
  expect(multiDay(start, null)).toBe(false);
  expect(multiDay(at(2026, 10, 2, 20), at(2026, 10, 3, 8))).toBe(false); // a night hackathon
  expect(multiDay(start, start + 86400)).toBe(false);                    // exactly a day: still expressible by time alone
  expect(daySpan(start, end)).toMatch(/^2\s?[–-]\s?12 \D+$/);
  expect(daySpan(at(2026, 9, 31, 10), at(2026, 10, 2, 10))).toMatch(/31 \D+ ?[–-] ?2 \D+/);
});
