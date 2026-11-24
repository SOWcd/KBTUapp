// The Forum feed's 30 s refresh against my own changes: a refresh asked before my delete must not bring the post back.
import { beforeEach, expect, it, vi } from 'vitest';

const { setChannelHeart, channelVisit, saveVisit } = vi.hoisted(() => ({
  setChannelHeart: vi.fn(), channelVisit: vi.fn(), saveVisit: vi.fn(),
}));
let answer: (v: unknown) => void = () => {};
vi.mock('../api', async () => ({ ApiErr: (await import('../api/errors')).ApiErr, api: { setChannelHeart, channelVisit, markChannelSeen: saveVisit, channelFeed: () => new Promise((done) => { answer = done; }) } }));
import { channel, channelUnread, loadChannel, loadOlder, markChannelSeen, pendingHearts, refreshChannel, selectChannelOrder, toggleHeart, touched, watchChannelVisit } from './channel.svelte';
import type { ChannelFeedPost, ChannelHeart, ChannelVisit } from '../api';
import { hit } from '../search';

const page = (posts: ChannelFeedPost[], cursor: string | null = null) => ({ posts, cursor });

const post = (id: number): ChannelFeedPost => ({ id, body: 'x', status: 'live', at: 0, msg: id, anon: false, nick: null, sign: 'A', mine: true, person: null, comments: 0, thread: null, faces: [], reactions: [], hearts: 0, hearted: false, hot: false, photos: [] });

beforeEach(async () => {
  for (const order of ['for_you', 'new'] as const) {
    const reset = refreshChannel(order); answer(page([])); await reset;
  }
  channel.order = 'for_you';
});

it('drops a refresh that was asked before my delete', async () => {
  channel.feed = [post(1), post(2)];
  const asked = loadChannel();                       // the poll, in flight
  channel.feed = channel.feed!.filter((p) => p.id !== 1); touched();  // I delete post 1
  answer(page([post(1), post(2)]));                        // the server's answer from before the delete
  await asked;
  expect(channel.feed!.map((p) => p.id)).toEqual([2]);
  const next = loadChannel(); answer(page([post(2)])); await next;  // the next refresh lands as usual
  expect(channel.feed!.map((p) => p.id)).toEqual([2]);
});

it('keeps the ranked snapshot while paging and refreshes when the tab reopens', async () => {
  channel.feed = null;
  let next = refreshChannel(); answer(page([post(3), post(5)], 'rank.next')); await next;
  expect(channel.more).toBe(true);
  const more = loadOlder(); answer(page([post(1), post(4)])); await more;
  expect(channel.more).toBe(false);
  await loadChannel(); // background polling does not replace a snapshot being read
  expect(channel.feed!.map((p) => p.id)).toEqual([3, 5, 1, 4]);
  next = refreshChannel(); answer(page([post(6), post(4)], 'rank.fresh')); await next;
  expect(channel.feed!.map((p) => p.id)).toEqual([6, 4]);
  expect(channel.more).toBe(true);
});

it.each(['for_you', 'new'] as const)('searches further pages with the same query in %s order', async (order) => {
  channel.order = order;
  const query = 'chess';
  const matches = () => (channel.feed ?? []).filter((p) => hit(query, [p.body]));
  const first = refreshChannel(); answer(page([{ ...post(6), body: 'Book club' }], 'search.next')); await first;
  expect(matches()).toEqual([]);
  expect(channel.more).toBe(true); // only the loaded posts have been searched
  const more = loadOlder();
  expect(matches()).toEqual([]);
  answer(page([{ ...post(4), body: 'Chess tournament' }], 'search.last')); await more;
  expect(matches().map((p) => p.id)).toEqual([4]);
  const last = loadOlder(); answer(page([{ ...post(2), body: 'Chess practice' }])); await last;
  expect(matches().map((p) => p.id)).toEqual([4, 2]);
  expect(channel.more).toBe(false);
  channel.order = 'for_you';
});

it('keeps each order and its cursor together when a request finishes after switching', async () => {
  const ranked = refreshChannel(); const rankAnswer = answer;
  selectChannelOrder('new');
  expect(channel.order).toBe('new');
  answer(page([post(6), post(5)], 'new.next'));
  rankAnswer(page([post(1), post(2)]));
  await ranked;
  expect(channel.feed!.map((p) => p.id)).toEqual([6, 5]);
  expect(channel.more).toBe(true);
  selectChannelOrder('for_you');
  answer(page([post(1), post(2)]));
  await Promise.resolve();
  expect(channel.feed!.map((p) => p.id)).toEqual([1, 2]);
});

it('leaves the feed as it is when a refresh brings the same posts (no rebuild, no flip measuring)', async () => {
  channel.feed = null;
  let next = loadChannel(); answer(page([post(2), post(1)])); await next;
  const before = channel.feed;
  next = loadChannel(); answer(page([post(2), post(1)])); await next;
  expect(channel.feed).toBe(before);
  next = loadChannel(); answer(page([{ ...post(2), comments: 1 }, post(1)])); await next;  // a count moved: set
  expect(channel.feed).not.toBe(before);
});

it('keeps rapid heart taps optimistic through a feed refresh and sends the final selection', async () => {
  let confirm!: (result: ChannelHeart) => void;
  setChannelHeart.mockReset().mockImplementation(() => new Promise<ChannelHeart>((resolve) => { confirm = resolve; }));
  channel.feed = [post(7)];
  const row = channel.feed[0];
  const saving = toggleHeart(row);
  expect(pendingHearts[7]).toEqual({ hearts: 1, hearted: true });
  await toggleHeart(row);
  expect(pendingHearts[7]).toEqual({ hearts: 0, hearted: false });
  const refresh = loadChannel();
  answer(page([{ ...post(7), hearts: 3 }]));
  await refresh;
  confirm({ hearts: 4, hearted: true });
  await Promise.resolve();
  expect(setChannelHeart.mock.calls).toEqual([[7, true], [7, false]]);
  expect(pendingHearts[7]).toEqual({ hearts: 3, hearted: false });
  confirm({ hearts: 3, hearted: false });
  await saving;
  expect(pendingHearts[7]).toBeUndefined();
  expect(channel.feed[0]).toMatchObject({ hearts: 3, hearted: false });
});

it('removes only the optimistic heart when saving fails', async () => {
  setChannelHeart.mockRejectedValueOnce(new Error('offline'));
  channel.feed = [post(8)];
  const saving = toggleHeart(channel.feed[0]);
  channel.feed[0].comments = 2;
  await expect(saving).rejects.toThrow('offline');
  expect(pendingHearts[8]).toBeUndefined();
  expect(channel.feed[0]).toMatchObject({ hearts: 0, hearted: false, comments: 2 });
});

it('shows unread publications without marking a prefetch, and keeps a visit through a stale poll', async () => {
  vi.useFakeTimers();
  const page = Object.assign(new EventTarget(), { hidden: false });
  vi.stubGlobal('document', page);
  channelVisit.mockResolvedValueOnce({ latest: 90, seen: 80 });
  const stop = watchChannelVisit();
  try {
    await Promise.resolve();
    expect(channelUnread()).toBe(true);
    expect(saveVisit).not.toHaveBeenCalled();

    let finishPoll!: (v: ChannelVisit) => void;
    channelVisit.mockImplementationOnce(() => new Promise((done) => { finishPoll = done; }));
    page.dispatchEvent(new Event('visibilitychange'));
    let saved!: () => void;
    saveVisit.mockImplementationOnce(() => new Promise<void>((done) => { saved = done; }));
    const marking = markChannelSeen(90);
    expect(channelUnread()).toBe(false); // leave the Forum while the write is in flight
    saved();
    await marking;
    finishPoll({ latest: 91, seen: 80 });
    await Promise.resolve();
    expect(channel.visit).toEqual({ latest: 91, seen: 90 });
    expect(channelUnread()).toBe(true);

    saveVisit.mockRejectedValueOnce(new Error('offline'));
    await markChannelSeen(91);
    expect(channelUnread()).toBe(true);
    page.hidden = true;
    await vi.advanceTimersByTimeAsync(30_000);
    expect(channelVisit).toHaveBeenCalledTimes(2);
  } finally {
    stop();
    vi.unstubAllGlobals();
    vi.useRealTimers();
  }
  expect(channelUnread()).toBe(false);
});
