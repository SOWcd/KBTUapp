import { expect, it } from 'vitest';
import { lineLen, lyricAt } from './lyrics';

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
