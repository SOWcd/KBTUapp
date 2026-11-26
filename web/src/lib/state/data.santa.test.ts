import { expect, it, vi } from 'vitest';
import { api, type EventFull, type SantaChats } from '../api';
import { changeSantaChat, data, eventDetails, loadSantaChat, prefetchEvent } from './data.svelte';

vi.mock('../api', async () => ({ ...(await import('../api/errors')), api: { event: vi.fn(), santaChat: vi.fn() } }));
vi.mock('./ui.svelte', () => ({ close: vi.fn(), overlays: [], say: vi.fn() }));
vi.mock('../stats', () => ({ count: vi.fn(), timed: vi.fn(), failed: vi.fn() }));
vi.mock('../../ui/burst', () => ({ burst: vi.fn() }));
const teamLoaded = vi.hoisted(() => vi.fn());
vi.mock('../../screens/sheets/EventTeam.svelte', () => ({ default: teamLoaded() }));

it('keeps a confirmed Santa send and report when a pre-write refresh arrives late', async () => {
  const replies: ((value: SantaChats) => void)[] = [];
  vi.mocked(api.santaChat).mockImplementation(() => new Promise((resolve) => replies.push(resolve)));
  const sent = { id: 2, mine: true, text: 'Sent', at: 1 };
  const received = { id: 1, mine: false, text: 'Received', at: 1 };
  const before = { to: { closed: false, msgs: [] }, from: { closed: false, msgs: [received] } };
  const after = { to: { closed: false, msgs: [sent] }, from: { closed: true, msgs: [] } };
  data.santaChat[1] = structuredClone(before);
  const loading = loadSantaChat(1);
  await changeSantaChat(1, async () => { data.santaChat[1].to = after.to; });
  await changeSantaChat(1, async () => { data.santaChat[1].from = after.from; });
  replies[0](before);
  await vi.waitFor(() => expect(replies).toHaveLength(2));
  expect(data.santaChat[1]).toEqual(after);
  replies[1](after);
  await expect(loading).resolves.toBe(true);
});

it('loads team controls while the event details are still pending', async () => {
  const event = { id: 2, teamMax: 5 } as EventFull;
  data.events = [event];
  let resolve!: (value: EventFull) => void;
  vi.mocked(api.event).mockImplementationOnce(() => new Promise((done) => { resolve = done; }));

  prefetchEvent(event.id);
  await vi.waitFor(() => expect(teamLoaded).toHaveBeenCalledOnce());
  const detail = eventDetails(event.id);
  expect(api.event).toHaveBeenCalledTimes(1);
  resolve(event);
  await expect(detail).resolves.toBe(event);
});
