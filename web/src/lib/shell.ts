// The service worker's rules (src/sw.ts runs them, vite.config.ts picks its files with them), pure so vitest checks them.
// One cache per build: the page, the code its first screen runs, the screens a ticket needs offline, the fonts and icons.

export const PREFIX = 'kb-shell-';
// Telegram's SDK comes from its own origin, and without it the app can't tell it runs in Telegram: offline, a student
// would land on the browser's sign-in instead of the ticket
export const SDK = 'https://telegram.org/js/telegram-web-app.js';
// the page from the network first; past this the kept copy opens the app (campus wifi that holds a request)
export const DEADLINE = 3000;
// lazy chunks the shell carries: the other languages (main.ts waits for one before the first render), the entrance
// outside Telegram (the home-screen app, the TWA), the ticket itself and the kept tickets' block (ui/OfflineTickets)
export const LAZY = ['kk', 'en', 'WebEntrance', 'TicketView', 'OfflineTickets'];
// Inter's files for Russian, Kazakh (cyrillic-ext) and English; the other subsets load if a page ever needs them
export const FONTS = /^assets\/inter-(?:latin|cyrillic|cyrillic-ext)-opsz-normal-[\w-]+\.woff2$/;
// public files the page and the home screen ask for by name (not hashed: refreshed in the background)
export const PUBLIC = ['manifest.json', 'favicon.svg', 'icon-192.png', 'icon-512.png', 'apple-touch-icon.png'];
const APP_PATHS = ['', 'show', 'screen'];

/** A chunk as the bundle describes it (Vite's manifest is made from the same graph). */
export interface Chunk { fileName: string; name?: string; imports?: string[]; css?: string[] }
export interface Shell { cache: string; entry: string; files: string[]; sdk: string | null }

/** What one build's worker keeps: what index.html loads, the LAZY chunks, each with the code and CSS it imports
 *  statically, the fonts. Not the images code imports: the ticket's module alone names every club's lanyard art (5 MB);
 *  the QR needs none of it, and what a screen shows online is kept as it loads (route 'asset').
 *  ponytail: art shown once is gone after the next deploy's worker; carry it over if a phone shows tickets without it */
export function shellOf(html: string, chunks: Chunk[], names: string[], lazy = LAZY): Shell {
  const byFile = new Map(chunks.map((c) => [c.fileName, c]));
  const files = new Set<string>();
  const add = (f: string) => {
    if (files.has(f)) return;
    files.add(f);
    const c = byFile.get(f);
    for (const g of [...(c?.imports ?? []), ...(c?.css ?? [])]) add(g);
  };
  const entry = /<script type="module"[^>]*\ssrc="\.\/(assets\/[^"]+\.js)"/.exec(html)?.[1];
  if (!entry) throw new Error('kb-sw: no entry script in index.html');
  for (const m of html.matchAll(/\s(?:src|href)="\.\/(assets\/[^"?#]+)"/g)) add(m[1]);
  for (const name of lazy) {
    const c = chunks.find((x) => x.name === name);
    if (!c) throw new Error(`kb-sw: no chunk named ${name}`);
    add(c.fileName);
  }
  for (const f of names) if (FONTS.test(f)) add(f);
  const sdk = /<script[^>]*\ssrc="(https:\/\/telegram\.org\/js\/telegram-web-app\.js[^"]*)"/.exec(html)?.[1] ?? null;
  const list = [...[...files].sort(), ...PUBLIC];
  return { cache: PREFIX + hash(html + '\n' + list.join('\n')), entry, files: list, sdk };
}

/** FNV-1a, 32 bits: a build's name, not a secret. */
export function hash(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 0x01000193);
  return (h >>> 0).toString(36);
}

/** page: network first (the next deploy at the next launch), the kept copy offline or past DEADLINE; asset: a hashed
 *  file, cache first; copy: the kept copy at once, refreshed for next time; null: the worker stays out (the API, media,
 *  other pages, anything not a GET, a range of a video). */
export type Route = 'page' | 'asset' | 'copy' | null;
export function route(req: { url: string; method: string; mode: string; range?: boolean }, scope: string): Route {
  if (req.method !== 'GET' || req.range) return null;
  const u = new URL(req.url), s = new URL(scope);
  if (u.origin + u.pathname === SDK) return 'copy';
  if (u.origin !== s.origin || !u.pathname.startsWith(s.pathname)) return null;
  const rel = u.pathname.slice(s.pathname.length);
  if (rel.startsWith('api/')) return null;
  // the app's own pages only (main.ts: /, /show, /screen); every other path is the server's (/privacy, a form under /f/,
  // a club's short link redirecting to t.me, /old/): served the app's page offline it would break or lie
  if (req.mode === 'navigate') return APP_PATHS.includes(rel.replace(/\/$/, '')) ? 'page' : null;
  if (rel.startsWith('assets/')) return 'asset';
  return PUBLIC.includes(rel) ? 'copy' : null;
}

/** The app's page as the server sent it now: kept as the next offline launch's shell (never a redirect or an error). */
export const keepsPage = (url: string, scope: string, r: { ok: boolean; type: string; redirected: boolean }): boolean =>
  new URL(url).pathname === new URL(scope).pathname && r.ok && r.type === 'basic' && !r.redirected;

/** A page of this worker's build only: a newer deploy's page in this cache would name lazy chunks it never kept (the
 *  ticket offline would fail); the newer worker keeps its own page as it installs. */
export const ofBuild = (html: string, entry: string): boolean => html.includes(entry);

/** How long a launch waits for the network before the kept page. Once the network has answered with a newer build (its
 *  worker not installed yet: a slow line, the Mini App closed early), never past it: launches wait for the network, so
 *  an old page opens online at most once. Offline the kept page still opens at once (firstOf: the network failed). */
export const deadline = (newerSeen: boolean): number => (newerSeen ? Infinity : DEADLINE);

/** A hashed file's answer worth keeping: never HTML (a missing file the server answered with its page). */
export const keepsAsset = (r: { ok: boolean; headers: { get(k: string): string | null } }): boolean =>
  r.ok && !(r.headers.get('content-type') ?? '').startsWith('text/html');

/** The kept caches a new build's worker deletes as it takes over: other builds' shells, never anything not ours. */
export const stale = (keys: string[], current: string): string[] => keys.filter((k) => k.startsWith(PREFIX) && k !== current);

/** The network's answer; past `ms` (Infinity: never), or when it fails, the kept copy if there is one (the network's still
 *  lands, for next time); neither: the network's own failure. */
export function firstOf<T>(net: Promise<T>, kept: () => Promise<T | undefined>, ms: number): Promise<T> {
  return new Promise((resolve, reject) => {
    let done = false;
    const give = (r: T) => { if (!done) { done = true; clearTimeout(late); resolve(r); } };
    // (a timer of Infinity fires at once)
    const late = Number.isFinite(ms) ? setTimeout(() => void kept().then((k) => { if (k) give(k); }, () => {}), ms) : undefined;
    net.then(give, async (e) => {
      clearTimeout(late);
      const k = await kept().catch(() => undefined);
      if (k) give(k);
      else if (!done) { done = true; reject(e); }
    });
  });
}
