import { expect, it, vi } from 'vitest';
import { loadMe, saveSwitch, session } from './session.svelte';

const { me, updateMe, tg } = vi.hoisted(() => ({ me: vi.fn(), updateMe: vi.fn(), tg: { initData: '', user: { id: 17 } as { id: number } | null } }));
vi.mock('../api', () => ({ api: { me, updateMe }, ApiErr: class extends Error {} }));
vi.mock('../tg', () => ({ tg }));
vi.mock('./cache', () => ({ clearCache: vi.fn() }));

it('loads the personal log for the verified account and clears it on revocation', async () => {
  const profile = { id: 7, tg: { id: 17 }, settings: { nDoor: true } };
  const account = { ...profile, reports: { consent: true } };
  const entry = { event: 1, org: 2, club: 'Club', title: 'Event', date: 0, status: 'present', comment: 'Set up' };
  me.mockResolvedValueOnce({ ...account, reportLog: [entry] }).mockResolvedValueOnce(account);

  await loadMe(false, true);
  await loadMe(true);
  expect(me.mock.calls).toEqual([[true], [false]]);
  expect(session.verified).toBe(true);
  expect(session.reportLog?.entries).toEqual([entry]);
  expect(session.me).not.toHaveProperty('reportLog');

  updateMe.mockResolvedValueOnce({ ...profile, settings: { nDoor: false } });
  await saveSwitch('nDoor', false);
  expect(session.me?.reports?.consent).toBe(true);

  me.mockResolvedValueOnce({ ...account, reports: { consent: false } });
  await loadMe(true);
  expect(session.reportLog).toBeNull();

  me.mockResolvedValueOnce(account).mockResolvedValueOnce({ ...account, reportLog: [] });
  await loadMe(true);
  expect(me.mock.calls).toEqual([[true], [false], [false], [false], [true]]);
  expect(session.reportLog?.entries).toEqual([]);

  me.mockResolvedValueOnce({ ...account, tg: { id: 18 }, reportLog: [entry] });
  await loadMe(true, true);
  expect(session.revoked).toBe(true);
  expect(session.reportLog).toBeNull();
});

it('uses the browser session response to verify the account and keep the log out of the profile', async () => {
  vi.resetModules();
  tg.user = null;
  me.mockClear();
  const { loadMe, session } = await import('./session.svelte');
  const profile = { id: 7, tg: { id: 17 }, reports: { consent: true }, reportLog: [] };

  await loadMe(false, true, profile as unknown as Awaited<ReturnType<typeof import('../api').api.me>>);
  expect(me).not.toHaveBeenCalled();
  expect(session.verified).toBe(true);
  expect(session.reportLog).toEqual({ owner: 7, entries: [] });
  expect(session.me).not.toHaveProperty('reportLog');
  tg.user = { id: 17 };
});
