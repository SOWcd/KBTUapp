import { describe, expect, it } from 'vitest';
import { deskRegistry } from './desk';

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
});
