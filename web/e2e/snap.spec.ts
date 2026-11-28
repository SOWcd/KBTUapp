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

test('Spy, the role held open', async ({ open }) => {
  const p = await ali(open);
  const sheet = await spy(p, { phase: 'play', span: 272, role: 'local', location: 'library', first: 3 });
  await p.look('spy-cover');
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
