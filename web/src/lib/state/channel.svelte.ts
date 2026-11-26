// The Forum tab's feed (screens/forum/Channel): the channel's posts and my own, asked for with the app (the speed rule:
// a page never waits for its data when it opens), refreshed quietly when the tab comes into view. In memory only:
// the posts' words stay out of the launch copy. focus: a post to bring into view (the bot's startapp=fp_<id> button).
// more: an older page may be there ("Show earlier", loadOlder).
import { api, ApiErr, type ChannelFeedPost, type ChannelHeart, type ChannelOrder, type ChannelVisit, type ForumWhy } from '../api';

const orders: ChannelOrder[] = ['for_you', 'new'];
const empty = () => ({ posts: null as ChannelFeedPost[] | null, cursor: null as string | null, paging: false, request: 0 });
const pages = $state({ for_you: empty(), new: empty() });
export const channel = $state({
  writing: 0, visit: null as ChannelVisit | null, order: 'for_you' as ChannelOrder,
  focus: null as number | null, why: {} as Record<number, ForumWhy>,
  get feed() { return pages[this.order].posts; },
  set feed(posts: ChannelFeedPost[] | null) { pages[this.order].posts = posts; },
  get more() { return !!pages[this.order].cursor; },
});

export function selectChannelOrder(order: ChannelOrder) {
  channel.order = order;
  void loadChannel(order);
}

export function refreshChannel(order = channel.order) {
  pages[order].paging = false;
  return loadChannel(order);
}

export function updateChannelPosts(update: (posts: ChannelFeedPost[]) => ChannelFeedPost[]) {
  for (const order of orders) {
    const page = pages[order];
    if (page.posts || order === channel.order) page.posts = update(page.posts ?? []);
  }
}

export function removeChannelPost(id: number) {
  const removed: { order: ChannelOrder; post: ChannelFeedPost; index: number }[] = [];
  for (const order of orders) {
    const page = pages[order], index = page.posts?.findIndex((p) => p.id === id) ?? -1;
    if (page.posts && index >= 0) {
      removed.push({ order, post: page.posts[index], index });
      page.posts = page.posts.filter((p) => p.id !== id);
    }
  }
  touched();
  return () => {
    touched();
    for (const { order, post, index } of removed) {
      const posts = pages[order].posts;
      if (posts && !posts.some((p) => p.id === id)) posts.splice(index, 0, post);
    }
  };
}

/** Every live post both feeds hold, once (the global search reads them before asking the server). */
export function channelPosts(): ChannelFeedPost[] {
  const all = new Map<number, ChannelFeedPost>();
  for (const order of orders) for (const p of pages[order].posts ?? []) if (p.status === 'live') all.set(p.id, p);
  return [...all.values()];
}

export function warmChannelFeeds() {
  for (const order of orders) void loadChannel(order);
}

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
      for (const order of orders) {
        const row = pages[order].posts?.find((p) => p.id === id);
        if (row) Object.assign(row, result);
      }
      Object.assign(post, result);
      if (result.hearted === pendingHearts[id].hearted) break;
      pendingHearts[id].hearts = result.hearts + (result.hearted ? -1 : 1);
    }
  } finally {
    delete pendingHearts[id];
  }
}

/** "I'm coming" to an ask for help, flipped on every copy of the card in the same frame; the server's count after,
 *  the old state back if it refuses */
export async function toggleComing(post: ChannelFeedPost): Promise<void> {
  const id = post.id, was = post.help;
  if (!was) return;
  // the card in hand too (a shared post opened outside the loaded pages is only that)
  const set = (help: ChannelFeedPost['help']) => { post.help = help; updateChannelPosts((posts) => posts.map((p) => (p.id === id ? { ...p, help } : p))); };
  const me = !was.me;
  set({ ...was, me, coming: Math.max(0, was.coming + (me ? 1 : -1)) });
  try {
    const got = await api.setChannelComing(id, me);
    touched();
    set({ ...was, ...got });
  } catch (e) {
    set(was);
    throw e;
  }
}

export async function loadChannel(order = channel.order): Promise<void> {
  const page = pages[order];
  // Once paging starts, keep the original order and cursor while the student reads.
  if (page.paging) return;
  const at = gen, request = ++page.request;
  try {
    const got = await api.channelFeed(order);
    if (at !== gen || request !== page.request) return;
    const next = [...(page.posts ?? []).filter((p) => p.id < 0), ...got.posts];
    if (!page.posts || JSON.stringify(next) !== JSON.stringify($state.snapshot(page.posts))) page.posts = next;
    page.cursor = got.cursor;
  } catch {
    if (at === gen && request === page.request && !page.posts) page.posts = [];
  }
}

/** Continue the current snapshot. Restart from the top when it expires. */
export async function loadOlder(): Promise<number[]> {
  const order = channel.order, page = pages[order], cursor = page.cursor;
  if (!cursor) return [];
  const at = gen, request = ++page.request, wasPaging = page.paging;
  page.paging = true;
  try {
    const got = await api.channelFeed(order, cursor);
    if (request !== page.request) return [];
    if (at !== gen) { page.paging = wasPaging; return []; }
    const have = new Set((page.posts ?? []).map((p) => p.id)), add = got.posts.filter((p) => !have.has(p.id));
    page.posts = [...(page.posts ?? []), ...add];
    page.cursor = got.cursor;
    return add.map((p) => p.id);
  } catch (e) {
    if (request !== page.request) return [];
    if (e instanceof ApiErr && e.code === 'not_found' && e.message === 'feed_cursor') {
      page.paging = false;
      await loadChannel(order);
      return [];
    }
    page.paging = wasPaging;
    throw e;
  }
}
