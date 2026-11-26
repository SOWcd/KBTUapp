// Anonymous usage counters (server logic/stats.py, which keeps the same names): today's totals of each key, no person
// in them. Batched here, sent at most every 60 s and when the page hides; a failure is dropped. Never awaited: a tap
// costs one Map write.
import { inTelegram, on, onAndroid, onIos, tg } from './tg';
import type { Kind as HeroKind } from './hero'; // the Afisha hero's cards by kind (server stats.HERO)

export type Screen = 'tab.afisha' | 'tab.forum' | 'tab.club' | 'tab.profile'
  | 'sheet.event' | 'sheet.club' | 'sheet.ticket' | 'sheet.person' | 'sheet.friends' | 'sheet.compose' | 'sheet.comments'
  | 'sheet.map' | 'sheet.week' | 'sheet.awards' | 'sheet.studio' | 'sheet.news' | 'sheet.feed' | 'sheet.assistant'
  | 'sheet.scanner' | 'sheet.doorpeople' | 'sheet.attendees' | 'sheet.manage' | 'sheet.editor' | 'sheet.team' | 'sheet.member' | 'sheet.joininbox'
  | 'sheet.pay' | 'sheet.people' | 'sheet.sponsors' | 'sheet.teams';
// the second line: what shipped since Nov 20, each counted where it's used
type Action = 'do.signup' | 'do.follow' | 'do.forum' | 'do.casting' | 'do.qr' | 'do.donate'
  | 'do.coming' | 'do.heart' | 'do.comment' | 'do.research' | 'do.pymk' | 'do.pymkon' | 'do.share' | 'do.filter' | 'do.past'
  | 'do.calendar' | 'do.photo' | 'do.helpus' | 'do.anon' | 'do.chatlink' | 'do.kri';
// the appeals composer's funnel (server stats.APPEALS): counts only, never a word
type Appeal = 'apl.open' | 'apl.typed' | 'apl.ai' | 'apl.sent' | 'apl.drop' | 'apl.del';
type Android = 'andr.sheet' | 'andr.go'; // the Android tester sheet, shown and tapped (server stats.ANDROID_APP)
type Source = 'from.none' | 'from.event' | 'from.club' | 'from.friend' | 'from.qr' | 'from.other';
// the key flows' steps (a flow may start at a sheet's own count), then what ends one short (server stats.FUNNELS): counts only
type Funnel = 'signup.tap' | 'signup.done' | 'signup.fail'
  | 'paid.file' | 'paid.sent' | 'paid.fail' | 'paid.bot'
  | 'post.open' | 'post.typed' | 'post.sent' | 'post.fail' | 'post.drop'
  | 'edit.open' | 'edit.saved' | 'edit.fail'
  | 'join.tap' | 'join.sent' | 'join.fail'
  | 'streak.t0' | 'streak.t1' | 'streak.t2' | 'streak.t3' | 'streak.t4' | 'streak.tap';
// a JS error's class (by its constructor, or a chunk that didn't load), never its message (server stats.JS_KINDS)
type JsKind = 'type' | 'ref' | 'range' | 'syntax' | 'chunk' | 'other';
// a failed API call: no answer, a 5xx, or the server's error code (server stats.API_KINDS; api/types.ts ApiError)
export type ApiKind = 'network' | 'server' | 'unauthorized' | 'need_student' | 'forbidden' | 'not_found' | 'full' | 'closed' | 'conflict'
  | 'guest_list' | 'rate_limited' | 'bad_input' | 'unavailable';
type Platform = 'ios' | 'android' | 'desktop' | 'web';
type Bucket = 0 | 1 | 2 | 3 | 4 | 5;
type Long = Bucket | 6;
type Key = Screen | Action | Appeal | Android | Source | Funnel | `hero.${'show' | 'tap'}.${HeroKind}` | `err.${Screen}` | `uniq.${Screen | Action}` | `sess.${Long}` | `time.${Long}`
  | `open.${Platform}.${Bucket}` | `js.${Screen}.${JsKind}` | `api.${Screen}.${ApiKind}` | `tti.${Screen}.${Platform}.${Bucket}`;

const EVERY = 60_000, GAP = 30_000; // GAP: hidden this long, the next showing is a new session
const OPEN_EDGES = [1000, 2000, 3000, 5000, 8000];
export const TTI_EDGES = [100, 250, 500, 1000, 2000]; // a tab's or a sheet's tap to its first frame (server stats.TTI)
const min = 60_000;
export const SESS_EDGES = [min / 2, min, 3 * min, 5 * min, 10 * min, 20 * min];
export const DAY_EDGES = [min, 5 * min, 10 * min, 20 * min, 40 * min, 60 * min];
const bag = new Map<Key, number>();
let timer: ReturnType<typeof setTimeout> | undefined;

export function count(key: Key): void {
  bag.set(key, (bag.get(key) ?? 0) + 1);
  timer ??= setTimeout(flush, EVERY);
}

// What stays on this device only and is never sent as it is: today's visible time, the open session, today's uniq flags.
// A blocked or empty storage only costs these numbers.
type Kept = { d: number; ms: number; v: number; at: number; u: string[] };
const KEY = 'kb-stats';
const today = () => Math.floor((Date.now() / 1000 + 5 * 3600) / 86400); // Almaty's calendar
let kept: Kept = { d: today(), ms: 0, v: 0, at: 0, u: [] };
let canKeep = false;
try { const j = JSON.parse(localStorage.getItem(KEY) || 'null'); if (j && typeof j.d === 'number' && Array.isArray(j.u)) kept = j; } catch { /* blocked or corrupted */ }
function save(): void {
  try { localStorage.setItem(KEY, JSON.stringify(kept)); canKeep = true; } catch { canKeep = false; }
}

/** A new calendar day: one key with yesterday's (or the last used day's) visible time, and the flags start over. */
function roll(): void {
  const d = today();
  if (d === kept.d) return;
  if (kept.ms > 0) count(`time.${bucketOf(kept.ms, DAY_EDGES) as Long}`);
  kept = { ...kept, d, ms: 0, u: [] };
}

export function flush(): void {
  clearTimeout(timer);
  timer = undefined;
  roll();
  if (bag.size && tg.initData) {
    // ponytail: uniq.* is per device, not per person (two phones count twice): the share of people it gives is close, not
    // exact; per person would need an id next to the numbers, which this feature must never have
    if (canKeep) for (const k of [...bag.keys()]) if (/^(tab|sheet|do)\./.test(k) && !kept.u.includes(k)) { kept.u.push(k); bag.set(`uniq.${k}` as Key, 1); }
    // keepalive, not sendBeacon: a beacon can't carry the Authorization header
    void fetch('/api/stats', { method: 'POST', keepalive: true, headers: { Authorization: `tma ${tg.initData}`, 'Content-Type': 'application/json' }, body: JSON.stringify(Object.fromEntries(bag)) }).catch(() => {});
  }
  bag.clear();
  save();
}

/** The class of the launch's startapp parameter, for where people come from; its value never leaves this function. */
export function launchedFrom(p: string): Source {
  if (!p) return 'from.none';
  if (/^(ev|ph|cm|tk|mg|tc)_/.test(p)) return 'from.event';
  if (/^(cl|rc|iv|join|st|sn|tm|jr|ce|memo)_/.test(p)) return 'from.club';
  if (/^(fr|r|u)_/.test(p)) return 'from.friend';
  if (/^(ci|hq|bq|sh)_/.test(p)) return 'from.qr';
  return 'from.other';
}

/** The histogram's bucket: under 1, 2, 3, 5, 8 seconds, or more (logic/stats.py BUCKETS). */
export function bucketOf(ms: number, edges = OPEN_EDGES): number {
  const i = edges.findIndex((edge) => ms < edge);
  return i < 0 ? edges.length : i;
}

let hid = document.hidden; // opened in the background: its time says nothing about loading
const platform = !inTelegram ? 'web' : onIos ? 'ios' : onAndroid ? 'android' : 'desktop';

/** The first useful frame is on the screen: the app's open time, counted from navigation start. */
export function painted(): void {
  if (!hid) count(`open.${platform}.${bucketOf(performance.now()) as Bucket}`);
}

/** A tab or sheet asked for at `since` (performance.now()) is on the screen: counted at the frame after it drew. A page
 *  hidden meanwhile says nothing (frames stop while hidden). */
export function timed(screen: Screen, since: number): void {
  if (document.hidden) return;
  requestAnimationFrame(() => requestAnimationFrame(() => {
    if (!document.hidden) count(`tti.${screen}.${platform}.${bucketOf(performance.now() - since, TTI_EDGES) as Bucket}`);
  }));
}

/** An uncaught error or rejection on `screen`: its class only; the message is looked at here and never sent. */
export function crashed(screen: Screen, e: unknown): void {
  if (e && typeof e === 'object' && 'code' in e && 'data' in e) return; // an ApiErr: already counted as a failed call
  const kind = /dynamically imported module|module script failed|Unable to preload/i.test(e instanceof Error ? e.message : String(e)) ? 'chunk'
    : JS[(e as Error)?.name] ?? 'other';
  count(`js.${screen}.${kind}`);
}
const JS: Record<string, JsKind> = { TypeError: 'type', ReferenceError: 'ref', RangeError: 'range', SyntaxError: 'syntax' };

let shownAt = 0; // 0: not on the screen now

/** Back on the screen (or the app opened): hidden long enough, the last session ends here, also one a closed app left behind. */
function shown(): void {
  if (shownAt) return;
  roll();
  if (kept.at && Date.now() - kept.at >= GAP) {
    if (kept.v > 0) count(`sess.${bucketOf(kept.v, SESS_EDGES) as Long}`);
    kept.v = 0;
  }
  kept.at = 0;
  shownAt = Date.now();
}

function away(): void {
  if (shownAt) {
    const now = Date.now(), ms = Math.max(0, now - shownAt), midnight = (today() * 86400 - 5 * 3600) * 1000;
    const before = Math.min(ms, Math.max(0, midnight - shownAt)); // the part of the visit before today's midnight belongs to the old day
    shownAt = 0;
    kept.ms += before;
    roll();
    kept.ms += ms - before; kept.v += ms; kept.at = now;
  }
  flush();
}

save();
roll();
if (!document.hidden) shown();
document.addEventListener('visibilitychange', () => { if (document.hidden) { hid = true; away(); } else shown(); });
addEventListener('pagehide', away);
on('deactivated', away);
on('activated', shown);
