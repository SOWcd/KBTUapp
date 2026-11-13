import { describe, expect, it } from 'vitest';
import { marked, missing } from './eventFill';

describe('the announcement fill', () => {
  it('marks the rows it filled', () => {
    expect(marked({}, true)).toEqual([]);
    expect(marked({ title: 'Quiz', start: '18:00', description: 'x', price: 500 }, true)).toEqual(['title', 'when', 'about', 'price']);
    expect(marked({ place: '256', price: 500 }, false)).toEqual(['place']); // no money rights: the price isn't put in
  });
  it('lists what is missing', () => {
    expect(missing({ date: '', start: '', place: ' ', tba: false })).toEqual(['date', 'time', 'place']);
    expect(missing({ date: '2026-11-20', start: '18:00', place: '', tba: true })).toEqual([]);
    expect(missing({ date: '2026-11-20', start: '', place: '256', tba: false })).toEqual(['time']);
  });
});
