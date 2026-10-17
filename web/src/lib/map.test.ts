// floorOf: a main-building room at the start of a place gives its floor; street addresses and other numbers never do.
// The Russian inputs are written as escapes (\u0410\u0443\u0434 = "Aud", \u0410\u0431\u0430\u044f = "Abaya") to keep the source English.
import { describe, expect, it } from 'vitest';
import { floorOf, nearRooms, roomOf } from './map';

it('finds the floor of a room, never of an address', () => {
  const cases: [string, number | null][] = [
    ['\u0410\u0443\u0434. 305', 3], ['\u0430\u0443\u0434 112', 1], ['\u041a\u0430\u0431\u0438\u043d\u0435\u0442 251', 2], ['305', 3], ['Room 412', 4],
    ['\u0410\u0431\u0430\u044f 150', null], ['1203', null], ['612', null], ['Atrium', null],
  ];
  for (const [place, floor] of cases) expect(floorOf(place), place).toBe(floor);
  expect(roomOf('\u0410\u0443\u0434. 305')).toBe('305');  // the number the map circles
  // a letter after the number is another room (251a is not 251), Latin or Cyrillic; a word after it is not a letter
  expect(roomOf('251a')).toBe('251a');
  expect(roomOf('251\u0431')).toBe('251b');
  expect(roomOf('305 \u0438 306')).toBe('305');
  expect(roomOf('305\u043a\u0430\u0431')).toBe('305');
  expect(floorOf('251a')).toBe(2);
  // Independence Hall's wing is 7xx on floor 2 (owner, Oct 15), by number or by name; the basement's 70 stays below
  expect(floorOf('728')).toBe(2);
  expect(roomOf('Independence Hall')).toBe('726');
  expect(floorOf('70')).toBe(0);
  // a hall by its name (the Kunaev hall, Russian and Kazakh), never the street of the same name
  expect(roomOf('\u0438\u043c. \u0414.\u0410. \u041a\u0443\u043d\u0430\u0435\u0432\u0430')).toBe('400a');
  expect(floorOf('\u0414.\u0410. \u049a\u043e\u043d\u0430\u0435\u0432 \u0430\u0442\u044b\u043d\u0434\u0430\u0493\u044b')).toBe(4);
  expect(roomOf('\u041a\u0443\u043d\u0430\u0435\u0432\u0430 21')).toBe(null);
  // the basement's 1-99 as the whole place, a letter kept; never a short number in an address
  expect(floorOf('45')).toBe(0);
  expect(roomOf('045')).toBe('45');
  expect(roomOf('43\u0430')).toBe('43a');
  expect(floorOf('12 \u043c\u043a\u0440')).toBe(null);
});

describe('nearRooms', () => {
  const floor = { '434': [[0.30, 0.40]], '436': [[0.32, 0.40]], '450': [[0.9, 0.9]] };
  it('a room off the plan: its numbered neighbours', () => {
    expect(nearRooms(floor, '435', 1).map(([k]) => k)).toEqual(['434', '436']); // close together: both
    expect(nearRooms(floor, '445', 1).map(([k]) => k)).toEqual(['450']); // 436 is 9 below, 450 5 above, far apart: the nearer
    expect(nearRooms(floor, '470', 1)).toEqual([]);
  });
});
