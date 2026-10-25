import { describe, expect, it } from 'vitest';
import { fmtPhone, kzPhone } from './phone';

describe('fmtPhone', () => {
  it('reads every shape a number arrives in', () => {
    for (const v of ['8 (701) 234-56-78', '87012345678', '+77012345678', '+7 701 234 56 78', '7012345678', '+7 8701 234 56 78'])
      expect(fmtPhone(v)).toBe('+7 701 234 56 78');
  });
  it('formats while typing and deleting', () => {
    expect(fmtPhone('7')).toBe('+7 7');
    expect(fmtPhone('8')).toBe('');            // the trunk 8 typed first
    expect(fmtPhone('870')).toBe('+7 70');
    expect(fmtPhone('+7 70662')).toBe('+7 706 62');
    expect(fmtPhone('+7 ')).toBe('');
    expect(fmtPhone('')).toBe('');
  });
});

describe('kzPhone', () => {
  it('gives the kept shape only for a whole number', () => {
    expect(kzPhone('8 (701) 234-56-78')).toBe('+77012345678');
    expect(kzPhone('+7 701 234 56 7')).toBeNull();
    expect(kzPhone('')).toBeNull();
  });
});
