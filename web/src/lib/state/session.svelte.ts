// Who is looking: the account from /api/me. Guests browse; any action goes through asStudent(),
// which opens the KBTU sign-in sheet and runs the action by itself after sign-in.
import { api, ApiErr, type Me, type ReportLogEntry, type Settings } from '../api';
import { CONSENT_VERSION } from '../legal';
import { inTelegram, tg } from '../tg';
import { clearCache } from './cache';
import { accountRequest, cancelAccountRequests, recovery } from './recovery';

// banned: the platform ban, why and whom to write; the app shows only that; policy: the version in force
// (the server's word: its forum part counts only with the forum on)
// board: the student forum (and the assistant, the event questions) is open to me: GET /api/me says so, the other
// answers that carry Me don't, so it's kept here; channel (the forum channel's tab) and tgComment too (a deleted Telegram comment of mine waits: App's moment)
export const session = $state({ me: null as Me | null, ready: false, verified: false, revoked: false, failed: false, banned: null as { reason: string | null; contact: string | null } | null, policy: CONSENT_VERSION, board: false, boardKnown: false, channel: false, tgComment: false,
  // /api/me alone carries these (a PATCH's me doesn't): kept apart so a settings change never drops them
  donate: '', support: [] as NonNullable<Me['support']>,
  reportLog: null as { owner: number; entries: ReportLogEntry[] } | null,
  reportConsentRevision: 0, reportConsentBusy: false });

// Optimistic Settings switches survive a refresh that started before the PATCH finished.
const pendingSwitches: Partial<Record<SwitchKey, boolean>> = {};
const savedSwitches: Partial<Record<SwitchKey, boolean>> = {};
type SwitchKey = Exclude<keyof Settings, 'lang' | 'theme'>;
let saveQueue: Promise<unknown> = Promise.resolve();

/** Apply the switch immediately and keep the latest choice visible during refreshes and saves. */
export function saveSwitch(key: SwitchKey, on: boolean): Promise<boolean> {
  if (!session.me) return Promise.resolve(false);
  savedSwitches[key] ??= session.me.settings[key];
  session.me.settings[key] = on;
  pendingSwitches[key] = on;
  const save = saveQueue.then(async () => {
    if (pendingSwitches[key] !== on) return false;
    try {
      const next = await api.updateMe({ [key]: on });
      if (pendingSwitches[key] === on) {
        delete pendingSwitches[key];
        delete savedSwitches[key];
      } else savedSwitches[key] = next.settings[key];
      if (session.me?.id === next.id) next.reports = session.me.reports; // PATCH omits report consent
      session.me = { ...next, settings: { ...next.settings, ...pendingSwitches } };
      return true;
    } catch (error) {
      if (pendingSwitches[key] === on) {
        delete pendingSwitches[key];
        if (session.me) session.me.settings[key] = savedSwitches[key] ?? !on;
        delete savedSwitches[key];
      }
      throw error;
    }
  });
  saveQueue = save.catch(() => {});
  return save;
}

const authAt = Number(new URLSearchParams(tg.initData).get('auth_date')) || 0;
export function forgetRecovery(tgId = tg.user?.id ?? session.me?.tg.id, auth?: number): void {
  recovery.invalidate(tgId, auth);
  session.verified = false;
}
function revoke(auth?: number) {
  forgetRecovery(undefined, auth);
  cancelAccountRequests(true);
  session.me = null;
  session.reportLog = null;
  session.revoked = true;
}
function banned(d: Record<string, unknown>) {
  clearCache(); // clear the snapshot before dropping the recovery scope
  forgetRecovery();
  cancelAccountRequests();
  session.banned = { reason: (d.reason as string | null) ?? null, contact: (d.contact as string | null) ?? null };
  session.reportLog = null;
}
if (typeof window !== 'undefined') {
  addEventListener('kb:banned', (e) => banned((e as CustomEvent).detail ?? {}));
  addEventListener('kb:signedOut', () => revoke());
  addEventListener('kb:web-session-ended', () => { if (!inTelegram && session.me) revoke(); });
  addEventListener('kb:initExpired', () => { if (tg.initData) revoke(authAt); });
  addEventListener('storage', (e: StorageEvent) => {
    if ((e.key === recovery.accountKey || e.key === null) && recovery.lost()) revoke();
  });
}

/** quiet: a background refresh; a failure leaves the screens as they are (no error page while coming back on a poor network). */
export async function loadMe(quiet = false, withReportLog = false, initial?: Awaited<ReturnType<typeof api.me>>): Promise<void> {
  if (session.revoked) return;
  const request = accountRequest(), previous = recovery.scope();
  const settingsAtStart = session.me?.settings;
  const reportRevision = session.reportConsentRevision;
  try {
    // The personal log lives in memory only. App saves session.me in its startup cache.
    const { reportLog, ...me } = initial ?? await api.me(withReportLog);
    if (request.aborted) return;
    if (session.revoked || recovery.lost()) { revoke(); return; }
    if (tg.user?.id !== undefined && tg.user.id !== me.tg.id) { revoke(); return; }
    if (me.deleteAt) forgetRecovery(me.tg.id);
    else if (!recovery.superseded()) {
      if (!recovery.verify(me.tg.id, me.id, !!me.student, me.no, authAt)) { revoke(); return; }
      if (previous && previous !== recovery.scope()) { revoke(); return; }
      session.verified = true;
    }
    if (session.me && session.me.id === me.id) {
      me.settings = { ...(session.me.settings === settingsAtStart ? me.settings : session.me.settings), ...pendingSwitches };
    }
    const sameAccount = session.me?.id === me.id;
    const staleConsent = sameAccount && (session.reportConsentBusy || reportRevision !== session.reportConsentRevision);
    const consentGranted = !staleConsent && sameAccount && session.me?.reports?.consent === false && me.reports?.consent;
    if (staleConsent) me.reports = session.me?.reports;
    else if (!me.reports?.consent) session.reportLog = null;
    else if (reportLog) session.reportLog = { owner: me.id, entries: reportLog };
    else if (session.reportLog?.owner !== me.id) session.reportLog = null;
    session.me = me; session.failed = false; session.banned = null; session.policy = me.consentNow ?? session.policy; session.board = !!me.board; session.channel = !!me.forumChannel; session.boardKnown = true; session.tgComment = !!me.tgComment; session.donate = me.donate ?? ''; session.support = me.support ?? [];
    if (consentGranted && !withReportLog) void loadMe(true, true);
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
  if (inTelegram) recovery.write(recovery.scope(), AGAIN, JSON.stringify(again ?? null));
  loginHook?.(() => {
    if (session.revoked || session.banned) return;
    if (inTelegram) takeAgain();
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
