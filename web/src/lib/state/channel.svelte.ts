// The Forum tab's feed (screens/forum/Channel): the channel's posts and my own, asked for with the app (the speed rule:
// a page never waits for its data when it opens), refreshed quietly when the tab comes into view. In memory only:
// the posts' words stay out of the launch copy.
import { api, type ChannelFeedPost } from '../api';

export const channel = $state({ feed: null as ChannelFeedPost[] | null });

export async function loadChannel(): Promise<void> {
  try { channel.feed = await api.channelFeed(); } catch { if (!channel.feed) channel.feed = []; }
}
