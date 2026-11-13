import { describe, expect, it } from 'vitest';
import { marked, merge, missing } from './eventFill';

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
  it('adds a second message without overwriting the form', () => {
    const now = { title: 'Quiz', date: '2026-11-20', start: '18:00', end: '', place: '', description: 'Old', price: '' };
    expect(merge(now, { title: 'Other', start: '19:00', end: '21:00', place: '305', description: 'Old and new', price: 500 })).toEqual({
      set: { description: 'Old and new', end: '21:00', place: '305', price: '500' }, differs: [{ k: 'start', v: '19:00' }] });
    expect(merge(now, { date: '2026-11-20', start: ' 18:00' })).toEqual({ set: {}, differs: [] }); // the same: nothing to ask
    // a default the organiser never set counts as empty
    expect(merge(now, { start: '19:00' }, { start: '18:00' }).set).toEqual({ start: '19:00' });
  });
});
