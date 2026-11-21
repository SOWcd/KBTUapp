// Device-local recovery shared by Mini App copies. An account marker invalidates leases held by older copies.
export const ACCOUNT_KEY = 'kb-recovery-account';
const PREFIX = 'kb-recovery:';
export const SCREEN_AGE = 6 * 60 * 60_000;
export const DRAFT_AGE = 7 * 24 * 60 * 60_000;
const V = 1;

interface Account { tg: number; user: number; epoch: string }
type RecordOf<T> = { v: number; at: number; value: T | null };
const scopeOf = (a: Account) => `${PREFIX}${a.tg}:${a.epoch}:`;
const accountId = (n: unknown): n is number => typeof n === 'number' && Number.isSafeInteger(n) && n > 0;
const clock = () => {
  const wall = Date.now(), precise = performance.timeOrigin + performance.now();
  return precise >= wall && precise < wall + 1 ? precise : wall;
};
const epoch = () => Math.random().toString(36).slice(2);

export function recoveryStore(storage: () => Storage, now = clock) {
  const get = (key: string) => { try { return storage().getItem(key); } catch { return null; } };
  const set = (key: string, value: string) => { try { storage().setItem(key, value); } catch { /* blocked or full */ } };
  const remove = (key: string) => { try { storage().removeItem(key); } catch { /* blocked */ } };
  const parse = <T,>(raw: string | null): T | null => { try { return JSON.parse(raw ?? 'null'); } catch { return null; } };
  const marker = () => get(ACCOUNT_KEY);
  const account = (raw: string | null) => {
    const a = parse<Account>(raw);
    return a && accountId(a.tg) && accountId(a.user) && typeof a.epoch === 'string' ? a : null;
  };
  const launch = marker(), windowId = epoch();
  let lease: string | null = null, cached: string | null = null;
  let stopped = false;
  const live = () => !stopped && !!lease && lease === marker();
  const fresh = (at: number, age: number) => {
    const current = now();
    return Number.isFinite(at) && at <= current && current - at < age;
  };
  function keys(): string[] {
    try { return Array.from({ length: storage().length }, (_, i) => storage().key(i) ?? ''); }
    catch { return []; }
  }
  function sweep(expected: string | null, keep?: Account) {
    const scope = keep && scopeOf(keep);
    for (const key of keys()) {
      if (marker() !== expected) return;
      if (/^kb-(?:nav|appeal|ask|again|round-\d+|cache-\d+)(?::\d+)?$/.test(key)) remove(key);
      else if (key.startsWith(PREFIX)) {
        if (!scope || !key.startsWith(scope)) { remove(key); continue; }
        if (key === scope + 'student' || key === scope + 'auth' || key === scope + 'snapshot') continue;
        const ttl = key.includes(':kb-nav:') ? SCREEN_AGE : key.endsWith(':kb-again') ? 30 * 60_000 : DRAFT_AGE;
        if (!fresh(parse<RecordOf<unknown>>(get(key))?.at ?? NaN, ttl)) remove(key);
      }
    }
  }
  function verify(tg: number, user: number, student = false, card?: number | null, auth = 0): boolean {
    if (stopped || !accountId(tg) || !accountId(user)) return false;
    const raw = marker(), existing = account(raw), same = existing?.tg === tg && existing.user === user;
    if (lease && (lease !== raw || !same)) return false;
    if (!lease && raw !== launch && (!same || account(launch)?.tg === tg)) {
      stopped = true;
      return false;
    }
    // Erasure keeps the Telegram row and makes it a guest, even if no copy saw the pending deletion.
    const oldCard = same ? get(scopeOf(existing) + 'student') : null;
    const erased = oldCard !== null && (!student || card != null && oldCard !== 's' && oldCard !== String(card));
    const first = !lease;
    lease = same && !erased ? raw : JSON.stringify({ tg, user, epoch: epoch() });
    if (lease !== raw) set(ACCOUNT_KEY, lease!);
    if (live()) {
      const a = account(lease)!;
      const prefix = scopeOf(a);
      if (student) set(prefix + 'student', card == null ? oldCard ?? 's' : String(card));
      if (auth > Number(get(prefix + 'auth'))) set(prefix + 'auth', String(auth));
      if (first || erased) sweep(lease, a);
    } else lease = null; // storage is blocked or full, but the verified app can run without it
    return true;
  }
  function invalidate(tg?: number, auth?: number) {
    const raw = marker(), a = account(raw), held = lease ?? cached;
    if (a && (held ? held === raw : launch === raw && a.tg === tg) && (auth === undefined || auth >= Number(get(scopeOf(a) + 'auth')))) {
      set(ACCOUNT_KEY, 'null'); // storage events tell the other copies to drop their account state
      sweep('null');
    } else if (!a) sweep(raw);
    stopped = true;
    lease = null;
  }
  const scope = () => live() ? scopeOf(account(lease)!) : null;
  const peek = (tg?: number) => {
    const raw = marker(), a = account(raw);
    if (stopped || raw !== launch || !a || a.tg !== tg) return null;
    cached = raw;
    return scopeOf(a);
  };
  function readRecord<T>(key: string, age: number): RecordOf<T> | null {
    const r = parse<RecordOf<T>>(get(key));
    return r?.v === V && fresh(r.at, age) ? r : null;
  }
  const readable = (owner: string | null) => !!owner && (owner === scope() || owner === peek(account(launch)?.tg));
  const read = <T,>(owner: string | null, key: string, age: number): T | null =>
    readable(owner) ? readRecord<T>(owner + key, age)?.value ?? null : null;
  function newest<T>(owner: string | null, key: string, age: number): T | null {
    if (!readable(owner)) return null;
    let best: RecordOf<T> | null = null;
    for (const k of keys().sort()) {
      if (!k.startsWith(owner + key + ':')) continue;
      const r = readRecord<T>(k, age);
      if (r && (!best || r.at >= best.at)) best = r;
    }
    return best?.value ?? null;
  }
  function write(owner: string | null, key: string, json: string, at = now()) {
    if (!owner || scope() !== owner) return;
    const k = owner + key;
    // The instant-load snapshot can be large. Read just the previous write's envelope.
    const prior = get(k), end = prior?.indexOf(',"value":') ?? -1;
    const last = parse<RecordOf<unknown>>(prior && end > 0 ? prior.slice(0, end) + '}' : null);
    if (last?.v === V && last.at > at && last.at <= now()) return;
    set(k, `{"v":${V},"at":${at},"value":${json}}`);
    if (scope() !== owner) remove(k);
  }
  function clear(owner: string | null, key: string) {
    if (owner && scope() === owner) remove(owner + key);
  }
  const writeCheckpoint = (owner: string | null, key: string, json: string) => write(owner, key + ':' + windowId, json);
  return { verify, invalidate, scope, peek, read, write, clear, newest, writeCheckpoint, now, lost: () => !stopped && (lease ?? cached) !== null && (lease ?? cached) !== marker(), superseded: () => stopped };

}

export const recovery = recoveryStore(() => localStorage);

let requests = new AbortController();
let closed = false;
export function cancelAccountRequests(revoke = false): void {
  requests.abort();
  requests = new AbortController();
  closed ||= revoke;
}
export const accountRequest = () => requests.signal;
export const accountClosed = () => closed || recovery.lost();
