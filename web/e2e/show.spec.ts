// QR check-in on a big screen (/show, server checkin.py): a laptop shows a pairing QR, the club's organizer connects it
// from Studio's Meetings with Telegram's QR scanner, the screen shows the meeting's rotating QR, and a member's scan
// counts on it. The cameras are Telegram's: its scanner popup gets the QR's text the way the client hands it over
// (qr_text_received); the member's phone camera is the API call its scan makes (POST /api/checkin).
import type { Page, TestInfo } from '@playwright/test';
import { test, expect, T, newContext, watch, checkScreen, settle, type Problems } from './fixtures';

/** A step on the laptop: its screenshot and the same checks as a phone's screen. */
async function shot(page: Page, name: string, info: TestInfo, problems: Problems) {
  await settle(page);
  await info.attach(`screen-${name}.png`, { body: await page.screenshot(), contentType: 'image/png' });
  await checkScreen(page, `screen / ${name}`, problems);
}

type ScreenState = { code: string; session?: number | null; param?: string | null; done?: number; expected?: number };

test('a meeting on a big screen: pair it from Studio, a member checks in, the count goes up', async ({ browser, open, qa, problems }, info) => {
  // Ali joins the club by its invite link (Dana's club has only her): the meeting expects its members
  const { token } = await qa.api<{ token: string }>('Dana', 'POST', '/orgs/1/invites', {});
  await qa.api('Ali', 'POST', `/invites/${token}`);

  // the laptop: /show, no Telegram, a pairing QR
  const ctx = await newContext(browser, info);
  const screen = await ctx.newPage();
  await screen.setViewportSize({ width: 1280, height: 800 });
  watch(screen, 'screen', qa.base, problems);
  let last: ScreenState | null = null;
  screen.on('response', async (r) => {
    if (!/\/api\/screen(\/pair)?$/.test(new URL(r.url()).pathname) || !r.ok()) return;
    const j = await r.json().catch(() => null);
    if (j) last = { ...last, ...j };
  });
  await screen.goto(`${qa.base}/show`);
  await expect(screen.getByRole('heading', { name: T('scr.pairTitle') })).toBeVisible();
  await expect.poll(() => last?.code ?? '').toMatch(/^[0-9a-f]{16}$/);
  await shot(screen, 'pairing', info, problems);

  // the organizer: Studio -> Meetings -> Connect a screen; Telegram's scanner reads the laptop's QR
  const dana = await open('Dana');
  await dana.goTab(T('page.clubs'));
  await dana.page.getByRole('button', { name: /^Open Mic Club/ }).first().click();
  const studio = dana.page.getByRole('region', { name: 'Open Mic Club' });
  await expect(studio).toBeVisible();
  await dana.step('studio');
  await studio.getByRole('button', { name: T('scr.page'), exact: true }).click();
  const connect = dana.page.getByRole('button', { name: T('scr.connect'), exact: true });
  await expect(connect).toBeVisible();
  await dana.step('meetings');
  await connect.click();
  await expect.poll(() => dana.page.evaluate(() => (window as unknown as { __tg: { events: string[] } }).__tg.events.includes('web_app_open_scan_qr_popup'))).toBe(true);
  const pairLink = `https://t.me/KBTUappBot?startapp=sh_${last!.code}`;
  await dana.page.evaluate((data) => (window as unknown as { Telegram: { WebView: { receiveEvent(e: string, d: unknown): void } } }).Telegram.WebView.receiveEvent('qr_text_received', { data }), pairLink);
  await expect(dana.page.getByText(T('scr.paired'))).toBeVisible();
  await dana.step('paired');

  // the screen: the meeting's rotating QR, nobody yet
  const meeting = T('scr.meeting', { date: '' }).trim().replace(/[·\s]+$/, '');
  await expect(screen.getByRole('heading', { name: new RegExp('^' + meeting.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')) })).toBeVisible();
  await expect.poll(() => last?.param ?? '').toMatch(/^ci_\d+_\d+_[0-9a-f]{16}$/);
  const count = screen.locator('.live .count b');
  await expect(count).toHaveText('0');
  await shot(screen, 'meeting', info, problems);

  // Ali's phone reads the QR on the screen: the scan the app makes from the ci_ link
  const r = await qa.api<{ done: boolean }>('Ali', 'POST', '/checkin', { p: last!.param });
  expect(r.done).toBe(true);
  await expect(count).toHaveText('1');
  await shot(screen, 'counted', info, problems);

  // the organizer's list says the same: one of the members came
  await expect(dana.page.getByRole('button', { name: new RegExp(T('scr.cameL')) })).toContainText('1');
  await dana.step('came');
  await ctx.close();
});
