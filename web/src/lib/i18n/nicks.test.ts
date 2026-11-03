// An anonymous post's nick in each language (the server keeps the indexes; its Russian is checked against these in
// server/tests/test_fchan_nicks.py); none, or indexes this build doesn't know: null, the post's sign shows instead.
import { expect, it } from 'vitest';
import { i18n } from './index.svelte';
import { nickName } from './nicks';

it('words a nick in ru, kk and en, the Russian adjective agreeing', () => {
  const said = (lang: 'ru' | 'kk' | 'en', nick: [number, number] | null) => { i18n.lang = lang; return nickName(nick); };
  expect(said('ru', [0, 0])).toBe('Тихая Лиса');
  expect(said('ru', [0, 1])).toBe('Тихий Барс');
  expect(said('ru', [0, 39])).toBe('Тихое Эхо');
  expect(said('kk', [0, 0])).toBe('Тыныш Түлкі');
  expect(said('en', [11, 24])).toBe('Night Comet');
  expect(said('en', null)).toBeNull();
  expect(said('en', [40, 0])).toBeNull();
  expect(said('ru', [0, 40])).toBeNull();
});
