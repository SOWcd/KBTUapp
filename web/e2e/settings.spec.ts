// Settings (Profile -> the gear): the language switch renders every tab in Russian, Kazakh and English with no
// missing-key text, and the theme switch turns html[data-theme]. How a missing string would show: t()
// (lib/i18n/index.svelte.ts) falls back to Russian for a word kk/en lack (their type forbids that), and a key missing in
// Russian too throws (a page error, which the harness fails on). So what could still reach the screen is a key
// itself, rendered where its text should be ("fc.heldSay"), or a hole t() left unfilled ("{name}"): both are looked
// for in every text node and label of the page, on every tab, in every language.
import { test, expect, type Phone, type Qa, reload } from './fixtures';
import type { Page } from '@playwright/test';
import ru from '../src/lib/i18n/ru';
import kk from '../src/lib/i18n/kk';
import en from '../src/lib/i18n/en';

type Lang = 'ru' | 'kk' | 'en';
const DICT = { ru, kk, en } as const;
const s = (lang: Lang, k: keyof typeof ru) => DICT[lang][k] as string;
// LANG_FULL (lib/i18n/index.svelte.ts): each language's name in the menu, in itself
const LANG_FULL: Record<Lang, string> = { ru: '\u0420\u0443\u0441\u0441\u043a\u0438\u0439', kk: '\u049a\u0430\u0437\u0430\u049b\u0448\u0430', en: 'English' };
const KEYS = Object.keys(ru);
const PREFIXES = [...new Set(KEYS.map((k) => k.split('.')[0]))];

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

const nav = (p: Page) => p.locator('nav.nav');

/** Profile -> the gear: the settings list */
async function settings(ali: Phone, lang: Lang) {
  const p = ali.page;
  await nav(p).getByRole('button', { name: s(lang, 'tab.profile') }).click();
  await p.getByRole('button', { name: s(lang, 'me.settings'), exact: true }).click();
  const list = p.getByRole('region', { name: s(lang, 'me.settings') });
  await expect(list).toBeVisible();
  await expect.poll(() => ali.back.shown(), { message: 'Telegram Back shows in settings' }).toBe(true);
  return list;
}

/** a settings row with a menu at it (language, theme): its menu's item, picked */
async function pick(p: Page, row: string, item: string) {
  await p.getByRole('region').getByRole('button').filter({ hasText: row }).click();
  const menu = p.getByRole('menu');
  await expect(menu).toBeVisible();
  await menu.getByRole('menuitemradio', { name: item }).click();
  await expect(menu).toBeHidden();
}

/** Every text node, label, placeholder and title in the page that reads like a raw key or an unfilled hole */
async function rawKeys(p: Page): Promise<string[]> {
  return p.evaluate(({ keys, prefixes }) => {
    const known = new Set(keys), pre = new Set(prefixes);
    // a key-shaped word under a key's prefix ("fc.heldSay", "say.hi.early"); a domain ("app.kbtu.kz") is not one
    const keyLike = (x: string) => known.has(x) || (/^[a-z]+(\.[A-Za-z0-9_]+)+$/.test(x) && pre.has(x.split('.')[0]) && !/\.(kz|com|ru|me|org|net|io|app)$/.test(x));
    const hole = (x: string) => /\{[a-zA-Z_]\w*\}/.test(x);
    const bad: string[] = [];
    const check = (x: string | null | undefined, where: string) => {
      const v = x?.trim();
      if (v && (keyLike(v) || hole(v))) bad.push(`${where}: ${v}`);
    };
    const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      const host = n.parentElement;
      if (host && !host.closest('script, style')) check(n.textContent, host.tagName.toLowerCase());
    }
    for (const el of document.querySelectorAll('[aria-label], [placeholder], [title], img[alt]')) {
      for (const a of ['aria-label', 'placeholder', 'title', 'alt']) check(el.getAttribute(a), `${el.tagName.toLowerCase()}[${a}]`);
    }
    return [...new Set(bad)];
  }, { keys: KEYS, prefixes: PREFIXES });
}

// each tab and something of its own that shows once it has its data (qa.py's seed)
const TABS: { tab: keyof typeof ru; shows: (lang: Lang) => string | RegExp }[] = [
  { tab: 'tab.afisha', shows: () => 'Open Mic: stand-up and music' },
  { tab: 'tab.forum', shows: () => 'Who wants to team up for the hackathon' },
  // qa's one club is below the size bar (logic/clubs.py orgs: `small`, kept for search): the tab's own rows instead
  { tab: 'page.clubs', shows: (lang) => s(lang, 'clubs.schoolsOffices') },
  { tab: 'tab.profile', shows: (lang) => s(lang, 'me.settings') },
];

async function everyTab(ali: Phone, lang: Lang) {
  const p = ali.page;
  // the nav says the tabs in this language: the language took
  for (const { tab } of TABS) await expect(nav(p).getByRole('button', { name: s(lang, tab), exact: true })).toBeVisible();
  for (const { tab, shows } of TABS) {
    const button = nav(p).getByRole('button', { name: s(lang, tab), exact: true });
    await button.click();
    await expect(button).toHaveAttribute('aria-current', 'page');
    const on = p.locator('section.tab.on');
    const want = shows(lang);
    // its text, or a button named so (Profile's gear has only its label)
    await expect(on.getByText(want).or(on.getByRole('button', { name: want })).first()).toBeVisible();
    await ali.look(`${lang} ${tab}`);
    expect(await rawKeys(p), `${lang}, ${tab}: text that reads like a raw key or an unfilled hole`).toEqual([]);
  }
}

for (const lang of ['ru', 'kk', 'en'] as const) {
  test(`every tab in ${lang} shows its words, never a raw key`, async ({ page, qa, open }) => {
    const ali = await openAli(page, qa, open);
    const p = ali.page;
    await expect(p.locator('html')).toHaveAttribute('lang', 'ru'); // qa's people's Telegram is in Russian
    await settings(ali, 'ru');
    await ali.look('settings ru');
    if (lang !== 'ru') {
      await pick(p, s('ru', 'me.guestLang'), LANG_FULL[lang]);
      // the switch lands with no reload: the list says its words in the new language at once
      await expect(p.getByRole('region', { name: s(lang, 'me.settings') })).toBeVisible();
      await expect(p.locator('html')).toHaveAttribute('lang', lang);
      await expect(p.getByRole('region').getByRole('button').filter({ hasText: s(lang, 'me.guestLang') })).toContainText(LANG_FULL[lang]);
      await ali.look(`settings ${lang}`);
      expect(await rawKeys(p), `${lang}, settings`).toEqual([]);
      // the server keeps it too, so the bot writes in it
      await expect.poll(async () => (await ali.api<{ settings: { lang: string } }>('/api/me')).settings.lang).toBe(lang);
    } else {
      expect(await rawKeys(p), 'ru, settings').toEqual([]);
    }
    await ali.back.press();
    await expect(p.getByRole('region', { name: s(lang, 'me.settings') })).toBeHidden();
    await expect.poll(() => ali.back.shown()).toBe(false);
    await everyTab(ali, lang);

    if (lang !== 'ru') {
      // a relaunch keeps the pick, whatever Telegram's own language says
      await reload(p);
      await expect(p.locator('html')).toHaveAttribute('lang', lang);
      await expect(nav(p).getByRole('button', { name: s(lang, 'tab.afisha'), exact: true })).toBeVisible();
      expect(await rawKeys(p), `${lang}, after a relaunch`).toEqual([]);
    }
  });
}

test('the theme switch in settings turns the whole app and stays', async ({ page, qa, open }, info) => {
  const from = (info.project.metadata?.theme as 'dark' | 'light') ?? 'dark';
  const to = from === 'dark' ? 'light' : 'dark';
  const ali = await openAli(page, qa, open);
  const p = ali.page;
  const html = p.locator('html');
  await expect(html).toHaveAttribute('data-theme', from); // Telegram's own scheme until a pick
  await settings(ali, 'ru');
  const row = p.getByRole('region').getByRole('button').filter({ hasText: s('ru', 'me.guestTheme') });
  await expect(row).toContainText(s('ru', `theme.${from}`));

  await pick(p, s('ru', 'me.guestTheme'), s('ru', `theme.${to}`));
  await expect(html).toHaveAttribute('data-theme', to);
  await expect(row).toContainText(s('ru', `theme.${to}`));
  const bg = await p.evaluate(() => getComputedStyle(document.body).backgroundColor);
  await ali.look(`theme ${to}`);
  // the server keeps it too
  await expect.poll(async () => (await ali.api<{ settings: { theme: string } }>('/api/me')).settings.theme).toBe(to);

  // a relaunch keeps the pick over Telegram's scheme (the link still passes the old one)
  await reload(p);
  await expect(html).toHaveAttribute('data-theme', to);
  expect(await p.evaluate(() => getComputedStyle(document.body).backgroundColor)).toBe(bg);
  await ali.look(`theme ${to} after a relaunch`);

  // and back
  await settings(ali, 'ru');
  await pick(p, s('ru', 'me.guestTheme'), s('ru', `theme.${from}`));
  await expect(html).toHaveAttribute('data-theme', from);
  await expect(p.getByRole('region').getByRole('button').filter({ hasText: s('ru', 'me.guestTheme') })).toContainText(s('ru', `theme.${from}`));
  expect(await p.evaluate(() => getComputedStyle(document.body).backgroundColor)).not.toBe(bg);
  await ali.look(`theme ${from} again`);
});
