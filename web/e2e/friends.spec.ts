// Friends: by someone's invite link (r_<code>, one tap makes friends) or by a request the other one accepts, and then
// the event shows which friends go. Dana is friends with both in the seed; Ali and Bota are not yet.
import type { Page } from '@playwright/test';
import { test, expect, type Phone, reload } from './fixtures';
import ru from '../src/lib/i18n/ru';

type Key = keyof typeof ru;
const s = (k: Key) => ru[k] as string;
const fill = (k: Key, vars: Record<string, string>) => s(k).replace(/\{(\w+)\}/g, (_, v: string) => vars[v]);

const FREE = 'Board games night';
const sheet = (page: Page, title: Key) => page.getByRole('dialog', { name: s(title) });
const card = (page: Page, title: string) => page.getByRole('button', { name: title, exact: true }).first(); // the Afisha's hero

/** A launch without a link may first offer the home-screen icon or celebrate a new award (App.svelte's launch moments):
 *  whenever one stands in the way, the person puts it aside the way they would */
async function asideLaunchMoments(page: Page) {
  await page.addLocatorHandler(page.getByRole('dialog', { name: s('inst.title') }), async (d) => {
    await d.getByRole('button', { name: s('inst.later'), exact: true }).click(); // enabled after its short hold
  });
  // Back closes it (the app's only way out of a full-screen overlay): Telegram's back_button_pressed
  await page.addLocatorHandler(page.getByText(s('unlock.kicker'), { exact: true }).first(), async () => {
    await page.evaluate(() => (window as unknown as { Telegram: { WebView: { receiveEvent: (e: string) => void } } }).Telegram.WebView.receiveEvent('back_button_pressed'));
  });
}

type Friends = { friends: { person: { id: number } }[] };
const friendIds = async (p: Phone) => (await p.api<Friends>('/api/friends')).friends.map((f) => f.person.id);

/** the app opened again from Telegram's menu: no start parameter, the lists fresh from the server */
// (the same URL again is only a jump within the page: reload it)
const relaunch = async (p: Phone) => {
  const url = p.page.url(), plain = url.replace(/\?startapp=[^#]*/, '');
  await (plain === url ? reload(p.page) : p.page.goto(plain));
};

/** Bota signs up to the free event on her phone (the seed had her there already: she starts from no sign-up) */
async function botaGoes(bota: Phone) {
  await card(bota.page, FREE).click();
  const ev = sheet(bota.page, 'cap.event');
  await ev.getByRole('button', { name: s('event.go'), exact: true }).click();
  await expect(ev.getByRole('button', { name: s('event.ticket'), exact: true })).toBeVisible();
  await expect.poll(async () => (await bota.api<{ my: { status: string } | null }>('/api/events/2')).my?.status).toBe('going');
  await bota.look('signed up');
  await bota.back.press();
  await expect(ev).toBeHidden();
}

/** Ali sees Bota among the friends who go, on the event's sheet and on its Afisha card */
async function aliSeesBota(ali: Phone) {
  const line = fill('event.friendGoes', { name: 'Bota A' });
  await relaunch(ali);
  await expect(ali.page.getByText(line).first()).toBeVisible(); // the Afisha card's line
  await ali.look('afisha friend goes');
  await card(ali.page, FREE).click();
  const ev = sheet(ali.page, 'cap.event');
  await expect(ev.getByText(line, { exact: true })).toBeVisible();
  await ali.look('event friend goes');
}

test('an invite link makes friends in one tap, then the event shows the friend going', async ({ open }) => {
  const ali = await open('Ali');
  await asideLaunchMoments(ali.page);
  const code = (await ali.api<{ referrals: { code: string } | null }>('/api/me')).referrals!.code;
  expect(await friendIds(ali)).not.toContain(3);
  await expect(card(ali.page, FREE)).toBeVisible();
  await expect(ali.page.getByText(fill('event.friendGoes', { name: 'Bota A' }))).toHaveCount(0); // not friends: not shown

  // Bota opens Ali's link: his card with "Add as a friend"
  const bota = await open('Bota', { path: `/?startapp=r_${code}` });
  await asideLaunchMoments(bota.page);
  await bota.api('/api/events/2/registration', undefined, 'DELETE');
  const person = sheet(bota.page, 'cap.person');
  await expect(person.getByText(s('fr.invitesYou'))).toBeVisible();
  await expect(person.getByText('Ali').first()).toBeVisible();
  await bota.look('invite landing');
  await person.getByRole('button', { name: s('person.addFriend'), exact: true }).click();
  // friends at once; Bota had an account before, so the toast says the invite doesn't count for Ali
  await expect(bota.page.getByText(s('ref.alreadyRegistered').split('\n')[0]).first()).toBeVisible();
  await expect(person.getByRole('button', { name: s('person.addFriend'), exact: true })).toHaveCount(0);
  await bota.look('friends now');
  expect(await friendIds(ali)).toContain(3);
  await bota.back.press();
  await expect(person).toBeHidden();
  await relaunch(bota); // her Afisha without the seed's sign-up
  await botaGoes(bota);

  await aliSeesBota(ali);
});

test('a friend request the other one accepts, then the event shows the friend going', async ({ open }) => {
  const ali = await open('Ali', { path: '/?startapp=u_3' }); // Bota's profile (her QR, a name tapped anywhere)
  await asideLaunchMoments(ali.page);
  const person = sheet(ali.page, 'cap.person');
  await expect(person.getByText('Bota').first()).toBeVisible();
  await person.getByRole('button', { name: s('person.addFriend'), exact: true }).click();
  await expect(person.getByRole('button', { name: s('person.requestSent'), exact: true })).toBeVisible();
  await ali.look('request sent');

  // Bota opens Ali's profile and accepts
  const bota = await open('Bota', { path: '/?startapp=u_2' });
  await asideLaunchMoments(bota.page);
  await bota.api('/api/events/2/registration', undefined, 'DELETE');
  const his = sheet(bota.page, 'cap.person');
  const accept = his.getByRole('button', { name: s('fr.acceptReq'), exact: true });
  await expect(accept).toBeVisible();
  await bota.look('request to answer');
  await accept.click();
  await expect(bota.page.getByText(fill('fr.accepted', { name: 'Ali N' })).first()).toBeVisible();
  await expect(accept).toHaveCount(0);
  await bota.look('accepted');
  expect(await friendIds(ali)).toContain(3);
  await bota.back.press();
  await expect(his).toBeHidden();
  await relaunch(bota);
  await botaGoes(bota);

  await aliSeesBota(ali);
});
