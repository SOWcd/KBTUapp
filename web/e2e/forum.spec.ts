// The Forum tab (FORUM_CHANNEL on in qa.py): writing a post, the way to a post's comments (they live in Telegram), the
// app's own heart. In qa there is no AI model (no --fake-ai) and the bot's sends are off: a new post is held for a
// moderator, and nothing about Telegram may show as an error to the person.
import { test, expect, type Phone, type Qa, reload } from './fixtures';
import type { Page } from '@playwright/test';
import ru from '../src/lib/i18n/ru';

const s = (k: keyof typeof ru) => ru[k] as string; // qa's people are Russian-speaking: the app opens in Russian
const POST = 'Does anyone have a spare laptop charger in the library today? Mine died before the exam.';

/** Ali, qa's student, with the launch's moments out of the way: a few seconds in they open over whatever is on
 *  screen, one at a time (lib/moments.ts): his new award (qa.py checked him in yesterday), then the home-screen offer.
 *  This phone has seen both: the award marked celebrated on the server (as the app does once it's shown), the offer
 *  marked shown in its storage. */
async function openAli(page: Page, qa: Qa, open: (who: 'Ali') => Promise<Phone>): Promise<Phone> {
  const init = new URLSearchParams(qa.link('Ali').split('#')[1]).get('tgWebAppData')!;
  const call = (path: string, body?: unknown) => page.request.fetch(`${qa.url}/api${path}`, {
    method: body ? 'POST' : 'GET', headers: { Authorization: `tma ${init}`, 'Content-Type': 'application/json' }, data: body ? JSON.stringify(body) : undefined });
  const me = await (await call('/me?reportLog=false')).json() as { unlocked: { code: string; level: number }[] };
  for (const u of me.unlocked) expect((await call('/me/unlocked', u)).ok()).toBe(true);
  await page.addInitScript(() => { try { localStorage.setItem('kb-install', '1'); } catch { /* storage blocked */ } });
  return open('Ali');
}

async function forum(phone: Phone): Promise<Page> {
  const p = phone.page;
  await p.getByRole('navigation', { name: s('nav.label') }).getByRole('button', { name: s('tab.forum') }).click();
  await expect(p.locator('article', { hasText: 'Who wants to team up for the hackathon' })).toBeVisible();
  return p;
}

/** what the app asked Telegram to do, by event type */
const asked = (p: Page, type: string) => p.evaluate((ty) => (window as unknown as { __tg: { events: [string, unknown][] } }).__tg.events
  .filter(([e]) => e === ty).map(([, d]) => d), type);

/** write a post through the composer and send it */
async function write(ali: Phone, p: Page, text: string) {
  await p.locator('[data-compose]').click();
  const dialog = p.getByRole('dialog', { name: s('fc.new') });
  await expect(dialog).toBeVisible();
  await expect.poll(() => ali.back.shown(), { message: 'Telegram Back shows while writing' }).toBe(true);
  await dialog.getByRole('textbox', { name: s('fc.ph') }).fill(text);
  await ali.look('compose filled');
  await dialog.getByRole('button', { name: s('fc.post') }).click();
  await expect(dialog).toBeHidden();
}

test('a new post is held for a moderator and says so, with no error', async ({ page, qa, open }) => {
  const ali = await openAli(page, qa, open);
  const p = await forum(ali);
  await ali.look('forum feed');

  // Back closes the window and keeps the words
  await p.locator('[data-compose]').click();
  const dialog = p.getByRole('dialog', { name: s('fc.new') });
  await dialog.getByRole('textbox', { name: s('fc.ph') }).fill('A draft');
  await ali.back.press();
  await expect(dialog).toBeHidden();
  await expect.poll(() => ali.back.shown()).toBe(false);
  await p.locator('[data-compose]').click();
  await expect(dialog.getByRole('textbox', { name: s('fc.ph') })).toHaveValue('A draft');
  await ali.back.press();
  await expect(dialog).toBeHidden();

  await write(ali, p, POST);
  // no AI here: the server holds it for a person, and the app says so once
  await expect(p.getByRole('status').filter({ hasText: s('fc.heldSay') })).toBeVisible();
  await expect(p.getByText(s('common.error'))).toHaveCount(0);
  const mine = p.locator('article', { hasText: POST });
  await expect(mine).toBeVisible();
  await expect(p.locator('article').first(), 'my post is at the top').toContainText(POST);
  // held: no heart, no comments, no Telegram link on it yet
  await expect(mine.getByRole('button', { name: new RegExp(`^${s('fc.appHearts')}`) })).toHaveCount(0);
  await expect(mine.getByRole('button', { name: new RegExp(`${s('fc.comments')}$`) })).toHaveCount(0);
  await ali.look('post held');

  const posts = await ali.api<{ body: string; status: string }[]>('/api/forum-posts');
  expect(posts.find((x) => x.body === POST)?.status).toBe('held');
  expect(await asked(p, 'web_app_open_tg_link'), 'nothing opened in Telegram').toEqual([]);

  // a reload keeps it at the top of my feed (the server's copy, not the stand-in)
  await reload(p);
  await forum(ali);
  await expect(p.locator('article', { hasText: POST })).toBeVisible();
  await expect(p.getByText(s('common.error'))).toHaveCount(0);
  await ali.look('post held after reload');
});

// A held post the AI never answered about reads "Waiting for a moderator" to its author once the look is over (60 s,
// fchannel.CHECK_OVER): the server test test_fchannel.py covers it with a moved clock, which a browser can't.

test("a post's comments open in Telegram", async ({ page, qa, open }) => {
  const ali = await openAli(page, qa, open);
  const p = await forum(ali);
  const post = p.locator('article', { hasText: 'Who wants to team up for the hackathon' });
  // who commented (faces), Telegram's reactions read-only, then the one button to the talk with its count
  await expect(post.getByRole('img', { name: new RegExp(`^${s('fc.reactions')}: .*7`) })).toBeVisible();
  const talk = post.getByRole('button', { name: `${s('fc.discuss')} 4 · ${s('fc.comments')}` }); // what it shows, then what it is
  await talk.scrollIntoViewIfNeeded();
  await ali.look('post with comments');
  const url = p.url();
  await talk.click();
  // Telegram opens the channel post's thread (the qa post is message 101); the app itself stays where it was
  await expect.poll(() => asked(p, 'web_app_open_tg_link')).toEqual([{ path_full: expect.stringMatching(/^\/KBTUappForum\/101(\?comment=\d+)?$/) }]);
  expect(p.url()).toBe(url);
  await expect(post).toBeVisible();
  await expect(p.getByText(s('common.error'))).toHaveCount(0);
});

test('a heart on a post answers at once and the server keeps it', async ({ page, qa, open }) => {
  const ali = await openAli(page, qa, open);
  const p = await forum(ali);
  const post = p.locator('article', { hasText: 'Lost a black umbrella' });
  const heart = post.getByRole('button', { name: new RegExp(`^${s('fc.appHearts')}: `) });
  await heart.scrollIntoViewIfNeeded();
  await expect(heart).toHaveAttribute('aria-pressed', 'false');
  await expect(heart).toHaveAccessibleName(`${s('fc.appHearts')}: 0`);
  await heart.click();
  await expect(heart).toHaveAttribute('aria-pressed', 'true');
  await expect(heart).toHaveAccessibleName(`${s('fc.appHearts')}: 1`);
  await expect(heart).toContainText('1');
  await ali.look('hearted');

  type Feed = { posts: { id: number; hearts: number; hearted: boolean }[] };
  const mine = async () => (await ali.api<Feed>('/api/forum-posts/feed/page?order=new')).posts.find((x) => x.id === 3);
  await expect.poll(mine).toMatchObject({ hearts: 1, hearted: true });

  // another person gets the count, not my pick (asked of the server: Dana's own phone opens with the home-screen
  // offer over it, whose close trips a WebKit error, see the report)
  const dana = await open('Dana');
  const theirs = (await dana.api<Feed>('/api/forum-posts/feed/page?order=new')).posts.find((x) => x.id === 3);
  expect(theirs).toMatchObject({ hearts: 1, hearted: false });

  // and a second tap takes it back
  await heart.click();
  await expect(heart).toHaveAttribute('aria-pressed', 'false');
  await expect(heart).toHaveAccessibleName(`${s('fc.appHearts')}: 0`);
  await expect.poll(mine).toMatchObject({ hearts: 0, hearted: false });
  await ali.look('heart taken back');
});
