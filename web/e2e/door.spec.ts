// The door (Scanner.svelte, server organizing.checkin): the club's organizer opens Check-in from Studio, checks in a
// ticket, lets in a walk-in by their badge QR, answers the 18+ question; the attendee's ticket then says checked in.
// No camera here: what a camera reads (the ticket's code, the badge QR's text) goes into the scanner's code field, the
// way a door with a dead camera types it.
import { test, expect, T } from './fixtures';
import type { App } from './fixtures';
import type { QaServer } from './server';

type Ev = { id: number; title: string; ageCheck?: boolean; my?: { ticketCode: string | null; checkedInAt: number | null } | null };

/** Studio of Dana's club, from the Clubs tab. */
async function studio(dana: App) {
  await dana.goTab(T('page.clubs'));
  await dana.page.getByRole('button', { name: /^Open Mic Club/ }).first().click();
  const s = dana.page.getByRole('region', { name: 'Open Mic Club' });
  await expect(s).toBeVisible();
  return s;
}

/** The event's own screen in Studio, then its Check-in (the Mark screen), switched to the scanner. */
async function doorOf(dana: App, title: string) {
  const s = await studio(dana);
  await s.getByRole('button', { name: new RegExp('^' + title.replace(/[+]/g, '\\+')) }).first().click();
  await dana.step('event-manage');
  await dana.page.getByRole('button', { name: T('mk.title'), exact: true }).last().click();
  await dana.page.getByRole('radio', { name: T('studio.scanner') }).click();
  await expect(dana.page.getByRole('textbox', { name: T('scan.code') })).toBeVisible();
  await dana.step('scanner');
}

async function typeCode(dana: App, code: string) {
  await dana.page.getByRole('textbox', { name: T('scan.code') }).fill(code);
  await dana.page.getByRole('button', { name: T('scan.mark'), exact: true }).click();
}

/** A free public event in 10 minutes (its door opens by itself at T-30), made and published by Dana. */
async function soon(qa: QaServer, title: string): Promise<Ev> {
  const now = Math.floor(Date.now() / 1000);
  const ev = await qa.api<Ev>('Dana', 'POST', '/orgs/1/events', { title, place: 'Atrium', startsAt: now + 600, endsAt: now + 3 * 3600, seats: null, emoji: 'popcorn_3d', color: '#2B4C9A', visibility: 'public' });
  await qa.api('Dana', 'POST', `/events/${ev.id}/publish`);
  return ev;
}

test('the door checks in a ticket; the attendee\'s ticket says checked in', async ({ open, qa }) => {
  // a free event soon, Ali signed up for it
  const doorEvent = await soon(qa, 'Door test');
  await qa.api('Ali', 'POST', `/events/${doorEvent.id}/registration`, {});
  const code = (await qa.api<Ev>('Ali', 'GET', `/events/${doorEvent.id}`)).my!.ticketCode!;

  // the organizer: Studio's Check-in for the next event (the day's one), the scanner, the ticket's code
  const dana = await open('Dana');
  const s = await studio(dana);
  await dana.step('studio');
  await s.getByRole('button', { name: T('mk.title'), exact: true }).click();
  await dana.page.getByRole('radio', { name: T('studio.scanner') }).click();
  await dana.step('scanner');
  await typeCode(dana, code);
  const result = dana.page.getByText(T('scan.ok'), { exact: true });
  await expect(result).toBeVisible();
  await expect(dana.page.getByText('Ali N', { exact: true }).filter({ visible: true }).first()).toBeVisible(); // the holder's face and name, to compare at the door
  await dana.step('checked-in');
  // the same ticket again: "already", never a second entry
  await typeCode(dana, code);
  await expect(dana.page.getByText(T('scan.already', { time: '' }).replace(/\s*$/, ''), { exact: false })).toBeVisible();
  await dana.step('already');

  // the attendee: the event's ticket is stamped
  const ali = await open('Ali');
  await ali.page.getByRole('button', { name: 'Door test' }).first().click();
  await expect(ali.sheet()).toBeVisible();
  await ali.step('event');
  await ali.sheet().getByRole('button', { name: T('event.ticket'), exact: true }).click();
  await expect(ali.page.getByText(new RegExp(T('tk.checkedIn', { time: '' }).trim()))).toBeVisible();
  await ali.step('ticket-checked-in');
});

test('a walk-in: the door reads the badge QR of someone who didn\'t sign up', async ({ open, qa }) => {
  // Bota's badge QR (Profile's Hero: t.me/KBTUappBot?startapp=u_<id>_<code>), as the camera reads it
  const bota = await qa.api<{ qr: string }>('Bota', 'GET', '/me');
  expect(bota.qr, 'qa.py seeds badge codes the app can read (10 of A-Z2-7)').toMatch(/^\d+_[A-Z2-7]{10}$/);
  const ev = await soon(qa, 'Walk-in test');
  const dana = await open('Dana');
  await doorOf(dana, 'Walk-in test');
  await typeCode(dana, `https://t.me/KBTUappBot?startapp=u_${bota.qr}`);
  await expect(dana.page.getByText(T('scan.ok'), { exact: true })).toBeVisible();
  await expect(dana.page.getByText(T('scan.walkIn'))).toBeVisible();
  await dana.step('walk-in');
  const after = await qa.api<Ev>('Bota', 'GET', `/events/${ev.id}`);
  expect(after.my?.checkedInAt).toBeTruthy();
});

test('an 18+ door: the scanner asks for the age after the ticket', async ({ open, qa }) => {
  // an 18+ door is a guest-list event (only the operator's import makes one): qa.py seeds it with Ali's ticket
  const events = await qa.api<Ev[]>('Ali', 'GET', '/events');
  const party = events.find((e) => e.ageCheck);
  expect(party, 'qa.py seeds an 18+ party').toBeTruthy();
  const code = (await qa.api<Ev>('Ali', 'GET', `/events/${party!.id}`)).my!.ticketCode!;
  const dana = await open('Dana');
  await doorOf(dana, party!.title);
  await typeCode(dana, code);
  await expect(dana.page.getByText(T('scan.ok'), { exact: true })).toBeVisible();
  await expect(dana.page.getByText(T('age.look'))).toBeVisible();
  await dana.step('age-question');
  await dana.page.getByRole('button', { name: T('age.adult'), exact: true }).click();
  await expect(dana.page.getByText(T('age.look'))).toBeHidden(); // answered: the card goes, the next guest
  await dana.step('age-answered');
  const door = await qa.api<{ person: { id: number }; adult?: boolean | null; checkedInAt: number | null }[]>('Dana', 'GET', `/events/${party!.id}/door`);
  expect(door.find((d) => d.person.id === 2)).toMatchObject({ adult: true });
});
