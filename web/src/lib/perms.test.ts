import { expect, it } from 'vitest';
import { opensStudio } from './perms';

it('routes plain members and followers to the club, organizers and delegated roles to Studio', () => {
  expect(opensStudio(undefined)).toBe(false);
  expect(opensStudio({ role: 'member', rights: ['door'] })).toBe(false);
  expect(opensStudio({ role: 'member', rights: ['door', 'reports'] })).toBe(true);
  expect(opensStudio({ role: 'head', rights: ['posts'] })).toBe(true);
  expect(opensStudio({ role: 'vice', rights: [] })).toBe(true);
});
