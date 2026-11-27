// The harness: every test gets a fresh seeded server (server/tools/qa.py on a free port, its own temp database) and
// opens the app as qa.py's made-up people through their signed links, the way Telegram opens a Mini App. A stand-in
// for Telegram's webview (window.TelegramWebviewProxy, which telegram-web-app.js talks to) records what the app asks
// of Telegram (the BackButton's visibility) and presses its Back. Every screen a test looks at (`look`) is checked:
// no console errors, no failed requests, no sideways scroll, no text spilling out of buttons; small tap targets are
// reported, not failed; a screenshot of each is attached to the test.
import { test as base, expect, type Page, type TestInfo } from '@playwright/test';
import { spawn, type ChildProcess } from 'node:child_process';
import { existsSync, mkdtempSync, rmSync } from 'node:fs';
import { createServer } from 'node:net';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';

const SERVER = resolve(import.meta.dirname, '../../server');
const PYTHON = process.env.QA_PYTHON || (existsSync(join(SERVER, '.venv/bin/python')) ? join(SERVER, '.venv/bin/python') : 'python3');

export type Who = 'Dana' | 'Ali' | 'Bota'; // qa.py's made-up people: Dana runs the Open Mic club, Bota moderates

export type Qa = {
  url: string;
  db: string;
  /** the signed link that opens the app as this person */
  link: (who: Who, extra?: Record<string, string>) => string;
};

const freePort = () => new Promise<number>((ok, fail) => {
  const s = createServer();
  s.unref();
  s.on('error', fail);
  s.listen(0, '127.0.0.1', () => { const p = (s.address() as { port: number }).port; s.close(() => ok(p)); });
});

async function startQa(now?: number): Promise<Qa & { stop: () => void }> {
  const port = await freePort();
  const dir = mkdtempSync(join(tmpdir(), 'kbtu-e2e-'));
  const db = join(dir, 'qa.db');
  const proc: ChildProcess = spawn(PYTHON, ['tools/qa.py', '--port', String(port), '--db', db, ...(now ? ['--now', String(now), '--clubs'] : [])], {
    cwd: SERVER, env: { ...process.env, PYTHONUNBUFFERED: '1' }, stdio: ['ignore', 'pipe', 'pipe'], detached: true,
  });
  const links: Partial<Record<Who, string>> = {};
  let log = '';
  proc.stdout!.on('data', (b: Buffer) => {
    log += b;
    for (const m of b.toString().matchAll(/^(Dana|Ali|Bota): (\S+)$/gm)) links[m[1] as Who] = m[2];
  });
  proc.stderr!.on('data', (b: Buffer) => { log += b; });
  const url = `http://127.0.0.1:${port}`;
  const stop = () => {
    try { process.kill(-proc.pid!, 'SIGTERM'); } catch { /* gone */ }
    rmSync(dir, { recursive: true, force: true });
  };
  for (let i = 0; ; i++) {
    if (proc.exitCode != null) { stop(); throw new Error(`qa.py exited:\n${log}`); }
    if (Object.keys(links).length === 3 && await fetch(`${url}/healthz`).then((r) => r.ok, () => false)) break;
    if (i > 300) { stop(); throw new Error(`qa.py did not start in 30 s:\n${log}`); }
    await new Promise((r) => setTimeout(r, 100));
  }
  return {
    url, db, stop,
    link: (who, { path = '/', ...extra } = {}) => {
      const p = new URLSearchParams(links[who]!.split('#')[1]);
      for (const [k, v] of Object.entries(extra)) p.set(k, v);
      return `${url}${path}#${p}`;
    },
  };
}

/** What the page did wrong, gathered while it runs and checked when the test ends. */
type Faults = { errors: string[]; failed: string[]; allow: RegExp[] };

/** One person's phone: the app opened as them, with Telegram stood in for. */
export type Phone = {
  page: Page;
  who: Who;
  /** Telegram's BackButton: is it shown, and press it */
  back: { shown: () => Promise<boolean>; press: () => Promise<void> };
  /** check the screen as it is now and attach its screenshot */
  look: (step: string) => Promise<void>;
  /** a request or console error this test expects (a refused tap, ...) */
  allow: (re: RegExp) => void;
  /** call the API as this person (what a camera or another device would send) */
  api: <T = unknown>(path: string, body?: unknown, method?: string) => Promise<T>;
};

/** path: open another page (/show); moments: keep the launch's award and home-screen offer (see openPhone) */
export type OpenOpts = { path?: string; moments?: boolean };

const theme = (info: TestInfo) => (info.project.metadata?.theme as 'dark' | 'light') ?? 'dark';
/** a project's fixed clock (Unix seconds; the snapshot projects): the server's and the browser's, so every screen says
 *  the same "in 2 days" on every run */
const clock = (info: TestInfo) => info.project.metadata?.now as number | undefined;

async function openPhone(page: Page, qa: Qa, who: Who, info: TestInfo, faults: Faults, opts: OpenOpts = {}): Promise<Phone> {
  const dark = theme(info) === 'dark';
  if (!opts.moments) {
    // The launch's moments (lib/moments.ts) open over whatever is on screen a few seconds in, one at a time: a new
    // award (qa.py checked Ali and Bota in yesterday) and the home-screen offer. A flow isn't about them, and their
    // timing made flows flaky, so this phone has seen them: the awards marked celebrated on the server (as the app does
    // once it shows one), the offer marked shown in its storage.
    const init = new URLSearchParams(qa.link(who).split('#')[1]).get('tgWebAppData')!;
    const call = (path: string, body?: unknown) => page.request.fetch(`${qa.url}/api${path}`, {
      method: body ? 'POST' : 'GET', headers: { Authorization: `tma ${init}`, 'Content-Type': 'application/json' }, data: body ? JSON.stringify(body) : undefined });
    const me = await (await call('/me')).json() as { unlocked?: { code: string; level: number }[] };
    for (const u of me.unlocked ?? []) expect((await call('/me/unlocked', u)).ok(), `award ${u.code} marked seen`).toBe(true);
    await page.addInitScript(() => { try { localStorage.setItem('kb-install', '1'); } catch { /* storage blocked */ } });
  }
  await page.addInitScript(() => {
    const w = window as unknown as { __tg: { events: [string, unknown][]; back: boolean }; TelegramWebviewProxy: unknown };
    w.__tg = { events: [], back: false };
    // the camera refused, as on a test machine (Playwright's WebKit hands out a fake one, Chromium none): the door
    // falls back to Telegram's own scanner, which a test answers (qr_text_received)
    if (typeof MediaDevices !== 'undefined') MediaDevices.prototype.getUserMedia = () => Promise.reject(new DOMException('no camera in tests', 'NotAllowedError'));
    w.TelegramWebviewProxy = {
      postEvent(type: string, data: string) {
        const d = data ? JSON.parse(data) : null;
        w.__tg.events.push([type, d]);
        if (type === 'web_app_setup_back_button') w.__tg.back = !!d?.is_visible;
      },
    };
  });
  if (clock(info)) await page.clock.install({ time: clock(info)! * 1000 }); // runs on from there; a test may fast-forward it
  page.on('console', (m) => { if (m.type() === 'error') faults.errors.push(`console: ${m.text()}`); });
  page.on('pageerror', (e) => faults.errors.push(`page: ${e.message}`));
  page.on('requestfailed', (r) => {
    const why = r.failure()?.errorText ?? '';
    if (/ERR_ABORTED|cancelled|NS_BINDING_ABORTED|Load request cancelled|Frame load interrupted/i.test(why)) return; // left the page / superseded (WebKit says the last on a reload)
    faults.failed.push(`${r.method()} ${r.url()} ${why}`);
  });
  page.on('response', (r) => { if (r.status() >= 400) faults.failed.push(`${r.request().method()} ${r.url()} ${r.status()}`); });

  const themeParams = JSON.stringify(dark ? { bg_color: '#000000', text_color: '#ffffff' } : { bg_color: '#ffffff', text_color: '#000000' });
  await page.goto(qa.link(who, { tgWebAppThemeParams: themeParams, ...(opts.path ? { path: opts.path } : {}) }));
  await expect(page.locator('html'), 'the theme Telegram passed').toHaveAttribute('data-theme', theme(info));
  const initData = await page.evaluate(() => (window as unknown as { Telegram: { WebApp: { initData: string } } }).Telegram.WebApp.initData);

  return {
    page, who,
    back: {
      shown: () => page.evaluate(() => (window as unknown as { __tg: { back: boolean } }).__tg.back),
      press: () => page.evaluate(() => (window as unknown as { Telegram: { WebView: { receiveEvent: (e: string) => void } } }).Telegram.WebView.receiveEvent('back_button_pressed')),
    },
    allow: (re) => faults.allow.push(re),
    look: (step) => look(page, info, `${who} ${step}`),
    api: async (path, body, method) => {
      const r = await page.request.fetch(`${qa.url}${path}`, {
        method: method ?? (body === undefined ? 'GET' : 'POST'),
        headers: { Authorization: `tma ${initData}`, 'Content-Type': 'application/json' },
        data: body === undefined ? undefined : JSON.stringify(body),
      });
      if (!r.ok()) throw new Error(`${path}: ${r.status()} ${await r.text()}`);
      return (r.status() === 204 ? null : await r.json()) as never;
    },
  };
}

/** Checks on the screen as it is and its screenshot: no sideways scroll, no text out of its button; small tap targets
 *  are reported (an annotation and a JSON attachment), not failed. */
export async function look(page: Page, info: TestInfo, step: string): Promise<void> {
  await page.evaluate(() => document.fonts?.ready);
  const found = await page.evaluate(() => {
    const vw = document.documentElement.clientWidth;
    const sideways = document.scrollingElement!.scrollWidth - vw;
    const shown = (el: Element) => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(el).visibility !== 'hidden'; };
    const name = (el: Element) => (el.getAttribute('aria-label') || el.textContent || el.tagName).trim().replace(/\s+/g, ' ').slice(0, 40);
    const spill: string[] = [], small: string[] = [];
    for (const b of document.querySelectorAll<HTMLElement>('button, [role="button"], a[href]')) {
      if (!shown(b) || b.closest('[inert], [aria-hidden="true"]')) continue;
      const box = b.getBoundingClientRect();
      if (box.right <= 0 || box.left >= vw) continue; // a carousel's card out of view
      // text that ends outside its button and isn't cut on purpose (an ellipsis)
      const walk = document.createTreeWalker(b, NodeFilter.SHOW_TEXT);
      for (let n = walk.nextNode(); n; n = walk.nextNode()) {
        if (!n.textContent?.trim()) continue;
        const host = n.parentElement!;
        if (!shown(host) || getComputedStyle(host).textOverflow === 'ellipsis' || host.closest('[style*="ellipsis"]')) continue;
        const range = document.createRange(); range.selectNodeContents(n);
        const r = range.getBoundingClientRect();
        if (r.right > box.right + 1 || r.left < box.left - 1) { spill.push(name(b)); break; }
      }
      if ((box.width < 44 || box.height < 44) && box.width * box.height > 0) small.push(`${name(b)} ${Math.round(box.width)}x${Math.round(box.height)}`);
    }
    return { sideways, spill: [...new Set(spill)], small: [...new Set(small)] };
  });
  const safe = step.replace(/[^\w-]+/g, '-');
  await info.attach(`${safe}.png`, { body: await page.screenshot(), contentType: 'image/png' });
  if (found.small.length) {
    info.annotations.push({ type: 'small tap targets', description: `${step}: ${found.small.join('; ')}` });
    await info.attach(`${safe}-small-targets.json`, { body: JSON.stringify(found.small, null, 1), contentType: 'application/json' });
  }
  expect.soft(found.sideways, `${step}: the page scrolls sideways by ${found.sideways}px`).toBeLessThanOrEqual(1);
  expect.soft(found.spill, `${step}: text spills out of a button`).toEqual([]);
}

export const test = base.extend<{ qa: Qa; open: (who: Who, opts?: OpenOpts) => Promise<Phone>; faults: Faults }>({
  // eslint-disable-next-line no-empty-pattern
  qa: async ({}, use, info) => {
    const qa = await startQa(clock(info));
    try { await use(qa); } finally { qa.stop(); }
  },
  faults: async ({}, use) => { // eslint-disable-line no-empty-pattern
    // the start-up probe for a Microsoft sign-in another browser finished (App.svelte, msClaim('')) answers 403 when
    // there is none, by design; the browser logs that response as a console error too
    // WebKit reports a ResizeObserver whose callback changed the layout as a page error; the spec calls it a notice (the
  // rest arrive the next frame), nothing breaks
  const f: Faults = { errors: [], failed: [], allow: [/\/api\/ms\/claim 403$/, /status of 403 \(Forbidden\)$/, /^page: ResizeObserver loop completed with undelivered notifications\.$/] };
    await use(f);
    const keep = (x: string) => !f.allow.some((re) => re.test(x));
    expect.soft(f.errors.filter(keep), 'console errors').toEqual([]);
    expect.soft(f.failed.filter(keep), 'failed requests').toEqual([]);
  },
  /** a phone per person: the first one uses the test's own page, others get their own browser context */
  open: async ({ page, browser, qa, faults }, use, info) => {
    const extra: { close: () => Promise<void> }[] = [];
    let first = true;
    await use(async (who, opts) => {
      if (first) { first = false; return openPhone(page, qa, who, info, faults, opts); }
      const ctx = await browser.newContext({ ...info.project.use, baseURL: undefined });
      extra.push(ctx);
      return openPhone(await ctx.newPage(), qa, who, info, faults, opts);
    });
    for (const c of extra) await c.close();
  },
});

export { expect };

/** On a fixed clock (the snap-* projects): the Afisha in, then the launch's greeting (a toast: "Physics in 40 min",
 *  once the day's data is in) come and gone. Its moment depends on the server's speed, so it would land on some
 *  screens' pictures or checks and not others. */
export async function settled(p: Phone): Promise<Phone> {
  await expect(p.page.getByRole('button', { name: 'Board games night', exact: true }).first()).toBeVisible();
  const hi = p.page.locator('.toast');
  await hi.waitFor({ timeout: 5000 }).catch(() => { /* no greeting this time */ });
  await p.page.clock.fastForward(10_000);
  await expect(hi).toHaveCount(0);
  return p;
}

/** The page reloaded, as a relaunch: WebKit reports the app's own start-up navigation as an interrupted reload
 *  ("Frame load interrupted"), the page loads all the same */
export async function reload(page: Page): Promise<void> {
  try { await page.reload(); } catch (e) {
    if (!/Frame load interrupted/.test(String(e))) throw e;
    await page.waitForLoadState('load');
  }
}
