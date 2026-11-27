// The door (issue #136): the organizer (Dana) opens an event's door screen from Studio, scans a ticket with Telegram's
// QR scanner, answers the 18+ question on an age-checked event, lets a walk-in in by their badge, and the attendee
// (Ali) sees "checked in" on their ticket.
import { spawnSync } from 'node:child_process';
import { existsSync } from 'node:fs';
import { join, resolve } from 'node:path';
import { test, expect, type Phone, type Qa } from './fixtures';
import ru from '../src/lib/i18n/ru';

const T = (k: string, vars: Record<string, string | number> = {}) =>
  ((ru as Record<string, unknown>)[k] as string).replace(/\{(\w+)\}/g, (_, v) => String(vars[v] ?? ''));
const before = (k: string) => T(k).split('{')[0]; // a string's fixed start, before its first {hole}

/** The launch's own moments a person waves away (the home-screen app's offer, a new award's card): out of the flow's way
 *  whenever they show up. */
async function calm(phone: Phone): Promise<Phone> {
  const p = phone.page;
  await p.addLocatorHandler(p.getByRole('button', { name: T('inst.later') }), (b) => b.click());
  // the award's own card (its kicker): Back closes it, as it closes every full-screen overlay
  await p.addLocatorHandler(p.getByText(T('unlock.kicker'), { exact: true }).first(), () => phone.back.press());
  return phone;
}

type Ev = { id: number; title: string; description?: string; place: string; seats: number | null; emoji: string; color: string; visibility?: string;
  my?: { ticketCode: string | null; checkedInAt: number | null } | null };
const now = () => Math.floor(Date.now() / 1000);

/** The event editor's save (PATCH), moving the event to have started a minute ago: its door is open, it's "today". */
async function startNow(org: Phone, id: number): Promise<void> {
  const e = await org.api<Ev>(`/api/events/${id}`);
  await org.api(`/api/events/${id}`, { title: e.title, description: e.description ?? '', place: e.place, startsAt: now() - 60, endsAt: now() + 3 * 3600,
    seats: e.seats, emoji: e.emoji, color: e.color, visibility: e.visibility ?? 'public' }, 'PATCH');
}

/** A free public event of the Open Mic club, published (sign-up is open until it starts). */
async function freeEvent(dana: Phone, title: string): Promise<number> {
  const body = { title, place: 'Room 101', startsAt: now() + 7200, endsAt: now() + 4 * 3600, seats: null, emoji: 'popcorn_3d', color: '#2B4C9A', visibility: 'public' };
  const { id } = await dana.api<Ev>('/api/orgs/1/events', body);
  await dana.api(`/api/events/${id}/publish`, {});
  return id;
}

/** The operator's CLI (server/kbtu/admin.py) on this test's database: what the creator does by hand (guest lists). */
function admin(qa: Qa, args: string[], input = ''): string {
  const server = resolve(import.meta.dirname, '../../server');
  const py = process.env.QA_PYTHON || (existsSync(join(server, '.venv/bin/python')) ? join(server, '.venv/bin/python') : 'python3');
  const r = spawnSync(py, ['-m', 'kbtu.admin', ...args], { cwd: server, input, encoding: 'utf8',
    env: { ...process.env, DB_PATH: qa.db, BOT_TOKEN: '1:' + 'qa'.repeat(18), TOKEN_KEY: Buffer.alloc(32, 7).toString('base64') } });
  if (r.status !== 0) throw new Error(`admin ${args.join(' ')}: ${r.stderr || r.stdout}`);
  return r.stdout;
}

/** Studio > the event > «Mark» (the door screen) > «Scanner»; the camera is refused here, so Telegram's scanner opens. */
async function openScanner(dana: Phone, title: string): Promise<void> {
  const p = dana.page;
  await p.getByRole('button', { name: T('page.clubs') }).first().click();
  await p.locator('section[aria-hidden="false"]').getByText('Open Mic Club', { exact: true }).first().click(); // the tab in view
  const studio = p.getByRole('region', { name: 'Open Mic Club' });
  await studio.getByText(title, { exact: true }).first().click();
  const markBtn = p.getByRole('button', { name: T('mk.title') }).filter({ visible: true }).last();
  await expect(p.getByText(T('mg.title'), { exact: true }).filter({ visible: true }).first()).toBeVisible();
  await dana.look('event in Studio');
  await markBtn.click();
  await p.getByRole('radio', { name: T('studio.scanner') }).click();
  await expect(p.getByRole('button', { name: T('scan.open') })).toBeVisible();
  await dana.look('door scanner');
}

const scanPopups = (p: Phone) => p.page.evaluate(() => (window as unknown as { __tg: { events: [string][] } }).__tg.events.filter((e) => e[0] === 'web_app_open_scan_qr_popup').length);

const answered = new WeakMap<Phone, number>(); // Telegram scanner openings a scan has already gone to

/** Telegram's QR scanner: open it (or wait for it to come back by itself) and read `text` with it. */
async function scan(dana: Phone, text: string, tap = true): Promise<void> {
  if (tap) await dana.page.getByRole('button', { name: T('scan.open') }).click();
  await expect.poll(() => scanPopups(dana), { message: 'Telegram\'s QR scanner opened' }).toBeGreaterThan(answered.get(dana) ?? 0);
  answered.set(dana, await scanPopups(dana));
  await dana.page.evaluate((data) => (window as unknown as { Telegram: { WebView: { receiveEvent: (e: string, d: unknown) => void } } })
    .Telegram.WebView.receiveEvent('qr_text_received', { data }), text);
}

test('the door scans a ticket and the attendee sees it on their ticket', async ({ open }) => {
  const desk = await open('Dana'); // set-up through the API, before Dana's phone opens the app (it reads Studio as it opens)
  const ali = await open('Ali');
  const id = await freeEvent(desk, 'Door night');
  await ali.api(`/api/events/${id}/registration`, {});
  await startNow(desk, id);
  const code = (await ali.api<Ev>(`/api/events/${id}`)).my!.ticketCode!;
  const dana = await calm(await open('Dana'));

  await openScanner(dana, 'Door night');
  await scan(dana, 'KBTU' + code);
  await expect(dana.page.getByText(T('scan.ok'), { exact: true })).toBeVisible();
  await expect(dana.page.getByText(/Ali/).filter({ visible: true }).first()).toBeVisible();
  await dana.look('ticket checked in');

  // the same ticket again: "already", not a second entry
  await scan(dana, 'KBTU' + code, false); // after a good scan Telegram's scanner comes back by itself for the queue
  await expect(dana.page.getByText(before('scan.already'))).toBeVisible();
  await dana.look('ticket already used');

  // Ali's ticket (the bot's button opens it: tk_<id>) says he's in
  const mine = await calm(await open('Ali', { path: `/?startapp=tk_${id}` }));
  await expect(mine.page.getByText(before('tk.checkedIn')).filter({ visible: true }).first()).toBeVisible();
  await mine.look('ticket checked in');
});

test('an 18+ door asks the age after the scan', async ({ open, qa }) => {
  // a guest-list event with the age check: only the creator makes one (admin event-new, then the list's import)
  admin(qa, ['founder', '1003']); // Bota is the creator here; she isn't in this test
  const at = new Date(Date.now() + 2 * 3600_000).toISOString();
  const made = admin(qa, ['event-new', 'openmic'], JSON.stringify({ title: 'Late show 18+', description: 'Stand-up after dark.', place: 'Atrium',
    starts_at: at, ends_at: new Date(Date.now() + 5 * 3600_000).toISOString(), guest_list: true, age_check: true }));
  const id = Number(made.match(/published (\d+)/)![1]);
  admin(qa, ['guests', String(id)], 'student_id,adult,username,full_name\n24B100002,,,Nurlanov Ali\n'); // Ali bought a ticket, his age unknown

  const ali = await open('Ali');
  const desk = await open('Dana');
  await startNow(desk, id);
  const code = (await ali.api<Ev>(`/api/events/${id}`)).my!.ticketCode!;
  const dana = await calm(await open('Dana'));

  await openScanner(dana, 'Late show 18+');
  await scan(dana, 'KBTU' + code);
  await expect(dana.page.getByText(T('scan.ok'), { exact: true })).toBeVisible();
  await expect(dana.page.getByText(T('age.look'))).toBeVisible();
  await dana.look('18+ question');
  await dana.page.getByRole('button', { name: T('age.adult'), exact: true }).click();
  await expect(dana.page.getByText(T('age.look'))).toBeHidden(); // answered: the card goes, the next guest is scanned
  await expect.poll(async () => (await dana.api<{ person: { id: number }; adult?: boolean | null }[]>(`/api/events/${id}/door`)).find((d) => d.person.id === 2)?.adult,
    { message: 'the door recorded Ali as 18+' }).toBe(true);
  await dana.look('18+ answered');

  const mine = await calm(await open('Ali', { path: `/?startapp=tk_${id}` }));
  await expect(mine.page.getByText(before('tk.checkedIn')).filter({ visible: true }).first()).toBeVisible();
  await mine.look('18+ ticket checked in');
});

test('a walk-in comes in by their badge QR', async ({ open }) => {
  const desk = await open('Dana');
  const bota = await open('Bota');
  const qr = (await bota.api<{ qr: string | null }>('/api/me')).qr ?? '';
  expect(qr, 'a badge code the door can read (core.PROFILE_QR)').toMatch(/^\d+_[A-Z2-7]{10}$/);
  const id = await freeEvent(desk, 'Walk-in night');
  await startNow(desk, id);
  const dana = await calm(await open('Dana'));

  await openScanner(dana, 'Walk-in night');
  await scan(dana, `https://t.me/KBTUappBot?startapp=u_${qr}`);
  await expect(dana.page.getByText(T('scan.ok'), { exact: true })).toBeVisible();
  await expect(dana.page.getByText(T('scan.walkIn'))).toBeVisible();
  await dana.look('walk-in checked in');

  const mine = await calm(await open('Bota', { path: `/?startapp=tk_${id}` }));
  await expect(mine.page.getByText(before('tk.checkedIn')).filter({ visible: true }).first()).toBeVisible();
  await mine.look('walk-in ticket');
});
