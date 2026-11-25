import { expect, test, vi } from 'vitest';
import { asked, offerDue, offerLater, restored, without } from './pymk';
import type { Friends, Suggestion } from './api';

const person = (id: number) => ({ id, name: `P${id}`, avatar: null, founder: false });
const s = (id: number, clubs = 1): Suggestion => ({ person: person(id), course: 2, school: 'SITE', clubs });
const page = (suggest: Suggestion[] | null): Friends => ({ friends: [], incoming: [], outgoing: [], going: [], suggest });

test('Add moves the card into my waiting requests at once, the next one moves up', () => {
  const f = page([s(1, 2), s(2), s(3)]);
  const next = asked(f, f.suggest![0], 100);
  expect(next.suggest!.map((x) => x.person.id)).toEqual([2, 3]);
  expect(next.outgoing).toEqual([{ person: person(1), fullName: 'P1', course: 2, school: 'SITE', at: 100 }]);
  expect(f.suggest).toHaveLength(3); // a new object: the old copy is the way back
});

test('the x takes the card away; a refusal puts it back in its place, once', () => {
  const f = page([s(1), s(2), s(3)]);
  const gone = without(f, 2);
  expect(gone.suggest!.map((x) => x.person.id)).toEqual([1, 3]);
  const back = restored(asked(gone, s(1), 5), s(2), 1);
  expect(back.suggest!.map((x) => x.person.id)).toEqual([3, 2]);
  expect(restored(back, s(2), 0)).toBe(back);
  expect(restored(asked(f, s(1), 5), s(1), 0).outgoing).toEqual([]);
  expect(without(page(null), 1).suggest).toBeNull(); // not turned on: nothing to take
});

test('"Not now" holds the offer back for 30 days on this phone; blocked storage just asks again', () => {
  const kept = new Map<string, string>();
  vi.stubGlobal('localStorage', { getItem: (k: string) => kept.get(k) ?? null, setItem: (k: string, v: string) => void kept.set(k, v) });
  expect(offerDue(1_000_000_000)).toBe(true);
  offerLater(1_000_000_000);
  expect(offerDue(1_000_000_000 + 29 * 86400)).toBe(false);
  expect(offerDue(1_000_000_000 + 31 * 86400)).toBe(true);
  vi.stubGlobal('localStorage', { getItem: () => { throw new Error('blocked'); }, setItem: () => { throw new Error('blocked'); } });
  expect(offerDue(1)).toBe(true);
  expect(() => offerLater(1)).not.toThrow();
  vi.unstubAllGlobals();
});
