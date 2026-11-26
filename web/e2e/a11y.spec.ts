// Accessibility (issue #362): axe-core on the main tabs and the most used sheets, at 375 px in both themes (the snap-*
// projects: qa.py's people on a fixed clock). Only serious and critical violations count, and only new ones fail: what
// was there when the check came in is listed in a11y-allow.txt, one line per element, to be fixed and struck off.
// A line: `<theme> <screen> <rule> <element>` (the element as axe's selector, Svelte's hashed classes left out). The
// app runs in English here (its kept language choice, set before the launch): the lines and labels stay readable to
// every contributor, and the repo keeps Cyrillic in the UI strings only.
import { readFileSync } from 'node:fs';
import AxeBuilder from '@axe-core/playwright';
import type { Page } from '@playwright/test';
import { test, expect, settled, type Phone } from './fixtures';
import en from '../src/lib/i18n/en';

const tr = (k: keyof typeof en) => en[k] as string;
const nav = (page: Page) => page.getByRole('navigation', { name: tr('nav.label') });

const ALLOW = new Set(readFileSync(new URL('./a11y-allow.txt', import.meta.url), 'utf8').split('\n')
  .map((l) => l.trim()).filter((l) => l && !l.startsWith('#')));

/** The serious and critical violations on the screen as it is, or only inside `scope` (a sheet: the tab under it has
 *  its own test), as allowlist lines */
async function found(page: Page, theme: string, screen: string, scope?: string): Promise<string[]> {
  const axe = new AxeBuilder({ page });
  const { violations } = await (scope ? axe.include(scope) : axe).analyze();
  return violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').flatMap((v) => v.nodes.map((n) =>
    `${theme} ${screen} ${v.id} ${n.target.join(' >> ').replace(/\.svelte-[\w-]+/g, '').replace(/\s+/g, ' ')}`));
}

const SHEET = '[role="dialog"]';

async function check(p: Phone, screen: string, scope?: string) {
  const theme = test.info().project.metadata.theme as string;
  await p.page.clock.fastForward(5000); // the app's timers run out (the capsule at rest), as for the snapshots
  const lines = [...new Set(await found(p.page, theme, screen, scope))];
  const fresh = lines.filter((l) => !ALLOW.has(l));
  const gone = [...ALLOW].filter((l) => l.startsWith(`${theme} ${screen} `) && !lines.includes(l));
  if (gone.length) test.info().annotations.push({ type: 'a11y fixed: strike off a11y-allow.txt', description: gone.join('\n') });
  expect(fresh, `${screen}: new serious or critical a11y violations (fix them; a deliberate exception goes into e2e/a11y-allow.txt)`).toEqual([]);
}

/** Ali, in English (lib/i18n: the kept choice wins over Telegram's language), past the launch's greeting */
async function ali(page: Page, open: (who: 'Ali') => Promise<Phone>) {
  await page.addInitScript(() => { try { localStorage.setItem('kb-lang', 'en'); } catch { /* storage blocked */ } });
  return settled(await open('Ali'));
}

test('Afisha', async ({ page, open }) => {
  await check(await ali(page, open), 'afisha');
});

for (const [screen, tab] of [['clubs', 'page.clubs'], ['forum', 'tab.forum'], ['me', 'tab.profile']] as const) {
  test(`the ${screen} tab`, async ({ page, open }) => {
    const p = await ali(page, open);
    await nav(p.page).getByRole('button', { name: tr(tab), exact: true }).click();
    await expect(nav(p.page).getByRole('button', { name: tr(tab), exact: true })).toHaveAttribute('aria-current', 'page');
    await check(p, screen);
  });
}

test('an event', async ({ page, open }) => {
  const p = await ali(page, open);
  await p.page.getByRole('button', { name: 'Open Mic: stand-up and music', exact: true }).first().click();
  await expect(p.page.getByRole('dialog').getByText('Atrium', { exact: true })).toBeVisible();
  await check(p, 'event', SHEET);
});

test('a ticket', async ({ page, open }) => {
  const p = await ali(page, open); // qa.py has Ali going to the board games night
  await p.page.getByRole('button', { name: tr('event.ticket'), exact: true }).first().click();
  await expect(p.page.getByText(tr('tk.hint'))).toBeVisible();
  await check(p, 'ticket', `[role="group"][aria-label="${tr('event.ticket')}"]`); // the pass, full screen over the tab
});

test('a person', async ({ page, open }) => {
  const p = await ali(page, open);
  await nav(p.page).getByRole('button', { name: tr('tab.profile'), exact: true }).click();
  await p.page.getByRole('button', { name: new RegExp(`^${tr('page.friends')}`) }).first().click();
  await p.page.getByRole('button', { name: /Dana Seitova/ }).click(); // his friend
  await expect(p.page.getByRole('dialog').getByText('Dana S', { exact: true })).toBeVisible();
  await check(p, 'person', SHEET);
});
