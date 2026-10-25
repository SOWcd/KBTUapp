import { expect, it, vi } from 'vitest';

// a school as api/client.ts leaves it in English: the name and abbreviation shown, the typed (Russian) name in orig
vi.mock('./state/data.svelte', () => ({ data: { orgs: [
  { id: 1, kind: 'school', name: 'School of Information Technology and Engineering', abbr: 'SITE', orig: { name: 'Shkola IT' },
    i18n: { kk: { name: 'IT mektebi', abbr: 'ATIM' }, en: { name: 'School of Information Technology and Engineering', abbr: 'SITE' } } },
  { id: 2, kind: 'club', name: 'Open Mic Club', abbr: 'OMC' },
] } }));
import { nameOf, schoolShort, shortOf } from './short';

it('shows a school by its abbreviation whatever language the portal wrote it in', () => {
  expect(schoolShort('Shkola IT')).toBe('SITE');
  expect(schoolShort(' it  MEKTEBI ')).toBe('SITE');
  expect(schoolShort('SITE')).toBe('SITE');
  expect(schoolShort('Some other school')).toBe('Some other school');
  expect(schoolShort(null)).toBe('');
  expect(schoolShort('Open Mic Club')).toBe('Open Mic Club'); // clubs aren't schools
});

it('keeps a club in full in lists and short only where asked', () => {
  expect(nameOf({ kind: 'club', name: 'Open Mic Club', abbr: 'OMC' })).toBe('Open Mic Club');
  expect(nameOf({ kind: 'school', name: 'School of Law', abbr: 'SL' })).toBe('SL');
  expect(shortOf({ name: 'Open Mic Club', abbr: 'OMC' })).toBe('Open Mic Club'); // fits: in full
  expect(shortOf({ name: 'Department of Youth Policy', abbr: 'DYP' })).toBe('DYP');
  expect(shortOf({ kind: 'school', name: 'School of Law', abbr: 'SL' })).toBe('SL');
  expect(shortOf({ name: 'New Club', abbr: null })).toBe('New Club');
});
