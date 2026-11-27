// The key screens as pictures, at 375 px in both themes (the snap-* projects): qa.py's people on a fixed clock,
// motion reduced, each compared with its baseline in e2e/snapshots/ by a few pixels at most. Bugs a flow can't see
// reach phones otherwise: a glass oval over a footer, a card past the screen's edges, a badge at the wrong size.
// Pixels differ between machines (fonts, the GPU), so the pictures are taken only by Chromium from Playwright's Linux
// image (`npm run e2e:snap`: e2e/linux.sh sets PW_WS); without it a test still checks the layout (fixtures.ts `look`: nothing
// wider than the screen, no text out of its button). Accepting a change: e2e/README.md.
import type { Locator, Page } from '@playwright/test';
import { test, expect, settled, type Phone } from './fixtures';
import ru from '../src/lib/i18n/ru';

const tr = (k: keyof typeof ru) => ru[k] as string;
const nav = (page: Page) => page.getByRole('navigation', { name: tr('nav.label') });

/** What runs past the screen's sides: an element wider than the screen, or past an edge, that no sideways scroller (a
 *  carousel) or clip box inside the screen's margins keeps in. The app's pages clip at the screen's own edges, so a card
 *  running past both is cut there without scrolling the page, and `look` alone wouldn't see it. */
function sticksOut(page: Page): Promise<string[]> {
  return page.evaluate(() => {
    const vw = document.documentElement.clientWidth, out: string[] = [];

    for (const el of document.body.querySelectorAll<HTMLElement>('*')) {
      const r = el.getBoundingClientRect(), cs = getComputedStyle(el);
      if (!r.width || !r.height || cs.visibility === 'hidden' || el.closest('[aria-hidden="true"], [inert]')) continue;
      if (r.left >= -1 && r.right <= vw + 1) continue;
      let clipped = false;
      for (let a = el.parentElement; a && a !== document.body; a = a.parentElement) {
        const ox = getComputedStyle(a).overflowX, ar = a.getBoundingClientRect();
        if (ox === 'auto' || ox === 'scroll' || (ox !== 'visible' && ar.left >= 1 && ar.right <= vw - 1)) { clipped = true; break; }
      }
      if (clipped) continue;
      const name = (el.getAttribute('aria-label') || el.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 30);
      out.push(`${el.tagName.toLowerCase()}.${[...el.classList].join('.')} "${name}" ${Math.round(r.left)}..${Math.round(r.right)}`);
    }
    return out;
  });
}

/** the screen checked, then (in the Linux browser) compared with its picture: the whole screen, or only `part` */
async function shot(p: Phone, name: string, part?: Locator) {
  await p.look(name);
  expect.soft(await sticksOut(p.page), `${name}: past the screen's sides`).toEqual([]);
  if (!process.env.PW_WS) return;
  // the app's own timers run out first: the capsule, rested, shows the live class instead of the tab's name. A glyph
  // still loading or a transition's last frame: toHaveScreenshot waits for two frames alike.
  await p.page.clock.fastForward(5000);
  // every picture in, <img> and CSS (the badge's art comes a moment after its card), as Hero.svelte waits for a lanyard
  await p.page.evaluate(() => {
    const urls = new Set<string>();
    for (const el of document.querySelectorAll('*')) for (const ps of [null, '::before', '::after'])
      for (const m of getComputedStyle(el, ps).backgroundImage.matchAll(/url\("?([^")]+)"?\)/g)) urls.add(m[1]);
    const css = [...urls].map((u) => { const im = new Image(); im.src = u; return im; });
    // a lazy <img> out of view never decodes: each wait has its ceiling
    const decoded = (i: HTMLImageElement) => Promise.race([i.decode().catch(() => {}), new Promise((r) => setTimeout(r, 3000))]);
    return Promise.all([...document.images, ...css].map(decoded));
  });
  // the light on the glass and the badge's sheen (glass.ts: --gx/--gy, the phone's tilt or a slow drift) held still
  await expect(part ?? p.page).toHaveScreenshot(`${name}.png`, { style: '* { --gx: 0 !important; --gy: 0 !important; }' });
}

const ali = async (open: (who: 'Ali') => Promise<Phone>) => settled(await open('Ali'));

test('Afisha, the top', async ({ open }) => {
  await shot(await ali(open), 'afisha');
});

// qa.py's events have no cover: one drawn here is put on them, so the hero's glass is seen over a picture. Two posters:
// a dark colourful one, and a near-white one (white words on the slab must hold on it)
const POSTER = {
  cover: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 1200"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#ff5a3c"/><stop offset=".55" stop-color="#c2185b"/><stop offset="1" stop-color="#2a0f4f"/></linearGradient></defs>
    <rect width="900" height="1200" fill="url(#g)"/><circle cx="640" cy="330" r="250" fill="#ffd23f"/><circle cx="640" cy="330" r="250" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="40"/>
    <rect x="-80" y="760" width="1100" height="90" fill="#fff" fill-opacity=".9" transform="rotate(-9 450 800)"/>
    <text x="70" y="1010" font-family="sans-serif" font-weight="800" font-size="170" fill="#fff">OPEN MIC</text><text x="76" y="1090" font-family="sans-serif" font-weight="600" font-size="44" letter-spacing="8" fill="#fff">STAND-UP AND MUSIC</text></svg>`,
  'cover-bright': `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 900 1200"><rect width="900" height="1200" fill="#fbfaf5"/><circle cx="250" cy="300" r="170" fill="#ffe45c"/>
    <rect x="-80" y="520" width="1100" height="70" fill="#e5322d" transform="rotate(-14 450 560)"/>
    <text x="60" y="900" font-family="sans-serif" font-weight="800" font-size="210" fill="#111">GAMES</text><text x="64" y="1060" font-family="sans-serif" font-weight="800" font-size="150" fill="#111">NIGHT</text>
    <text x="68" y="1130" font-family="sans-serif" font-weight="600" font-size="40" letter-spacing="8" fill="#555">BOARD GAMES · ROOM 305</text></svg>`,
};
for (const [name, svg] of Object.entries(POSTER)) test(`Afisha, the hero over a poster (${name})`, async ({ open }) => {
  const p = await open('Ali');
  const cover = { url: `fx/${name}.svg`, thumb: `fx/${name}.svg`, w: 900, h: 1200, blur: '', color: name === 'cover' ? '#c2185b' : '#f4f1e6' };
  await p.page.route((u) => u.pathname.endsWith(`/fx/${name}.svg`), (route) => route.fulfill({ contentType: 'image/svg+xml', body: svg }));
  await p.page.route((u) => u.pathname === '/api/events', async (route) => {
    const r = await route.fetch();
    await route.fulfill({ response: r, json: ((await r.json()) as object[]).map((e) => ({ ...e, cover })) });
  });
  await p.page.reload();
  await settled(p);
  await shot(p, `afisha-${name}`); // the whole first screen: the card among the circles and the list
});

// TEMP (r4): the other two directions, for the owner's pick
for (const v of [2, 3]) for (const name of ['cover', 'none']) test(`Afisha, direction ${v} (${name})`, async ({ open }) => {
  const p = await open('Ali');
  const cover = name === 'none' ? null : { url: 'fx/cover.svg', thumb: 'fx/cover.svg', w: 900, h: 1200, blur: '', color: '#c2185b' };
  await p.page.route((u) => u.pathname.endsWith('/fx/cover.svg'), (route) => route.fulfill({ contentType: 'image/svg+xml', body: POSTER.cover }));
  await p.page.route((u) => u.pathname === '/api/events', async (route) => {
    const r = await route.fetch();
    await route.fulfill({ response: r, json: ((await r.json()) as object[]).map((e) => (cover ? { ...e, cover } : e)) });
  });
  await p.page.evaluate((n) => localStorage.setItem('kbtu.afv', String(n)), v);
  await p.page.reload();
  await settled(p);
  await shot(p, `afisha-alt${v}-${name}`);
});

test('an event', async ({ open }) => {
  const p = await ali(open);
  await p.page.getByRole('button', { name: 'Open Mic: stand-up and music', exact: true }).first().click();
  const sheet = p.page.getByRole('dialog').filter({ hasText: 'Atrium' });
  await expect(sheet).toBeVisible();
  await shot(p, 'event', sheet); // the sheet alone: the Afisha under it scrolls to the card the tap found
});

test('Clubs', async ({ open }) => {
  const p = await ali(open);
  await nav(p.page).getByRole('button', { name: tr('page.clubs'), exact: true }).click();
  await expect(p.page.getByRole('button', { name: new RegExp(`^${tr('clubs.schoolsOffices')}`) })).toBeVisible();
  await shot(p, 'clubs');
});

test('Forum', async ({ open }) => {
  const p = await ali(open);
  await nav(p.page).getByRole('button', { name: tr('tab.forum'), exact: true }).click();
  await expect(p.page.locator('section[aria-hidden="false"]').getByRole('article').first()).toBeVisible();
  await shot(p, 'forum');
});

test('Profile with the badge', async ({ open }) => {
  const p = await ali(open);
  await nav(p.page).getByRole('button', { name: tr('tab.profile'), exact: true }).click();
  await expect(p.page.getByRole('button', { name: tr('look.photo'), exact: true })).toBeVisible();
  await shot(p, 'profile');
});

test('the anthem', async ({ open }) => {
  const p = await ali(open);
  await nav(p.page).getByRole('button', { name: tr('tab.profile'), exact: true }).click();
  await p.page.getByRole('button', { name: tr('anthem.title') }).click();
  const sheet = p.page.getByRole('dialog', { name: tr('anthem.title') });
  await expect(sheet).toBeVisible();
  await shot(p, 'anthem', sheet); // the sheet alone: the Profile dimmed above it settles at its own pace (a friend's face)
});

test('the assistant\'s welcome', async ({ open }) => {
  const p = await ali(open);
  await p.page.getByRole('button', { name: tr('as.askAi'), exact: true }).click();
  await expect(p.page.getByRole('dialog', { name: tr('as.title') })).toBeVisible();
  await shot(p, 'assistant');
});
