// data.offline: what turns on the kept tickets on the Afisha and the "Offline" badge on the ticket sheet (TicketView).
import { beforeEach, expect, it, vi } from 'vitest';

const { calls } = vi.hoisted(() => ({ calls: {} as Record<string, ReturnType<typeof vi.fn>> }));
// every API call answers an empty list unless a test says otherwise
vi.mock('../api', async () => ({
  ApiErr: (await import('../api/errors')).ApiErr,
  api: new Proxy({}, { get: (_, k: string) => (calls[k] ??= vi.fn(async () => [])) }),
}));
vi.mock('./session.svelte', () => ({ session: { me: null }, loadMe: vi.fn(), asStudent: vi.fn() }));
vi.mock('./ui.svelte', () => ({ close: vi.fn(), overlays: [], say: vi.fn() }));
vi.mock('../i18n/index.svelte', () => ({ t: (k: string) => k, tn: (k: string) => k, i18n: { lang: 'en' }, subjectOf: (s: string) => s }));
vi.mock('../tg', () => ({ tg: { initData: '' }, haptic: {}, requestWriteAccess: vi.fn() }));
vi.mock('../stats', () => ({ count: vi.fn(), timed: vi.fn(), failed: vi.fn() }));
vi.mock('../../ui/burst', () => ({ burst: vi.fn() }));
vi.mock('./sheets', () => ({ sheets: {} }));
vi.mock('./staffAccess.svelte', () => ({ onStaffLoss: vi.fn(), staffStill: vi.fn() }));

import { ApiErr } from '../api/errors';
import { data, loadAfisha } from './data.svelte';

beforeEach(() => { for (const k of Object.keys(calls)) delete calls[k]; data.offline = false; data.error = false; });
const events = () => (calls.events ??= vi.fn());

it('the events never reached the server: offline (the kept tickets, the ticket sheet\'s badge)', async () => {
  events().mockRejectedValueOnce(new ApiErr('unavailable', 'network'));
  await loadAfisha();
  expect(data.offline).toBe(true);
  expect(data.error).toBe(true);
});

it('the server answered with an error: an error, not offline (no "saved on this phone" note over a live server)', async () => {
  events().mockRejectedValueOnce(new ApiErr('unavailable'));
  await loadAfisha();
  expect(data.offline).toBe(false);
  expect(data.error).toBe(true);
});

it('the network back: the next answer clears the note', async () => {
  events().mockRejectedValueOnce(new ApiErr('unavailable', 'network'));
  await loadAfisha();
  expect(data.offline).toBe(true);
  events().mockResolvedValueOnce([]);
  await loadAfisha();
  expect(data.offline).toBe(false);
  expect(data.error).toBe(false);
});

it('only the events decide: another list failing offline leaves the Afisha online', async () => {
  (calls.posts ??= vi.fn()).mockRejectedValueOnce(new ApiErr('unavailable', 'network'));
  events().mockResolvedValueOnce([]);
  await loadAfisha();
  expect(data.offline).toBe(false);
});
