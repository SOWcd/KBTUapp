// Anonymous usage counters (server logic/stats.py, which keeps the same names): today's totals of each key, no person
// in them. Batched here, sent at most every 60 s and when the page hides; a failure is dropped. Never awaited: a tap
// costs one Map write.
import { inTelegram, on, onAndroid, onIos, tg } from './tg';

export type Screen = 'tab.afisha' | 'tab.forum' | 'tab.club' | 'tab.profile'
  | 'sheet.event' | 'sheet.club' | 'sheet.ticket' | 'sheet.person' | 'sheet.friends' | 'sheet.compose' | 'sheet.comments'
  | 'sheet.map' | 'sheet.week' | 'sheet.awards' | 'sheet.studio' | 'sheet.admin' | 'sheet.news' | 'sheet.feed' | 'sheet.assistant';
type Action = 'do.signup' | 'do.follow' | 'do.forum' | 'do.casting' | 'do.qr' | 'do.donate';
type Source = 'from.none' | 'from.event' | 'from.club' | 'from.friend' | 'from.qr' | 'from.other';
type Bucket = 0 | 1 | 2 | 3 | 4 | 5;
type Key = Screen | Action | Source | `err.${Screen}` | `open.${'ios' | 'android' | 'desktop' | 'web'}.${Bucket}`;

const EVERY = 60_000;
const bag = new Map<Key, number>();
let timer: ReturnType<typeof setTimeout> | undefined;

export function count(key: Key): void {
  bag.set(key, (bag.get(key) ?? 0) + 1);
  timer ??= setTimeout(flush, EVERY);
}

export function flush(): void {
  clearTimeout(timer);
  timer = undefined;
  if (!bag.size) return;
  const body = JSON.stringify(Object.fromEntries(bag));
  bag.clear();
  if (!tg.initData) return;
  // keepalive, not sendBeacon: a beacon can't carry the Authorization header
  void fetch('/api/stats', { method: 'POST', keepalive: true, headers: { Authorization: `tma ${tg.initData}`, 'Content-Type': 'application/json' }, body }).catch(() => {});
}

/** The class of the launch's startapp parameter, for where people come from; its value never leaves this function. */
export function launchedFrom(p: string): Source {
  if (!p) return 'from.none';
  if (/^(ev|ph|cm|tk|mg)_/.test(p)) return 'from.event';
  if (/^(cl|rc|iv|join|st|tm|jr|ce|memo)_/.test(p)) return 'from.club';
  if (/^(fr|r|u)_/.test(p)) return 'from.friend';
  if (/^(ci|hq|bq|sh)_/.test(p)) return 'from.qr';
  return 'from.other';
}

/** The histogram's bucket: under 1, 2, 3, 5, 8 seconds, or more (logic/stats.py BUCKETS). */
export function bucketOf(ms: number): Bucket {
  const i = [1000, 2000, 3000, 5000, 8000].findIndex((edge) => ms < edge);
  return (i < 0 ? 5 : i) as Bucket;
}

let hid = document.hidden; // opened in the background: its time says nothing about loading
const platform = !inTelegram ? 'web' : onIos ? 'ios' : onAndroid ? 'android' : 'desktop';

/** The first useful frame is on the screen: the app's open time, counted from navigation start. */
export function painted(): void {
  if (!hid) count(`open.${platform}.${bucketOf(performance.now())}`);
}

document.addEventListener('visibilitychange', () => { if (document.hidden) { hid = true; flush(); } });
addEventListener('pagehide', flush);
on('deactivated', flush);
