import { describe, expect, it } from 'vitest';
import { marked, merge, missing, nextQuestion, updateDraft, type ChatFill } from './eventFill';

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
    const now = { title: 'Quiz', date: '2026-11-20', endDate: '', start: '18:00', end: '', place: '', description: 'Old', price: '' };
    expect(merge(now, { title: 'Other', start: '19:00', end: '21:00', place: '305', description: 'Old and new', price: 500 })).toEqual({
      set: { description: 'Old and new', end: '21:00', place: '305', price: '500' }, differs: [{ k: 'start', v: '19:00' }] });
    expect(merge(now, { date: '2026-11-20', start: ' 18:00' })).toEqual({ set: {}, differs: [] }); // the same: nothing to ask
    // a default the organiser never set counts as empty
    expect(merge(now, { start: '19:00' }, { start: '18:00' }).set).toEqual({ start: '19:00' });
    expect(merge(now, { endDate: '2026-11-21' }).set).toEqual({ endDate: '2026-11-21' }); // a second day
  });
});

it('keeps unknown decisions distinct from explicit defaults throughout the chat', () => {
  let d: ChatFill = { title: 'Quiz', start: '19:00', date: '2027-02-01', place: 'Hall' };
  const turns = [
    ['paid', { paid: true }], ['price', { price: 500 }], ['payTo', { payTo: 'Test Recipient' }], ['payPhone', { payPhone: '+77000000000' }],
    ['seats', { seats: 0 }], ['registration', { registration: 'date' }], ['regDate', { regDate: '2027-01-31' }],
    ['regTime', { regTime: '18:00' }], ['teams', { teams: true }], ['teamMin', { teamMin: 2 }], ['teamMax', { teamMax: 4 }], ['teamCap', { teamCap: 0 }],
  ] as const;
  for (const [question, patch] of turns) {
    expect(nextQuestion(d, true)).toBe(question);
    d = updateDraft(d, patch);
  }
  expect(nextQuestion(d, true)).toBe('ready');
  expect(nextQuestion(d, false)).toBe('paidRight');
  expect(nextQuestion(updateDraft(d, { meeting: true }), true)).toBe('meeting');
  d = updateDraft(d, { paid: false, registration: 'start', teams: false, tba: true });
  expect(d).toMatchObject({ paid: false, teams: false, tba: true, seats: 0 });
  for (const key of ['price', 'payPhone', 'payTo', 'teamMax', 'regDate', 'place']) expect(d).not.toHaveProperty(key);
  expect(nextQuestion(d, true)).toBe('ready');
});
