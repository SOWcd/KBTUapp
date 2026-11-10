// The Forum feed's 30 s refresh against my own changes: a refresh asked before my delete must not bring the post back.
import { expect, it, vi } from 'vitest';

let answer: (v: unknown) => void = () => {};
vi.mock('../api', () => ({ api: { channelFeed: () => new Promise((done) => { answer = done; }) } }));
import { channel, loadChannel, loadOlder, PAGE, touched } from './channel.svelte';
import type { ChannelFeedPost } from '../api';

const post = (id: number): ChannelFeedPost => ({ id, body: 'x', status: 'live', at: 0, msg: id, anon: false, nick: null, sign: 'A', mine: true, person: null, comments: 0, thread: null, faces: [], reactions: [], hot: false, photos: [] });

it('drops a refresh that was asked before my delete', async () => {
  channel.feed = [post(1), post(2)];
  const asked = loadChannel();                       // the poll, in flight
  channel.feed = channel.feed!.filter((p) => p.id !== 1); touched();  // I delete post 1
  answer([post(1), post(2)]);                        // the server's answer from before the delete
  await asked;
  expect(channel.feed!.map((p) => p.id)).toEqual([2]);
  const next = loadChannel(); answer([post(2)]); await next;  // the next refresh lands as usual
  expect(channel.feed!.map((p) => p.id)).toEqual([2]);
});

it('keeps the older pages under a refresh, and "more" by the page size', async () => {
  const ids = (from: number, n: number) => Array.from({ length: n }, (_, i) => post(from - i));
  channel.feed = null;
  let next = loadChannel(); answer(ids(200, PAGE)); await next;
  expect(channel.more).toBe(true);
  next = loadOlder().then(() => {}); answer(ids(150, 3)); await next;     // the last page: 150..148
  expect(channel.feed!.length).toBe(PAGE + 3); expect(channel.more).toBe(false);
  next = loadChannel(); answer(ids(201, PAGE)); await next;              // a new post on top: nothing below is lost
  expect(channel.feed!.map((p) => p.id)).toEqual(ids(201, PAGE + 4).map((p) => p.id));  // 201..152, 151 kept, 150..148
});

it('leaves the feed as it is when a refresh brings the same posts (no rebuild, no flip measuring)', async () => {
  channel.feed = null;
  let next = loadChannel(); answer([post(2), post(1)]); await next;
  const before = channel.feed;
  next = loadChannel(); answer([post(2), post(1)]); await next;
  expect(channel.feed).toBe(before);
  next = loadChannel(); answer([{ ...post(2), comments: 1 }, post(1)]); await next;  // a count moved: set
  expect(channel.feed).not.toBe(before);
});
