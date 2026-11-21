// The Forum tab's feed (screens/forum/Channel): the channel's posts and my own, asked for with the app (the speed rule:
// a page never waits for its data when it opens), refreshed quietly when the tab comes into view. In memory only:
// the posts' words stay out of the launch copy. focus: a post to bring into view (the bot's startapp=fp_<id> button).
// more: an older page may be there ("Show earlier", loadOlder).
import { api, type ChannelFeedPost, type ChannelHeart, type ChannelVisit, type ForumWhy } from '../api';

export const PAGE = 50; // the server's FEED_MAX
// why: the AI's reason for my posts it held (ChannelCompose asks once the post is in; shown under it, to me alone)
// writing: the writing window is up (ChannelCompose): the pill it grew out of hides
export const channel = $state({ writing: 0, visit: null as ChannelVisit | null, feed: null as ChannelFeedPost[] | null, focus: null as number | null, more: false, why: {} as Record<number, ForumWhy> });

// bumped by a change of mine (a post, a delete): a refresh asked before it lands stale (the 30 s poll answering after my
// delete brought the post back, after my post's answer took it away), so it's dropped; the next one is fresh
let gen = 0;
export const touched = () => { gen++; };

let pendingVisit = $state.raw<{ msg: number } | null>(null);
export const channelUnread = () => !!channel.visit && channel.visit.latest > Math.max(channel.visit.seen, pendingVisit?.msg ?? 0);

export async function markChannelSeen(msg: number): Promise<void> {
  if (!channel.visit || msg <= Math.max(channel.visit.seen, pendingVisit?.msg ?? 0)) return;
  const visit = { msg };
  pendingVisit = visit;
  try {
    await api.markChannelSeen(msg);
    if (pendingVisit === visit && channel.visit) channel.visit.seen = Math.max(channel.visit.seen, msg);
  } catch { /* retry when the next poll comes in */ }
  finally { if (pendingVisit === visit) pendingVisit = null; }
}

// Refresh the dot even while another tab is open. An older GET must keep a visit confirmed meanwhile.
export function watchChannelVisit(): () => void {
  let active = true, loading = false;
  const poll = async () => {
    if (loading || document.hidden) return;
    loading = true;
    try {
      const visit = await api.channelVisit();
      if (active) channel.visit = { latest: visit.latest, seen: Math.max(visit.seen, channel.visit?.seen ?? 0) };
    } catch { /* retry on the next poll */ } finally { loading = false; }
  };
  void poll();
  const timer = setInterval(poll, 30_000);
  document.addEventListener('visibilitychange', poll);
  return () => {
    active = false;
    clearInterval(timer);
    document.removeEventListener('visibilitychange', poll);
    channel.visit = null;
    pendingVisit = null;
  };
}

// A poll can replace a card while a tap is in flight. Keep the optimistic count over the feed
// until the server confirms the last tap, sending at most one request per post at a time.
export const pendingHearts = $state<Record<number, ChannelHeart>>({});

export async function toggleHeart(post: ChannelFeedPost): Promise<void> {
  const id = post.id, pending = pendingHearts[id], current = pending ?? post;
  pendingHearts[id] = { hearted: !current.hearted, hearts: current.hearts + (current.hearted ? -1 : 1) };
  if (pending) return;
  try {
    for (;;) {
      const result = await api.setChannelHeart(id, pendingHearts[id].hearted);
      touched();
      const row = channel.feed?.find((p) => p.id === id);
      if (row) Object.assign(row, result);
      if (result.hearted === pendingHearts[id].hearted) break;
      pendingHearts[id].hearts = result.hearts + (result.hearted ? -1 : 1);
    }
  } finally {
    delete pendingHearts[id];
  }
}

// the channel's order: a post by its message in the channel; mine not out yet above them all
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
    const next = [...(channel.feed ?? []).filter((p) => p.id < 0), ...got, ...older];
    // the same posts (most refreshes: on the tab's open, every 30 s): nothing is set, so the list isn't rebuilt and its
    // flip doesn't measure every post (a forced layout of the whole feed each time)
    if (!channel.feed || JSON.stringify(next) !== JSON.stringify($state.snapshot(channel.feed))) channel.feed = next;
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
