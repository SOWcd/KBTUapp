import { afterEach, describe, expect, it, vi } from 'vitest';
import { draftRecord } from '../draft';
import { ACCOUNT_KEY, DRAFT_AGE, recoveryStore, SCREEN_AGE } from './recovery';
import { checkpoint, launchNavigation, readNavigation, type Navigation } from './navigation';

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
const nav: Navigation = { tab: 'club', club: 3, scroll: { top: 480, item: 'club-3', offset: 24 }, sheet: { kind: 'event', id: 7 } };
const home: Navigation = { tab: 'afisha', club: null, scroll: { top: 0 }, sheet: null };
function save(store: ReturnType<typeof recoveryStore>, value: unknown) {
  store.writeCheckpoint(store.scope(), 'kb-nav', JSON.stringify(value));
}
afterEach(() => vi.useRealTimers());

describe('cold Mini App recovery', () => {
  it('recovers a tab, anchor and one safe sheet after verifying the Telegram identity', () => {
    const d = device(), first = d.open();
    first.verify(100, 1);
    save(first, nav);

    const reopened = d.open();
    expect(readNavigation(reopened)).toBeNull();
    expect(reopened.verify(100, 1)).toBe(true);
    expect(readNavigation(reopened)).toEqual(nav);
  });

  it('ignores invalid destinations and extra overlay data', () => {
    const d = device(), window = d.open();
    window.verify(100, 1);
    for (const kind of ['ticket', 'qr', 'receipt', 'scanner', 'admin', 'join', 'award', 'compose']) {
      save(window, { ...home, sheet: { kind, id: 1, token: 'example' }, stack: [nav.sheet] });
      expect(readNavigation(window)).toEqual(home);
    }
    save(window, { ...nav, sheet: { ...nav.sheet, token: 'example' } });
    expect(readNavigation(window)).toEqual(nav);
  });

  it('does not read a checkpoint when an explicit link or verified Microsoft return is present', () => {
    const read = vi.fn(() => nav);
    expect(launchNavigation('ev_19', false, read)).toBeNull();
    expect(launchNavigation('unknown_link', false, read)).toBeNull();
    expect(launchNavigation('', true, read)).toBeNull();
    expect(read).not.toHaveBeenCalled();
    expect(launchNavigation('', false, read)).toEqual(nav);
  });

  it('expires screens after six hours and drafts after seven days without refreshing either on read', () => {
    const d = device(), first = d.open();
    first.verify(100, 1);
    save(first, nav);
    first.write(first.scope(), 'kb-join-1', '"answer"');

    d.time(SCREEN_AGE - 1);
    const second = d.open();
    second.verify(100, 1);
    expect(readNavigation(second)).toEqual(nav);
    d.time(1);
    expect(readNavigation(second)).toBeNull();
    expect(second.read(second.scope(), 'kb-join-1', DRAFT_AGE)).toBe('answer');
    d.time(DRAFT_AGE - SCREEN_AGE);
    expect(second.read(second.scope(), 'kb-join-1', DRAFT_AGE)).toBeNull();
  });

  it('keeps the latest actual change between two copies, including when the older copy hides', () => {
    const d = device(), first = d.open();
    first.verify(100, 1);
    const second = d.open();
    second.verify(100, 1);
    const old = { ...home, tab: 'profile' as const };
    const saveFirst = checkpoint((json) => first.writeCheckpoint(first.scope(), 'kb-nav', json), home);
    const saveSecond = checkpoint((json) => second.writeCheckpoint(second.scope(), 'kb-nav', json), home);

    saveFirst(old);
    d.time(1);
    saveSecond(nav);
    d.time(1);
    saveFirst(old);
    expect(readNavigation(first)).toEqual(nav);
    expect([...d.values.keys()].filter((k) => k.includes(':kb-nav:'))).toHaveLength(2);
    saveFirst(home);
    expect(readNavigation(second)).toEqual(home);
  });

  it('purges the prior account and legacy records, and rejects pending work from the prior account', () => {
    const d = device(), old = d.open();
    d.storage.setItem('kb-round-5', 'unowned');
    d.storage.setItem('kb-appeal', 'unowned');
    d.storage.setItem('kb-ask:100', 'without an expiry');
    old.verify(100, 1);
    save(old, nav);
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
    save(a, nav);
    const b = d.open();
    b.verify(100, 1, false);
    expect(readNavigation(b)).toBeNull();
    expect(a.lost()).toBe(true);

    save(b, nav);
    const c = d.open();
    c.verify(100, 1);
    b.invalidate(100);
    expect(c.lost()).toBe(true);
    expect(readNavigation(c)).toBeNull();
  });

  it('keeps a newly verified account epoch when an older cold window notices the purge', () => {
    const d = device(), a = d.open();
    a.verify(100, 1, true, 52);
    const waiting = d.open();
    expect(waiting.peek(100)).toBe(a.scope());
    const next = d.open();
    next.verify(100, 1, false);
    save(next, home);
    expect(waiting.lost()).toBe(true);
    waiting.invalidate(100);
    expect(readNavigation(next)).toEqual(home);
  });

  it('restores a browser checkpoint without disturbing the Mini App when signing out', () => {
    const d = device(), mini = d.open(), browser = d.open(true);
    mini.verify(100, 1);
    save(mini, nav);
    browser.verify(200, 2);
    save(browser, home);

    const reopened = d.open(true);
    expect(reopened.verify(200, 2)).toBe(true);
    expect(readNavigation(reopened)).toEqual(home);
    browser.invalidate(200);
    expect(reopened.lost()).toBe(true);
    expect(readNavigation(reopened)).toBeNull();
    expect(readNavigation(mini)).toEqual(nav);
  });

  it('does not let an older expired Telegram credential purge a newer verified copy', () => {
    const d = device(), a = d.open();
    a.verify(100, 1, true, 52, 100);
    const b = d.open();
    b.verify(100, 1, true, 52, 200);
    save(b, nav);
    a.invalidate(100, 100);
    expect(readNavigation(b)).toEqual(nav);
  });

  it('leaves the verified app usable when storage is unavailable', () => {
    const window = recoveryStore(() => { throw new Error('storage denied'); });
    expect(window.verify(100, 1)).toBe(true);
    expect(window.scope()).toBeNull();
    expect(window.lost()).toBe(false);
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
