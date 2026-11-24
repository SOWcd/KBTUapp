// Forum: a student writes a post to the channel (in qa there is no AI, so it waits: its card says so, to its author
// alone), hearts someone else's post (optimistic: the count moves in the tap's frame and stays after a reload) and
// opens its discussion, which lives in Telegram (the app hands the comments' link to the client).
import { test, expect, T, type App } from './fixtures';

/** A post's card in the feed, by a fragment of its words. */
const post = (app: App, words: string) => app.page.locator('article.post').filter({ hasText: words });

async function toForum(app: App) {
  await app.goTab(T('tab.forum'));
  await expect(app.page.locator('article.post').first()).toBeVisible();
}

test('forum: write a post, heart one, open its comments', async ({ open }) => {
  const ali = await open('Ali');
  await toForum(ali);
  await ali.step('forum');

  // write: the composer opens over the feed, the post lands at the top at once and waits for review
  await ali.page.locator('button[data-compose]').click();
  const composer = ali.page.getByRole('dialog', { name: T('fc.new') });
  await expect(composer).toBeVisible();
  const words = 'Anyone up for a morning run around the campus on Saturday? Meeting at the main entrance at 8.';
  await composer.getByRole('textbox', { name: T('fc.ph') }).fill(words);
  await ali.step('compose');
  await composer.getByRole('button', { name: T('fc.post') }).click();
  await expect(composer).toBeHidden();
  const mine = post(ali, words);
  await expect(mine).toBeVisible();
  // held (no AI in qa): "checking" while the server looks, then "waits for a moderator"; never live in the channel
  await expect(mine.getByText(new RegExp(`${T('fc.checking')}|${T('fc.human')}`))).toBeVisible();
  await expect(mine.getByRole('button', { name: new RegExp(T('fc.comments')) })).toHaveCount(0);
  await ali.step('posted-held');

  // a reload keeps it, still mine and still waiting
  await ali.page.reload();
  await ali.ready();
  await toForum(ali);
  await expect(post(ali, words).getByText(new RegExp(`${T('fc.checking')}|${T('fc.human')}`))).toBeVisible();
  await ali.step('held-after-reload');

  // heart Bota's live post (the umbrella): pressed and +1 at once, kept by the server
  const umbrella = post(ali, 'black umbrella');
  const heart = umbrella.locator('button.heart');
  await expect(heart).toHaveAttribute('aria-pressed', 'false');
  const before = Number((await heart.getAttribute('aria-label'))!.split(': ').pop());
  await heart.click();
  await expect(heart).toHaveAttribute('aria-pressed', 'true');
  await expect(heart).toHaveAttribute('aria-label', `${T('fc.appHearts')}: ${before + 1}`);
  await ali.step('hearted');
  await ali.page.waitForLoadState('networkidle');
  await ali.page.reload();
  await ali.ready();
  await toForum(ali);
  await expect(post(ali, 'black umbrella').locator('button.heart')).toHaveAttribute('aria-pressed', 'true');
  // and back off
  await post(ali, 'black umbrella').locator('button.heart').click();
  await expect(post(ali, 'black umbrella').locator('button.heart')).toHaveAttribute('aria-label', `${T('fc.appHearts')}: ${before}`);
  await ali.step('unhearted');

  // comments: the hackathon post has 4; its discussion opens in Telegram (the client gets the link)
  const hackathon = post(ali, 'hackathon');
  const talk = hackathon.getByRole('button', { name: `${T('fc.comments')}: 4` });
  await expect(talk).toBeVisible();
  await talk.click();
  await expect.poll(() => ali.page.evaluate(() => (window as unknown as { __tg: { events: string[] } }).__tg.events)).toContain('web_app_open_tg_link');
  await ali.step('comments');
});

test('forum: another student never sees a held post of another', async ({ open }) => {
  // the post from the test above is in this file's server
  const bota = await open('Bota');
  await toForum(bota);
  // nobody else sees another's held post in the feed
  await expect(post(bota, 'morning run')).toHaveCount(0);
  await bota.step('feed-without-held');
});
