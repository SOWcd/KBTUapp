// The Forum tab's feed (screens/forum/Channel): the channel's posts and my own, asked for with the app (the speed rule:
// a page never waits for its data when it opens), refreshed quietly when the tab comes into view. In memory only:
// the posts' words stay out of the launch copy. focus: a post to bring into view (the bot's startapp=fp_<id> button).
// more: an older page may be there ("Show earlier", loadOlder).
import { api, type ChannelFeedPost } from '../api';

export const PAGE = 50; // the server's FEED_MAX
export const channel = $state({ feed: null as ChannelFeedPost[] | null, focus: null as number | null, more: false });

// bumped by a change of mine (a post, a delete): a refresh asked before it lands stale (the 30 s poll answering after my
// delete brought the post back, after my post's answer took it away), so it's dropped; the next one is fresh
let gen = 0;
export const touched = () => { gen++; };

export async function loadChannel(): Promise<void> {
  // a post of mine still on its way (a temporary id below 0, ChannelCompose) stays on top through a refresh; the older
  // pages I opened stay under the fresh first one. ponytail: those aren't refreshed (a post deleted there stays till the
  // tab is reopened); refresh them too if it shows
  const at = gen;
  try {
    const got = await api.channelFeed(); if (at !== gen) return;
    const floor = got.length ? got[got.length - 1].id : 0;
    const older = (channel.feed ?? []).filter((p) => p.id > 0 && p.id < floor);
    channel.feed = [...(channel.feed ?? []).filter((p) => p.id < 0), ...got, ...older];
    if (!older.length) channel.more = got.length >= PAGE;
  } catch { if (!channel.feed) channel.feed = []; }
}

/** The next page under the last post shown; the ids it added. */
export async function loadOlder(): Promise<number[]> {
  const last = Math.min(...(channel.feed ?? []).filter((p) => p.id > 0).map((p) => p.id));
  const got = await api.channelFeed(last);
  const have = new Set((channel.feed ?? []).map((p) => p.id)), add = got.filter((p) => !have.has(p.id));
  channel.feed = [...(channel.feed ?? []), ...add];
  channel.more = got.length >= PAGE;
  return add.map((p) => p.id);
}
