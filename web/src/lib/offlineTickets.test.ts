import { describe, expect, it, vi } from 'vitest';
import type { EventCard, MyRegistration, OrgRef } from './api';
import { ApiErr, unreachable } from './api/errors';
import { endOf, sanitize, ticketsOf } from './offlineTickets';

vi.mock('./state/data.svelte', () => ({ data: { orgs: [] } })); // awards reads the clubs for badges

const NOW = 1_800_000_000;
const my = (over: Partial<MyRegistration> = {}): MyRegistration =>
  ({ status: 'going', cancelReason: null, ticketCode: 'AB7K', holdUntil: null, checkedInAt: null, receipt: 'none', ...over });
const org: OrgRef = { id: 3, slug: 'club', name: 'Club', short: 'C', emoji: '', cover: 0, kind: 'club', official: false };
// an event card as the server sends it, with the things about other people a ticket must never carry
const ev = (id: number, over: Partial<EventCard> = {}): EventCard => ({
  id, title: `Event ${id}`, startsAt: NOW + 3600, endsAt: NOW + 7200, place: 'Hall 1', online: false, status: 'published', my: my(),
  friends: [{ id: 9, name: 'A friend' }], org, description: 'secret plan', ...over,
} as unknown as EventCard);

describe('ticketsOf', () => {
  it('keeps my going tickets with a code, and only the fields the QR and its card need', () => {
    expect(ticketsOf([ev(1)], NOW)).toEqual([{ id: 1, title: 'Event 1', startsAt: NOW + 3600, endsAt: NOW + 7200, place: 'Hall 1', online: false, code: 'AB7K', look: 'kbtu', logo: null }]);
    const json = JSON.stringify(ticketsOf([ev(1)], NOW));
    for (const s of ['friend', 'Club', 'secret', 'receipt', 'holdUntil']) expect(json).not.toContain(s);
  });

  it('takes the look from the organizer, including illustrated and inline marks', () => {
    const events = [ev(1, { org: { ...org, slug: 'qoloner' } }), ev(2, { org: { ...org, slug: 'studex' } })];
    expect(ticketsOf(events, NOW).map((t) => t.look)).toEqual(['qoloner', 'studex']);
  });

  it('skips what isn\'t a ticket of mine: a hold, a waitlist, cancelled, no code, no sign-up, a cancelled event', () => {
    const events = [
      ev(1, { my: my({ status: 'hold' }) }), ev(2, { my: my({ status: 'waitlist' }) }), ev(3, { my: my({ status: 'cancelled' }) }),
      ev(4, { my: my({ ticketCode: null }) }), ev(5, { my: null }), ev(6, { status: 'cancelled' }), ev(7),
    ];
    expect(ticketsOf(events, NOW).map((t) => t.id)).toEqual([7]);
  });

  it('drops what is over: by its end, or three hours after a start without one', () => {
    expect(ticketsOf([ev(1, { startsAt: NOW - 7200, endsAt: NOW - 1 })], NOW)).toEqual([]);
    expect(ticketsOf([ev(2, { startsAt: NOW - 3 * 3600, endsAt: null })], NOW)).toEqual([]);
    expect(ticketsOf([ev(3, { startsAt: NOW - 3 * 3600 + 60, endsAt: null })], NOW).map((t) => t.id)).toEqual([3]); // still on: the door is open
  });

  it('soonest first', () => {
    expect(ticketsOf([ev(1, { startsAt: NOW + 9000 }), ev(2, { startsAt: NOW + 100 })], NOW).map((t) => t.id)).toEqual([2, 1]);
  });
});

describe('endOf', () => {
  it('is the event\'s own end, else three hours after its start', () => {
    expect(endOf({ startsAt: 100, endsAt: 500 })).toBe(500);
    expect(endOf({ startsAt: 100, endsAt: null })).toBe(100 + 3 * 3600);
  });
});

describe('sanitize', () => {
  const old = { id: 1, title: 'T', startsAt: NOW + 10, endsAt: null, place: 'P', online: false, code: 'AB7K' };
  const ok = { ...old, look: 'kbtu', logo: null };

  it('reads back what was kept', () => {
    expect(sanitize(JSON.parse(JSON.stringify([ok])), NOW)).toEqual([ok]);
  });

  it('keeps old tickets and falls back to the app look for unknown keys', () => {
    for (const look of [undefined, 'removed', '__proto__']) expect(sanitize([{ ...old, look }], NOW)).toEqual([ok]);
  });

  it('only retains small PNG data URLs for looks with an image', () => {
    const logo = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aGp0AAAAASUVORK5CYII=';
    const branded = { ...ok, look: 'qoloner' };
    expect(sanitize([{ ...branded, logo }], NOW)).toEqual([{ ...branded, logo }]);
    expect(sanitize([{ ...ok, logo }], NOW)).toEqual([ok]);
    for (const invalid of ['/assets/mark.webp', 'https://example.com/mark.png', 'data:image/svg+xml,<svg/>', logo + 'A'.repeat(32_768)]) {
      expect(sanitize([{ ...branded, logo: invalid }], NOW)).toEqual([branded]);
    }
  });

  it('takes nothing that isn\'t a list', () => {
    for (const raw of [null, undefined, 'x', 5, { 0: ok }]) expect(sanitize(raw, NOW)).toEqual([]);
  });

  it('drops malformed entries, keeps the good ones', () => {
    const bad = [
      null, 'x', { ...ok, id: 0 }, { ...ok, id: -1 }, { ...ok, id: 1.5 }, { ...ok, id: '1' }, { ...ok, title: 5 }, { ...ok, place: null },
      { ...ok, online: 'no' }, { ...ok, startsAt: 'soon' }, { ...ok, startsAt: Infinity }, { ...ok, endsAt: 'later' }, { ...ok, endsAt: NaN },
      { ...ok, code: '' }, { ...ok, code: 'ab7k' }, { ...ok, code: 'AB 7K' }, { ...ok, code: '<img src=x>' }, { ...ok, code: 'A'.repeat(9) },
    ];
    expect(sanitize([...bad, { ...ok, id: 2 }], NOW).map((t) => t.id)).toEqual([2]);
  });

  it('carries no field it wasn\'t told about, and bounds the texts', () => {
    const [t] = sanitize([{ ...ok, friends: ['x'], __proto__: { polluted: 1 }, title: 'T'.repeat(500), place: 'P'.repeat(500) }], NOW);
    expect(Object.keys(t).sort()).toEqual(['code', 'endsAt', 'id', 'logo', 'look', 'online', 'place', 'startsAt', 'title']);
    expect(t.title.length).toBe(200);
    expect(t.place.length).toBe(200);
  });

  it('one per event, expired ones gone, twenty at most', () => {
    expect(sanitize([ok, { ...ok, code: 'ZZZZ' }], NOW)).toEqual([ok]);
    expect(sanitize([{ ...ok, startsAt: NOW - 4 * 3600 }], NOW)).toEqual([]);
    expect(sanitize(Array.from({ length: 30 }, (_, i) => ({ ...ok, id: i + 1, startsAt: NOW + i })), NOW)).toHaveLength(20);
  });
});

describe('unreachable', () => {
  it('is the network only, never an answer from the server', () => {
    expect(unreachable(new ApiErr('unavailable', 'network'))).toBe(true);
    expect(unreachable(new ApiErr('unavailable'))).toBe(false); // a 5xx without a body: the server answered
    expect(unreachable(new ApiErr('unauthorized'))).toBe(false);
    expect(unreachable(new ApiErr('forbidden', 'init_data'))).toBe(false);
    expect(unreachable(new TypeError('Failed to fetch'))).toBe(false);
    expect(unreachable(undefined)).toBe(false);
  });
});
