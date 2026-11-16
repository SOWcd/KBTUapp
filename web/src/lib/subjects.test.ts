import { describe, expect, it } from 'vitest';
import { byName, fold, subjectOf } from './subjects';

const CALC = '\u0418\u0441\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u0435 2';
describe('subjects', () => {
  it('folds spacing, case and look-alikes as the server tool does', () => {
    expect(fold(' \u0418\u0441\u0447\u0438\u0441\u043b\u0435\u043d\u0438\u0435  2 ')).toBe(fold(CALC));
    expect(fold('\u0410\u043d\u0433\u043b\u0438\u0439\u0441\u043a\u0438\u0439 (B1)')).toBe(fold('\u0410\u043d\u0433\u043b\u0438\u0439\u0441\u043a\u0438\u0439(\u04121)')); // Latin B, Cyrillic V
  });
  it("finds a class's card by any of its names", () => {
    const idx = byName([{ id: 'a1', name: CALC, codes: ['MAT1246'] }]);
    const c = { weekday: 1, begins: '09:00', ends: '10:00', subject: 'Calculus 2', kind: null, room: null, teacher: null };
    expect(subjectOf(c, idx)).toBeUndefined();
    expect(subjectOf({ ...c, names: { ru: CALC + ' ' } }, idx)?.id).toBe('a1');
  });
});
