import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import type { EventCard } from '../api';

const { register, unregister, decline, actions } = vi.hoisted(() => ({
  register: vi.fn(), unregister: vi.fn(), decline: vi.fn(), actions: [] as Promise<void>[],
}));
vi.mock('../api', async () => ({ ApiErr: (await import('../api/errors')).ApiErr, api: { register, unregister, decline } }));
vi.mock('./session.svelte', () => ({
  session: { me: { student: {}, memberships: [], canDm: true } }, loadMe: vi.fn(),
  asStudent: (action: () => Promise<void>) => { actions.push(action()); },
}));
vi.mock('./ui.svelte', () => ({ close: vi.fn(), overlays: [], say: vi.fn() }));
vi.mock('../i18n/index.svelte', () => ({ t: (k: string) => k, tn: (k: string) => k, i18n: { lang: 'en' } }));
vi.mock('../tg', () => ({ tg: { initData: '' }, haptic: { tap: vi.fn(), ok: vi.fn(), warn: vi.fn(), error: vi.fn(), soft: vi.fn() } }));
vi.mock('../stats', () => ({ count: vi.fn(), timed: vi.fn(), failed: vi.fn() }));
vi.mock('../../ui/burst', () => ({ burst: vi.fn() }));
vi.mock('./sheets', () => ({ sheets: {} }));
vi.mock('../teamConsent', () => ({ TEAM_CONSENT: 'test', teamConsentOk: vi.fn() }));
vi.mock('./staffAccess.svelte', () => ({ onStaffLoss: vi.fn(), staffStill: vi.fn() }));

import { data, eventById, goingBusy, goingPending, toggleGoing, declineInvite } from './data.svelte';

const card = (my: EventCard['my'] = null): EventCard => ({
  id: 1, status: 'published', title: 'Test event', org: { id: 2 }, taken: 0, seats: null, price: null, my,
}) as EventCard;
const ticket = { status: 'going', ticketCode: 'K7M2', cancelReason: null, holdUntil: null, checkedInAt: null, receipt: 'none' } as const;

beforeEach(() => { vi.useFakeTimers(); vi.clearAllMocks(); data.events = [card()]; actions.length = 0; });
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); });

it('opens an optimistic free registration immediately and keeps it pending until the code arrives', async () => {
  let answer!: (e: EventCard) => void;
  register.mockImplementationOnce(() => new Promise<EventCard>((resolve) => { answer = resolve; }));
  toggleGoing(1);
  await Promise.resolve();
  expect(eventById(1)?.my).toMatchObject({ status: 'going', ticketCode: null });
  expect(goingPending.has(1)).toBe(true);
  expect(goingBusy.has(1)).toBe(false); // the immediate Ticket action stays available
  toggleGoing(1); await Promise.resolve();
  expect(register).toHaveBeenCalledTimes(1);
  expect(unregister).not.toHaveBeenCalled();
  answer(card(ticket));
  await Promise.all(actions);
  expect(goingPending.has(1)).toBe(false);
  expect(eventById(1)?.my?.ticketCode).toBe('K7M2');
});

it('settles a failed free registration and restores its previous state', async () => {
  register.mockRejectedValueOnce(new Error('offline'));
  toggleGoing(1);
  await Promise.all(actions);
  expect(goingPending.has(1)).toBe(false);
  expect(eventById(1)).toMatchObject({ my: null, taken: 0 });
});

it('waits for a new code when rejoining instead of showing the cancelled ticket', async () => {
  const cancelled = { ...ticket, status: 'cancelled' as const, ticketCode: 'OLD1' };
  data.events = [card(cancelled)];
  let answer!: (e: EventCard) => void;
  register.mockImplementationOnce(() => new Promise<EventCard>((resolve) => { answer = resolve; }));
  toggleGoing(1);
  await Promise.resolve();
  expect(goingPending.has(1)).toBe(true);
  expect(eventById(1)?.my).toMatchObject({ status: 'going', ticketCode: null });
  answer(card(ticket));
  await Promise.all(actions);
  expect(eventById(1)?.my?.ticketCode).toBe('K7M2');
  expect(goingPending.has(1)).toBe(false);
});

it('keeps the issued ticket during cancellation and after a failed cancellation', async () => {
  data.events = [card(ticket)];
  let reject!: (error: Error) => void;
  unregister.mockImplementationOnce(() => new Promise((_resolve, no) => { reject = no; }));
  toggleGoing(1);
  await Promise.resolve();
  expect(goingPending.has(1)).toBe(true);
  expect(eventById(1)?.my).toEqual(ticket);
  reject(new Error('offline'));
  await Promise.all(actions);
  expect(goingPending.has(1)).toBe(false);
  expect(eventById(1)?.my).toEqual(ticket);
  unregister.mockResolvedValueOnce(card({ ...ticket, status: 'cancelled' }));
  toggleGoing(1);
  await Promise.all(actions);
  expect(eventById(1)?.my?.status).toBe('cancelled');
});

it('keeps a meeting ticket when declining fails', async () => {
  data.events = [{ ...card(ticket), meeting: true }];
  decline.mockRejectedValueOnce(new Error('offline'));
  declineInvite(1, 'Cannot attend');
  expect(goingPending.has(1)).toBe(true);
  await Promise.all(actions);
  expect(goingPending.has(1)).toBe(false);
  expect(eventById(1)?.my).toEqual(ticket);
});
