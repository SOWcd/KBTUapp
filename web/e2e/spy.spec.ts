// Spy (Profile -> Games): a whole round against the real server. Dana makes the room on her phone; Ali and Bota come
// in by its code and play through the API, as their phones would. The pictures of each state: snap.spec.ts.
import { test, expect } from './fixtures';
import type { Who } from './fixtures';
import ru from '../src/lib/i18n/ru';

type Room = { id: number; v: number; phase: string; role?: string; players: { id: number }[]; me: number };

test('a round of Spy: a room, three players, the role, the vote, the reveal', async ({ open, qa, request }) => {
  const dana = await open('Dana'), { page } = dana;
  await page.getByRole('navigation', { name: ru['nav.label'] }).getByRole('button', { name: ru['tab.profile'], exact: true }).click();
  await page.getByRole('button', { name: ru['games.title'], exact: true }).click();
  const sheet = page.getByRole('dialog').filter({ has: page.locator('.home, .phase') });
  await sheet.locator('.home .btn').click();
  const code = (await sheet.locator('.digits').innerText()).replace(/\D/g, '');
  expect(code).toMatch(/^\d{4}$/);
  await expect(sheet.locator('.ft .btn').first()).toBeDisabled(); // alone: no Start yet
  await dana.look('spy lobby');

  // the other two, as their phones would call
  const call = (who: Who) => async (path: string, body: unknown): Promise<{ room?: Room } & Room> => {
    const init = new URLSearchParams(qa.link(who).split('#')[1]).get('tgWebAppData')!;
    const r = await request.post(`${qa.url}/api/rooms${path}`, { headers: { Authorization: `tma ${init}` }, data: body });
    expect(r.ok(), `${who} ${path}: ${r.status()}`).toBe(true);
    return r.json();
  };
  const others = [call('Ali'), call('Bota')];
  const rooms = () => Promise.all(others.map((c) => c('/join', { code }))); // a player already in gets the room back
  const [first] = await rooms();
  const move = (c: (typeof others)[number], r: Room, m: object) => c(`/${r.id}`, { id: Math.random().toString(36).slice(2), v: r.v, ...m });

  await sheet.locator('.ft .btn').first().click(); // Start, once her phone has seen the three
  const secret = sheet.locator('.secret');
  await expect(secret).toBeVisible();
  const box = (await secret.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await expect(secret.locator('.big')).toBeVisible();
  await dana.look('spy role');
  await page.mouse.up();
  await expect(secret.locator('.big')).toHaveCount(0);

  await sheet.locator('.foot .btn').click(); // the host: to the vote
  await expect(sheet.locator('.cand')).toHaveCount(2);
  await sheet.locator('.cand').first().click();
  await expect(sheet.locator('.cand').first()).toHaveAttribute('aria-pressed', 'true');
  await dana.look('spy vote');
  await expect(sheet.locator('.ballot .sh')).toContainText('1'); // her vote is in before the others' end the vote
  // each of the others votes for Dana; whoever the spy is, the round then ends in a guess or at once
  for (const [i, r] of (await rooms()).entries()) await move(others[i], r, { type: 'vote', target: first.players[0].id });
  for (const [i, r] of (await rooms()).entries()) if (r.phase === 'guess' && r.role === 'spy') await move(others[i], r, { type: 'guess', location: 'library' });
  const mine = await dana.api<Room>('/api/rooms/join', { code });
  if (mine.phase === 'guess') await dana.api(`/api/rooms/${mine.id}`, { id: 'g1', v: mine.v, type: 'guess', location: 'library' });
  await expect(sheet.locator('.end')).toBeVisible();
  await dana.look('spy reveal');
});
