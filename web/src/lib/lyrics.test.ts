import { expect, it } from 'vitest';
import { lineLen, lyricAt, wordAt } from './lyrics';
import { SUNG, words } from './i18n/anthem';

it('lights the line being sung, and a pause as dots before the next one', () => {
  const s = [10, 14, 18, 40, 44];
  expect(lineLen(s)).toBe(4);
  expect(lyricAt(s, [], 5, 60)).toEqual({ line: -1, next: 0, p: 0.5 });   // the intro
  expect(lyricAt(s, [], 15, 60).line).toBe(1);                            // until the next line starts
  expect(lyricAt(s, [], 21.9, 60).line).toBe(2);                          // a pause follows: its own 4 s
  expect(lyricAt(s, [], 22, 60)).toEqual({ line: -1, next: 3, p: 0 });
  expect(lyricAt(s, [null, null, 20], 21, 60)).toEqual({ line: -1, next: 3, p: 0.05 }); // its end marked by hand
  expect(lyricAt(s, [], 50, 60)).toEqual({ line: -1, next: -1, p: 0 });  // after the last line: nothing
});

it('fills the word being sung, then the next', () => {
  const o = [0, 0.5, 1.5];
  expect(wordAt(o, 0.25, 4)).toEqual({ w: 0, f: 0.5 });
  expect(wordAt(o, 1, 4)).toEqual({ w: 1, f: 0.5 });
  expect(wordAt(o, 2.1, 4)).toEqual({ w: 2, f: 0.5 });  // the last word: HOLD (1.2 s) at most
  expect(wordAt(o, 1.7, 1.9)).toEqual({ w: 2, f: 0.5 }); // or until the line goes dark
  expect(wordAt(o, -1, 4)).toEqual({ w: 0, f: 0 });
});

it('times every word of the anthem inside its line, in order', () => {
  const s = SUNG.map((l) => l.t!);
  for (const l of SUNG) {
    expect(l.o.length).toBe(l.w.length);
    expect(l.o.every((x, k) => k === 0 ? x === 0 : x > l.o[k - 1])).toBe(true);
    expect(l.t! + l.o[l.o.length - 1]).toBeLessThan(s[l.i + 1] ?? Infinity);
    if (l.end != null) expect(l.end).toBeGreaterThan(l.t! + l.o[l.o.length - 1]);
  }
  expect(s.every((x, i) => !i || x > s[i - 1])).toBe(true);
  expect(words('A – b c')).toEqual(['A –', 'b', 'c']);
});
