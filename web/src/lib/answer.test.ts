import { describe, expect, it } from 'vitest';
import { answer } from './answer';

describe('answer', () => {
  it('splits the answer, the emoji facts and the source', () => {
    const a = answer('Room 264, second floor.\n\u{1F558} Mon-Fri 9:00-18:00\n\u{1F4CD} The Tole bi entrance\n(Student handbook, 2026)');
    expect(a.source).toBe('Student handbook, 2026');
    expect(a.lines).toEqual([
      { e: '', t: 'Room 264, second floor.' },
      { e: '\u{1F558}', t: 'Mon-Fri 9:00-18:00' },
      { e: '\u{1F4CD}', t: 'The Tole bi entrance' },
    ]);
  });
  it('has no source when the last line is not one bracketed group', () => {
    expect(answer('Yes.\nSee the policy (p. 3)').source).toBe('');
    expect(answer('Yes.\n(a) first and (b) second').source).toBe('');
    expect(answer('Yes.\n(a) first and (b) second').lines[1].t).toBe('(a) first and (b) second');
    expect(answer('Yes.\nAsk the office.').lines).toHaveLength(2);
  });
  it('keeps brackets inside the source', () => {
    expect(answer('Yes.\n(Policy (2026), p. 7.3)').source).toBe('Policy (2026), p. 7.3');
  });
  it('leaves a one-line answer whole', () => {
    expect(answer('(I do not know)')).toEqual({ source: '', lines: [{ e: '', t: '(I do not know)' }] });
    expect(answer('  Busy now  ').lines).toEqual([{ e: '', t: 'Busy now' }]);
  });
  it('drops empty lines', () => {
    expect(answer('One\n\n\nTwo\n').lines.map((l) => l.t)).toEqual(['One', 'Two']);
  });
  it('takes a keycap, a flag, a variation selector and a joined emoji as one lead', () => {
    expect(answer('Steps\n1️⃣ Apply')).toMatchObject({ lines: [{}, { e: '1️⃣', t: 'Apply' }] });
    expect(answer('Where\n\u{1F1F0}\u{1F1FF} Almaty').lines[1]).toEqual({ e: '\u{1F1F0}\u{1F1FF}', t: 'Almaty' });
    expect(answer('Mind\n⚠️ Below 50').lines[1]).toEqual({ e: '⚠️', t: 'Below 50' });
    expect(answer('Who\n\u{1F468}‍\u{1F3EB} The teacher').lines[1]).toEqual({ e: '\u{1F468}‍\u{1F3EB}', t: 'The teacher' });
    expect(answer('Hi\n\u{1F44B}\u{1F3FD} there').lines[1]).toEqual({ e: '\u{1F44B}\u{1F3FD}', t: 'there' });
  });
  it('does not take a digit, or an emoji with no words, for a lead', () => {
    expect(answer('When\n9:00 to 18:00').lines[1]).toEqual({ e: '', t: '9:00 to 18:00' });
    expect(answer('Ok\n\u{1F44D}').lines[1]).toEqual({ e: '', t: '\u{1F44D}' });
  });
});
