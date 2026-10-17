// A card the app only partly knows yet (opened from a friend row before the server answers) shows no numbers rather
// than wrong zeros; the full card shows all three.
import { expect, it } from 'vitest';
import { hero } from './awards';
import type { PersonCard } from './api';

const card = (attended: number): PersonCard => ({ id: 7, name: 'Ali T.', avatar: null, founder: false, no: 6, course: 2, school: 'SITE', bio: '', attended, past: [],
  clubs: [], showcase: [], shelf: [], awards: { achievements: [], badges: [] }, friendship: 'friends', friendsSince: 1, going: [] });

it('hides the numbers of a card it only partly knows', () => {
  expect(hero(card(-1)).loaded).toBe(false);
  expect(hero(card(3))).toMatchObject({ loaded: true, earned: 0, total: 0, next: null });
});

it('shows the card number zero-padded, a dash while there is none', () => {
  expect(hero(card(0)).no).toBe('00006');
  expect(hero({ ...card(0), founder: true, no: 0 }).no).toBe('00000');
  expect(hero({ ...card(0), no: null }).no).toBe('—');
});
