import { expect, test } from 'vitest';
import { pickHi, EVERY, type Next } from './greet';
import { at } from './time';

const hhmm = () => '18:00';
const key = (now: number, next: Next | null = null, lastOpen: number | null = null, lastHi: number | null = null) =>
  pickHi(now, ', Aru', next, lastOpen, lastHi, hhmm)?.key ?? null;

test('useful facts first, then special days, absence, weekday, time of day', () => {
  const mon = at(2026, 11, 14, 9); // Monday 14 Dec 2026, 09:00, the exam weeks
  const cls: Next = { kind: 'class', title: 'Calculus · 301', at: mon + 1200, emoji: null };
  const ev: Next = { kind: 'event', title: 'Open mic', at: mon + 9 * 3600, emoji: null };
  expect(key(mon, cls, mon - 30 * 86400)).toBe('say.hi.class');
  expect(pickHi(mon, '', cls, null, null, hhmm)?.vars.n).toBe('20');
  expect(key(mon, ev)).toBe('say.hi.event');
  expect(key(mon, { ...cls, at: mon - 60 })).toBe('say.hi.exams'); // a class already running isn't news
  expect(key(at(2026, 11, 16, 12))).toBe('say.hi.independence');
  expect(key(at(2026, 2, 22, 12), null, at(2025, 0, 1))).toBe('say.hi.nauryz'); // a holiday beats the absence
  const tue = at(2026, 10, 10, 13); // Tuesday 10 Nov
  expect(key(tue, null, tue - 8 * 86400)).toBe('say.hi.back');
  expect(key(tue, null, tue - 2 * 86400)).toBe('say.hi.day');
  expect(key(at(2026, 10, 9, 8))).toBe('say.hi.monday');
  expect(key(at(2026, 10, 13, 19))).toBe('say.hi.friday');
  expect(key(at(2026, 10, 14, 15))).toBe('say.hi.weekend');
  expect([2, 6, 9, 14, 20, 23].map((h) => key(at(2026, 10, 10, h))))
    .toEqual(['say.hi.late', 'say.hi.early', 'say.hi.morning', 'say.hi.day', 'say.hi.evening', 'say.hi.night']);
  expect(key(at(2027, 0, 1, 3))).toBe('say.hi.late'); // a holiday doesn't greet at 3 a.m.
});

test('at most once per three hours', () => {
  const now = at(2026, 10, 10, 13);
  expect(key(now, null, null, now - EVERY + 60)).toBeNull();
  expect(key(now, null, null, now - EVERY)).toBe('say.hi.day');
  expect(key(now, null, null, now + 3600)).toBe('say.hi.day'); // a clock moved back doesn't silence it
});
