// The service worker (dist/sw.js, built by vite.config.ts serviceWorker(); main.ts registers it in production only).
// Its rules are lib/shell.ts. The API, media and other pages never pass through it: a student's data is never kept here.
// ponytail: no kill switch in the app. To take the worker off phones, deploy a sw.js that only deletes the kb-shell-*
// caches and calls self.registration.unregister() (a 404 for sw.js stops updates but leaves the installed worker running).
import { DEADLINE, firstOf, keepsAsset, keepsPage, ofBuild, route, stale, type Shell } from './lib/shell';

// this build's shell, written in by vite.config.ts
const SHELL = '__KB_SHELL__' as unknown as Shell;

// the parts of the worker's scope this file uses (the app's tsconfig has the DOM's types, not the worker's)
interface Ext extends Event { waitUntil(p: Promise<unknown>): void }
interface Fetch extends Ext { request: Request; preloadResponse: Promise<Response | undefined>; respondWith(r: Promise<Response>): void }
const sw = self as unknown as {
  registration: { scope: string; navigationPreload?: { enable(): Promise<void> } };
  clients: { claim(): Promise<void> };
  skipWaiting(): Promise<void>;
  addEventListener(type: 'install' | 'activate', fn: (e: Ext) => void): void;
  addEventListener(type: 'fetch', fn: (e: Fetch) => void): void;
};
const scope = () => sw.registration.scope;
const got = async (url: string, init: RequestInit) => {
  const r = await fetch(url, init);
  if (!r.ok || url.includes('/assets/') && !keepsAsset(r)) throw new Error(`kb-sw: ${r.status} ${url}`);
  return r;
};

// A new deploy's worker takes over at once (skipWaiting, claim): its shell is complete before it does, the old ones go.
sw.addEventListener('install', (e) => {
  void sw.skipWaiting();
  e.waitUntil((async () => {
    const cache = await caches.open(SHELL.cache);
    // a sw.js of another build than the page the server sends now (a CDN's copy): no install, tried again next launch
    const page = await got(scope(), { cache: 'reload' });
    if (!ofBuild(await page.clone().text(), SHELL.entry)) throw new Error('kb-sw: the page is of another build');
    await Promise.all(SHELL.files.map(async (f) => {
      const url = new URL(f, scope()).href;
      // a hashed file never changes: the last build's copy is this one (30 deploys a day re-download only what changed)
      const had = f.startsWith('assets/') ? await caches.match(url) : undefined;
      await cache.put(url, had && keepsAsset(had) ? had : await got(url, { cache: 'no-cache' }));
    }));
    await cache.put(scope(), page);
    // Telegram's own file: an opaque answer, kept as it is; without it the app still opens (then as in a browser)
    if (SHELL.sdk) await fetch(SHELL.sdk, { mode: 'no-cors' }).then((r) => cache.put(SHELL.sdk!, r)).catch(() => {});
  })());
});

sw.addEventListener('activate', (e) => e.waitUntil((async () => {
  // the page's request starts while the worker wakes up, not after: the worker never delays the first paint
  await sw.registration.navigationPreload?.enable().catch(() => {});
  await Promise.all(stale(await caches.keys(), SHELL.cache).map((k) => caches.delete(k)));
  await sw.clients.claim();
})()));

sw.addEventListener('fetch', (e) => {
  const r = e.request, how = route({ url: r.url, method: r.method, mode: r.mode, range: r.headers.has('range') }, scope());
  if (how === 'page') e.respondWith(page(e));
  else if (how === 'asset') e.respondWith(asset(e));
  else if (how === 'copy') e.respondWith(copy(e));
});

// (no preloadResponse before Safari 15.4: the worker's own fetch, started before anything else)
function page(e: Fetch): Promise<Response> {
  const net = Promise.resolve(e.preloadResponse).then((r) => r ?? fetch(e.request)).then((r) => {
    if (keepsPage(e.request.url, scope(), r)) {
      const copy = r.clone();
      e.waitUntil(copy.clone().text().then((html) => ofBuild(html, SHELL.entry) ? caches.open(SHELL.cache).then((c) => c.put(scope(), copy)) : undefined));
    }
    return r;
  });
  e.waitUntil(net.catch(() => {}));
  return firstOf(net, () => caches.open(SHELL.cache).then((c) => c.match(scope())), DEADLINE);
}

async function asset(e: Fetch): Promise<Response> {
  const cache = await caches.open(SHELL.cache), had = await cache.match(e.request);
  if (had) return had;
  const r = await fetch(e.request);
  // a lazy screen opened once is there offline too (until the next build's worker)
  if (keepsAsset(r)) e.waitUntil(cache.put(e.request, r.clone()));
  return r;
}

async function copy(e: Fetch): Promise<Response> {
  const cache = await caches.open(SHELL.cache), had = await cache.match(e.request);
  const net = fetch(e.request).then((r) => {
    if (r.ok || r.type === 'opaque') e.waitUntil(cache.put(e.request, r.clone()));
    return r;
  });
  if (!had) return net;
  e.waitUntil(net.catch(() => {}));
  return had;
}
