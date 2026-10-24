// Post labels (SPEC §4.10): the composer's chips by code, named in the UI language; an older free-text tag shows as is.
import type { Post, PostTag } from './api';
import { t } from './i18n/index.svelte';

export const POST_TAGS: PostTag[] = ['important', 'recruiting', 'results', 'news'];
export const tagName = (tag: string | null): string | null =>
  tag && (POST_TAGS as string[]).includes(tag) ? t(`tag.${tag}` as 'tag.news') : tag;

/** News as stories (owner, Oct 24): one circle per club, the broadcasts (DMP, KBTU App) first, then clubs with something
 *  unread, then by their newest post. A club's posts play oldest first and open at its first unread, as Telegram's
 *  stories do. Only the last 30 days: older posts stay on the club's page. */
export interface StoryGroup { org: Post['org']; posts: Post[]; unread: boolean; cast: boolean }
export const STORY_DAYS = 30;
export function storyGroups(casts: Post[], posts: Post[], now: number): StoryGroup[] {
  const by = new Map<number, StoryGroup>();
  for (const [cast, list] of [[true, casts], [false, posts]] as const)
    for (const p of list) {
      if (p.createdAt < now - STORY_DAYS * 86400) continue;
      const g = by.get(p.org.id) ?? { org: p.org, posts: [], unread: false, cast };
      if (!g.posts.some((x) => x.id === p.id)) g.posts.push(p);
      g.unread ||= !p.read;
      by.set(p.org.id, g);
    }
  const newest = (g: StoryGroup) => Math.max(...g.posts.map((p) => p.createdAt));
  for (const g of by.values()) g.posts.sort((a, b) => a.createdAt - b.createdAt);
  return [...by.values()].sort((a, b) => +b.cast - +a.cast || +b.unread - +a.unread || newest(b) - newest(a));
}
/** where a club's stories open: its first unread post, else its newest */
export const storyStart = (g: StoryGroup): number => { const i = g.posts.findIndex((p) => !p.read); return i < 0 ? g.posts.length - 1 : i; };
