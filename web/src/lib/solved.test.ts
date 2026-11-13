// The app's "Solved" line rules agree with the server's on every shared case (server/tests/solved_rules.json).
import { expect, it } from 'vitest';
import { monthName, solvedClean, solvedWhy } from './solved';
import rules from '../../../server/tests/solved_rules.json';

it.each(rules.cases as [string, string | null][])('%j is %s', (text, why) => {
  expect(solvedWhy(text)).toBe(why);
});

it('cleans as the server keeps it', () => {
  expect(solvedClean('  Wi-Fi \n\n in the  library\u0007 was slow ')).toBe('Wi-Fi in the library was slow');
});

it('names the month, the year only when not this one', () => {
  const now = new Date('2026-11-13T10:00:00Z');
  expect(monthName('2026-11', 'en', now)).toBe('November');
  expect(monthName('2025-11', 'en', now)).toBe('November 2025');
});
