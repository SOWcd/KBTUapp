// Clubs: Dana (the Open Mic Club's vice) opens a recruitment round in Studio, Ali finds the club, opens its page and
// applies, and Dana sees Ali's application on the round's board.
import { test, expect, T, type App } from './fixtures';

const CLUB = 'Open Mic Club';

test('a student applies to a club round, its vice sees it in Studio', async ({ open }) => {
  const dana = await open('Dana');

  await test.step('Dana opens a recruitment round in Studio', async () => {
    await dana.goTab(T('page.clubs'));
    await dana.page.getByRole('button', { name: new RegExp(`^${CLUB}`) }).first().click();
    const studio = dana.page.getByRole('region', { name: CLUB });
    await expect(studio.getByRole('heading', { name: CLUB })).toBeVisible();
    await dana.step('studio');
    await studio.getByRole('button', { name: new RegExp(`^${T('cast.card')}`) }).click();
    const setup = dana.sheet();
    await expect(setup.getByRole('button', { name: T('cast.openGo') })).toBeVisible();
    await setup.getByRole('textbox', { name: T('cast.newTag') }).fill('Stage');
    await setup.getByRole('button', { name: T('cast.newTag') }).click();
    await expect(setup.getByRole('button', { name: 'Stage' })).toBeVisible(); // the new department's chip, picked
    await dana.step('round-setup');
    await setup.getByRole('button', { name: T('cast.openGo') }).click();
    await expect(dana.page.getByText(T('cast.opened'))).toBeVisible();
    await dana.step('round-open');
  });

  const ali = await open('Ali');

  await test.step('Ali finds the club and applies', async () => {
    await ali.goTab(T('page.clubs'));
    await ali.step('clubs');
    // a club under the registry's size bar is found by search (clubs.listed): pull the list down to its field
    const search = ali.page.getByRole('searchbox', { name: T('clubs.search') });
    await search.evaluate((el) => el.closest('.scroll')?.scrollTo({ top: 0 }));
    await expect(search).toBeEditable();
    await search.fill('Open Mic');
    await ali.page.getByRole('button', { name: new RegExp(`^${CLUB}`) }).first().click();
    const club = ali.sheet();
    await expect(club.getByRole('heading', { name: new RegExp(`^${CLUB}`) })).toBeVisible();
    await expect(club.getByText(new RegExp(`^${T('cast.recruiting', { when: '.+' })}$`))).toBeVisible();
    await ali.step('club');
    await club.getByRole('button', { name: T('join.apply'), exact: true }).click();
    // the round asks for nothing (one department, no questions): one tap sends it, or its sheet's Send does
    const send = ali.page.getByRole('button', { name: T('cast.send'), exact: true });
    const sent = ali.page.getByText(T('cast.sent'));
    const quick = ali.page.getByText(T('cast.sentShares'));
    await expect(send.or(sent).or(quick).first()).toBeVisible();
    if (await send.isVisible()) {
      await ali.step('apply-sheet');
      await send.click();
      await expect(sent).toBeVisible();
    }
    await ali.step('applied');
  });

  await test.step('Dana sees the application in Studio', async () => {
    await dana.page.reload();
    await dana.ready();
    await dana.goTab(T('page.clubs'));
    await dana.page.getByRole('button', { name: new RegExp(`^${CLUB}`) }).first().click();
    const studio = dana.page.getByRole('region', { name: CLUB });
    const recruit = studio.getByRole('button', { name: new RegExp(`^${T('cast.card')}`) });
    await expect(recruit).toContainText('1'); // one fresh application on the tile
    await dana.step('studio-new-app');
    await recruit.click();
    // the application's row: the applicant (qa.py's Ali Nurlanov) and the department picked
    await expect(dana.sheet().getByRole('button', { name: /Nurlanov Ali.*Stage/ })).toBeVisible();
    await dana.step('round-board');
  });
});
