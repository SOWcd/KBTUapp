import { afterEach, describe, expect, it, vi } from 'vitest';
import { DEADLINE, FONTS, firstOf, hash, keepsAsset, keepsPage, LAZY, ofBuild, PREFIX, PUBLIC, route, shellOf, stale, type Chunk } from './shell';

const SCOPE = 'https://kbtu.sow.kz/';
const get = (url: string, mode = 'no-cors', extra: { method?: string; range?: boolean } = {}) => ({ url, mode, method: 'GET', ...extra });

describe('route', () => {
  it('sends the app\'s own pages network-first, any query or deep path, /show too', () => {
    expect(route(get(SCOPE, 'navigate'), SCOPE)).toBe('page');
    expect(route(get(SCOPE + '?tgWebAppStartParam=ev_5#tgWebAppData=x', 'navigate'), SCOPE)).toBe('page');
    expect(route(get(SCOPE + 'show', 'navigate'), SCOPE)).toBe('page');
  });

  it('leaves the server\'s own files and pages to the network, even offline', () => {
    for (const p of ['install.html', 'privacy.html', '.well-known/assetlinks.json', 'manifest.json', 'privacy', 'terms', 'f/club-form', 'cal/abc', 'exit', 'old/', 'demo', 'jcc', 'pitch'])
      expect(route(get(SCOPE + p, 'navigate'), SCOPE)).toBeNull();
    expect(route(get(SCOPE + 'screen/', 'navigate'), SCOPE)).toBe('page');
  });

  it('never touches the API, media, other origins, writes or a video\'s range', () => {
    expect(route(get(SCOPE + 'api/me', 'cors'), SCOPE)).toBeNull();
    expect(route(get(SCOPE + 'api/events'), SCOPE)).toBeNull();
    expect(route(get(SCOPE + 'api/', 'navigate'), SCOPE)).toBeNull();
    expect(route(get(SCOPE + 'media/ab/cd.webp'), SCOPE)).toBeNull();
    expect(route(get(SCOPE + 'emoji/party_popper_3d.webp'), SCOPE)).toBeNull();
    expect(route(get('https://example.com/assets/a.js'), SCOPE)).toBeNull();
    expect(route(get(SCOPE + 'assets/a.js', 'cors', { method: 'POST' }), SCOPE)).toBeNull();
    expect(route(get(SCOPE + 'assets/howto-1.mp4', 'no-cors', { range: true }), SCOPE)).toBeNull();
  });

  it('hashed files cache-first, the named public files and Telegram\'s SDK from the kept copy', () => {
    expect(route(get(SCOPE + 'assets/index-Bvlj7STC.js', 'cors'), SCOPE)).toBe('asset');
    for (const p of PUBLIC) expect(route(get(SCOPE + p), SCOPE)).toBe('copy');
    expect(route(get('https://telegram.org/js/telegram-web-app.js?59'), SCOPE)).toBe('copy');
    expect(route(get('https://telegram.org/js/telegram-widget.js?22'), SCOPE)).toBeNull(); // the sign-in widget: online only
  });

  it('stays inside a sub-path scope (the same build under /next/)', () => {
    const next = 'https://kbtu.sow.kz/next/';
    expect(route(get(next + 'assets/a.js'), next)).toBe('asset');
    expect(route(get(SCOPE + 'assets/a.js'), next)).toBeNull();
    expect(route(get(SCOPE, 'navigate'), next)).toBeNull();
    expect(route(get(next + 'api/me'), next)).toBeNull();
  });
});

describe('keepsPage', () => {
  const ok = { ok: true, type: 'basic', redirected: false };
  it('keeps only the root page, as sent, never an error or a redirect', () => {
    expect(keepsPage(SCOPE + '?startapp=x', SCOPE, ok)).toBe(true);
    expect(keepsPage(SCOPE + 'show', SCOPE, ok)).toBe(false);
    expect(keepsPage(SCOPE, SCOPE, { ...ok, ok: false })).toBe(false);
    expect(keepsPage(SCOPE, SCOPE, { ...ok, redirected: true })).toBe(false);
    expect(keepsPage(SCOPE, SCOPE, { ...ok, type: 'opaqueredirect' })).toBe(false);
  });
});

describe('ofBuild and keepsAsset', () => {
  const r = (ok: boolean, type: string | null) => ({ ok, headers: { get: (k: string) => (k === 'content-type' ? type : null) } });
  it('keeps a page only of this worker\'s build', () => {
    expect(ofBuild('<script type="module" src="./assets/index-A.js"></script>', 'assets/index-A.js')).toBe(true);
    expect(ofBuild('<script type="module" src="./assets/index-B.js"></script>', 'assets/index-A.js')).toBe(false); // a newer deploy's
  });
  it('never keeps the server\'s page answering a missing hashed file', () => {
    expect(keepsAsset(r(true, 'text/javascript; charset=utf-8'))).toBe(true);
    expect(keepsAsset(r(true, null))).toBe(true);
    expect(keepsAsset(r(true, 'text/html; charset=utf-8'))).toBe(false);
    expect(keepsAsset(r(false, 'text/javascript'))).toBe(false);
  });
});

describe('stale', () => {
  it('deletes the other builds\' shells and nothing that isn\'t ours', () => {
    expect(stale([PREFIX + 'a', PREFIX + 'b', 'other-lib', 'kb-something'], PREFIX + 'b')).toEqual([PREFIX + 'a']);
    expect(stale([PREFIX + 'b'], PREFIX + 'b')).toEqual([]);
  });
});

describe('shellOf', () => {
  const html = `<!doctype html><head>
<link rel="preload" as="font" type="font/woff2" href="./assets/inter-latin-opsz-normal-AAA.woff2" crossorigin>
<script defer src="https://telegram.org/js/telegram-web-app.js?59"></script>
<script type="module" crossorigin src="./assets/index-ENTRY.js"></script>
<link rel="modulepreload" crossorigin href="./assets/ui-UI.js">
<link rel="stylesheet" crossorigin href="./assets/index-CSS.css">
<link rel="manifest" href="/manifest.json"></head>`;
  const chunks: Chunk[] = [
    { fileName: 'assets/index-ENTRY.js', name: 'index', imports: ['assets/ui-UI.js'], css: ['assets/index-CSS.css'] },
    { fileName: 'assets/ui-UI.js', name: 'ui', imports: [] },
    { fileName: 'assets/kk-K.js', name: 'kk' }, { fileName: 'assets/en-E.js', name: 'en' },
    { fileName: 'assets/WebEntrance-W.js', name: 'WebEntrance', imports: ['assets/ui-UI.js', 'assets/qr-Q.js'] },
    { fileName: 'assets/TicketView-T.js', name: 'TicketView', imports: ['assets/qr-Q.js'], css: ['assets/TicketView-T.css'] },
    { fileName: 'assets/OfflineTickets-O.js', name: 'OfflineTickets', imports: ['assets/qr-Q.js'] },
    { fileName: 'assets/qr-Q.js', name: 'qr' },
    { fileName: 'assets/EventSheet-S.js', name: 'EventSheet', imports: ['assets/maplibre-M.js'] },
    { fileName: 'assets/maplibre-M.js', name: 'maplibre' },
  ];
  const names = [...chunks.map((c) => c.fileName), 'assets/inter-cyrillic-opsz-normal-C.woff2', 'assets/inter-cyrillic-ext-opsz-normal-X.woff2',
    'assets/inter-greek-opsz-normal-G.woff2', 'assets/inter-latin-opsz-italic-I.woff2', 'index.html', 'sw.js'];

  it('takes the page\'s files, the offline screens with all they import, the three fonts and the public files', () => {
    const s = shellOf(html, chunks, names);
    expect(s.entry).toBe('assets/index-ENTRY.js');
    expect(s.sdk).toBe('https://telegram.org/js/telegram-web-app.js?59');
    expect(s.files).toEqual([
      'assets/OfflineTickets-O.js', 'assets/TicketView-T.css', 'assets/TicketView-T.js', 'assets/WebEntrance-W.js', 'assets/en-E.js',
      'assets/index-CSS.css', 'assets/index-ENTRY.js', 'assets/inter-cyrillic-ext-opsz-normal-X.woff2',
      'assets/inter-cyrillic-opsz-normal-C.woff2', 'assets/inter-latin-opsz-normal-AAA.woff2', 'assets/kk-K.js', 'assets/qr-Q.js', 'assets/ui-UI.js',
      ...PUBLIC,
    ]);
  });

  it('leaves out what the offline start never needs: other screens, the map, other font subsets', () => {
    const { files } = shellOf(html, chunks, names);
    for (const f of ['assets/EventSheet-S.js', 'assets/maplibre-M.js', 'assets/inter-greek-opsz-normal-G.woff2', 'assets/inter-latin-opsz-italic-I.woff2', 'sw.js', 'index.html'])
      expect(files).not.toContain(f);
  });

  it('names the cache by the build: the same build the same name, any change of the page or a file a new one', () => {
    const a = shellOf(html, chunks, names);
    expect(a.cache.startsWith(PREFIX)).toBe(true);
    expect(shellOf(html, chunks, names).cache).toBe(a.cache);
    expect(shellOf(html.replace('index-ENTRY', 'index-ENTRY2'), chunks.map((c) => c.name === 'index' ? { ...c, fileName: 'assets/index-ENTRY2.js' } : c), names).cache).not.toBe(a.cache);
    expect(shellOf(html, chunks.map((c) => c.name === 'kk' ? { ...c, fileName: 'assets/kk-K2.js' } : c), names).cache).not.toBe(a.cache);
  });

  it('fails the build rather than ship a shell without its entry or an offline screen', () => {
    expect(() => shellOf(html.replace(/<script type="module"[^>]+><\/script>/, ''), chunks, names)).toThrow(/entry/);
    expect(() => shellOf(html, chunks.filter((c) => c.name !== 'TicketView'), names)).toThrow(/TicketView/);
  });

  it('copes with a page without Telegram\'s SDK', () => {
    expect(shellOf(html.replace(/<script defer[^>]+><\/script>/, ''), chunks, names).sdk).toBeNull();
  });

  it('knows the chunks and fonts it must carry', () => {
    expect(LAZY).toEqual(expect.arrayContaining(['WebEntrance', 'TicketView', 'OfflineTickets', 'kk', 'en']));
    expect(FONTS.test('assets/inter-cyrillic-ext-opsz-normal-BwkfbSeq.woff2')).toBe(true);
    expect(FONTS.test('assets/inter-vietnamese-opsz-normal-BwkfbSeq.woff2')).toBe(false);
  });
});

describe('hash', () => {
  it('is stable and short', () => {
    expect(hash('abc')).toBe(hash('abc'));
    expect(hash('abc')).not.toBe(hash('abd'));
    expect(hash('x'.repeat(10_000))).toMatch(/^[0-9a-z]{1,7}$/);
  });
});

describe('firstOf', () => {
  afterEach(() => vi.useRealTimers());
  const later = <T,>() => { let res!: (v: T) => void, rej!: (e: unknown) => void; const p = new Promise<T>((a, b) => { res = a; rej = b; }); return { p, res, rej }; };

  it('gives the network\'s answer when it comes in time', async () => {
    vi.useFakeTimers();
    const kept = vi.fn(async () => 'kept');
    const r = firstOf(Promise.resolve('net'), kept, DEADLINE);
    await expect(r).resolves.toBe('net');
    vi.advanceTimersByTime(DEADLINE * 2);
    expect(kept).not.toHaveBeenCalled();
  });

  it('opens the kept copy past the deadline on a network that holds the request', async () => {
    vi.useFakeTimers();
    const net = later<string>();
    const r = firstOf(net.p, async () => 'kept', DEADLINE);
    await vi.advanceTimersByTimeAsync(DEADLINE);
    await expect(r).resolves.toBe('kept');
    net.res('net'); // lands later (sw.ts keeps it for next time); the answer stays the kept one
    await expect(r).resolves.toBe('kept');
  });

  it('waits on past the deadline when nothing is kept (the first launch)', async () => {
    vi.useFakeTimers();
    const net = later<string>();
    const r = firstOf(net.p, async () => undefined, DEADLINE);
    await vi.advanceTimersByTimeAsync(DEADLINE * 3);
    net.res('net');
    await expect(r).resolves.toBe('net');
  });

  it('offline: the kept copy at once, or the network\'s own failure when there is none', async () => {
    await expect(firstOf(Promise.reject(new TypeError('offline')), async () => 'kept', DEADLINE)).resolves.toBe('kept');
    await expect(firstOf(Promise.reject(new TypeError('offline')), async () => undefined, DEADLINE)).rejects.toThrow('offline');
    await expect(firstOf(Promise.reject(new TypeError('offline')), () => Promise.reject(new Error('no cache')), DEADLINE)).rejects.toThrow('offline');
  });
});
