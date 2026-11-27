// Spy's places here are the server's (logic/spy.py LOCATIONS), id for id, and each has its name in ru, kk and en.
import { expect, it } from 'vitest';
import py from '../../../../server/kbtu/logic/spy.py?raw';
import ru from '../../lib/i18n/ru';
import kk from '../../lib/i18n/kk';
import en from '../../lib/i18n/en';
import { PLACES, placeKey } from './places';

it('the same places as the server, each named in all three languages', () => {
  const block = py.slice(py.indexOf('LOCATIONS = ('), py.indexOf('\n)\n', py.indexOf('LOCATIONS = (')));
  const server = [...block.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
  expect(PLACES).toEqual(server);
  for (const d of [ru, kk, en]) for (const p of PLACES) expect(d[placeKey(p)], p).toBeTruthy();
});
