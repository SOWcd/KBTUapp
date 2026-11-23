// Afisha's filters: a school and a type over the held list, one of each at a time, chips only for what is there.
import { expect, it } from 'vitest';
import { afishaFilter, choices, clearFilter, filterEvents, isType, pick, schoolsOf } from './afisha.svelte';
import type { EventCard, OrgRef } from '../api';

const org = (slug: string, kind: OrgRef['kind']) => ({ id: slug.length, slug, name: slug, short: slug, emoji: '', cover: 0, kind, official: kind !== 'club' }) as OrgRef;
const ev = (id: number, o: Partial<EventCard> = {}) => ({ id, org: org('chess', 'club'), coHost: null, price: null, online: false, firstYear: false, ...o }) as EventCard;

const list = [
  ev(1),                                                              // a club's free event
  ev(2, { org: org('site', 'school'), price: 2000 }),                 // a school's paid one
  ev(3, { coHost: org('bs', 'school'), online: true }),               // a club with a school, online
  ev(4, { org: org('site', 'school'), school: 'site', firstYear: true }), // only for SITE's students, 1st year
  ev(5, { teamMin: 2, teamMax: 4, price: 500 }),                      // a team event
];
const ids = (f: Parameters<typeof filterEvents>[1]) => filterEvents(list, f).map((e) => e.id);

it('reads a type from what the card carries', () => {
  expect(list.filter((e) => isType(e, 'free')).map((e) => e.id)).toEqual([1, 3, 4]);
  expect(list.filter((e) => isType(e, 'paid')).map((e) => e.id)).toEqual([2, 5]);
  expect(list.filter((e) => isType(e, 'online')).map((e) => e.id)).toEqual([3]);
  expect(list.filter((e) => isType(e, 'firstYear')).map((e) => e.id)).toEqual([4]);
  expect(list.filter((e) => isType(e, 'team')).map((e) => e.id)).toEqual([5]);
});

it('takes a school from the host, the co-host or the event being only for it, once', () => {
  expect(list.map(schoolsOf)).toEqual([[], ['site'], ['bs'], ['site'], []]);
  expect(schoolsOf(ev(6, { org: org('chess', 'club'), school: 'fit' }))).toEqual(['fit']);
});

it('filters by school, by type, and by both at once; no filter is the same list', () => {
  expect(filterEvents(list, { school: null, type: null })).toBe(list);
  expect(ids({ school: 'site', type: null })).toEqual([2, 4]);
  expect(ids({ school: null, type: 'paid' })).toEqual([2, 5]);
  expect(ids({ school: 'site', type: 'free' })).toEqual([4]);
  expect(ids({ school: 'bs', type: 'paid' })).toEqual([]); // the empty state
});

it('offers only chips that lead somewhere, and keeps the chosen ones', () => {
  expect(choices(list, { school: null, type: null })).toEqual({ types: ['free', 'paid', 'online', 'firstYear', 'team'], schools: ['bs', 'site'] });
  expect(choices([ev(1)], { school: 'fit', type: 'online' })).toEqual({ types: ['free', 'online'], schools: ['fit'] });
});

it('one of each kind at a time; the chosen chip again clears it', () => {
  pick('type', 'paid');
  pick('type', 'online');
  pick('school', 'site');
  expect({ ...afishaFilter }).toEqual({ school: 'site', type: 'online' });
  pick('type', 'online');
  expect({ ...afishaFilter }).toEqual({ school: 'site', type: null });
  clearFilter();
  expect({ ...afishaFilter }).toEqual({ school: null, type: null });
});
