// A student's evening: Afisha is there before its data, an event's sheet, a free sign-up and its ticket, cancelling and
// signing up again, and a paid event up to the Kaspi receipt step. Ali (qa.py) already goes to "Board games night"
// (free), so his first move there is the ticket and its cancel; "Open Mic" (2 000 tenge) he hasn't touched.
import { test, expect, T, App, settle, newContext, watch, linkFor, type Theme } from './fixtures';

const FREE = 'Board games night', PAID = 'Open Mic: stand-up and music';

test('student: afisha, free sign-up, ticket, cancel, again, paid event to the receipt', async ({ browser, qa, problems, open }, info) => {
  await test.step('Afisha draws before its data arrives', async () => {
    // every API answer held back 3 s: the tabs and the screen must not wait for them (AGENTS.md, Speed)
    const ctx = await newContext(browser, info);
    let release!: () => void;
    const gate = new Promise<void>((r) => (release = r));
    await ctx.route(/\/api\//, async (r) => { await gate; await r.continue().catch(() => {}); });
    const page = await ctx.newPage();
    watch(page, 'Ali', qa.base, problems);
    await page.goto(linkFor(qa.links.Ali, (info.project.use.colorScheme ?? 'dark') as Theme));
    const app = new App(page, 'Ali', info, problems);
    await expect(app.nav()).toBeVisible({ timeout: 2500 });
    await expect(app.tab(T('tab.afisha'))).toHaveAttribute('aria-current', 'page');
    await app.step('afisha-before-data');
    release();
    await expect(page.getByRole('button', { name: FREE, exact: true }).first()).toBeVisible();
    await ctx.close();
  });

  const ali = await open('Ali');
  const page = ali.page;
  const going = () => ali.sheet().getByRole('button', { name: T('event.go'), exact: true });
  const ticket = () => ali.sheet().getByRole('button', { name: T('event.ticket'), exact: true });

  async function cancelTicket() {
    await ticket().click();
    const cancel = page.getByRole('button', { name: T('event.cancelReg'), exact: true }).first();
    await expect(cancel).toBeVisible();
    await ali.step('ticket');
    await cancel.click();
    const yes = page.getByRole('button', { name: T('tk.cancelGo'), exact: true });
    await expect(yes).toBeVisible();
    await ali.step('cancel-ask');
    await yes.click();
    // back on the event: the sign-up button again, in the tap's frame
    await expect(going()).toBeVisible();
  }

  await test.step('open the free event', async () => {
    await expect(page.getByRole('button', { name: FREE, exact: true }).first()).toBeVisible();
    await ali.step('afisha');
    await page.getByRole('button', { name: FREE, exact: true }).last().click();
    await expect(ali.sheet()).toBeVisible();
    await expect(ali.sheet().getByText(FREE).first()).toBeVisible();
    await expect(ticket()).toBeVisible();
    await ali.step('event-going');
  });

  await test.step('cancel the ticket he had', cancelTicket);
  await ali.step('event-not-going');

  await test.step('sign up (free): the ticket appears', async () => {
    await going().click();
    await expect(ticket()).toBeVisible();
    await ali.step('signed-up');
  });

  await test.step('cancel and sign up again', async () => {
    await cancelTicket();
    await going().click();
    await expect(ticket()).toBeVisible();
    await ali.step('signed-up-again');
  });

  await test.step('a paid event reaches the Kaspi receipt step', async () => {
    // Back closes the stack down to Afisha (the ticket view, then the event)
    for (let i = 0; i < 5 && (await ali.backShown()); i++) { await ali.back(); await settle(page); }
    await expect(ali.nav()).toBeVisible();
    await page.getByRole('button', { name: PAID, exact: true }).first().click();
    const buy = ali.sheet().getByRole('button', { name: T('event.goPrice', { price: '2 000 ₸' }), exact: true });
    await expect(buy).toBeVisible();
    await ali.step('paid-event');
    await buy.click();
    const upload = page.getByRole('button', { name: T('pay.upload'), exact: true });
    await expect(upload).toBeVisible();
    await expect(page.getByRole('dialog', { name: T('pay.title') })).toBeVisible();
    await ali.step('kaspi-receipt');
  });
});
