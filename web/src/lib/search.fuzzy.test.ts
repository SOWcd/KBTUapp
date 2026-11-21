import { expect, it } from 'vitest';
import { hit } from './search';

it('finds names across scripts and with a typo', () => {
  expect(hit('aigerim', ['\u0410\u0439\u0433\u0435\u0440\u0438\u043c \u0421\u0430\u0442\u043f\u0430\u0435\u0432\u0430'])).toBe(true);
  expect(hit('\u0436\u0430\u043d\u0441\u0430\u044f', ['Zhansaya Smail'])).toBe(true);
  expect(hit('Satpeva', ['Aigerim Satpayeva'])).toBe(true);
  expect(hit('Ivan', ['Aigerim Satpayeva'])).toBe(false);
  expect(hit('ai', ['Aigerim'])).toBe(true);
});
