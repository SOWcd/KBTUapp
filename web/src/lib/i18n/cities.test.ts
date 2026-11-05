import { expect, test } from 'vitest';
import { cityName } from './cities';

test('a city in the app language, whatever spelling was stored', () => {
  expect(cityName('Semey', 'ru')).toBe('Семей');
  expect(cityName('Almaty', 'ru')).toBe('Алматы');
  expect(cityName('Орал', 'en')).toBe('Uralsk');
  expect(cityName('Qaragandy', 'kk')).toBe('Қарағанды');
  expect(cityName('Ust-Kamenogorsk', 'ru')).toBe('Усть-Каменогорск');
  expect(cityName('Милан', 'en')).toBe('Милан');
});
