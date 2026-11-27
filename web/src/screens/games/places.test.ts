// Spy's places here are the server's (logic/spy.py LOCATIONS), id for id, and each has its name in ru, kk and en.
import { expect, it } from 'vitest';
import py from '../../../../server/kbtu/logic/spy.py?raw';
import { PLACE_NAMES, PLACES } from '../../lib/i18n/spyPlaces';

it('the same places as the server, each named in all three languages', () => {
  const block = py.slice(py.indexOf('LOCATIONS = ('), py.indexOf('\n)\n', py.indexOf('LOCATIONS = (')));
  expect(PLACES).toEqual([...block.matchAll(/"([a-z_]+)"/g)].map((m) => m[1]));
  for (const names of Object.values(PLACE_NAMES)) for (const p of PLACES) expect(names[p], p).toBeTruthy();
});
