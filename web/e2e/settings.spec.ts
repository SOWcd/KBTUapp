// Settings: the language (ru -> kk -> en -> ru) changes every tab at once, with no raw key on any screen; the theme
// switches both ways and stays after a reload. Settings open in place on Profile (the gear), Menu rows pick a value.
import { test, expect, T, type App } from './fixtures';
import ru from '../src/lib/i18n/ru';
import kk from '../src/lib/i18n/kk';
import en from '../src/lib/i18n/en';

type Dict = Parameters<typeof T>[2];
const DICT = { ru, kk, en } as unknown as Record<'ru' | 'kk' | 'en', NonNullable<Dict>>;
const KEYS = new Set(Object.keys(ru));
const FULL = { ru: '\u0420\u0443\u0441\u0441\u043a\u0438\u0439', kk: '\u049a\u0430\u0437\u0430\u049b\u0448\u0430', en: 'English' } as const;
const TABS = ['tab.afisha', 'tab.forum', 'page.clubs', 'tab.profile'] as const;

/** A tab in the given language, by its own label. */
async function goTab(app: App, lang: keyof typeof DICT, key: (typeof TABS)[number]) {
  const d = DICT[lang];
  const tab = app.page.getByRole('navigation', { name: T('nav.label', {}, d), exact: true }).getByRole('button', { name: T(key, {}, d), exact: true });
  await tab.click();
  await expect(tab).toHaveAttribute('aria-current', 'page');
}

/** Opens settings in place: Profile, then the gear. */
async function openSettings(app: App, lang: keyof typeof DICT) {
  const d = DICT[lang];
  await goTab(app, lang, 'tab.profile');
  await app.page.getByRole('button', { name: T('me.settings', {}, d), exact: true }).click();
  await expect(app.page.getByRole('region', { name: T('me.settings', {}, d) })).toBeVisible();
}

/** Picks a value from a settings row's menu (Row + ui/Menu). */
async function pick(app: App, row: string, item: string) {
  await app.page.getByRole('region').getByRole('button', { name: new RegExp(`^${row}`) }).click();
  await app.page.getByRole('menu').getByRole('menuitemradio', { name: item }).click();
  await expect(app.page.getByRole('menu')).toBeHidden();
}

/** Raw dictionary keys a screen shows (a key t() didn't find would print as itself). */
async function rawKeys(app: App): Promise<string[]> {
  const text = await app.page.locator('body').innerText();
  return [...new Set(text.match(/\b[a-z][a-zA-Z]*\.[a-zA-Z][\w.]*\b/g) ?? [])].filter((k) => KEYS.has(k));
}

test('settings: every tab in ru, kk and en, no missing keys', async ({ open }, info) => {
  const dana = await open('Dana'); // runs a club: Clubs and Profile have the most on them
  const leaks: string[] = [];
  for (const lang of ['kk', 'en', 'ru'] as const) {
    const was = lang === 'kk' ? 'ru' : lang === 'en' ? 'kk' : 'en';
    await openSettings(dana, was);
    await pick(dana, T('me.guestLang', {}, DICT[was]), FULL[lang]);
    // the switch is in place: the row says the new language in the new language's own words
    await expect(dana.page.getByRole('region', { name: T('me.settings', {}, DICT[lang]) })).toBeVisible();
    await expect(dana.page.locator('html')).toHaveAttribute('lang', lang);
    await dana.step(`settings-${lang}`);
    await dana.back(); // settings close on Telegram's Back
    await expect(dana.page.getByRole('region', { name: T('me.settings', {}, DICT[lang]) })).toBeHidden();
    for (const tab of TABS) {
      await goTab(dana, lang, tab);
      await dana.step(`${lang}-${tab}`);
      expect.soft(await rawKeys(dana), `${lang} / ${tab}: raw keys on screen`).toEqual([]);
      // Russian left in the English UI (seed content is partly Russian: reported, not failed)
      if (lang === 'en') {
        const text = await dana.page.locator('body').innerText();
        for (const line of text.split('\n')) if (/\p{Script=Cyrillic}/u.test(line)) leaks.push(`${tab}: ${line.trim().slice(0, 80)}`);
      }
    }
  }
  if (leaks.length) await info.attach('cyrillic-in-en.txt', { body: [...new Set(leaks)].join('\n'), contentType: 'text/plain' });
});

test('settings: dark and light, kept after a reload', async ({ open }, info) => {
  const ali = await open('Ali');
  const html = ali.page.locator('html');
  const start = (info.project.use.colorScheme ?? 'dark') as 'dark' | 'light';
  const other = start === 'dark' ? 'light' : 'dark';
  // the app starts in Telegram's scheme (the project's theme rides in the link)
  await expect(html).toHaveAttribute('data-theme', start);
  await ali.step(`theme-${start}`);
  for (const to of [other, start]) {
    await openSettings(ali, 'ru');
    await pick(ali, T('me.guestTheme'), T(`theme.${to}`));
    await expect(html).toHaveAttribute('data-theme', to);
    await ali.back();
    await expect(ali.page.getByRole('region', { name: T('me.settings') })).toBeHidden();
    await ali.goTab(T('tab.afisha'));
    await ali.step(`theme-${to}`);
    if (to === other) {
      await ali.page.reload();
      await ali.ready();
      await expect(html).toHaveAttribute('data-theme', other);
    }
  }
});
