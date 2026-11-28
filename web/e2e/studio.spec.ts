// Studio: Dana (the Open Mic Club's Vice) makes an event with the manual editor, publishes it, and edits it; a
// student sees it on the Afisha, and the change. A co-host: another organization (made with the admin CLI, its
// President is Ali) is invited from the editor and accepts in its own Studio (logic/cohosts.py).
import { spawnSync } from 'node:child_process';
import { resolve } from 'node:path';
import { test, expect, type Phone, type Qa, reload } from './fixtures';
import main from '../src/lib/i18n/ru';
import staff from '../src/lib/i18n/staff.ru';

const ru = { ...main, ...staff };

const tr = (k: keyof typeof ru) => ru[k] as string;
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
const nav = (ph: Phone) => ph.page.getByRole('navigation', { name: tr('nav.label') });

/** the server's admin CLI on the test's database (what the app's owner does by hand: a club, a role) */
function admin(qa: Qa, args: string[]): string {
  const server = resolve(import.meta.dirname, '../../server');
  const py = process.env.QA_PYTHON || resolve(server, '.venv/bin/python');
  const r = spawnSync(py, ['-m', 'kbtu.admin', ...args], { cwd: server, encoding: 'utf8',
    env: { ...process.env, DB_PATH: qa.db, BOT_TOKEN: '1:' + 'qa'.repeat(18), TOKEN_KEY: Buffer.alloc(32, 7).toString('base64') } });
  if (r.status !== 0) throw new Error(`admin ${args.join(' ')}: ${r.stderr || r.stdout}`);
  return r.stdout;
}

/** The keyboard put away (the focused field blurred), as a phone's own Done does before a tap elsewhere. qa.py's links
 *  say iOS, where the app lifts a sheet by the keyboard's expected height while a field has the focus
 *  (lib/state/keyboard.svelte.ts); an emulated click's press blurs the field, the sheet drops, and the release lands
 *  off its button. A finger on the phone keeps its target. */
const keyboardDown = (p: Phone['page']) => p.evaluate(() => (document.activeElement as HTMLElement | null)?.blur());

/** Clubs tab -> the club's Studio */
async function studio(ph: Phone, club: string, listed = club) {
  const p = ph.page;
  await nav(ph).getByRole('button', { name: tr('page.clubs') }).click();
  await p.getByRole('button', { name: new RegExp(`^${esc(listed)}\\b`) }).first().click();
  const s = p.getByRole('region', { name: club });
  await expect(s).toBeVisible();
  return s;
}

/** Studio -> Create -> Event: the editor, one page (KRI's line on top, the fields under it) */
async function newEvent(dana: Phone) {
  const p = dana.page;
  const s = await studio(dana, 'Open Mic Club');
  await s.getByRole('button', { name: tr('studio.create'), exact: true }).click();
  await p.getByRole('menu').getByRole('menuitem', { name: tr('studio.newShort') }).click();
  await expect(p.getByRole('textbox', { name: tr('ex.name') })).toBeVisible();
}

/** Publish; the editor's check before it (no cover, no description here) is answered "as is" */
async function publish(ph: Phone) {
  const p = ph.page;
  // the action at the form's end (its island may float up too: either does the same)
  await p.getByRole('button', { name: tr('ed.publish'), exact: true }).first().click();
  const anyway = p.getByRole('button', { name: tr('ex.publishAnyway'), exact: true });
  await expect(anyway).toBeVisible();
  await ph.look('check before publishing');
  await anyway.click();
}

/** the editor's pushed page (one at a time) closes with Telegram's Back, the only Back */
async function panelDone(ph: Phone, inside: ReturnType<Phone['page']['locator']>) {
  await ph.back.press();
  await expect(inside, 'the page closed').toBeHidden(); // pages nest (More settings -> a co-host): Back pops one
}

async function place(ph: Phone, where: string) {
  const p = ph.page;
  await p.getByRole('button', { name: tr('ex.placeAdd') }).click();
  const field = p.getByRole('textbox', { name: tr('ed.place'), exact: true });
  await expect(p.getByRole('button', { name: tr('ed.placeMain'), exact: true })).toHaveAttribute('aria-pressed', 'true');
  await p.getByRole('button', { name: tr('ed.placeElsewhere'), exact: true }).click();
  await expect(p.getByRole('textbox', { name: tr('ed.placeLink'), exact: true })).toBeVisible();
  await ph.look('elsewhere place fields');
  await p.getByRole('button', { name: tr('ed.placeMain'), exact: true }).click();
  await ph.look('main building place fields');
  await field.fill(where);
  await keyboardDown(p);
  await panelDone(ph, field);
}

test('Studio: a new event by hand, published, edited, on the Afisha for a student', async ({ open }) => {
  const dana = await open('Dana');
  const p = dana.page;
  await newEvent(dana);
  await dana.look('editor');
  await p.getByRole('textbox', { name: tr('ex.name') }).fill('Poetry slam');
  await keyboardDown(p);
  await place(dana, 'Room 412');
  // the capacity is a choice, never a default (the editor asks for it)
  await p.getByRole('button', { name: new RegExp(`^${esc(tr('ed.seats'))}`) }).click();
  const unlimited = p.getByRole('radio', { name: tr('ex.unlimited'), exact: true });
  await unlimited.click();
  await panelDone(dana, unlimited);
  await dana.look('filled in');
  await publish(dana);
  // published: Studio lists it
  const s = p.getByRole('region', { name: 'Open Mic Club' });
  await expect(s.getByRole('button', { name: /Poetry slam/ })).toBeVisible();
  await dana.look('published');

  // a student sees it on the Afisha
  const ali = await open('Ali');
  await expect(ali.page.getByText('Poetry slam').first()).toBeVisible();
  await ali.look('on the Afisha');

  // Dana edits the title; the student's Afisha has the new one after a relaunch
  await s.getByRole('button', { name: /Poetry slam/ }).click();
  await p.getByRole('button', { name: tr('studio.edit'), exact: true }).first().click();
  const title = p.getByRole('textbox', { name: tr('ex.name') });
  await expect(title).toHaveValue('Poetry slam');
  await title.fill('Poetry slam: finals');
  await keyboardDown(p);
  await p.getByRole('button', { name: tr('common.save'), exact: true }).last().click();
  await expect(p.getByText('Poetry slam: finals').filter({ visible: true }).first()).toBeVisible();
  await dana.look('edited');
  await reload(ali.page);
  await expect(ali.page.getByText('Poetry slam: finals').first()).toBeVisible();
  await ali.look('edited on the Afisha');
});

test('Studio: a co-host club is invited from the editor and accepts in its own Studio', async ({ open, qa }) => {
  // a school (kind school): the picker lists clubs over the registry's size bar (logic/clubs.py CLUB_MIN, 5 people; qa.py
  // has three) and schools; Ali heads it
  admin(qa, ['org', 'debate', 'Debate Society', 'DS', 'artist_palette_3d', '--school']);
  admin(qa, ['role', '@ali', 'debate', 'president']);
  const dana = await open('Dana');
  const p = dana.page;
  await newEvent(dana);
  await p.getByRole('textbox', { name: tr('ex.name') }).fill('Chess and jokes');
  await keyboardDown(p);
  await place(dana, 'Atrium');
  await p.getByRole('button', { name: new RegExp(`^${esc(tr('ed.seats'))}`) }).click();
  const unlimited = p.getByRole('radio', { name: tr('ex.unlimited'), exact: true });
  await unlimited.click();
  await panelDone(dana, unlimited);
  await p.getByRole('button', { name: new RegExp(`^${esc(tr('ex.more'))}`) }).click(); // the co-host lives in More settings
  await p.getByRole('button', { name: new RegExp(`^${esc(tr('co.invite'))}`) }).click();
  await p.getByRole('textbox', { name: tr('co.search') }).or(p.getByPlaceholder(tr('co.search'))).first().fill('Debate');
  await keyboardDown(p);
  await p.getByRole('button', { name: 'DS', exact: true }).click(); // a school shows by its short name
  await expect(p.getByText(tr('co.afterSave'))).toBeVisible();
  await dana.look('co-host picked');
  await panelDone(dana, p.getByText(tr('co.afterSave')));
  await panelDone(dana, p.getByRole('button', { name: new RegExp(`^${esc(tr('co.invite'))}`) })); // and More settings
  await publish(dana);
  await expect(p.getByRole('region', { name: 'Open Mic Club' }).getByRole('button', { name: /Chess and jokes/ })).toBeVisible();

  // Ali, the society's President: its Studio asks; he accepts
  const ali = await open('Ali');
  const debate = await studio(ali, 'DS') // a school goes by its short name;
  const ask = debate.getByText(tr('co.ask').replace('{club}', 'Open Mic Club'), { exact: false });
  await expect(ask).toBeVisible();
  await ali.look('co-host asked');
  await debate.getByRole('button', { name: tr('co.yes'), exact: true }).click();
  // asked once more, with what it means (the event on the club's page)
  const confirm = ali.page.getByRole('alertdialog').or(ali.page.getByRole('dialog').filter({ hasText: tr('co.acceptPlain') })).last();
  await expect(confirm.getByText(tr('co.acceptPlain'))).toBeVisible();
  await ali.look('co-host confirm');
  await confirm.getByRole('button', { name: tr('co.yes'), exact: true }).click();
  await expect(ali.page.getByText(tr('co.saidYes'))).toBeVisible();
  await ali.look('co-host accepted');
  // the event is on the society's own list now
  await expect(debate.getByRole('button', { name: /Chess and jokes/ })).toBeVisible();
});
