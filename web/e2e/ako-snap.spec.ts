// Admissions (server logic/ako.py) as pictures, at 375 px in both themes (the snap-* projects, qa.py --ako): the
// applicant's page step by step in a plain browser (a manager's prefilled link: documents, the interview time, sending,
// the status page), a sent package's page, the website's start link; and the managers' desk in Studio with a package.
// Pictures are compared only in the Linux browser (PW_WS); elsewhere the layout checks still run. Accepting: e2e/README.md.
import type { Locator, Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { test, expect, openAko, type Phone } from './fixtures';
import main from '../src/lib/i18n/ru';
import ako from '../src/lib/i18n/ako.ru';

test.use({ qaArgs: ['--ako'] });
const ru = { ...main, ...ako } as Record<string, string>;
const tr = (k: string) => ru[k].replace(/\u00ad/g, '');

async function shot(p: Phone, name: string, part?: Locator) {
  await p.look(name);
  if (!process.env.PW_WS) return;
  await p.page.clock.fastForward(5000);
  // a lazy <img> out of view never decodes: each wait has its ceiling (as snap.spec.ts)
  await p.page.evaluate(() => Promise.all([...document.images].map((i) => Promise.race([i.decode().catch(() => {}), new Promise((r) => setTimeout(r, 3000))]))));
  await expect(part ?? p.page).toHaveScreenshot(`${name}.png`, { style: '* { --gx: 0 !important; --gy: 0 !important; }' });
}

/** a page of a document, picked with the document card's "Choose a file" (its own file chooser) */
async function attach(page: Page, doc: string, n: number) {
  const card = page.locator('article').filter({ hasText: tr(`ako.doc.${doc}`) });
  const chooser = page.waitForEvent('filechooser');
  await card.getByRole('button', { name: tr('ako.file') }).click();
  await (await chooser).setFiles({ name: `${doc}.webp`, mimeType: 'image/webp', buffer: PAGE });
  await expect(card.getByText(tr('ako.photoPage'), { exact: true })).toHaveCount(n);
}
// a page to attach: any picture the server decodes (it re-encodes it); the app's own art will do
const PAGE = readFileSync(resolve(import.meta.dirname, '../public/emoji/party_popper_3d.webp'));

test('admissions: the applicant from a manager\'s link to the status page', async ({ page, qa, faults }, info) => {
  const p = await openAko(page, qa, qa.ako.link!, info, faults);
  await expect(page.getByRole('heading', { name: tr('ako.docsTitle'), exact: true })).toBeVisible();
  await shot(p, 'ako-docs');
  await page.getByRole('button', { name: tr('ako.consentOk') }).click();
  await attach(page, 'cv', 1);
  await attach(page, 'diploma', 1);
  // the file chooser's click scrolls by whatever the browser likes: one fixed place for the picture
  await page.getByText(tr('ako.firstGroup'), { exact: true }).evaluate((e) => e.scrollIntoView({ block: 'start', behavior: 'instant' }));
  await shot(p, 'ako-docs-done');
  await page.getByRole('button', { name: tr('ako.next') }).click();
  await expect(page.getByRole('heading', { name: tr('ako.slotTitle'), exact: true })).toBeVisible();
  await page.getByRole('radio', { name: /1[05]:[03]0/ }).first().click();
  await expect(page.getByText(new RegExp(tr('ako.slotPicked').replace('{when}', '.+'))).first()).toBeVisible();
  await shot(p, 'ako-slot');
  await page.getByRole('button', { name: tr('ako.next') }).click();
  await expect(page.getByRole('button', { name: tr('ako.send') })).toBeVisible();
  await shot(p, 'ako-send');
  await page.getByRole('button', { name: tr('ako.send') }).click();
  await expect(page.getByText(tr('ako.doneTitle')).or(page.getByText(tr('ako.status.sent'))).first()).toBeVisible();
  await page.clock.fastForward(4000);
  await shot(p, 'ako-status');
});

test('admissions: a sent package and the website\'s start', async ({ page, qa, faults }, info) => {
  const p = await openAko(page, qa, qa.ako.sent!, info, faults);
  await expect(page.getByText(tr('ako.status.sent')).first()).toBeVisible();
  await shot(p, 'ako-sent');
  await page.goto(qa.url + qa.ako.start!);
  await expect(page.getByText('Executive MBA').first()).toBeVisible();
  await shot(p, 'ako-start');
});

test('admissions: the managers\' desk in Studio', async ({ open }) => {
  const p = await open('Dana');
  // her first time in an office's team: its welcome first (App.svelte, OfficeWelcome)
  const hi = p.page.getByRole('button', { name: main['say.hi.teamGo'] as string });
  if (await hi.waitFor({ timeout: 6000 }).then(() => true, () => false)) await hi.click();
  await p.page.getByRole('navigation', { name: main['nav.label'] as string }).getByRole('button', { name: main['page.clubs'] as string }).click();
  await p.page.getByRole('button', { name: /^(\u0410\u041a\u041e|\u0410\u043a\u0430\u0434\u0435\u043c\u0438\u044f)/ }).first().click();
  await p.page.getByRole('button', { name: tr('studio.ako') }).click();
  const desk = p.page.getByRole('region', { name: tr('akd.title') });
  await expect(desk.getByText('\u0415\u0440\u043b\u0430\u043d \u0421\u0430\u043f\u0430\u0440\u043e\u0432')).toBeVisible();
  await shot(p, 'ako-desk');
  await desk.getByText(tr('akd.tabSlots')).click();
  await shot(p, 'ako-desk-slots');
  await desk.getByText(tr('akd.tabApps')).click();
  await desk.getByText('\u0415\u0440\u043b\u0430\u043d \u0421\u0430\u043f\u0430\u0440\u043e\u0432').click();
  const sheet = p.page.getByRole('dialog').filter({ hasText: '\u0415\u0440\u043b\u0430\u043d \u0421\u0430\u043f\u0430\u0440\u043e\u0432' });
  await expect(sheet).toBeVisible();
  await shot(p, 'ako-package', sheet);
});
