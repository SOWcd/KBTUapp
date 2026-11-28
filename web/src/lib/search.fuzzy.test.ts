import { expect, it } from 'vitest';
import { cyrKey, hit, score } from './search';

const aigerim = '\u0410\u0439\u0433\u0435\u0440\u0438\u043c';
const asel = '\u04d8\u0441\u0435\u043b';
const qazaq = '\u049a\u0430\u0437\u0430\u049b';
const zhansaya = '\u0416\u0430\u043d\u0441\u0430\u044f';

it.each([
  ['FQUTHBV', aigerim, 2],
  ['fqutqhbv', aigerim, 1],
  ['\u0444\u0448\u043f\u0443\u043a\u0448\u044c', 'Aigerim', 2],
  [';tyz', '\u0416\u0435\u043d\u044f', 2],
  [':tyz', '\u0416\u0435\u043d\u044f', 2],
  ['2ctk', asel, 2],
  ['2\u0441\u0435\u043b', asel, 2],
  ['@ctk', asel, 2],
  ['2', asel, 0],
  ['0fpf0', qazaq, 2],
  ['\u0441\u0434\u0433\u0438\u04d9\u04a3', 'Club24', 2],
  ['\u0430\u0441\u0435\u043b', asel, 3],
  ['aigerim', aigerim, 2],
  ['jansa', zhansaya, 2],
  [zhansaya, 'Zhansaya Smail', 2],
  ['Maria', '\u041c\u0430\u0440\u0438\u044f', 2],
  ['\u042e\u043b\u0438\u044f', 'Iulia', 2],
  ['Yelena', '\u0415\u043b\u0435\u043d\u0430', 2],
  ['Mikhail', '\u041c\u0438\u0445\u0430\u0438\u043b', 2],
  ['Shevchenko', '\u0428\u0435\u0432\u0447\u0435\u043d\u043a\u043e', 2],
  ['Shchuka', '\u0429\u0443\u043a\u0430', 2],
  ['Tsarev', '\u0426\u0430\u0440\u0451\u0432', 2],
  ['Shyngys', '\u0428\u044b\u04a3\u0493\u044b\u0441', 2],
  ['Ghalym', '\u0492\u0430\u043b\u044b\u043c', 2],
  ['\u00d6rken', '\u04e8\u0440\u043a\u0435\u043d', 2],
  ['Q\u016brman\u011fazy', '\u049a\u04b1\u0440\u043c\u0430\u043d\u0493\u0430\u0437\u044b', 2],
  ['Sattpayyeva', 'Satpayeva', 2],
  ['Satpeva', 'Aigerim Satpayeva', 1],
  ['Agierim', 'Aigerim', 1],
  ['Nightmra', 'Nightmare on Tole Bi', 1],
  ['xathom', 'Phantom', 0],
  ['xathomzz', 'Phantomize', 0],
  ['xhanxomi', 'Phantomize', 1],
  ['xhanxomixati', 'Phantomization', 1],
  ['Ivax', 'Aigerim Satpayeva', 0],
  ['Ajg', 'Aigerim', 0],
  ['24bal0001', '24bal0002', 0],
  ['CS100', 'CS101', 0],
  ['b', 'IT Club', 0],
  ['ai', 'Aigerim', 3],
  ['STRASSE', 'Stra\u00dfe', 3],
  ['rjytw-2ctk', '\u043a\u043e\u043d\u0435\u0446 \u04d8\u0441\u0435\u043b', 2],
  ['bi-tole', 'A Nightmare on Tole Bi Street', 3],
  [';', 'Chess', 0],
] as const)('scores %s against %s as %i', (q, name, expected) => {
  expect(score(q, [name])).toBe(expected);
  expect(hit(q, [name])).toBe(expected > 0);
});

it('requires every query word within a single name and uses the best alias', () => {
  expect(score('satp fquthbv', [`${aigerim} Satpayeva`])).toBe(2);
  expect(score('satp fqutqhbv', [`${aigerim} Satpayeva`])).toBe(1);
  expect(score('satp fquthbv', [aigerim, 'Satpayeva'])).toBe(0);
  expect(score('aigerim', ['Aigerm', aigerim, 'Aigerim Satpayeva'])).toBe(3);
  expect(score('aigerim', [undefined, null, ''])).toBe(0);
  expect(score('  ', ['Aigerim'])).toBe(0);
});

it('sorts Latin names among Cyrillic ones', () => {
  const text = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' }); // as in sort.svelte.ts
  const names = ['Misgarli Ibrahim', '\u0410\u0439\u0433\u0435\u0440\u0438\u043c', '\u042f\u043d\u0430', '\u041c\u0430\u0440\u0430\u0442', '\u041d\u0443\u0440\u043b\u0430\u043d'];
  expect(names.sort((a, b) => text.compare(cyrKey(a), cyrKey(b))))
    .toEqual(['\u0410\u0439\u0433\u0435\u0440\u0438\u043c', '\u041c\u0430\u0440\u0430\u0442', 'Misgarli Ibrahim', '\u041d\u0443\u0440\u043b\u0430\u043d', '\u042f\u043d\u0430']);
});
