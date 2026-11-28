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
      // (.pane-under: the page a pushed one covers, drifted left on purpose, base.css)
      if (!r.width || !r.height || cs.visibility === 'hidden' || el.closest('[aria-hidden="true"], [inert], .pane-under')) continue;
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
async function shot(p: Phone, name: string, part?: Locator, stopped = false) {
  await p.look(name);
  expect.soft(await sticksOut(p.page), `${name}: past the screen's sides`).toEqual([]);
  if (!process.env.PW_WS) return;
  // stopped: the test holds the page's clock (Spy's countdown), and the screen has no pictures to wait for
  if (!stopped) {
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
  }
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
type Ev = { startsAt: number };
/** every event as `change` makes it (what qa.py's seed has none of) */
async function changed(p: Phone, change: (e: Ev) => object) {
  await p.page.route((u) => u.pathname === '/api/events', async (route) => {
    const r = await route.fetch();
    await route.fulfill({ response: r, json: ((await r.json()) as Ev[]).map((e) => ({ ...e, ...change(e) })) });
  });
  await p.page.reload();
  return settled(p);
}
/** every event wears the drawn poster `name` */
async function covered(p: Phone, name: keyof typeof POSTER, more: object = {}) {
  const cover = { url: `fx/${name}.svg`, thumb: `fx/${name}.svg`, w: 900, h: 1200, blur: '', color: name === 'cover' ? '#c2185b' : '#f4f1e6' };
  await p.page.route((u) => u.pathname.endsWith(`/fx/${name}.svg`), (route) => route.fulfill({ contentType: 'image/svg+xml', body: POSTER[name] }));
  return changed(p, () => ({ cover, ...more }));
}
for (const name of ['cover', 'cover-bright'] as const) test(`Afisha, the hero over a poster (${name})`, async ({ open }) => {
  await shot(await covered(await open('Ali'), name), `afisha-${name}`); // the whole first screen: the card among the circles and the list
});

/** the Open Mic's sheet, alone: the Afisha under it scrolls to the card the tap found */
async function eventSheet(p: Phone, name: string, end = false, linked = false) {
  if (!linked) await p.page.getByRole('button', { name: 'Open Mic: stand-up and music', exact: true }).first().click();
  const sheet = p.page.getByRole('dialog').filter({ hasText: 'Atrium' });
  await expect(sheet).toBeVisible();
  if (end) {
    await expect(sheet.getByRole('button', { name: tr('cm.report') })).toBeAttached(); // its last row is in
    await sheet.locator('.body').first().evaluate((b) => b.scrollTo(0, b.scrollHeight));
  }
  await shot(p, name, sheet);
}
test('an event', async ({ open }) => eventSheet(await ali(open), 'event'));
// its words lie on the picture: over a dark poster and a near-white one
for (const name of ['cover', 'cover-bright'] as const) test(`an event over a poster (${name})`, async ({ open }) => eventSheet(await covered(await open('Ali'), name), `event-${name}`));
// called off: its cover goes grey. By its link: the Afisha lists no cancelled event to tap
test('a cancelled event', async ({ open }) => eventSheet(await covered(await open('Ali', { path: '/?startapp=ev_1' }), 'cover', { status: 'cancelled' }), 'event-cancelled', false, true));
// the island with a note in it (a sign-up deadline), the sheet scrolled to its end: the last row stays clear of the island
test('an event, its end over the island', async ({ open }) => eventSheet(await changed(await open('Ali'), (e) => ({ regUntil: e.startsAt - 3600 })), 'event-end', true));

test('Clubs', async ({ open }) => {
  const p = await ali(open);
  await nav(p.page).getByRole('button', { name: tr('page.clubs'), exact: true }).click();
  await expect(p.page.getByRole('button', { name: new RegExp(`^${tr('clubs.schoolsOffices')}`) })).toBeVisible();
  await shot(p, 'clubs');
});

test('Clubs, every club in its list', async ({ open }) => {
  const p = await ali(open);
  await nav(p.page).getByRole('button', { name: tr('page.clubs'), exact: true }).click();
  await p.page.getByRole('heading', { name: new RegExp(`^${tr('clubs.allClubs')}`) }).evaluate((el) => el.closest('section')!.scrollIntoView({ block: 'start' })); // the card's top clear of the capsule (its scroll margin)
  await shot(p, 'clubs-list');
});

test('Clubs, with my own', async ({ open }) => {
  const p = await settled(await open('Dana'));
  await nav(p.page).getByRole('button', { name: tr('page.clubs'), exact: true }).click();
  await expect(p.page.getByRole('heading', { name: tr('clubs.mineTitle') })).toBeVisible();
  await shot(p, 'clubs-mine');
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

test('the campus map', async ({ open }) => {
  const p = await ali(open);
  // the map's "free now" rooms are off on this server: it answers 404 by design (client.ts mapRooms)
  p.allow(/\/api\/map\/rooms 404$/);
  p.allow(/status of 404 \(Not Found\)$/);
  await p.page.locator('[data-more]').click(); // the map opens from the Afisha's "More"
  await p.page.getByRole('menuitem', { name: tr('map.open'), exact: true }).click();
  await expect(p.page.getByRole('group', { name: tr('map.floors') })).toBeVisible();
  await shot(p, 'map');
});

test('a club\'s Studio', async ({ open }) => {
  const p = await settled(await open('Dana')); // Dana runs the Open Mic Club
  await nav(p.page).getByRole('button', { name: tr('page.clubs'), exact: true }).click();
  await p.page.getByRole('button', { name: /^Open Mic Club\b/ }).first().click();
  await expect(p.page.getByRole('region', { name: 'Open Mic Club' })).toBeVisible();
  await shot(p, 'studio');
});

test('Afisha on the smallest phone', async ({ open, page }) => {
  await page.setViewportSize({ width: 320, height: 568 }); // the one 320 px picture: what fits at 375 may not here
  await shot(await ali(open), 'afisha-320');
});

// Spy (screens/games/Spy.svelte): each state from a made-up room the test answers the API with. A real room's code,
// roles and place differ every run; its clock here is the page's own, stopped ten minutes in, so each picture has the
// same seconds left. The whole round against the real server: spy.spec.ts.
const SPY_PEOPLE = ['Ali N', 'Dana S', 'Bota A', 'Timur K', 'Aigerim B'].map((name, i) => ({ id: i + 1, name, avatar: null, founder: false }));
const SPY_PAUSE = 1795582800 + 600; // playwright.config.ts SNAP_AT, ten minutes on
type SpyRoom = { phase: string; span?: number } & Record<string, unknown>;

async function spy(p: Phone, room?: SpyRoom) {
  const { page } = p;
  if (room) await page.route('**/api/rooms**', async (route) => {
    if (route.request().method() === 'GET') return route.fulfill({ status: 204 }); // the poll: nothing moved
    const { span, ...r } = room;
    await route.fulfill({ json: { id: 7, game: 'spy', code: '0427', v: 3, me: 1, host: 1, live: false, players: SPY_PEOPLE, minutes: 5,
      now: await page.evaluate(() => Date.now() / 1000), deadline: span ? SPY_PAUSE + span - 0.5 : null, ...r } });
  });
  await nav(page).getByRole('button', { name: tr('tab.profile'), exact: true }).click();
  await page.getByRole('button', { name: tr('games.title'), exact: true }).click();
  const sheet = page.getByRole('dialog').filter({ has: page.locator('.home, .phase') });
  await expect(sheet.locator('.home')).toBeVisible();
  if (room) {
    await sheet.locator('.home .btn').click();
    await expect(sheet.locator('.phase')).toBeVisible();
    await page.clock.pauseAt(SPY_PAUSE * 1000);
  }
  return sheet;
}

test('Spy, no room yet', async ({ open }) => {
  const p = await ali(open);
  await spy(p);
  await shot(p, 'spy-home');
});

test('Spy, the host\'s lobby', async ({ open }) => {
  const p = await ali(open);
  const sheet = await spy(p, { phase: 'lobby', players: SPY_PEOPLE.slice(0, 2) });
  await expect(sheet.locator('.plate .qm')).toBeVisible();
  await shot(p, 'spy-lobby', undefined, true);
});

test('Spy, the sealed role and the role held open', async ({ open }) => {
  const p = await ali(open);
  const sheet = await spy(p, { phase: 'play', span: 272, role: 'local', location: 'library', first: 3 });
  await shot(p, 'spy-envelope', undefined, true);
  const box = (await sheet.locator('.env').boundingBox())!;
  await p.page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await p.page.mouse.down();
  await expect(sheet.locator('.env .big')).toBeVisible();
  await shot(p, 'spy-role', undefined, true);
  await p.page.mouse.up();
  await expect(sheet.locator('.env .big')).toHaveCount(0); // let go: the role is out of the page
});

test('Spy, the vote', async ({ open }) => {
  const p = await ali(open);
  await spy(p, { phase: 'vote', span: 41, role: 'local', location: 'library', voted: [1, 2, 4], myVote: 3 });
  await shot(p, 'spy-vote', undefined, true);
});

test('Spy, the caught spy names the place', async ({ open }) => {
  const p = await ali(open);
  await spy(p, { phase: 'guess', span: 22, role: 'spy', accused: 1 });
  await shot(p, 'spy-guess', undefined, true);
});

test('Spy, the reveal', async ({ open }) => {
  const p = await ali(open);
  await spy(p, { phase: 'reveal', role: 'local', location: 'library',
    result: { spy: 3, accused: 3, guess: 'coworking', winner: 'locals', why: 'wrong_guess', votes: [{ from: 1, to: 3 }, { from: 2, to: 3 }, { from: 3, to: 4 }, { from: 4, to: 3 }, { from: 5, to: 2 }] } });
  await shot(p, 'spy-reveal', undefined, true);
});
