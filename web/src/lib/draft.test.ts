import { afterEach, expect, it, vi } from 'vitest';
import { accountDraft } from './draft';

afterEach(() => vi.unstubAllGlobals());

it.each(['kb-appeal', 'kb-ask', 'kb-round-7'])('isolates %s across account switches', (name) => {
  const store = new Map([[name, 'unattributed draft']]);
  vi.stubGlobal('localStorage', {
    removeItem: (k: string) => store.delete(k),
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => store.set(k, v),
  });
  const first = accountDraft(name, 11);
  expect(first.read()).toBeNull();
  expect(store.has(name)).toBe(false);
  first.save('first draft');
  const second = accountDraft(name, 12);
  expect(second.read()).toBeNull();
  second.save('second draft');
  first.save(null);
  expect(accountDraft(name, 12).read()).toBe('second draft');
  accountDraft(name, undefined).save('unknown');
  expect(store.size).toBe(1);
});
