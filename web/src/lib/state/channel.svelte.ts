// The Forum tab's feed (screens/forum/Channel): the channel's posts and my own, asked for with the app (the speed rule:
// a page never waits for its data when it opens), refreshed quietly when the tab comes into view. In memory only:
// the posts' words stay out of the launch copy. focus: a post to bring into view (the bot's startapp=fp_<id> button).
import { api, type ChannelFeedPost } from '../api';

export const channel = $state({ feed: null as ChannelFeedPost[] | null, focus: null as number | null });

// bumped by a change of mine (a post, a delete): a refresh asked before it lands stale (the 30 s poll answering after my
// delete brought the post back, after my post's answer took it away), so it's dropped; the next one is fresh
let gen = 0;
export const touched = () => { gen++; };

export async function loadChannel(): Promise<void> {
  // a post of mine still on its way (a temporary id below 0, ChannelCompose) stays on top through a refresh
  const at = gen;
  try { const got = await api.channelFeed(); if (at !== gen) return; channel.feed = [...(channel.feed ?? []).filter((p) => p.id < 0), ...got]; }
  catch { if (!channel.feed) channel.feed = []; }
}
