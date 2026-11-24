// The suite's fixtures: a fresh qa.py server per spec file, the app opened as a made-up person in Telegram's shoes
// (telegram-web-app.js reads the signed initData from the link; a TelegramWebviewProxy stub plays the client, so the
// BackButton's state is seen and its press sent the way Telegram sends it), and the checks every screen gets.
import { test as base, expect, type Browser, type BrowserContext, type Page, type TestInfo } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { startQa, type Person, type QaServer } from './server';
import { TG_SCRIPT } from './global-setup';
import ru from '../src/lib/i18n/ru';
import en from '../src/lib/i18n/en';
import kk from '../src/lib/i18n/kk';

export type Theme = 'dark' | 'light';
type Dict = Record<string, string | { other: string }>;

/** A UI string the way the app's t() fills it (ru unless given another dictionary). */
export function T(key: keyof typeof ru, vars: Record<string, string | number> = {}, dict: Dict = ru as Dict): string {
  const e = dict[key];
  const s = typeof e === 'string' ? e : e.other;
  return s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m));
}

/** A label as its accessible name: the soft hyphens long words carry for wrapping are not in it. */
export const N = (s: string) => s.replace(/\u00ad/g, '');

/** Runs in the page before any script: the Telegram client's side of the bridge. */
function tgClient() {
  const w = window as unknown as Record<string, unknown>;
  // the home-screen offer (App.svelte installHint, once per phone; closable only after 5 s) seen already on this
  // phone: a launch nicety no flow tests, which would cover the first screen of every one
  try { if (!localStorage.getItem('kb-install')) localStorage.setItem('kb-install', '1'); } catch { /* storage blocked */ }
  const st = { back: false, events: [] as string[] };
  w.__tg = st;
  w.TelegramWebviewProxy = {
    postEvent(type: string, data: string) {
      st.events.push(type);
      if (type === 'web_app_setup_back_button') { try { st.back = !!JSON.parse(data).is_visible; } catch { /* malformed */ } }
    },
  };
}

/** One person's app: the page plus the steps a flow takes on it. */
export class App {
  shots = 0;
  constructor(readonly page: Page, readonly who: Person, readonly info: TestInfo, readonly problems: Problems) {}

  /** Telegram's BackButton: shown by the app right now? */
  backShown(): Promise<boolean> {
    return this.page.evaluate(() => (window as unknown as { __tg: { back: boolean } }).__tg.back);
  }
  /** Presses Telegram's BackButton, as the client does (it must be shown). */
  async back(): Promise<void> {
    await expect.poll(() => this.backShown(), { message: 'BackButton shown' }).toBe(true);
    await this.page.evaluate(() => (window as unknown as { Telegram: { WebView: { receiveEvent(e: string): void } } }).Telegram.WebView.receiveEvent('back_button_pressed'));
  }
  /** Up: the tabs drawn, the first data in, and whatever the launch put over them (a new award, a greeting) closed the
   *  way a person would, so a flow starts on the bare tab. The launch's moments queue (lib/moments.ts), each 0.6-0.8 s
   *  after nothing is open: the screen is calm once that beat has passed with nothing new coming up. */
  async ready(): Promise<void> {
    await this.page.waitForLoadState('networkidle');
    // a full-screen overlay (a new award) has its own bottom x and no Back (ui/CloseX); a sheet has Back
    const closeX = this.page.locator('button.closex:visible').last();
    const next = this.page.locator('[role="dialog"]:visible, button.closex:visible').first();
    for (let i = 0; i < 12; i++) {
      await settle(this.page);
      if (await closeX.isVisible()) { await closeX.click(); continue; }
      if (await this.backShown()) { await this.back(); continue; }
      if (!(await next.waitFor({ state: 'visible', timeout: 2000 }).then(() => true, () => false))) break;
    }
    await expect(this.nav()).toBeVisible({ timeout: 20_000 });
    await settle(this.page);
  }
  /** The tab bar, in whatever language the app is in (Afisha has a nav of its own, the week). */
  nav() {
    return this.page.getByRole('navigation', { name: anyLang('nav.label') });
  }
  tab(label: string) {
    return this.nav().getByRole('button', { name: label, exact: true });
  }
  async goTab(label: string): Promise<void> {
    await this.tab(label).click();
    await expect(this.tab(label)).toHaveAttribute('aria-current', 'page');
  }
  /** The top sheet (dialogs stack; the last one is on top). */
  sheet() {
    return this.page.locator('[role="dialog"]:not([aria-hidden="true"])').last();
  }
  /** A step's screenshot (a test artifact) and the checks every screen visited gets. */
  async step(name: string): Promise<void> {
    await settle(this.page);
    const n = String(++this.shots).padStart(2, '0');
    await this.info.attach(`${this.who}-${n}-${name}.png`, { body: await this.page.screenshot(), contentType: 'image/png' });
    await checkScreen(this.page, `${this.who} / ${name}`, this.problems);
  }
}

/** Waits for the page to stop moving: no running animations on the compositor (never a fixed sleep). */
export async function settle(page: Page): Promise<void> {
  await page.waitForFunction(() => document.getAnimations().every((a) => a.playState !== 'running' || a.effect?.getTiming().iterations === Infinity),
    undefined, { timeout: 5000 }).catch(() => { /* an endless decorative loop: the screen is still usable */ });
}

const esc = (x: string) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
/** A UI string in any of the three languages, as an exact-match pattern. */
export const anyLang = (key: keyof typeof ru) => new RegExp(`^(${[ru, en, kk].map((d) => esc(T(key, {}, d as Dict))).join('|')})$`);

export interface Problems { errors: string[]; requests: string[]; small: string[] }

/** No horizontal scroll, no text spilling out of a button (fail); tap targets under 44 px (report only). */
export async function checkScreen(page: Page, where: string, problems: Problems): Promise<void> {
  const r = await page.evaluate(() => {
    const vw = innerWidth;
    const seen = (el: Element) => { const b = el.getBoundingClientRect(); const s = getComputedStyle(el); return b.width > 0 && b.height > 0 && s.visibility !== 'hidden' && b.bottom > 0 && b.top < innerHeight && b.right > 0 && b.left < vw && !el.closest('[inert],[aria-hidden="true"]'); };
    const label = (el: Element) => (el.getAttribute('aria-label') || el.textContent || el.tagName).trim().replace(/\s+/g, ' ').slice(0, 40);
    const scroll = Math.max(document.documentElement.scrollWidth, document.body.scrollWidth) - vw;
    const overflow: string[] = [], small: string[] = [];
    for (const b of document.querySelectorAll('button, a[href], [role="button"]')) {
      if (!seen(b)) continue;
      const br = b.getBoundingClientRect();
      // text spilling out: a text node's box past the button's own (ellipsis inside is fine: it stays inside)
      const w = document.createTreeWalker(b, NodeFilter.SHOW_TEXT);
      for (let n = w.nextNode(); n; n = w.nextNode()) {
        if (!n.textContent?.trim()) continue;
        const rg = document.createRange(); rg.selectNodeContents(n);
        const tr = rg.getBoundingClientRect();
        const clip = n.parentElement && getComputedStyle(n.parentElement).overflow !== 'visible' ? n.parentElement.getBoundingClientRect() : null;
        const box = clip ?? tr;
        if (tr.width && (box.right > br.right + 1 || box.left < br.left - 1)) { overflow.push(label(b)); break; }
      }
      if (br.width < 44 || br.height < 44) small.push(`${label(b)} ${Math.round(br.width)}x${Math.round(br.height)}`);
    }
    return { scroll, overflow, small };
  });
  if (r.small.length) problems.small.push(...r.small.map((s) => `${where}: ${s}`));
  expect.soft(r.scroll, `${where}: horizontal scroll`).toBeLessThanOrEqual(0);
  expect.soft(r.overflow, `${where}: text overflowing buttons`).toEqual([]);
}

/** What the browser context gets from the project: the phone, the theme, motion on. */
function ctxOptions(info: TestInfo) {
  const u = info.project.use;
  return { viewport: u.viewport, colorScheme: u.colorScheme, hasTouch: true, isMobile: u.isMobile, deviceScaleFactor: u.deviceScaleFactor, userAgent: u.userAgent, reducedMotion: 'no-preference' as const, locale: 'ru-RU', timezoneId: 'Asia/Almaty' };
}

/** The link qa.py printed, with Telegram's theme as the project's (telegram-web-app.js takes its colorScheme from it). */
export function linkFor(link: string, theme: Theme, path = '/'): string {
  const u = new URL(link);
  const h = new URLSearchParams(u.hash.slice(1));
  h.set('tgWebAppThemeParams', JSON.stringify(theme === 'dark' ? { bg_color: '#000000', text_color: '#ffffff' } : { bg_color: '#ffffff', text_color: '#000000' }));
  u.pathname = path;
  u.hash = h.toString();
  return u.toString();
}

let qa: QaServer | null = null, qaFile = '';

type Fixtures = { qaEnv: Record<string, string>; qa: QaServer; open: (who: Person, path?: string, raw?: boolean) => Promise<App>; problems: Problems };

export const test = base.extend<Fixtures, { stopQa: void }>({
  stopQa: [async ({}, use) => { await use(); await qa?.stop(); qa = null; }, { scope: 'worker', auto: true }],
  // a spec file's own server switches (e.g. QA_ADMIN_TG_IDS), via test.use({ qaEnv })
  qaEnv: [{}, { option: true }],
  // a fresh server per spec file (its tests share it, in order)
  qa: async ({ qaEnv }, use, info) => {
    if (!qa || qaFile !== info.file) { await qa?.stop(); qa = await startQa(qaEnv); qaFile = info.file; }
    await use(qa);
  },
  problems: async ({}, use, info) => {
    const p: Problems = { errors: [], requests: [], small: [] };
    await use(p);
    if (p.small.length) info.annotations.push({ type: 'tap targets under 44 px', description: [...new Set(p.small)].join('\n') });
    if (p.small.length) await info.attach('tap-targets.txt', { body: [...new Set(p.small)].join('\n'), contentType: 'text/plain' });
    expect(p.errors, 'console errors').toEqual([]);
    expect(p.requests, 'failed requests').toEqual([]);
  },
  open: async ({ browser, qa, problems }, use, info) => {
    const contexts: BrowserContext[] = [];
    const theme = (info.project.use.colorScheme ?? 'dark') as Theme;
    await use(async (who, path = '/', raw = false) => {
      const ctx = await newContext(browser, info);
      contexts.push(ctx);
      const page = await ctx.newPage();
      watch(page, who, qa.base, problems);
      await page.goto(linkFor(qa.links[who], theme, path));
      const app = new App(page, who, info, problems);
      if (!raw) await app.ready();
      return app;
    });
    for (const c of contexts) await c.close();
  },
});

export async function newContext(browser: Browser, info: TestInfo): Promise<BrowserContext> {
  const ctx = await browser.newContext(ctxOptions(info));
  const script = readFileSync(TG_SCRIPT);
  await ctx.route(/^https:\/\/telegram\.org\/js\/telegram-web-app\.js/, (r) => r.fulfill({ body: script, contentType: 'application/javascript' }));
  await ctx.addInitScript(tgClient);
  return ctx;
}

/** Answers the API gives on purpose, by its own tested contract (not failures):
 *  POST /api/ms/claim 403 = "no Microsoft sign-in waits for this Telegram", asked on every launch (App.svelte; test_core). */
const EXPECTED: RegExp[] = [/^POST \/api\/ms\/claim 403$/];
const expected = (line: string) => EXPECTED.some((re) => re.test(line));

/** Console errors and failed requests, wherever the flow goes. */
export function watch(page: Page, who: string, origin: string, problems: Problems): void {
  page.on('console', (m) => {
    // a failed load is counted once, by its response below (with its URL)
    if (m.type() === 'error' && !/^Failed to load resource/.test(m.text())) problems.errors.push(`${who}: ${m.text()} (${m.location().url.replace(origin, '')})`);
  });
  page.on('pageerror', (e) => problems.errors.push(`${who}: ${e.message}`));
  page.on('requestfailed', (r) => {
    const why = r.failure()?.errorText ?? '';
    if (/abort|cancel/i.test(why)) return; // the app (or a navigation) let go of it on purpose
    // WebKit: a <video> asks again for a blob: the app revoked as its sheet closed (InstallSheet); nothing a person sees
    if (r.url().startsWith('blob:') && /WebKitBlobResource/.test(why)) return;
    problems.requests.push(`${who}: ${r.method()} ${r.url()} ${why}`);
  });
  page.on('response', (r) => {
    if (r.status() < 400) return;
    const line = `${r.request().method()} ${r.url().replace(origin, '').replace(/\?.*/, '')} ${r.status()}`;
    if (!expected(line)) problems.requests.push(`${who}: ${line}`);
  });
}

export { expect };
