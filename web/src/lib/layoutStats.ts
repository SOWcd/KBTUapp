// The phone's layout numbers, once a launch (server logic/stats.py LAY_*; a lazy chunk, loaded by stats.ts painted()):
// where the phone puts its edges and where the tab bar ends up, so the owner reads them per platform without a
// screenshot (`admin stats-layout`). Buckets only: no exact size names a device.
import { bucketOf, count, platform, type LayMetric } from './stats';
import { tgTry } from './tg';

// 0, 1-8, 9-16, 17-24, 25-32, 33-48, 49-64, 65+ px (server stats.LAY)
const LAY_EDGES = [1, 9, 17, 25, 33, 49, 65];
const TG_MAJORS = ['6', '7', '8', '9', '10', '11', '12']; // server stats.TG_MAJORS; any other is 'x'
let done = false;

/** On the screen now, or when it next is (a hidden page has no layout worth reading). */
export function measure(): void {
  if (done) return;
  if (document.hidden) { document.addEventListener('visibilitychange', measure, { once: true }); return; }
  done = true;
  let major = 'x';
  const at = (m: LayMetric, px: number | undefined) => {
    if (typeof px === 'number' && isFinite(px)) count(`lay.${platform}.${major}.${m}.${bucketOf(Math.max(0, Math.round(px)), LAY_EDGES)}`);
  };
  tgTry((w) => {
    const v = /^\d+/.exec(w.version)?.[0] ?? '';
    major = TG_MAJORS.includes(v) ? v : 'x';
    at('safe_b', w.safeAreaInset?.bottom); at('safe_t', w.safeAreaInset?.top);
    at('content_b', w.contentSafeAreaInset?.bottom); at('content_t', w.contentSafeAreaInset?.top);
    if (w.viewportStableHeight) at('stable', innerHeight - w.viewportStableHeight); // under 0 counts as 0
    count(`lay.${platform}.${major}.full.${w.isFullscreen ? 1 : 0}`);
  });
  const probe = document.createElement('div');
  probe.style.cssText = 'position:fixed;left:0;top:0;width:1px;height:env(safe-area-inset-bottom,0px);visibility:hidden;pointer-events:none';
  document.body.append(probe);
  at('env_b', probe.offsetHeight);
  probe.remove();
  // the tab bar's lower edge to the window's (10 px of it is by design, Nav .dock); not while it's slid away or native
  const dock = document.querySelector('nav.nav')?.parentElement;
  const root = document.documentElement;
  if (dock && !('sheet' in root.dataset) && !('ntabs' in root.dataset)) at('gap', innerHeight - dock.getBoundingClientRect().bottom);
}
