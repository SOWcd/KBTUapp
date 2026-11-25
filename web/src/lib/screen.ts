export type ScreenState = { code: string; bot: string; session?: number; title?: string; ended?: number | null;
  done?: number; pending?: number; param?: string | null; phase?: 'in' | 'out'; departed?: number; expires: number };
const KEEP = 'kb-show';

// One request at a time per pairing; a reset or unmount makes every older response inert.
export function screenPoll(receive: (state: ScreenState | null) => void) {
  let secret = '', generation = 0, stopped = false;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let request: AbortController | undefined;
  try { secret = sessionStorage.getItem(KEEP) ?? ''; localStorage.removeItem(KEEP); } catch { /* storage unavailable */ }
  function save() {
    try { if (secret) sessionStorage.setItem(KEEP, secret); else sessionStorage.removeItem(KEEP); } catch { /* storage unavailable */ }
  }
  async function poll() {
    const gen = generation, at = Date.now(), pairing = !secret;
    const controller = request = new AbortController();
    const deadline = setTimeout(() => controller.abort(), 12_000);
    try {
      const r = await fetch(pairing ? '/api/screen/pair' : '/api/screen', {
        ...(pairing ? { method: 'POST' } : { headers: { 'X-Screen': secret } }), signal: controller.signal,
      });
      const body = await r.json().catch(() => null);
      if (stopped || gen !== generation) return;
      if (!pairing && r.status === 403 && body?.message === 'screen') {
        secret = ''; save(); receive(null);
      } else if (r.ok && body) {
        const { secret: pairedSecret, ...state } = body;
        if (pairing) { secret = pairedSecret; save(); }
        const seconds = state.session == null ? (state.left ?? state.ttl ?? 0) : (state.ttl ?? 0);
        receive({ ...state, expires: at + seconds * 1000 });
        if (state.session == null && seconds <= 0) { secret = ''; save(); }
      }
    } catch { /* Keep the tab's secret through a network failure. */ }
    finally {
      clearTimeout(deadline);
      if (!stopped && gen === generation) timer = setTimeout(poll, 2000);
    }
  }
  void poll();
  return {
    again() { generation++; clearTimeout(timer); request?.abort(); secret = ''; save(); receive(null); void poll(); },
    stop() { stopped = true; clearTimeout(timer); request?.abort(); },
  };
}

export function screenView(state: ScreenState | null, now: number) {
  const fresh = !!state && now < state.expires;
  return {
    fresh,
    entry: fresh && state?.param ? state.bot + state.param : '',
    pair: fresh && state ? state.bot + 'sh_' + state.code : '',
    arrivals: state?.done ?? 0,
  };
}
