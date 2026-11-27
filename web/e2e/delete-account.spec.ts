// Deleting an account (server/kbtu/logic/account.py): Ali asks in the settings, the app says when and
// offers the way back; a week later the bot's round (delete_due) deletes it, and then his friend and his club no
// longer see him, and his own app is a guest's.
import { test, expect, type Phone, type Qa, reload } from './fixtures';
import type { Page } from '@playwright/test';
import { execFileSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import ru, { type Key } from '../src/lib/i18n/ru';

const tr = (k: Key) => (ru[k] as string).replace(/­/g, ''); // soft hyphens aren't in the accessible names
const SERVER = resolve(import.meta.dirname, '../../server');
const PYTHON = process.env.QA_PYTHON || (existsSync(join(SERVER, '.venv/bin/python')) ? join(SERVER, '.venv/bin/python') : 'python3');

/** a week on: the bot's round runs the deletions that are due (outbox.py send_due -> logic.delete_due) */
function weekLater(qa: Qa) {
  execFileSync(PYTHON, ['-c', `import sys
from kbtu import db, logic
con = db.connect(sys.argv[1])
n = con.execute("UPDATE users SET delete_at = 1 WHERE delete_at IS NOT NULL").rowcount
assert n == 1, n
logic.delete_due(con)
assert not con.execute("SELECT 1 FROM students WHERE user_id = 2").fetchone(), "not deleted"`, qa.db], { cwd: SERVER });
}

const nav = (page: Page) => page.getByRole('navigation', { name: tr('nav.label') });
const tab = (p: Phone, k: Key) => nav(p.page).getByRole('button', { name: tr(k), exact: true }).click();
const dialog = (page: Page, k: Key) => page.getByRole('dialog', { name: tr(k), exact: true });

test.beforeEach(async ({ page, faults }) => {
  // a phone that has seen the home-screen offer before (that launch moment can't be closed for 5 s, by design)
  await page.addInitScript(() => { try { localStorage.setItem('kb-install', '1'); } catch { /* no storage */ } });
  faults.allow.push(/ResizeObserver loop completed with undelivered notifications/); // WebKit's harmless notice
});

/** a phone in its own browser: the home-screen offer marked seen, then the app opened afresh */
async function relaunch(p: Phone) {
  await p.page.context().addInitScript(() => { try { localStorage.setItem('kb-install', '1'); } catch { /* no storage */ } });
  await p.page.waitForLoadState('load');
  await reload(p.page);
  await expect(nav(p.page)).toBeVisible();
}

/** Dana's friends page: who's in it */
async function friendsOf(dana: Phone) {
  await tab(dana, 'tab.profile');
  await dana.page.getByRole('button', { name: new RegExp(`^${tr('page.friends')}`) }).first().click();
  const friends = dialog(dana.page, 'page.friends');
  await expect(friends.getByRole('button', { name: /Bota Askarova/ })).toBeVisible();
  return friends;
}

/** the Open Mic club's sheet from Dana's Clubs tab */
async function clubOf(dana: Phone) {
  await tab(dana, 'page.clubs');
  // the Popular row opens the club as everyone sees it (the Mine row opens its Studio)
  await dana.page.getByRole('button', { name: new RegExp(`^Open Mic Club ${tr('clubs.official')}`) }).first().click();
  const club = dialog(dana.page, 'cap.club');
  await expect(club.getByRole('heading', { level: 2, name: /^Open Mic Club/ })).toBeVisible();
  return club;
}

test('Ali deletes his account: a week later his friend and his club no longer see him', async ({ open, qa }) => {
  const ali = await open('Ali');
  // the award he earned yesterday has had its moment already (a launch moment that would otherwise come up over
  // these taps whenever nothing is open)
  const me = await ali.api<{ unlocked?: { code: string; level: number }[] }>('/api/me');
  for (const u of me.unlocked ?? []) await ali.api('/api/me/unlocked', { code: u.code, level: u.level });
  await relaunch(ali);

  // Ali asks to join Dana's club and she accepts
  await ali.api('/api/orgs/1/join-requests', {});
  const dana = await open('Dana');
  const asks = await dana.api<{ id: number; person: { id: number } }[]>('/api/orgs/1/join-requests');
  await dana.api(`/api/join-requests/${asks.find((r) => r.person.id === 2)!.id}/accept`, {});
  await relaunch(dana);

  // before: Ali is Dana's friend and in the club's members
  let friends = await friendsOf(dana);
  await expect(friends.getByRole('button', { name: /Ali Nurlanov/ })).toBeVisible();
  await dana.look('friends before');
  await dana.back.press();
  await expect(friends).toBeHidden();
  let club = await clubOf(dana);
  await club.getByRole('button', { name: new RegExp(`^${tr('club.everyone')}`) }).click();
  const members = dana.page.getByRole('dialog', { name: 'Open Mic Club', exact: true });
  await expect(members.getByRole('button', { name: /Ali N$/ })).toBeVisible();
  await dana.look('club members before');
  await dana.back.press();
  await expect(members).toBeHidden();
  await dana.back.press();
  await expect(club).toBeHidden();

  // Ali: Profile -> Settings -> Privacy -> Delete account
  await tab(ali, 'tab.profile');
  await ali.page.getByRole('button', { name: tr('me.settings'), exact: true }).click();
  const settings = ali.page.getByRole('region', { name: tr('me.settings'), exact: true });
  await settings.getByRole('button', { name: tr('set.privacy'), exact: true }).click();
  const privacy = ali.page.getByRole('region', { name: tr('set.privacy'), exact: true });
  await privacy.getByRole('button', { name: tr('me.deleteData'), exact: true }).click();
  const sheet = dialog(ali.page, 'del.title');
  await expect(sheet.getByRole('heading', { name: tr('del.title') })).toBeVisible();
  await expect(sheet.getByRole('alert')).toContainText(tr('del.lost')); // what goes: his awards and his club
  await ali.look('delete sheet');
  await sheet.getByRole('button', { name: tr('del.forever'), exact: true }).click();

  // the app says when, the sheet goes, and the delete row with it (asked once)
  await expect(sheet).toBeHidden();
  await expect(ali.page.getByRole('status').filter({ hasText: tr('del.done').split('{date}')[0] })).toBeVisible();
  await expect(privacy.getByRole('button', { name: tr('me.deleteData'), exact: true })).toHaveCount(0);
  await ali.look('deletion asked');
  await ali.back.press();
  await expect(privacy).toBeHidden();
  await ali.back.press();
  await expect(settings).toBeHidden();
  // Me says when, with the way back
  const soon = ali.page.getByRole('alert').filter({ hasText: tr('del.soon').split('{date}')[0] });
  await expect(soon).toBeVisible();
  await expect(soon.getByRole('button', { name: tr('del.keep'), exact: true })).toBeVisible();
  await ali.look('profile: deletion in a week');

  // a week later
  weekLater(qa);

  await relaunch(dana);
  friends = await friendsOf(dana);
  await expect(friends.getByRole('button', { name: /Ali/ })).toHaveCount(0);
  await dana.look('friends after');
  await dana.back.press();
  await expect(friends).toBeHidden();
  club = await clubOf(dana);
  // nowhere in the club's sheet: not a member, not among the friends who came to its past event
  await expect(club.getByRole('button', { name: /Ali N/ })).toHaveCount(0);
  await expect(club.getByRole('button', { name: /Dana S/ })).toBeVisible();
  const everyone = club.getByRole('button', { name: new RegExp(`^${tr('club.everyone')}`) });
  if (await everyone.count()) {
    await everyone.click();
    const left = dana.page.getByRole('dialog', { name: 'Open Mic Club', exact: true });
    await expect(left.getByRole('button', { name: /^DS Dana S/ })).toBeVisible();
    await expect(left.getByRole('button', { name: /Ali N/ })).toHaveCount(0);
  }
  await dana.look('club after');

  // Ali opens the app again: a guest, asked to sign in, his profile gone
  await reload(ali.page);
  await tab(ali, 'tab.profile');
  await expect(ali.page.getByRole('heading', { level: 1, name: tr('guest.title'), exact: true })).toBeVisible();
  await expect(ali.page.getByRole('button', { name: tr('guest.button'), exact: true })).toBeVisible();
  await expect(ali.page.getByText('Ali N', { exact: true })).toHaveCount(0);
  await ali.look('after deletion: a guest');
});
