// Who is looking: the account from /api/me. Guests browse; any action goes through asStudent(),
// which opens the KBTU sign-in sheet and runs the action by itself after sign-in (SPEC §2).
import { api, type Me } from '../api';

export const session = $state({ me: null as Me | null, ready: false, failed: false });

export async function loadMe(): Promise<void> {
  try { session.me = await api.me(); session.failed = false; } catch { session.failed = true; }
  session.ready = true;
}

let loginHook: ((after: () => void) => void) | null = null;
export function setLoginHook(fn: (after: () => void) => void): void { loginHook = fn; }

export function asStudent(action: () => void): void {
  if (session.me?.student) action();
  else loginHook?.(action);
}

export const isStudent = () => !!session.me?.student;
