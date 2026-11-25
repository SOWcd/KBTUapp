import { ApiErr } from '../api/errors';

/** A sheet's latest read. Keep the last response during a refresh, unless access is gone. */
export function readState<T>(fetch: () => Promise<T>, optionalTeam = false) {
  const state = $state({ value: undefined as T | undefined, status: 'loading' as 'loading' | 'ready' | 'error' | 'unavailable' });
  let latest = 0;
  async function load() {
    const request = ++latest;
    state.status = 'loading';
    try {
      const value = await fetch();
      if (request !== latest) return;
      state.value = value;
      state.status = 'ready';
    } catch (e) {
      if (request !== latest) return;
      if (e instanceof ApiErr && ['unauthorized', 'need_student', 'forbidden', 'not_found'].includes(e.code)) state.value = undefined;
      // Some door helpers may read guests but not the club's team (checkin._lists).
      state.status = optionalTeam && e instanceof ApiErr && e.code === 'forbidden' && e.message === 'screen' ? 'unavailable' : 'error';
    }
  }
  return { state, load };
}
