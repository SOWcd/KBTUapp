// Telegram's BackButton is the app's only Back: each press closes the top sheet alone, the one under it is there
// again, the button hides when nothing is left to close, and the screen under it is never blank.
import { test, expect, T, N, settle, type App } from './fixtures';

test.describe.configure({ timeout: 150_000 }); // WebKit at 320 px takes up to a minute for the longer stack

/** The sheets open now, bottom to top (a closing one is gone from the list once its animation ends). */
const dialogs = (a: App) => a.page.getByRole('dialog');

/** The screen under the sheets is never blank: the tab bar, the tab's own content with words in it, and something
 *  real under the screen's centre (not the bare page). */
async function notBlank(a: App): Promise<void> {
  await expect(a.nav()).toBeVisible();
  const main = a.page.getByRole('main');
  await expect(main).toBeVisible();
  expect((await main.innerText()).trim().length, 'the tab has content').toBeGreaterThan(20);
  const hit = await a.page.evaluate(() => { const el = document.elementFromPoint(innerWidth / 2, innerHeight / 2); return !!el && el !== document.body && el !== document.documentElement; });
  expect(hit, 'something under the screen centre').toBe(true);
}

/** Back once: the top sheet goes, `under` (its title) is on top again, or nothing is left and the button hides. */
async function backTo(a: App, count: number, under?: string): Promise<void> {
  await a.back();
  await expect(dialogs(a)).toHaveCount(count);
  if (under) await expect(dialogs(a).last()).toHaveAttribute('aria-label', under);
  else await expect.poll(() => a.backShown(), { message: 'BackButton hidden with no sheet left' }).toBe(false);
  await settle(a.page);
  if (count) { // the sheet below is whole again (the tab bar hides under sheets)
    const top = dialogs(a).last();
    await expect(top).toBeVisible();
    expect((await top.innerText()).trim().length, 'the sheet has content').toBeGreaterThan(10);
  } else await notBlank(a);
}

test('Afisha: event, its club, a person; Back closes them in order', async ({ open }) => {
  const ali = await open('Ali');
  await notBlank(ali);
  expect(await ali.backShown()).toBe(false);

  await ali.page.getByRole('main').getByRole('button', { name: 'Board games night' }).first().click();
  await expect(dialogs(ali)).toHaveCount(1);
  await expect(dialogs(ali).last()).toHaveAttribute('aria-label', T('cap.event'));
  await expect.poll(() => ali.backShown()).toBe(true);
  await ali.step('event');

  await dialogs(ali).last().getByRole('button', { name: 'Open Mic Club' }).first().click();
  await expect(dialogs(ali)).toHaveCount(2);
  await expect(dialogs(ali).last()).toHaveAttribute('aria-label', T('cap.club'));
  await ali.step('club');

  await dialogs(ali).last().getByRole('button', { name: /Dana/ }).first().click();
  await expect(dialogs(ali)).toHaveCount(3);
  await expect(dialogs(ali).last()).toHaveAttribute('aria-label', T('cap.person'));
  await ali.step('person');

  await backTo(ali, 2, T('cap.club'));
  await expect(dialogs(ali).last().getByRole('heading', { name: /Open Mic Club/ })).toBeVisible();
  await ali.step('back-to-club');
  await backTo(ali, 1, T('cap.event'));
  await expect(dialogs(ali).last().getByRole('heading', { name: 'Board games night' })).toBeVisible();
  await ali.step('back-to-event');
  await backTo(ali, 0);
  await expect(ali.tab(T('tab.afisha'))).toHaveAttribute('aria-current', 'page');
  await ali.step('back-to-afisha');
});

test('Profile: friends, a friend; settings and a page in them; Back closes each', async ({ open }) => {
  const dana = await open('Dana');
  await dana.goTab(T('tab.profile'));
  await notBlank(dana);

  // sheets: Friends, then a friend's profile
  await dana.page.getByRole('main').getByRole('button', { name: new RegExp(`^${T('page.friends')}`) }).click();
  await expect(dialogs(dana)).toHaveCount(1);
  await expect(dialogs(dana).last()).toHaveAttribute('aria-label', T('page.friends'));
  await dana.step('friends');
  await dialogs(dana).last().getByRole('button', { name: /Ali/ }).first().click();
  await expect(dialogs(dana)).toHaveCount(2);
  await expect(dialogs(dana).last()).toHaveAttribute('aria-label', T('cap.person'));
  await dana.step('friend');
  await backTo(dana, 1, T('page.friends'));
  await dana.step('back-to-friends');
  await backTo(dana, 0);
  await expect(dana.tab(T('tab.profile'))).toHaveAttribute('aria-current', 'page');
  await dana.step('back-to-profile');

  // Settings (a mode of Profile, not a sheet) and Privacy in it: Back leaves the page, then the settings
  await dana.page.getByRole('main').getByRole('button', { name: T('me.settings') }).click();
  const settings = dana.page.getByRole('region', { name: T('me.settings') });
  await expect(settings).toBeVisible();
  await expect.poll(() => dana.backShown()).toBe(true);
  await dana.step('settings');
  await settings.getByRole('button', { name: N(T('set.privacy')) }).click();
  const privacy = dana.page.getByRole('region', { name: N(T('set.privacy')) });
  await expect(privacy).toBeVisible();
  await dana.step('privacy');
  await dana.back();
  await expect(privacy).toBeHidden();
  await expect(settings).toBeVisible();
  await dana.step('back-to-settings');
  await dana.back();
  await expect(settings).toBeHidden();
  await expect.poll(() => dana.backShown(), { message: 'BackButton hidden after settings' }).toBe(false);
  await notBlank(dana);
  await dana.step('back-out-of-settings');
});
