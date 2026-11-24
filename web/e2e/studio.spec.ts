// Studio: Dana (the Open Mic Club's vice) creates an event in the manual editor, publishes it, edits it, and it shows on
// Ali's Afisha; then she asks a second club to co-host it and its President (Ali) accepts in his Studio.
import { test, expect, T, settle, type App } from './fixtures';

/** A panel's field typed into, then the keyboard put away before Done: the app's iOS keyboard guess (lib/state/keyboard)
 *  lifts the panel while a field has the focus, and a desktop engine moves the focus on mousedown, so the panel would
 *  drop away under the pointer mid-click (a real iPhone keeps the focus on a button tap). */
async function typeIn(app: App, label: string, text: string): Promise<void> {
  const field = app.page.getByRole('textbox', { name: label, exact: true });
  await field.fill(text);
  await field.blur();
  await settle(app.page);
}

const CLUB = 'Open Mic Club', SECOND = 'Chess'; // asked as "Chess Club": a club's name keeps no "Club" (logic.org_name)
const TITLE = 'Poetry slam', EDITED = 'Poetry slam night';

// the second club needs the creator's yes (club applications are the admin's): Bota is qa.py's admin for this file only
test.use({ qaEnv: { QA_ADMIN_TG_IDS: '1003' } });

test('an event made in Studio by hand, published, edited, on Afisha, co-hosted', async ({ open, qa }) => {
  const dana = await open('Dana');
  const studio = dana.page.getByRole('region', { name: CLUB });
  const editor = dana.page.locator('.pk'); // the editor's focused panel (one at a time)

  await test.step('Dana creates an event in the manual editor and publishes it', async () => {
    await dana.goTab(T('page.clubs'));
    await dana.page.getByRole('button', { name: new RegExp(`^${CLUB}`) }).first().click();
    await expect(studio.getByRole('heading', { name: CLUB })).toBeVisible();
    await studio.getByRole('button', { name: T('studio.create'), exact: true }).click();
    await dana.page.getByRole('menuitem', { name: T('studio.newShort') }).click();
    // a new event opens on the assistant's chat; "Edit by hand" is the manual editor
    await dana.page.getByRole('button', { name: T('ed.byHand') }).click();
    const name = dana.page.getByRole('textbox', { name: T('ex.name') });
    await expect(name).toBeVisible();
    await dana.step('editor');
    await name.fill(TITLE);
    await name.blur();
    await dana.page.getByRole('button', { name: T('ex.placeAdd') }).click();
    await typeIn(dana, T('ed.place'), 'Room 101');
    await editor.getByRole('button', { name: T('ex.done') }).click();
    await expect(editor).toBeHidden();
    await dana.page.getByRole('button', { name: new RegExp(`^${T('ed.seats')}`) }).click();
    await editor.getByRole('radio', { name: T('ex.unlimited') }).click();
    await editor.getByRole('button', { name: T('ex.done') }).click();
    await expect(editor).toBeHidden();
    await dana.step('editor-filled');
    await dana.page.getByRole('button', { name: T('ed.publish'), exact: true }).click();
    // the check before publishing: no cover and no description are only advice
    await expect(editor.getByRole('button', { name: T('ex.publishAnyway') })).toBeVisible();
    await dana.step('publish-check');
    await editor.getByRole('button', { name: T('ex.publishAnyway') }).click();
    await expect(studio.getByRole('button', { name: new RegExp(`^${TITLE} .*Room 101`) })).toBeVisible();
    await dana.step('published');
  });

  await test.step('Dana edits it', async () => {
    await studio.getByRole('button', { name: new RegExp(`^${TITLE} `) }).click();
    await dana.sheet().getByRole('button', { name: T('studio.edit'), exact: true }).click();
    const name = dana.page.getByRole('textbox', { name: T('ex.name') });
    await expect(name).toHaveValue(TITLE);
    await name.fill(EDITED);
    await name.blur();
    await settle(dana.page);
    await dana.step('editing');
    await dana.page.getByRole('button', { name: T('common.save'), exact: true }).click();
    const anyway = editor.getByRole('button', { name: T('ex.saveAnyway') });
    await expect(anyway.or(name)).toBeVisible();
    if (await anyway.isVisible()) await anyway.click(); // the same advice as before publishing, when it has some
    // the editor closes onto the event's own sheet, under its new name; Back once goes to Studio
    await expect(name).toBeHidden();
    await expect(dana.sheet().getByText(EDITED)).toBeVisible();
    await dana.step('edited-sheet');
    await dana.back();
    const row = studio.getByRole('button', { name: new RegExp(`^${EDITED} `) });
    await expect(row).toBeVisible();
    await dana.step('edited');
  });

  const ali = await open('Ali');

  await test.step('it shows on Afisha for another student', async () => {
    const card = ali.page.getByRole('button', { name: EDITED, exact: true });
    await expect(card).toBeVisible();
    await card.scrollIntoViewIfNeeded();
    await ali.step('afisha');
    await card.click();
    await expect(ali.sheet().getByText(EDITED).first()).toBeVisible();
    await ali.step('event-sheet');
    await ali.back();
    await expect(ali.nav()).toBeVisible();
  });

  await test.step('a co-host invite to another club, accepted', async () => {
    // the second club: Ali asks to start one and the admin (Bota) says yes. A fresh club has fewer than CLUB_MIN people,
    // so it is off the registry, and the editor's "Invite a club" lists the registry's clubs only: the invite goes by
    // the API, the answer is Ali's in his Studio (see the PR: a second club in qa.py's seed would let the UI send it)
    const app = await qa.api<{ id: number }>('Ali', 'POST', '/club-applications',
      { name: `${SECOND} Club`, short: 'CC', description: 'Chess evenings for everyone, any level.', emoji: 'popcorn_3d', cover: 0, links: [] });
    const made = await qa.api<{ orgId: number }>('Bota', 'POST', `/admin/club-applications/${app.id}`, { approve: true });
    const events = await qa.api<{ id: number; title: string }[]>('Dana', 'GET', '/events?org=1');
    const ev = events.find((e) => e.title === EDITED);
    expect(ev, 'the edited event in the club list').toBeTruthy();
    await qa.api('Dana', 'PUT', `/events/${ev!.id}/cohost`, { orgId: made.orgId });

    await ali.page.reload();
    await ali.ready();
    await ali.goTab(T('page.clubs'));
    await ali.page.getByRole('button', { name: new RegExp(`^${SECOND} `) }).first().click();
    const his = ali.page.getByRole('region', { name: SECOND, exact: true });
    const ask = his.getByText(T('co.ask', { club: CLUB }));
    await expect(ask).toBeVisible();
    await ask.scrollIntoViewIfNeeded();
    await ali.step('cohost-invite');
    await his.getByRole('button', { name: T('co.yes'), exact: true }).click();
    // the app's own confirm (sheets.ask): an alert over the Studio
    const confirm = ali.page.locator('[role="alertdialog"], [role="dialog"]').filter({ hasText: T('co.acceptAsk', { club: CLUB }) });
    await expect(confirm).toBeVisible();
    await ali.step('cohost-confirm');
    await confirm.getByRole('button', { name: T('co.yes'), exact: true }).click();
    await expect(ali.page.getByText(T('co.saidYes'))).toBeVisible();
    await expect(ask).toBeHidden();
    // the event is on his club's Studio too now
    await expect(his.getByRole('button', { name: new RegExp(`^${EDITED} `) })).toBeVisible();
    await ali.step('cohost-accepted');
  });
});
