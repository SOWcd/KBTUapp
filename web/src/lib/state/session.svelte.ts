// Who is looking: the account from /api/me. Guests browse; any action goes through asStudent(),
// which opens the KBTU sign-in sheet and runs the action by itself after sign-in (SPEC §2).
import { api, ApiErr, type Me } from '../api';

// banned: the platform ban (owner, Oct 22), why and whom to write; the app shows only that
export const session = $state({ me: null as Me | null, ready: false, failed: false, banned: null as { reason: string | null; contact: string | null } | null });

import { clearCache } from './cache';
function banned(d: Record<string, unknown>) {
  session.banned = { reason: (d.reason as string | null) ?? null, contact: (d.contact as string | null) ?? null };
  clearCache(); // the next launch doesn't show the old app first
}
if (typeof window !== 'undefined') addEventListener('kb:banned', (e) => banned((e as CustomEvent).detail ?? {}));

export async function loadMe(): Promise<void> {
  try { session.me = await api.me(); session.failed = false; session.banned = null; } catch (x) {
    session.failed = true;
    if (x instanceof ApiErr && x.code === 'forbidden' && x.message === 'banned') banned(x.data);
  }
  session.ready = true;
}

let loginHook: ((after: () => void) => void) | null = null;
export function setLoginHook(fn: (after: () => void) => void): void { loginHook = fn; }

export function asStudent(action: () => void): void {
  if (session.me?.student) action();
  else loginHook?.(action);
}

export const isStudent = () => !!session.me?.student;
