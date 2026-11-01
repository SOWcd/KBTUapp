// The forum channel's "My posts" (screens/forum/Channel): asked for with the app, as soon as a student is here (the
// speed rule: a page never waits for its data when it opens), refreshed quietly when the tab comes into view. In memory
// only: one's own posts' words stay out of the launch copy.
import { api, type ChannelPost } from '../api';

export const channel = $state({ mine: null as ChannelPost[] | null });

export async function loadChannel(): Promise<void> {
  try { channel.mine = await api.channelPosts(); } catch { if (!channel.mine) channel.mine = []; }
}
