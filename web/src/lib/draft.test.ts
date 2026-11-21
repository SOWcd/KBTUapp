import { expect, it } from 'vitest';
import { draftRecord } from './draft';
import { recoveryStore } from './state/recovery';

it.each(['kb-appeal', 'kb-ask', 'kb-round-7'])('requires a verified account and clears %s on account switch', (name) => {
  const values = new Map([[name, 'unattributed draft']]);
  const storage: Storage = {
    get length() { return values.size; },
    key: (i) => [...values.keys()][i] ?? null,
    removeItem: (k) => { values.delete(k); },
    getItem: (k) => values.get(k) ?? null,
    setItem: (k, v) => { values.set(k, v); },
    clear: () => values.clear(),
  };
  const a = recoveryStore(() => storage);
  a.verify(11, 1);
  const first = draftRecord<string>(a.scope(), name, a);
  expect(first.read()).toBeNull();
  expect(values.has(name)).toBe(false);
  first.track(null);
  first.track('first draft');
  first.flush();

  const b = recoveryStore(() => storage);
  const unverified = draftRecord<string>(b.peek(11), name, b);
  expect(unverified.read()).toBeNull();
  b.verify(12, 2);
  const second = draftRecord<string>(b.scope(), name, b);
  expect(second.read()).toBeNull();
  second.track(null);
  second.track('second draft');
  second.flush();
  first.track('late edit');
  first.flush();
  expect(first.read()).toBeNull();
  expect(second.read()).toBe('second draft');
  expect([...values.values()].some((v) => v.includes('first draft') || v.includes('late edit'))).toBe(false);
});
