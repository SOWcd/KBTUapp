// QR check-in on a big screen (issue #136): a laptop opens /show, the organizer (Dana) pairs it from Studio's
// «Meetings» with Telegram's QR scanner and starts the club's meeting; a member (Ali) scans the rotating QR with his
// phone (it opens the app on ci_<session>_<slot>_<sig>) and the screen counts him.
import { test, expect, type Phone } from './fixtures';
import ru from '../src/lib/i18n/ru';

const T = (k: string, vars: Record<string, string | number> = {}) =>
  ((ru as Record<string, unknown>)[k] as string).replace(/\{(\w+)\}/g, (_, v) => String(vars[v] ?? ''));

type ScreenState = { code: string; session?: number; param?: string | null; done?: number; expected?: number };

/** The launch's own moments a person waves away (the home-screen app's offer, a new award's card): out of the flow's way
 *  whenever they show up. */
async function calm(phone: Phone): Promise<Phone> {
  const p = phone.page;
  await p.addLocatorHandler(p.getByRole('button', { name: T('inst.later') }), (b) => b.click());
  // the award's own card (its kicker and its x), never another overlay's x under it
  const close = p.getByRole('button', { name: T('common.close') });
  const award = p.locator('div').filter({ has: p.getByText(T('unlock.kicker'), { exact: true }) }).filter({ has: close }).last();
  await p.addLocatorHandler(award, (a) => a.getByRole('button', { name: T('common.close') }).click());
  return phone;
}

/** What the laptop's tab shows, asked the way it asks (its secret stays in its sessionStorage). */
async function screenState(screen: Phone): Promise<ScreenState> {
  const secret = await screen.page.evaluate(() => sessionStorage.getItem('kb-show') ?? '');
  expect(secret, 'the screen has paired with the server').not.toBe('');
  const r = await screen.page.request.get(new URL('/api/screen', screen.page.url()).href, { headers: { 'X-Screen': secret } });
  expect(r.ok()).toBe(true);
  return r.json();
}

const scanPopups = (p: Phone) => p.page.evaluate(() => (window as unknown as { __tg: { events: [string][] } }).__tg.events.filter((e) => e[0] === 'web_app_open_scan_qr_popup').length);

test('a club meeting on the big screen counts a member who scans it', async ({ open }) => {
  // Ali joins the club first (through the API, before Dana's phone opens the app): the meeting expects its members
  const ali = await open('Ali');
  await ali.api('/api/orgs/1/join-requests', {});
  const desk = await open('Dana');
  const [req] = await desk.api<{ id: number }[]>('/api/orgs/1/join-requests');
  await desk.api(`/api/join-requests/${req.id}/accept`, {});
  const dana = await calm(await open('Dana'));

  // the laptop: /show in a plain browser shows its pairing QR
  const screen = await open('Bota', { path: '/show' });
  await expect(screen.page.getByRole('heading', { name: T('scr.pairTitle') })).toBeVisible();
  await screen.look('show pairing');
  const { code } = await screenState(screen);

  // Dana: Clubs > Open Mic Club (Studio) > Meetings > Connect a screen, Telegram's scanner reads the laptop's QR
  const p = dana.page;
  await p.getByRole('button', { name: T('page.clubs') }).first().click();
  await p.locator('section[aria-hidden="false"]').getByText('Open Mic Club', { exact: true }).first().click(); // the tab in view
  await p.getByRole('region', { name: 'Open Mic Club' }).getByText(T('scr.page'), { exact: true }).click();
  const connect = p.getByRole('button', { name: T('scr.connect') });
  await expect(connect).toBeVisible();
  await dana.look('meetings');
  await connect.click();
  await expect.poll(() => scanPopups(dana), { message: 'Telegram\'s QR scanner opened' }).toBeGreaterThan(0);
  await p.evaluate((data) => (window as unknown as { Telegram: { WebView: { receiveEvent: (e: string, d: unknown) => void } } })
    .Telegram.WebView.receiveEvent('qr_text_received', { data }), `https://t.me/KBTUappBot?startapp=sh_${code}`);
  await expect(p.getByText(T('scr.paired'))).toBeVisible(); // a new meeting of the club, started, on the laptop
  await expect(p.getByText(T('scr.live'), { exact: true })).toBeVisible();
  await dana.look('meeting started');

  // the laptop now shows the meeting's rotating QR: nobody yet, of the club's two members
  await expect(screen.page.getByText(T('scr.scan'))).toBeVisible();
  const count = screen.page.locator('.count');
  await expect(count).toHaveText(/^0\s*\/\s*2$/);
  await screen.look('show running');

  // Ali's phone camera reads the QR: Telegram opens the app on its start parameter
  const { param } = await screenState(screen);
  expect(param).toMatch(/^ci_\d+_\d+_[0-9a-f]{16}$/);
  const phone = await calm(await open('Ali', { path: `/?startapp=${param}` }));
  await expect(phone.page.getByText(T('ci.hDone'))).toBeVisible();
  await phone.look('checked in by the screen');

  // the screen counts him (it polls every 2 s), and so does Dana's meeting page
  await expect(count).toHaveText(/^1\s*\/\s*2$/);
  await screen.look('show counted');
  await expect(p.getByText(T('scr.ofM', { m: 2 }))).toBeVisible();
  await expect(p.locator('.big .n')).toHaveText('1');
  await dana.look('meeting counted');
});
