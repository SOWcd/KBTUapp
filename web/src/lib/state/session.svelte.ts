// Who is looking: the account from /api/me. Guests browse; any action goes through asStudent(),
// which opens the KBTU sign-in sheet and runs the action by itself after sign-in (SPEC §2).
import { api, ApiErr, type Me } from '../api';
import { CONSENT_VERSION } from '../legal';
import { tg } from '../tg';
import { clearCache } from './cache';
import { ACCOUNT_KEY, accountRequest, cancelAccountRequests, recovery } from './recovery';

// banned: the platform ban, why and whom to write; the app shows only that; policy: the version in force
// (the server's word: its forum part counts only with the forum on)
// board: the student forum (and the assistant, the event questions) is open to me: GET /api/me says so, the other
// answers that carry Me don't, so it's kept here; channel (the forum channel's tab) and tgComment too (a deleted Telegram comment of mine waits: App's moment)
export const session = $state({ me: null as Me | null, ready: false, verified: false, revoked: false, failed: false, banned: null as { reason: string | null; contact: string | null } | null, policy: CONSENT_VERSION, board: false, boardKnown: false, channel: false, tgComment: false,
  // /api/me alone carries these (a PATCH's me doesn't): kept apart so a settings change never drops them
  donate: '', support: [] as NonNullable<Me['support']> });

// Optimistic Settings switches survive a refresh that started before the PATCH finished.
export const pendingSwitches: Record<string, boolean> = {};

const authAt = Number(new URLSearchParams(tg.initData).get('auth_date')) || 0;
export function forgetRecovery(auth?: number): void {
  recovery.invalidate(tg.user?.id ?? session.me?.tg.id, auth);
  session.verified = false;
}
function revoke(auth?: number) {
  forgetRecovery(auth);
  cancelAccountRequests(true);
  session.me = null;
  session.revoked = true;
}
function banned(d: Record<string, unknown>) {
  clearCache(); // clear the snapshot before dropping the recovery scope
  forgetRecovery();
  cancelAccountRequests();
  session.banned = { reason: (d.reason as string | null) ?? null, contact: (d.contact as string | null) ?? null };
}
if (typeof window !== 'undefined') {
  addEventListener('kb:banned', (e) => banned((e as CustomEvent).detail ?? {}));
  addEventListener('kb:signedOut', () => revoke());
  addEventListener('kb:initExpired', () => { if (tg.initData) revoke(authAt); });
  addEventListener('storage', (e: StorageEvent) => {
    if ((e.key === ACCOUNT_KEY || e.key === null) && recovery.lost()) revoke();
  });
}

/** quiet: a background refresh; a failure leaves the screens as they are (no error page while coming back on a poor network). */
export async function loadMe(quiet = false): Promise<void> {
  if (session.revoked) return;
  const request = accountRequest(), previous = recovery.scope();
  const settingsAtStart = session.me?.settings;
  try {
    const me = await api.me();
    if (request.aborted) return;
    if (session.revoked || recovery.lost()) { revoke(); return; }
    if (tg.user?.id !== undefined && tg.user.id !== me.tg.id) { revoke(); return; }
    if (me.deleteAt) forgetRecovery();
    else if (!recovery.superseded()) {
      if (!recovery.verify(me.tg.id, me.id, !!me.student, me.no, authAt)) { revoke(); return; }
      if (previous && previous !== recovery.scope()) { revoke(); return; }
      session.verified = true;
    }
    if (session.me && session.me.id === me.id) {
      me.settings = { ...(session.me.settings === settingsAtStart ? me.settings : session.me.settings), ...pendingSwitches };
    }
    session.me = me; session.failed = false; session.banned = null; session.policy = me.consentNow ?? session.policy; session.board = !!me.board; session.channel = !!me.forumChannel; session.boardKnown = true; session.tgComment = !!me.tgComment; session.donate = me.donate ?? ''; session.support = me.support ?? [];
    if (me.avatar) new Image().src = me.avatar; // the profile tab opens with its photo in place
  } catch (x) {
    if (recovery.lost()) { revoke(); return; }
    if (!quiet && !request.aborted) session.failed = true;
    if (x instanceof ApiErr && x.code === 'forbidden' && x.message === 'banned') banned(x.data);
  } finally { session.ready = true; }
}

/** My running check-in, unless its event ended since the server said so. */
export const runningCheckin = (at = Date.now() / 1000) => { const c = session.me?.checkin; return c && c.until > at ? c : null; };

let loginHook: ((after: () => void, lock?: boolean) => void) | null = null;
export function setLoginHook(fn: (after: () => void, lock?: boolean) => void): void { loginHook = fn; }

// Microsoft's return link opens the app anew, and the action's closure is gone by then: `again` is the action as a start
// param (rc_<club>, newclub), kept on the phone and replayed after that sign-in
const AGAIN = 'kb-again', AGAIN_AGE = 30 * 60_000;
/** The bar's corner is KRI (Nav): the assistant open to me (BOARD) and I'm a student; else it is the map (a guest, BOARD
 *  off), and Afisha's header drops its own map button. */
export const kriCorner = (): boolean => session.board && !!session.me?.student;
// lock: the sheet fills the screen and can't be pulled or backed away until signed in (a check-in scan)
export function asStudent(action: () => void, again?: string, lock = false): void {
  if (session.revoked || session.banned) return;
  if (session.me?.student) return action();
  const owner = recovery.scope();
  recovery.write(owner, AGAIN, JSON.stringify(again ?? null));
  loginHook?.(() => {
    if (session.revoked || session.banned) return;
    takeAgain();
    action();
  }, lock);
}
/** The action a guest wanted before a Microsoft sign-in (half an hour at most), taken once. */
export function takeAgain(): string | null {
  const owner = recovery.scope();
  const p = recovery.read<string>(owner, AGAIN, AGAIN_AGE);
  if (p) recovery.clear(owner, AGAIN);
  return typeof p === 'string' ? p : null;
}
