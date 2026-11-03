// The Forum feed's 30 s refresh against my own changes: a refresh asked before my delete must not bring the post back.
import { expect, it, vi } from 'vitest';

let answer: (v: unknown) => void = () => {};
vi.mock('../api', () => ({ api: { channelFeed: () => new Promise((done) => { answer = done; }) } }));
import { channel, loadChannel, touched } from './channel.svelte';
import type { ChannelFeedPost } from '../api';

const post = (id: number): ChannelFeedPost => ({ id, body: 'x', status: 'live', at: 0, msg: id, anon: false, sign: 'A', mine: true, person: null, comments: 0, thread: null, faces: [], reactions: [], hot: false, top: false });

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
