// Account deletion: Bota (Dana's friend, a member of her club) asks to delete her account in Settings; once the week
// to change her mind has run out (the nightly sweep, logic.delete_due, run here at once), Dana's friends and the
// club's people no longer have her.
import { test, expect, T, N, type App } from './fixtures';

const BOTA = 3; // qa.py's PEOPLE: Bota's user id

/** Dana's lists: her friends (Profile) and the club's people (its sheet, from her event). */
async function friendsOf(a: App) {
  await a.goTab(T('tab.profile'));
  await a.page.getByRole('main').getByRole('button', { name: new RegExp(`^${T('page.friends')}`) }).click();
  const s = a.page.getByRole('dialog', { name: T('page.friends') });
  await expect(s.getByRole('button', { name: /Ali/ })).toBeVisible();
  return s;
}

async function clubOf(a: App) {
  await a.goTab(T('tab.afisha'));
  await a.page.getByRole('main').getByRole('button', { name: 'Board games night' }).first().click();
  await a.page.getByRole('dialog', { name: T('cap.event') }).getByRole('button', { name: 'Open Mic Club' }).first().click();
  const s = a.page.getByRole('dialog', { name: T('cap.club') });
  await expect(s.getByRole('heading', { name: /Open Mic Club/ })).toBeVisible();
  return s;
}

test('a deleted account is gone from friends and the club', async ({ open, qa }) => {
  test.setTimeout(240_000); // three launches and the sweep: longer than one flow
  // made-up data: Bota joins Dana's club (the seed has only Dana in it)
  qa.py(`con.execute("INSERT INTO org_members (org_id, user_id, role, joined_at) VALUES (1, ${BOTA}, 'member', strftime('%s'))")`);

  // before: Dana sees Bota among her friends and in the club's people
  const dana = await open('Dana');
  let friends = await friendsOf(dana);
  await expect(friends.getByRole('button', { name: /Bota/ })).toBeVisible();
  await dana.step('friends-before');
  await dana.back();
  let club = await clubOf(dana);
  await club.getByRole('button', { name: new RegExp(T('club.everyone')) }).click();
  const people = dana.page.getByRole('dialog').last();
  await expect(people.getByText(/Bota/).first()).toBeVisible();
  await dana.step('club-people-before');
  await dana.page.close();

  // Bota: Profile, Settings, Privacy, Delete account, then the week starts
  const bota = await open('Bota');
  await bota.goTab(T('tab.profile'));
  await bota.page.getByRole('main').getByRole('button', { name: T('me.settings') }).click();
  await bota.page.getByRole('button', { name: N(T('set.privacy')) }).click();
  await bota.page.getByRole('button', { name: T('me.deleteData') }).click();
  const del = bota.page.getByRole('dialog', { name: T('del.title') });
  await expect(del.getByRole('button', { name: T('del.forever') })).toBeVisible();
  await bota.step('delete-sheet');
  await del.getByRole('button', { name: T('del.forever') }).click();
  await expect(bota.page.getByRole('status').filter({ hasText: T('del.done').split('{date}')[0] })).toBeVisible();
  await bota.step('delete-asked');
  // the account works meanwhile, with the way back on Me
  await expect(del).toBeHidden();
  await bota.page.close();

  // the week runs out: the nightly sweep deletes her
  qa.py(`con.execute("UPDATE users SET delete_at = 1 WHERE id = ${BOTA}")\nlogic.delete_due(con)\nassert not con.execute("SELECT 1 FROM students WHERE user_id = ${BOTA}").fetchone()`);

  // after: Dana's friends and the club's people have no Bota
  const again = await open('Dana');
  friends = await friendsOf(again);
  await expect(friends.getByRole('button', { name: /Bota/ })).toHaveCount(0);
  await again.step('friends-after');
  await again.back();
  club = await clubOf(again);
  await expect(club.getByText(/Bota/)).toHaveCount(0);
  const everyone = club.getByRole('button', { name: new RegExp(T('club.everyone')) });
  if (await everyone.count()) { // shown only while the club has more people than its leaders
    await everyone.click();
    await expect(again.page.getByRole('dialog').last().getByText(/Bota/)).toHaveCount(0);
  }
  await again.step('club-after');
});
