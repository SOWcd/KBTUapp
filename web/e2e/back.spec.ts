// Telegram's BackButton is the app's only Back (AGENTS.md "One Back"): it closes the top sheet or full-screen view and
// nothing under it, hides once nothing is left to close, and never leaves a blank screen however often it's pressed.
import { test, expect, type Phone } from './fixtures';
import type { Page } from '@playwright/test';
import ru, { type Key } from '../src/lib/i18n/ru';

const tr = (k: Key) => (ru[k] as string).replace(/­/g, ''); // soft hyphens aren't in the accessible names

// a phone that has seen the home-screen offer before: that launch moment (5 s that Back can't close, by design) stays
// out of the way of these flows
test.beforeEach(async ({ page, faults }) => {
  await page.addInitScript(() => { try { localStorage.setItem('kb-install', '1'); } catch { /* no storage */ } });
  // WebKit reports a ResizeObserver that resized what it observes as an error event: the spec's harmless notice, not
  // a script error
  faults.allow.push(/ResizeObserver loop completed with undelivered notifications/);
});

const home = (page: Page) => page.getByRole('heading', { level: 1, name: tr('common.today'), exact: true });
const nav = (page: Page) => page.getByRole('navigation', { name: tr('nav.label') });
const dialog = (page: Page, k: Key, heading?: string | RegExp) => {
  const d = page.getByRole('dialog', { name: tr(k), exact: true });
  return heading ? d.filter({ has: page.getByRole('heading', { name: heading, exact: true }) }) : d;
};
// the app sets "stand-up" with a non-breaking hyphen
const openMic = /^Open Mic: stand.up and music/;
const awardCard = (page: Page) => page.getByRole('heading', { level: 2, name: tr('ach.first_in.name'), exact: true });

/** the badge has finished turning (Hero's flip: 760 ms) */
const turned = (page: Page) => expect.poll(() => page.locator(`button[aria-label="${tr('me.cardFront')}"]`)
  .evaluate((b) => b.closest('.card')!.getAnimations({ subtree: true }).filter((a) => a.playState === 'running' && a.effect?.getComputedTiming().endTime !== Infinity).length)).toBe(0);

async function backShown(p: Phone, shown: boolean) {
  await expect.poll(() => p.back.shown(), { message: `Telegram's Back button ${shown ? 'shown' : 'hidden'}` }).toBe(shown);
}

/** the home screen, nothing over it, Back hidden */
async function atHome(p: Phone) {
  await expect(home(p.page)).toBeVisible();
  await expect(nav(p.page)).toBeVisible();
  await expect(p.page.getByRole('dialog')).toHaveCount(0);
  await backShown(p, false);
}

/** Dana: the event, a friend going to it, his award: three sheets on top of each other */
async function openStack(dana: Phone) {
  const { page } = dana;
  await atHome(dana);
  await page.getByRole('button', { name: 'Board games night', exact: true }).first().click();
  const event = dialog(page, 'cap.event', 'Board games night');
  await expect(event).toBeVisible();
  await backShown(dana, true);
  await dana.look('event sheet');

  await event.getByRole('button', { name: 'Ali N', exact: true }).click();
  const person = dialog(page, 'cap.person');
  await expect(person.getByText('Ali N', { exact: true })).toBeVisible();
  await backShown(dana, true);
  await dana.look('person over the event');

  await person.getByRole('button', { name: new RegExp(`^${tr('ach.first_in.name')}`) }).click();
  await expect(awardCard(page)).toBeVisible();
  await expect(page.getByText(tr('ach.first_in.how'))).toBeVisible();
  await backShown(dana, true);
  await dana.look('award over the person');
  return { event, person };
}

test('Back closes the sheets one at a time, then hides, and more Back never blanks the screen', async ({ open }) => {
  const dana = await open('Dana');
  const { page } = dana;
  const { event, person } = await openStack(dana);

  await dana.back.press();
  await expect(awardCard(page)).toBeHidden();
  await expect(person).toBeVisible();
  await expect(event).toBeVisible();
  await backShown(dana, true);
  await dana.look('back: the award closed, the person is there');

  await dana.back.press();
  await expect(person).toBeHidden();
  await expect(event).toBeVisible();
  await backShown(dana, true);
  await dana.look('back: the person closed, the event is there');

  await dana.back.press();
  await expect(event).toBeHidden();
  await atHome(dana);
  await dana.look('back: home');

  // Telegram may still deliver a press (a double tap, a late event): nothing to close, nothing changes
  for (let i = 0; i < 3; i++) await dana.back.press();
  await atHome(dana);
  await expect(page.getByRole('button', { name: 'Board games night', exact: true }).first()).toBeVisible();
  await dana.look('back pressed on home: still home');
});

test('quick Back presses close exactly as many sheets as were pressed', async ({ open }) => {
  const dana = await open('Dana');
  const { page } = dana;
  const { event, person } = await openStack(dana);

  // two presses while the first exit still plays: the award and the person go, the event stays
  await dana.back.press();
  await dana.back.press();
  await expect(awardCard(page)).toBeHidden();
  await expect(person).toBeHidden();
  await expect(event).toBeVisible();
  await expect(event.getByRole('heading', { name: 'Board games night', exact: true })).toBeVisible();
  await backShown(dana, true);
  await dana.look('two quick backs: the event is left');

  await dana.back.press();
  await atHome(dana);
});

test('Back walks back through event, its club and another event of the club', async ({ open }) => {
  const dana = await open('Dana');
  const { page } = dana;
  await atHome(dana);

  await page.getByRole('button', { name: 'Board games night', exact: true }).first().click();
  const first = dialog(page, 'cap.event', 'Board games night');
  await expect(first).toBeVisible();
  await first.getByRole('button', { name: 'Open Mic Club', exact: true }).click();
  const club = dialog(page, 'cap.club');
  await expect(club.getByRole('heading', { level: 2, name: /^Open Mic Club/ })).toBeVisible();
  await dana.look('club over the event');

  await club.getByRole('button', { name: openMic }).click();
  const second = dialog(page, 'cap.event', openMic);
  await expect(second).toBeVisible();
  await backShown(dana, true);
  await dana.look('another event over the club');

  await dana.back.press();
  await expect(second).toBeHidden();
  await expect(club).toBeVisible();
  await expect(first).toBeVisible();
  await dana.look('back: the club');

  await dana.back.press();
  await expect(club).toBeHidden();
  await expect(first).toBeVisible();
  await backShown(dana, true);

  await dana.back.press();
  await expect(first).toBeHidden();
  await atHome(dana);
  await dana.back.press();
  await atHome(dana);
});

test('Back closes the full-screen campus map back to the home screen', async ({ open }) => {
  const dana = await open('Dana');
  const { page } = dana;
  // the map's "free now" rooms are off on this server: it answers 404 by design (client.ts mapRooms)
  dana.allow(/\/api\/map\/rooms 404$/);
  dana.allow(/status of 404 \(Not Found\)$/);
  await atHome(dana);

  // qa.py's server has the assistant on, so the bar's corner is its light and the map opens from the Afisha's "More"
  await page.locator('.solo .more button, button.s.more').click();
  await page.getByRole('menuitem', { name: tr('map.open'), exact: true }).click();
  const floors = page.getByRole('group', { name: tr('map.floors') });
  await expect(floors).toBeVisible();
  await backShown(dana, true); // once the map's opening (its iris) is done
  await dana.look('map');

  await dana.back.press();
  await expect(floors).toBeHidden();
  await atHome(dana);
  await dana.look('back from the map: home');
  await dana.back.press();
  await atHome(dana);
});

test('on the Profile tab Back undoes the tab\'s own state and its pages, never the tab itself', async ({ open }) => {
  const dana = await open('Dana');
  const { page } = dana;
  await atHome(dana);

  // a tab is not a page on a stack: no Back on it, and a stray press keeps it
  await nav(page).getByRole('button', { name: tr('tab.profile'), exact: true }).click();
  const settings = page.getByRole('button', { name: tr('me.settings'), exact: true });
  await expect(settings).toBeVisible();
  await backShown(dana, false);
  await dana.back.press();
  await expect(settings).toBeVisible();
  await expect(nav(page)).toBeVisible();
  await dana.look('profile tab');

  // my badge turned to its QR side: Back turns it face on
  const photo = page.getByRole('button', { name: tr('look.photo'), exact: true });
  await expect(photo).toBeVisible();
  await page.getByRole('button', { name: tr('me.qr'), exact: true }).click();
  const front = page.getByRole('button', { name: tr('me.cardFront'), exact: true });
  await expect(front).toBeVisible();
  await expect(photo).toBeHidden();
  await backShown(dana, true);
  await turned(page);
  await dana.look('badge on its QR side');
  await dana.back.press();
  await expect(front).toBeHidden();
  await expect(photo).toBeVisible();
  await backShown(dana, false);
  await turned(page);
  await dana.back.press();
  await expect(photo).toBeVisible();
  await expect(settings).toBeVisible();

  // my friends: a page over the tab
  await page.getByRole('button', { name: new RegExp(`^${tr('page.friends')}`) }).first().click();
  const friends = dialog(page, 'page.friends');
  await expect(friends.getByRole('button', { name: /Ali Nurlanov/ })).toBeVisible();
  await backShown(dana, true);
  await dana.look('friends over the profile');
  await dana.back.press();
  await expect(friends).toBeHidden();
  await expect(settings).toBeVisible();
  await backShown(dana, false);

  // the settings and a page pushed from them
  await settings.click();
  const set = page.getByRole('region', { name: tr('me.settings'), exact: true });
  await expect(set).toBeVisible();
  await backShown(dana, true);
  await set.getByRole('button', { name: tr('set.privacy'), exact: true }).click();
  const privacy = page.getByRole('region', { name: tr('set.privacy'), exact: true });
  await expect(privacy).toBeVisible();
  await dana.look('privacy over the settings');
  await dana.back.press();
  await expect(privacy).toBeHidden();
  await expect(set).toBeVisible();
  await backShown(dana, true);
  await dana.back.press();
  await expect(set).toBeHidden();
  await expect(settings).toBeVisible();
  await expect(nav(page)).toBeVisible();
  await backShown(dana, false);
  await dana.back.press();
  await expect(settings).toBeVisible();
  await dana.look('back to the profile tab');
});

test('Back pressed while my badge is still turning to its QR side turns it face on', async ({ open }) => {
  const dana = await open('Dana');
  const { page } = dana;
  await atHome(dana);
  await nav(page).getByRole('button', { name: tr('tab.profile'), exact: true }).click();
  const photo = page.getByRole('button', { name: tr('look.photo'), exact: true });
  await expect(photo).toBeVisible();

  // a quick "show my QR, no, back": the press comes during the 760 ms turn
  await page.getByRole('button', { name: tr('me.qr'), exact: true }).click();
  await backShown(dana, true);
  await dana.back.press();
  await turned(page);
  await expect(page.getByRole('button', { name: tr('me.cardFront'), exact: true })).toBeHidden();
  await expect(photo).toBeVisible();
  await backShown(dana, false);
  await dana.look('badge face on after a quick back');
});
