import { afterEach, describe, expect, it, vi } from 'vitest';
import { draftRecord } from '../draft';
import { ACCOUNT_KEY, DRAFT_AGE, TICKETS_AGE, recoveryStore } from './recovery';

function device() {
  let at = 100_000;
  const values = new Map<string, string>();
  const storage: Storage = {
    get length() { return values.size; },
    key: (i) => [...values.keys()][i] ?? null,
    getItem: (key) => values.get(key) ?? null,
    setItem: (key, value) => { values.set(key, value); },
    removeItem: (key) => { values.delete(key); },
    clear: () => values.clear(),
  };
  return {
    storage, values, time: (ms: number) => { at += ms; },
    open: (web = false) => recoveryStore(() => storage, () => at, web),
  };
}
afterEach(() => vi.useRealTimers());

describe('account-scoped storage', () => {
  it('expires drafts after seven days without refreshing them on read', () => {
    const d = device(), first = d.open();
    first.verify(100, 1);
    first.write(first.scope(), 'kb-join-1', '"answer"');

    d.time(DRAFT_AGE - 1);
    const second = d.open();
    second.verify(100, 1);
    expect(second.read(second.scope(), 'kb-join-1', DRAFT_AGE)).toBe('answer');
    d.time(1);
    expect(second.read(second.scope(), 'kb-join-1', DRAFT_AGE)).toBeNull();
  });

  it('purges the prior account and legacy records, and rejects pending work from the prior account', () => {
    const d = device(), old = d.open();
    d.storage.setItem('kb-round-5', 'unowned');
    d.storage.setItem('kb-appeal', 'unowned');
    d.storage.setItem('kb-ask:100', 'without an expiry');
    old.verify(100, 1);
    old.write(old.scope(), 'kb-ask', '"private"');
    const oldOwner = old.scope();
    const pending = d.open();
    expect(pending.peek(100)).toBe(oldOwner);

    const next = d.open();
    expect(next.peek(200)).toBeNull();
    next.verify(200, 2);
    expect(old.lost()).toBe(true);
    expect(pending.lost()).toBe(true);
    expect(pending.verify(100, 1)).toBe(false);
    expect(next.read(next.scope(), 'kb-ask', DRAFT_AGE)).toBeNull();
    old.write(oldOwner, 'kb-ask', '"late"');
    expect(old.read(oldOwner, 'kb-ask', DRAFT_AGE)).toBeNull();
    expect([...d.values.keys()].every((k) => k === ACCOUNT_KEY || k.startsWith(next.scope()!))).toBe(true);
  });

  it('invalidates both copies on purge and rotates recovery when an erased student returns', () => {
    const d = device(), a = d.open();
    a.verify(100, 1, true, 52);
    a.write(a.scope(), 'kb-ask', '"student draft"');
    const b = d.open();
    b.verify(100, 1, false);
    expect(b.read(b.scope(), 'kb-ask', DRAFT_AGE)).toBeNull();
    expect(a.lost()).toBe(true);

    b.write(b.scope(), 'kb-ask', '"guest draft"');
    const c = d.open();
    c.verify(100, 1);
    expect(c.read(c.scope(), 'kb-ask', DRAFT_AGE)).toBe('guest draft');
    b.invalidate(100);
    expect(c.lost()).toBe(true);
    expect(c.read(c.scope(), 'kb-ask', DRAFT_AGE)).toBeNull();
  });

  it('keeps a newly verified account epoch when an older cold window notices the purge', () => {
    const d = device(), a = d.open();
    a.verify(100, 1, true, 52);
    const waiting = d.open();
    expect(waiting.peek(100)).toBe(a.scope());
    const next = d.open();
    next.verify(100, 1, false);
    next.write(next.scope(), 'kb-ask', '"new draft"');
    expect(waiting.lost()).toBe(true);
    waiting.invalidate(100);
    expect(next.read(next.scope(), 'kb-ask', DRAFT_AGE)).toBe('new draft');
  });

  it('keeps browser and Mini App drafts in separate sign-in scopes', () => {
    const d = device(), mini = d.open(), browser = d.open(true);
    mini.verify(100, 1);
    mini.write(mini.scope(), 'kb-ask', '"Mini App draft"');
    browser.verify(200, 2);
    browser.write(browser.scope(), 'kb-ask', '"browser draft"');

    const reopened = d.open(true);
    expect(reopened.verify(200, 2)).toBe(true);
    expect(reopened.read(reopened.scope(), 'kb-ask', DRAFT_AGE)).toBe('browser draft');
    browser.invalidate(200);
    expect(reopened.lost()).toBe(true);
    expect(reopened.read(reopened.scope(), 'kb-ask', DRAFT_AGE)).toBeNull();
    expect(mini.read(mini.scope(), 'kb-ask', DRAFT_AGE)).toBe('Mini App draft');
  });

  it('does not let an older expired Telegram credential purge a newer verified copy', () => {
    const d = device(), a = d.open();
    a.verify(100, 1, true, 52, 100);
    const b = d.open();
    b.verify(100, 1, true, 52, 200);
    b.write(b.scope(), 'kb-ask', '"new draft"');
    a.invalidate(100, 100);
    expect(b.read(b.scope(), 'kb-ask', DRAFT_AGE)).toBe('new draft');
  });

  it('leaves the verified app usable when storage is unavailable', () => {
    const window = recoveryStore(() => { throw new Error('storage denied'); });
    expect(window.verify(100, 1)).toBe(true);
    expect(window.scope()).toBeNull();
    expect(window.lost()).toBe(false);
  });
});

describe('offline tickets in the account scope', () => {
  const TICKETS = '[{"id":1}]';

  it('outlive a draft\'s week, then go after a month without a launch', () => {
    const d = device(), first = d.open();
    first.verify(100, 1);
    first.write(first.scope(), 'tickets', TICKETS);
    first.write(first.scope(), 'kb-ask', '"draft"');

    d.time(DRAFT_AGE + 1);
    const second = d.open();
    second.verify(100, 1);
    expect(second.read(second.scope(), 'kb-ask', DRAFT_AGE)).toBeNull();
    expect(second.read(second.scope(), 'tickets', TICKETS_AGE)).toEqual([{ id: 1 }]);
    d.time(TICKETS_AGE - DRAFT_AGE);
    const third = d.open();
    third.verify(100, 1);
    expect([...d.values.keys()].some((k) => k.endsWith(':tickets'))).toBe(false);
  });

  it('read before the server answers: the same Telegram user only; outside Telegram the last signed-in account', () => {
    const d = device(), mini = d.open(), web = d.open(true);
    mini.verify(100, 1);
    mini.write(mini.scope(), 'tickets', TICKETS);
    web.verify(200, 2);
    web.write(web.scope(), 'tickets', '[{"id":2}]');

    const mine = d.open(), theirs = d.open(), browser = d.open(true);
    expect(mine.read(mine.last(100), 'tickets', TICKETS_AGE)).toEqual([{ id: 1 }]);
    expect(theirs.last(300)).toBeNull(); // another Telegram account on this phone gets no scope: keptTickets reads nothing
    expect(browser.read(browser.last(), 'tickets', TICKETS_AGE)).toEqual([{ id: 2 }]);
  });

  it('go with signing out, and with a drop before any answer', () => {
    const d = device(), a = d.open(true);
    a.verify(200, 2);
    a.write(a.scope(), 'tickets', TICKETS);
    a.invalidate(200);
    expect(d.open(true).last()).toBeNull();
    expect([...d.values.keys()].some((k) => k.endsWith(':tickets'))).toBe(false);

    const b = d.open(true);
    b.verify(200, 2);
    b.write(b.scope(), 'tickets', TICKETS);
    const cold = d.open(true);
    cold.drop('tickets'); // the server said this browser is signed out
    expect(cold.read(cold.last(), 'tickets', TICKETS_AGE)).toBeNull();
  });
});

describe('deferred draft writes', () => {
  it('lets the newer edit win even when the old window flushes last', () => {
    vi.useFakeTimers();
    const d = device(), first = d.open(), second = d.open();
    first.verify(100, 1);
    second.verify(100, 1);
    const old = draftRecord<string>(first.scope(), 'kb-comment-post-7', first);
    const newer = draftRecord<string>(second.scope(), 'kb-comment-post-7', second);
    old.track(null);
    newer.track(null);
    old.track('old draft');
    d.time(1);
    newer.track('new draft');
    vi.advanceTimersByTime(300);
    old.flush();
    expect(newer.read()).toBe('new draft');
  });

  it('preserves edits made from another copy while a send is pending', () => {
    vi.useFakeTimers();
    const d = device(), first = d.open(), second = d.open();
    first.verify(100, 1);
    second.verify(100, 1);
    const sending = draftRecord<string>(first.scope(), 'kb-join-7', first);
    const editing = draftRecord<string>(second.scope(), 'kb-join-7', second);
    const sentAt = first.now();
    editing.track(null);
    d.time(1);
    editing.track('a newer answer');
    editing.flush();
    sending.discard(sentAt);
    expect(sending.read()).toBe('a newer answer');
  });

  it('keeps a pending edit in the sending form when an older send completes', () => {
    vi.useFakeTimers();
    const d = device(), store = d.open();
    store.verify(100, 1);
    const draft = draftRecord<string>(store.scope(), 'kb-ask', store);
    draft.track(null);
    draft.track('submitted text');
    const sentAt = store.now();
    d.time(1);
    draft.track('new edit');
    draft.discard(sentAt);
    draft.flush();
    expect(draft.read()).toBe('new edit');
  });

  it('clears stored text and queued edits immediately when going anonymous', () => {
    vi.useFakeTimers();
    const d = device(), store = d.open();
    store.verify(100, 1);
    const draft = draftRecord<string>(store.scope(), 'kb-appeal', store);
    draft.track(null);
    draft.track('named draft');
    draft.flush();
    draft.track('queued edit');
    draft.discard();
    draft.flush();
    expect(draft.read()).toBeNull();
    expect([...d.values.values()].some((v) => v.includes('named draft') || v.includes('queued edit'))).toBe(false);
  });

  it('drops drafts on discard and prevents old pending edits from reviving them', () => {
    vi.useFakeTimers();
    const d = device(), store = d.open();
    store.verify(100, 1);
    const older = draftRecord<string>(store.scope(), 'kb-appeal', store);
    const latest = draftRecord<string>(store.scope(), 'kb-appeal', store);
    older.track(null);
    older.track('previous text');
    d.time(1);
    latest.discard();
    older.flush();
    expect(latest.read()).toBeNull();
    expect([...d.values.values()].some((v) => v.includes('previous text'))).toBe(false);
  });
});
