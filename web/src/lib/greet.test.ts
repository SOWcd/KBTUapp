import { expect, test, vi } from 'vitest';
import { pickHi, nextUp, EVERY, type Next } from './greet';
import type { ClassItem, EventCard } from './api';
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

test('what is next: a future class within the hour, else my event later today, never a running class', () => {
  const now = at(2026, 10, 10, 13);
  const c = (b: number) => ({ c: { subject: 'Calculus' } as ClassItem, b, e: b + 3000 });
  const ev = (startsAt: number, status = 'going') =>
    ({ title: 'Open mic', startsAt, status: 'published', my: { status }, emoji: 'microphone_3d', org: { emoji: null } }) as unknown as EventCard;
  const up = (slots: ReturnType<typeof c>[], events: EventCard[]) => nextUp(now, slots, events, (x) => x.subject, () => 'books_3d');
  expect(up([c(now - 600), c(now + 1800)], [])).toMatchObject({ kind: 'class', at: now + 1800 }); // the running one skipped
  expect(up([c(now - 600)], [ev(now + 5 * 3600)])).toMatchObject({ kind: 'event', title: 'Open mic', at: now + 5 * 3600 });
  expect(up([c(now + 2 * 3600)], [ev(now - 600), ev(now + 3600, 'hold'), ev(now + 12 * 3600)])).toBeNull(); // started, not mine, tomorrow
});

test('every launch is recorded; the absence counts from the launch before', async () => {
  const store = new Map<string, string>([['kb-open', String(at(2026, 10, 1, 12))]]);
  vi.stubGlobal('localStorage', { getItem: (k: string) => store.get(k) ?? null, setItem: (k: string, v: string) => store.set(k, v) });
  const launch = async () => { vi.resetModules(); return import('./greet'); };
  const now = at(2026, 10, 10, 13);
  (await launch()).opened(now - 3600); // a deep-link launch after 9 days: no greeting, still recorded
  expect(store.get('kb-open')).toBe(String(now - 3600));
  const g = await launch();
  g.opened(now);
  expect(g.hiNow(now + 5, '', null, hhmm)?.key).toBe('say.hi.day'); // not "long time no see"
  store.set('kb-open', String(now - 8 * 86400)); store.delete('kb-hi');
  const h = await launch();
  h.opened(now); // at mount; the greeting later in the same launch still sees the launch before
  expect(h.hiNow(now + 5, '', null, hhmm)?.key).toBe('say.hi.back');
  vi.unstubAllGlobals();
});

test('at most once per three hours', () => {
  const now = at(2026, 10, 10, 13);
  expect(key(now, null, null, now - EVERY + 60)).toBeNull();
  expect(key(now, null, null, now - EVERY)).toBe('say.hi.day');
  expect(key(now, null, null, now + 3600)).toBe('say.hi.day'); // a clock moved back doesn't silence it
});
