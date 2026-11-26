// A student's own path through events: the Afisha from the last launch's copy, a free event's sign-up, ticket and
// cancel, and a paid event up to its Kaspi receipt step.
import type { Page } from '@playwright/test';
import { test, expect, reload } from './fixtures';
import ru from '../src/lib/i18n/ru';

type Key = keyof typeof ru;
const s = (k: Key) => ru[k] as string;
/** a string's words before its first {hole}: "Go · {price}" matches whatever the price */
const lead = (k: Key) => s(k).split('{')[0];
const esc = (x: string) => x.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

const FREE = 'Board games night', PAID = 'Open Mic: stand-up and music';

const sheet = (page: Page, title: Key) => page.getByRole('dialog', { name: s(title) });
// an event shows twice on the Afisha (the hero up top and its day's row): the first is the hero
const card = (page: Page, title: string) => page.getByRole('button', { name: title, exact: true }).first();

/** A launch without a link may first offer the home-screen icon or celebrate a new award (App.svelte's launch moments):
 *  whenever one stands in the way, the person puts it aside the way they would */
async function asideLaunchMoments(page: Page) {
  await page.addLocatorHandler(page.getByRole('dialog', { name: s('inst.title') }), async (d) => {
    await d.getByRole('button', { name: s('inst.later'), exact: true }).click(); // enabled after its short hold
  });
  await page.addLocatorHandler(page.getByText(s('unlock.kicker'), { exact: true }).first(), async () => {
    await page.getByRole('button', { name: s('common.close'), exact: true }).last().click();
  });
}

test('the Afisha shows the last launch at once, no spinner, while the server answers', async ({ open }) => {
  const ali = await open('Ali');
  await asideLaunchMoments(ali.page);
  const { page } = ali;
  await expect(card(page, FREE)).toBeVisible();
  await ali.look('afisha first launch');
  // the copy for the next launch is written when the app is idle
  await expect.poll(() => page.evaluate(() => Object.keys(localStorage).some((k) => k.endsWith('snapshot')))).toBe(true);

  // the next launch: the events list request is held until the screen has been checked
  let release!: () => void;
  const held = new Promise<void>((r) => { release = r; });
  let asked = false;
  await page.route((u) => u.pathname === '/api/events', async (route) => { asked = true; await held; await route.continue(); });
  await reload(page);
  await expect(card(page, FREE)).toBeVisible();
  await expect(card(page, PAID)).toBeVisible();
  expect(asked, 'the app asked the server for fresh events').toBe(true);
  await expect(page.locator('[aria-busy="true"]'), 'no loading placeholder').toHaveCount(0);
  await ali.look('afisha from the last launch');
  const fresh = page.waitForResponse((r) => new URL(r.url()).pathname === '/api/events');
  release();
  await fresh;
  await expect(card(page, FREE)).toBeVisible();
});

test('a free event: sign up, the ticket, cancel, sign up again', async ({ open }) => {
  const ali = await open('Ali');
  await asideLaunchMoments(ali.page);
  const { page } = ali;
  // the seed has Ali going already: start him from no sign-up (what another device of his would do)
  await ali.api('/api/events/2/registration', undefined, 'DELETE');
  await reload(page);

  await card(page, FREE).click();
  const ev = sheet(page, 'cap.event');
  await expect(ev.getByText(FREE).first()).toBeVisible();
  expect(await ali.back.shown(), 'Back shows over a sheet').toBe(true);
  const go = ev.getByRole('button', { name: s('event.go'), exact: true });
  await expect(go).toBeVisible();
  await ali.look('free event sheet');

  // sign up: the ticket in place of the button, at once
  await go.click();
  const ticketBtn = ev.getByRole('button', { name: s('event.ticket'), exact: true });
  await expect(ticketBtn).toBeVisible();
  await ali.look('signed up');

  // the ticket itself, with its code
  await ticketBtn.click();
  const ticket = page.getByRole('group', { name: s('event.ticket') });
  await expect(ticket).toBeVisible();
  await expect(ticket.getByText(s('tk.code'), { exact: true })).toBeVisible();
  await ali.look('ticket');
  // the server has it too
  const reg = await ali.api<{ my: { status: string; ticketCode: string | null } | null }>('/api/events/2');
  expect(reg.my?.status).toBe('going');
  expect(reg.my?.ticketCode).toBeTruthy();

  // cancel from the ticket, confirmed
  await page.getByRole('button', { name: s('event.cancelReg'), exact: true }).click();
  const confirm = page.getByRole('button', { name: s('tk.cancelGo'), exact: true });
  await expect(confirm).toBeVisible();
  await ali.look('cancel asked');
  await confirm.click();
  await expect(ticket).toBeHidden();
  // back on the event (or the Afisha under it): "Going" again
  await expect(page.getByRole('button', { name: s('event.go'), exact: true }).first()).toBeVisible();
  await ali.look('cancelled');
  await expect.poll(async () => (await ali.api<{ my: { status: string } | null }>('/api/events/2')).my?.status).not.toBe('going');

  // close what is open with Telegram's Back until the Afisha shows, then sign up again from its card
  for (let n = await page.getByRole('dialog').count(); n > 0; n--) {
    await ali.back.press();
    await expect(page.getByRole('dialog')).toHaveCount(n - 1);
  }
  await expect(page.getByRole('dialog')).toHaveCount(0);
  expect(await ali.back.shown(), 'no Back on the Afisha').toBe(false);
  await card(page, FREE).click();
  await ev.getByRole('button', { name: s('event.go'), exact: true }).click();
  await expect(ev.getByRole('button', { name: s('event.ticket'), exact: true })).toBeVisible();
  await expect.poll(async () => (await ali.api<{ my: { status: string } | null }>('/api/events/2')).my?.status).toBe('going');
  await ali.back.press();
  await expect(ev).toBeHidden();
  // the Afisha's hero (my next event) has the ticket too
  const hero = card(page, FREE).locator('..');
  await expect(hero.getByRole('button', { name: s('event.ticket'), exact: true })).toBeVisible();
  await ali.look('afisha with the ticket');
});

test('a plain venue name opens 2GIS from the hero, timeline, event and ticket', async ({ open }) => {
  const dana = await open('Dana');
  await dana.api('/api/events/2/place', { place: 'PlatformA' });
  const ali = await open('Ali');
  const { page } = ali;
  const links = () => page.evaluate(() => (window as unknown as { __tg: { events: [string, { url?: string }][] } }).__tg.events
    .filter(([type, data]) => type === 'web_app_open_link' && data.url === 'https://2gis.kz/almaty/search/PlatformA').length);
  const where = { name: 'PlatformA', exact: true };
  const hero = page.locator('.hero').filter({ has: page.getByRole('button', { name: FREE, exact: true }) });
  const row = page.locator('.day .row').filter({ has: page.getByRole('button', { name: FREE, exact: true }) });
  const ev = sheet(page, 'cap.event');

  await hero.getByRole('button', where).click();
  await expect.poll(links).toBe(1);
  await ali.look('venue in the hero');
  await row.getByRole('button', where).click();
  await expect.poll(links).toBe(2);
  await ali.look('venue in the timeline');
  await row.getByRole('button', { name: FREE, exact: true }).click();
  await ev.getByRole('button', { name: new RegExp('^PlatformA') }).click();
  await expect.poll(links).toBe(3);
  await ali.look('venue in the event');
  await ev.getByRole('button', { name: s('event.ticket'), exact: true }).click();
  await page.getByRole('group', { name: s('event.ticket') }).getByRole('button', where).click();
  await expect.poll(links).toBe(4);
  await ali.look('venue in the ticket');
});

test('a paid event leads to its Kaspi receipt step', async ({ open }) => {
  const ali = await open('Ali');
  await asideLaunchMoments(ali.page);
  const { page } = ali;
  await card(page, PAID).click();
  const ev = sheet(page, 'cap.event');
  const go = ev.getByRole('button', { name: new RegExp(`^${esc(lead('event.goPrice'))}`) });
  await expect(go).toBeVisible();
  await ali.look('paid event sheet');

  await go.click();
  const pay = sheet(page, 'pay.title');
  await expect(pay).toBeVisible();
  await expect(pay.getByText('Arman A.')).toBeVisible(); // who to pay, from the event
  await expect(pay.getByText(s('pay.to'), { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: s('pay.upload') })).toBeVisible();
  await ali.look('kaspi receipt step');
  // the seat is held on the server until the receipt comes
  expect((await ali.api<{ my: { status: string } | null }>('/api/events/1')).my?.status).toBe('hold');

  // let the seat go: back to "Going · price"
  await pay.getByRole('button', { name: s('pay.release'), exact: true }).click();
  await expect(pay).toBeHidden();
  await expect.poll(async () => (await ali.api<{ my: { status: string } | null }>('/api/events/1')).my?.status).not.toBe('hold');
  await expect(page.getByRole('button', { name: new RegExp(`^${esc(lead('event.goPrice'))}`) }).first()).toBeVisible();
  await ali.look('hold released');
});
