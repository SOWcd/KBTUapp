// Who is looking: the account from /api/me. Guests browse; any action goes through asStudent(),
// which opens the KBTU sign-in sheet and runs the action by itself after sign-in (SPEC §2).
import { api, ApiErr, type Me } from '../api';
import { CONSENT_VERSION } from '../legal';

// banned: the platform ban, why and whom to write; the app shows only that; policy: the version in force
// (the server's word: its forum part counts only with the forum on)
export const session = $state({ me: null as Me | null, ready: false, failed: false, banned: null as { reason: string | null; contact: string | null } | null, policy: CONSENT_VERSION });

import { clearCache } from './cache';
function banned(d: Record<string, unknown>) {
  session.banned = { reason: (d.reason as string | null) ?? null, contact: (d.contact as string | null) ?? null };
  clearCache(); // the next launch doesn't show the old app first
}
if (typeof window !== 'undefined') addEventListener('kb:banned', (e) => banned((e as CustomEvent).detail ?? {}));

export async function loadMe(): Promise<void> {
  try {
    session.me = await api.me(); session.failed = false; session.banned = null; session.policy = session.me.consentNow ?? session.policy;
    if (session.me.avatar) new Image().src = session.me.avatar; // the profile tab opens with its photo in place
  } catch (x) {
    session.failed = true;
    if (x instanceof ApiErr && x.code === 'forbidden' && x.message === 'banned') banned(x.data);
  }
  session.ready = true;
}

let loginHook: ((after: () => void) => void) | null = null;
export function setLoginHook(fn: (after: () => void) => void): void { loginHook = fn; }

// Microsoft's return link opens the app anew, and the action's closure is gone by then: `again` is the action as a start
// param (rc_<club>, newclub), kept on the phone and replayed after that sign-in
const AGAIN = 'kb-again';
export function asStudent(action: () => void, again?: string): void {
  if (session.me?.student) return action();
  try { if (again) localStorage.setItem(AGAIN, JSON.stringify({ p: again, at: Date.now() })); else localStorage.removeItem(AGAIN); } catch { /* blocked */ }
  loginHook?.(() => { takeAgain(); action(); });
}
/** The action a guest wanted before a Microsoft sign-in (half an hour at most), taken once */
export function takeAgain(): string | null {
  try {
    const a = JSON.parse(localStorage.getItem(AGAIN) ?? 'null');
    localStorage.removeItem(AGAIN);
    return a && Date.now() - a.at < 30 * 60_000 ? String(a.p) : null;
  } catch { return null; }
}

export const isStudent = () => !!session.me?.student;
