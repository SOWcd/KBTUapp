import { describe, expect, it } from 'vitest';
import { once, order, rank, textScore } from './find';

// Cyrillic by code point (the repo's rule outside UI strings)
const MATAN = String.fromCodePoint(0x41c, 0x430, 0x442, 0x435, 0x43c, 0x430, 0x442, 0x438, 0x43a, 0x430); // "Matematika"
const ROBO = String.fromCodePoint(0x420, 0x43e, 0x431, 0x43e, 0x442, 0x43e, 0x442, 0x435, 0x445, 0x43d, 0x438, 0x43a, 0x430); // "Robototekhnika"

describe('global search ranking', () => {
  const names = (x: { n: string }) => [x.n];

  it('finds by prefix, Latin transliteration and the wrong layout, case-insensitively', () => {
    const items = [{ n: ROBO }, { n: MATAN }, { n: 'Chess club' }];
    expect(rank('CHESS', items, names).map((f) => f.item.n)).toEqual(['Chess club']);
    expect(rank('matem', items, names).map((f) => f.item.n)).toEqual([MATAN]); // Latin-typed Russian
    expect(rank('vfntv', items, names).map((f) => f.item.n)).toEqual([MATAN]); // typed on the English layout
  });

  it('puts exact prefixes before looser matches, keeps the source order on ties, and caps', () => {
    const items = [{ n: 'Debate' }, { n: 'Dance' }, { n: 'Dancing' }];
    expect(rank('danc', items, names).map((f) => f.item.n)).toEqual(['Dance', 'Dancing']);
    expect(rank('d', items, names, 2)).toHaveLength(2);
    expect(rank('zzz', items, names)).toEqual([]);
  });

  it('a long text matches by its words, never by a typo', () => {
    expect(textScore('tutor', 'Looking for a calculus tutor')).toBe(3);
    expect(textScore('tuotr', 'Looking for a calculus tutor')).toBe(0);
  });

  it('orders groups by their best match, ties in the fixed order', () => {
    const f = (score: number) => [{ item: 1, score }];
    expect(order({ subject: f(3), club: f(2), event: f(2), place: f(3) })).toEqual(['place', 'subject', 'event', 'club']);
    expect(order({ event: [], news: f(1) })).toEqual(['news']);
  });

  it('keeps the first copy', () => {
    expect(once([{ id: 1, a: 1 }, { id: 2 }, { id: 1, a: 2 }], (x) => x.id)).toEqual([{ id: 1, a: 1 }, { id: 2 }]);
  });
});
