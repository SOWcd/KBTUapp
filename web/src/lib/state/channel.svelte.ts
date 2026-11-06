// The Forum tab's feed (screens/forum/Channel): the channel's posts and my own, asked for with the app (the speed rule:
// a page never waits for its data when it opens), refreshed quietly when the tab comes into view. In memory only:
// the posts' words stay out of the launch copy. focus: a post to bring into view (the bot's startapp=fp_<id> button).
// more: an older page may be there ("Show earlier", loadOlder).
import { api, type ChannelFeedPost, type ForumWhy } from '../api';

export const PAGE = 50; // the server's FEED_MAX
// why: the AI's reason for my posts it held (ChannelCompose asks once the post is in; shown under it, to me alone)
// writing: the writing window is up (ChannelCompose): the pill it grew out of hides
export const channel = $state({ writing: 0, feed: null as ChannelFeedPost[] | null, focus: null as number | null, more: false, why: {} as Record<number, ForumWhy> });

// bumped by a change of mine (a post, a delete): a refresh asked before it lands stale (the 30 s poll answering after my
// delete brought the post back, after my post's answer took it away), so it's dropped; the next one is fresh
let gen = 0;
export const touched = () => { gen++; };

// the channel's order (owner, Nov 3): a post by its message in the channel; mine not out yet above them all
const key = (p: { msg?: number | null }) => p.msg ?? Number.MAX_SAFE_INTEGER;

export async function loadChannel(): Promise<void> {
  // a post of mine still on its way (a temporary id below 0, ChannelCompose) stays on top through a refresh; the older
  // pages I opened stay under the fresh first one. ponytail: those aren't refreshed (a post deleted there stays till the
  // tab is reopened); refresh them too if it shows
  const at = gen;
  try {
    const got = await api.channelFeed(); if (at !== gen) return;
    const floor = got.length ? key(got[got.length - 1]) : 0;
    const older = (channel.feed ?? []).filter((p) => p.id > 0 && key(p) < floor);
    channel.feed = [...(channel.feed ?? []).filter((p) => p.id < 0), ...got, ...older];
    if (!older.length) channel.more = got.length >= PAGE;
  } catch { if (!channel.feed) channel.feed = []; }
}

/** The next page under the last post shown; the ids it added. */
export async function loadOlder(): Promise<number[]> {
  const last = Math.min(...(channel.feed ?? []).filter((p) => p.id > 0 && p.msg).map(key));
  const got = await api.channelFeed(last);
  const have = new Set((channel.feed ?? []).map((p) => p.id)), add = got.filter((p) => !have.has(p.id));
  channel.feed = [...(channel.feed ?? []), ...add];
  channel.more = got.length >= PAGE;
  return add.map((p) => p.id);
}
