import { expect, test, vi } from 'vitest';
import { at } from './time';
import { roomNow } from './rooms';

const week = { '1': [9, 10, 14], '3': [22] }; // Monday 9-11 and 14-15, Wednesday 22-23
// 2026-11-16 is a Monday
const mon = (h: number, m = 0) => at(2026, 10, 16, h, m);

test('free or busy now, and until when', () => {
  expect(roomNow(week, mon(8, 30))).toEqual({ free: true, until: 9 });
  expect(roomNow(week, mon(9, 15))).toEqual({ free: false, until: 11 }); // two classes in a row
  expect(roomNow(week, mon(11, 59))).toEqual({ free: true, until: 14 });
  expect(roomNow(week, mon(14, 0))).toEqual({ free: false, until: 15 }); // the last class of the day
  expect(roomNow(week, mon(15, 0))).toEqual({ free: true, until: null }); // free until the evening
  expect(roomNow({}, mon(10))).toEqual({ free: true, until: null });
});

test('Sunday and the night: free', () => {
  expect(roomNow({ '7': [10] }, at(2026, 10, 22, 10))).toEqual({ free: true, until: null });
  expect(roomNow(week, at(2026, 10, 18, 22, 30))).toEqual({ free: true, until: null }); // Wednesday 22:30, past the day's grid
});

test('Almaty time on a phone in another zone', () => {
  // 09:30 in Almaty is 04:30 UTC, 05:30 in Berlin, 23:30 the day before in New York: the room is busy all the same
  const ts = mon(9, 30);
  expect(new Date(ts * 1000).getUTCHours()).toBe(4);
  vi.stubEnv('TZ', 'America/New_York');
  try { expect(new Date(ts * 1000).getHours()).toBe(23); expect(roomNow(week, ts)).toEqual({ free: false, until: 11 }); } finally { vi.unstubAllEnvs(); }
});
