// A club's recruitment round (server casting.py): the club opens it, a student finds the club and applies, the club's
// casting team sees the application in Studio. qa.py's club has no President: Dana is its Vice, and a Vice has the
// "casting" right by level (logic/core.py RIGHTS), so she is the club's team here.
import type { APIRequestContext } from '@playwright/test';
import { test, expect, type Phone, type Qa, type Who, reload } from './fixtures';
import ru from '../src/lib/i18n/ru';

const tr = (k: keyof typeof ru) => ru[k] as string;
/** the text of a key up to its first {hole}: for strings with a date in them */
const head = (k: keyof typeof ru) => tr(k).split('{')[0];
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/** The API as someone, from another device (no page): what the club does before the student opens the app. */
function device(qa: Qa, request: APIRequestContext, who: Who) {
  const init = new URLSearchParams(qa.link(who).split('#')[1]).get('tgWebAppData')!;
  return async <T = unknown>(path: string, body?: unknown): Promise<T> => {
    const r = await request.fetch(`${qa.url}${path}`, {
      method: body === undefined ? 'GET' : 'POST', headers: { Authorization: `tma ${init}`, 'Content-Type': 'application/json' },
      data: body === undefined ? undefined : JSON.stringify(body),
    });
    if (!r.ok()) throw new Error(`${path}: ${r.status()} ${await r.text()}`);
    return (await r.json()) as T;
  };
}

/** The launch's own moments (a new award, the home-screen offer) are other flows: seen once, then the app reopened. */
async function calm(ph: Phone) {
  const me = await ph.api<{ unlocked?: { code: string; level: number }[] }>('/api/me');
  for (const u of me.unlocked ?? []) if (u.code !== 'first50') await ph.api('/api/me/unlocked', u);
  await ph.page.evaluate(() => localStorage.setItem('kb-install', '1'));
  await reload(ph.page);
  await expect(ph.page.getByRole('navigation', { name: tr('nav.label') })).toBeVisible();
}

const ROUND = { title: 'Spring casting', departments: [], questions: [{ kind: 'short', text: 'Why us?', required: true }] };
const roundBody = () => ({ ...ROUND, closesAt: Math.floor(Date.now() / 1000) + 7 * 86400 });

test('a student applies to a club round and its team sees it in Studio', async ({ open, qa, request }) => {
  // the club opened its round earlier (from Dana's phone, before anyone here opens the app)
  await device(qa, request, 'Dana')('/api/orgs/1/round', roundBody());

  const ali = await open('Ali');
  await calm(ali);
  const p = ali.page;
  // the club from one of its events on the Afisha
  await p.getByRole('button', { name: 'Board games night' }).first().click();
  await p.getByRole('dialog').last().getByRole('button', { name: 'Open Mic Club' }).click();
  const club = p.getByRole('dialog').filter({ has: p.getByRole('heading', { name: /Open Mic Club/ }) });
  await expect(club.getByText(new RegExp('^' + esc(head('cast.recruiting'))))).toBeVisible();
  expect(await ali.back.shown()).toBe(true);
  await ali.look('club with an open round');

  await club.getByRole('button', { name: tr('join.apply'), exact: true }).click();
  const form = p.getByRole('dialog').filter({ has: p.getByRole('heading', { name: ROUND.title }) });
  await expect(form.getByText('Why us?')).toBeVisible();
  await ali.look('round form');
  // sending without the required answer: refused in place, nothing sent
  await form.getByRole('button', { name: tr('cast.send') }).click();
  await expect(form.getByText(tr('ed.need'))).toBeVisible();
  await form.getByLabel('Why us?').fill('I host the open mic at my dorm');
  await form.getByRole('button', { name: tr('cast.send') }).click();
  await expect(p.getByRole('status').filter({ hasText: tr('cast.sent') })).toBeVisible();
  await expect(form.getByText(tr('cast.botTells'))).toBeVisible();
  await expect(form.getByRole('button', { name: tr('cast.change') })).toBeVisible();
  await ali.look('applied');

  // Back: the club again, now marked applied
  await ali.back.press();
  await expect(form).toBeHidden();
  await expect(club.getByRole('button', { name: tr('cast.applied'), exact: true })).toBeVisible();
  await ali.look('club after applying');

  // the club's team: Studio's Recruiting row counts the new one; the board has it with the answer
  const dana = await open('Dana');
  await calm(dana);
  const d = dana.page;
  await d.getByRole('navigation', { name: tr('nav.label') }).getByRole('button', { name: tr('page.clubs') }).click();
  await d.getByRole('button', { name: /Open Mic Club/ }).first().click();
  const studio = d.getByRole('region', { name: 'Open Mic Club' });
  const recruit = studio.getByRole('button', { name: new RegExp(`^${esc(tr('cast.card'))} 1$`) });
  await expect(recruit).toBeVisible();
  await dana.look('studio with a new application');
  await recruit.click();
  const board = d.getByRole('dialog', { name: ROUND.title });
  const row = board.getByRole('button', { name: /Nurlanov Ali/ });
  await expect(row).toBeVisible();
  await dana.look('round board');
  await row.click();
  await expect(board.getByText('I host the open mic at my dorm')).toBeVisible();
  await expect(board.getByText('Why us?')).toBeVisible();
  await dana.look('application');
});

// A round shows on the club at once after the club opens it: the clubs list's cached part (logic/core.py shared(), 15 s)
// is keyed by a row that carries the open round (logic/clubs.py listed()), so a student's Apply goes to the round.
test('a round shows on the club at once after the club opens it', async ({ open }) => {
  const dana = await open('Dana'); // her start caches the clubs list
  await dana.api('/api/orgs/1/round', roundBody());
  const ali = await open('Ali');
  await calm(ali);
  const p = ali.page;
  await p.getByRole('button', { name: 'Board games night' }).first().click();
  await p.getByRole('dialog').last().getByRole('button', { name: 'Open Mic Club' }).click();
  const club = p.getByRole('dialog').filter({ has: p.getByRole('heading', { name: /Open Mic Club/ }) });
  await expect(club.getByText(new RegExp('^' + esc(head('cast.recruiting')))), 'the round, within the cache\'s 15 s').toBeVisible({ timeout: 3000 });
});
