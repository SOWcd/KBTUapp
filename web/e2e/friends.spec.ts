// Friends: Ali shows his invite (the QR of his one link, r_<code>), Bota opens that link and adds him in one tap (the
// link is the inviter's yes: server profiles.add_by_link), Ali's open invite sees her arrive, and on an event both go
// to ("Board games night", qa.py) Bota now sees Ali among the friends going. Dana is already friends with both.
import { test, expect, T, App, settle, newContext, watch, linkFor, type Theme } from './fixtures';

const EVENT = 'Board games night';
/** A UI template as a pattern: its {holes} match a name ("Ali", "Ali N.", ...). */
const like = (s: string) => new RegExp(s.replace(/[.*+?^$()|[\]\\]/g, '\\$&').replace(/\\?\{\w+\\?\}/g, 'Ali[^,]*'));

test('friends: invite link, one tap, the other side sees it, friends going', async ({ browser, qa, problems, open }, info) => {
  test.setTimeout(150_000); // four launches of the app (three people, one relaunch)
  const theme = (info.project.use.colorScheme ?? 'dark') as Theme;
  const goes = like(T('event.friendGoes', { name: '{name}' }));

  const bota0 = await open('Bota');
  await test.step('before: Bota sees no friend of hers named Ali going', async () => {
    await bota0.page.getByRole('button', { name: EVENT, exact: true }).last().click();
    await expect(bota0.sheet().getByText(EVENT).first()).toBeVisible();
    await expect(bota0.sheet().getByRole('button', { name: T('event.ticket'), exact: true })).toBeVisible();
    await expect(bota0.sheet().getByText(goes)).toHaveCount(0);
    await bota0.step('event-before');
    await bota0.page.context().close();
  });

  const ali = await open('Ali');
  let code = '';
  await test.step('Ali opens his invite: the QR of his link', async () => {
    await ali.goTab(T('tab.profile'));
    await ali.step('profile');
    await ali.page.getByRole('button', { name: T('page.friends'), exact: true }).click();
    await expect(ali.page.getByRole('dialog', { name: T('page.friends') })).toBeVisible();
    await ali.step('friends');
    await ali.sheet().getByRole('button', { name: T('fr.add'), exact: true }).first().click();
    await expect(ali.page.getByRole('dialog', { name: T('fr.addTitle') })).toBeVisible();
    await ali.step('invite-qr');
    // the code in his QR: the same one his /me carries (the QR itself is a canvas)
    code = await ali.page.evaluate(async () => {
      const w = window as unknown as { Telegram: { WebApp: { initData: string } } };
      const r = await fetch('/api/me', { headers: { Authorization: 'tma ' + w.Telegram.WebApp.initData } });
      return ((await r.json()) as { referrals: { code: string } | null }).referrals?.code ?? '';
    });
    expect(code).toMatch(/^[A-Z2-7]{10}$/);
  });

  await test.step('Bota opens the link and adds him in one tap', async () => {
    // the link as Telegram opens it: startapp=r_<code> (tg.ts reads it from the query too)
    const ctx = await newContext(browser, info);
    const page = await ctx.newPage();
    watch(page, 'Bota', qa.base, problems);
    const u = new URL(linkFor(qa.links.Bota, theme));
    u.search = `?startapp=r_${code}`;
    await page.goto(u.toString());
    const bota = new App(page, 'Bota', info, problems);
    const add = page.getByRole('button', { name: T('person.addFriend'), exact: true });
    await expect(add).toBeVisible({ timeout: 20_000 });
    await expect(page.getByText(T('fr.invitesYou'))).toBeVisible();
    await bota.step('invite-landing');
    await add.click();
    await expect(page.getByRole('button', { name: T('inv.toButton') })).toBeVisible();
    await bota.step('now-friends');

    await test.step('the other side: Ali\'s open invite sees her join', async () => {
      await expect(ali.page.getByText(T('fr.nowFriend')).first()).toBeVisible({ timeout: 15_000 });
      await ali.step('invite-joined');
    });

    await test.step('friends going: Bota sees Ali on the event, in the same session', async () => {
      await bota.ready();
      await page.getByRole('button', { name: EVENT, exact: true }).last().click();
      await expect(bota.sheet().getByText(EVENT).first()).toBeVisible();
      await bota.step('friends-going-same-session');
      // soft: a known bug (the Afisha's events keep the friends they had at launch, see the PR's bug list); the rest goes on
      await expect.soft(bota.sheet().getByText(goes).first(), 'a new friend shows among friends going without a relaunch').toBeVisible({ timeout: 5000 });
    });
    await ctx.close();
  });

  await test.step('friends going: after a relaunch Bota sees Ali on the event', async () => {
    const bota = await open('Bota');
    await bota.page.getByRole('button', { name: EVENT, exact: true }).last().click();
    await expect(bota.sheet().getByText(EVENT).first()).toBeVisible();
    await expect(bota.sheet().getByText(goes).first()).toBeVisible();
    await bota.step('friends-going');
  });
});
