import { expect, it, vi } from 'vitest';
import { ApiErr } from '../api/errors';
import { readState } from './readState.svelte';

function deferred<T>() {
  let resolve!: (value: T) => void, reject!: (error: unknown) => void;
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

it('distinguishes a pending or failed roster from a successfully empty roster and retries', async () => {
  const request = deferred<string[]>();
  const fetch = vi.fn().mockReturnValueOnce(request.promise).mockResolvedValueOnce([]);
  const { state, load } = readState<string[]>(fetch);
  const loading = load();
  expect(state).toEqual({ status: 'loading', value: undefined });
  request.reject(new Error('offline'));
  await loading;
  expect(state).toEqual({ status: 'error', value: undefined });
  const retry = load();
  expect(state.status).toBe('loading');
  await retry;
  expect(state).toEqual({ status: 'ready', value: [] });
});

it('keeps the last roster while refreshing or offline, but drops it when access is revoked', async () => {
  const refresh = deferred<string[]>();
  const fetch = vi.fn().mockResolvedValueOnce(['Guest']).mockReturnValueOnce(refresh.promise)
    .mockRejectedValueOnce(new ApiErr('forbidden'));
  const { state, load } = readState<string[]>(fetch);
  await load();
  const loading = load();
  expect(state).toEqual({ status: 'loading', value: ['Guest'] });
  refresh.reject(new Error('offline'));
  await loading;
  expect(state).toEqual({ status: 'error', value: ['Guest'] });
  await load();
  expect(state).toEqual({ status: 'error', value: undefined });
});

it('ignores older successes and failures after a newer roster request', async () => {
  const first = deferred<string[]>(), second = deferred<string[]>(), third = deferred<string[]>();
  const fetch = vi.fn().mockReturnValueOnce(first.promise).mockReturnValueOnce(second.promise).mockReturnValueOnce(third.promise);
  const { state, load } = readState<string[]>(fetch);
  const a = load(), b = load(), c = load();
  third.resolve(['Latest']); await c;
  first.resolve(['Old']); await a;
  second.reject(new ApiErr('forbidden')); await b;
  expect(state).toEqual({ status: 'ready', value: ['Latest'] });
});

it.each(['unauthorized', 'need_student', 'not_found'] as const)('clears a previous roster after %s', async (code) => {
  const fetch = vi.fn().mockResolvedValueOnce(['Guest']).mockRejectedValueOnce(new ApiErr(code));
  const { state, load } = readState<string[]>(fetch);
  await load();
  await load();
  expect(state).toEqual({ status: 'error', value: undefined });
});

it('omits an unavailable optional team roster without hiding other failures', async () => {
  const fetch = vi.fn().mockResolvedValueOnce(['Team member']).mockRejectedValueOnce(new ApiErr('forbidden', 'screen'))
    .mockRejectedValueOnce(new Error('offline')).mockRejectedValueOnce(new ApiErr('forbidden', 'consent'));
  const { state, load } = readState<string[]>(fetch, true);
  await load();
  await load();
  expect(state).toEqual({ status: 'unavailable', value: undefined });
  await load();
  expect(state.status).toBe('error');
  await load();
  expect(state.status).toBe('error');
});

it('distinguishes a round read failure from a confirmed closed round, then recovers on retry', async () => {
  const fetch = vi.fn().mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce(null)
    .mockResolvedValueOnce({ open: true });
  const { state, load } = readState<{ open: boolean } | null>(fetch);
  await load();
  expect(state).toEqual({ status: 'error', value: undefined });
  await load();
  expect(state).toEqual({ status: 'ready', value: null });
  await load();
  expect(state).toEqual({ status: 'ready', value: { open: true } });
});
