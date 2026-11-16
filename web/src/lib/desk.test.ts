import { describe, expect, it } from 'vitest';
import type { OrgRef } from './api';
import { chosen, deskRegistry } from './desk';

describe('deskRegistry', () => {
  it('opens for an overseer on a computer with a plain launch', () => expect(deskRegistry(true, '', true)).toBe(true));
  it('a start param of its own wins', () => {
    for (const p of ['ev_12', 'cl_3', 'ms_abc', 'friends']) expect(deskRegistry(true, p, true)).toBe(false);
  });
  it('never on a phone, never for others', () => {
    expect(deskRegistry(true, '', false)).toBe(false);
    expect(deskRegistry(false, '', true)).toBe(false);
    expect(deskRegistry(undefined, '', true)).toBe(false);
  });
  it('opened once in this launch: no auto-open', () => expect(deskRegistry(true, '', true, true)).toBe(false));
});

describe('chosen', () => {
  const org = (id: number, official = false) => ({ id, name: `Club ${id}`, official }) as unknown as OrgRef;
  it('follows the row by id (a toggled check replaces the object)', () => {
    const rows = [{ org: org(1) }, { org: org(2, true) }];
    expect(chosen(2, rows, null)).toBe(rows[1].org);
    rows[1] = { org: org(2, false) };
    expect(chosen(2, rows, null)?.official).toBe(false);
  });
  it('nothing chosen when the list on screen lacks it', () => {
    expect(chosen(3, [{ org: org(1) }], null)).toBe(null);
    expect(chosen(1, [{ org: org(1) }], [])).toBe(null);
    expect(chosen(1, [{ org: org(1) }], [{ clubs: [{ org: org(2) }] }])).toBe(null);
    expect(chosen(null, [{ org: org(1) }], null)).toBe(null);
  });
  it('a club found by search: the registry row when there is one', () => {
    const rows = [{ org: org(2, true) }];
    expect(chosen(2, rows, [{ clubs: [{ org: org(2) }] }])).toBe(rows[0].org);
    expect(chosen(5, rows, [{ clubs: [{ org: org(5) }] }])?.id).toBe(5);
  });
});
