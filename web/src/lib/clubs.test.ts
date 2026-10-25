import { describe, expect, it } from 'vitest';
import type { Org } from './api';
import { byWeight, hit } from './clubs';

const org = (id: number, name: string, members: number, subscribers: number, gov = false) => ({ id, name, members, subscribers, abbr: null, ...(gov ? { gov } : {}) }) as unknown as Org;

describe('the Clubs tab order', () => {
  it('puts the Student Government first, then members, then followers, empty clubs last', () => {
    const l = [org(1, 'Empty', 0, 0), org(2, 'Followed', 0, 9), org(3, 'Big', 30, 1), org(4, 'Gov', 2, 0, true), org(5, 'Mid', 30, 4)];
    expect(l.sort(byWeight).map((o) => o.name)).toEqual(['Gov', 'Mid', 'Big', 'Followed', 'Empty']);
  });
  it('finds by name or short name', () => {
    const o = { ...org(1, 'Open Mic', 1, 1), abbr: 'OM' } as Org;
    expect([hit(o, 'mic'), hit(o, ' om '), hit(o, 'chess')]).toEqual([true, true, false]);
  });
});
