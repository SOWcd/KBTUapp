// Post labels (SPEC §4.10): the composer's chips by code, named in the UI language; an older free-text tag shows as is.
import type { EventCard, Post, PostTag } from './api';
import { SvelteSet } from 'svelte/reactivity';
import { t } from './i18n/index.svelte';

export const POST_TAGS: PostTag[] = ['important', 'recruiting', 'results', 'news'];
export const tagName = (tag: string | null): string | null =>
  tag && (POST_TAGS as string[]).includes(tag) ? t(`tag.${tag}` as 'tag.news') : tag;

/** News as stories: one circle per club, the broadcasts (DMP, KBTU App) first, then clubs with something
 *  unread, then by their newest. A circle holds the club's posts and its new events, oldest first, opening at the first unseen, as
 *  Telegram's stories do. Posts of the last 30 days; events published in the last 14 and not over yet. Older posts stay
 *  on the club's page. An event is "seen" on this device (`seen`), a post read on the server. */
export type Story = { post: Post; ev?: never } | { ev: EventCard; post?: never };
export interface StoryGroup { org: Post['org']; items: Story[]; unread: boolean; cast: boolean }
export const STORY_DAYS = 30, EVENT_DAYS = 14;
const at = (s: Story) => (s.post ? s.post.createdAt : s.ev!.publishedAt ?? s.ev!.startsAt);
export const unseen = (s: Story, seen: ReadonlySet<number>) => (s.post ? !s.post.read : !seen.has(s.ev!.id));
export function storyGroups(casts: Post[], posts: Post[], now: number, events: EventCard[] = [], seen: ReadonlySet<number> = new Set()): StoryGroup[] {
  const by = new Map<number, StoryGroup>();
  const put = (org: Post['org'], s: Story, cast: boolean, id: string) => {
    const g = by.get(org.id) ?? { org, items: [], unread: false, cast };
    if (!g.items.some((x) => (x.post ? 'p' + x.post.id : 'e' + x.ev!.id) === id)) g.items.push(s);
    g.unread ||= unseen(s, seen);
    by.set(org.id, g);
  };
  for (const [cast, list] of [[true, casts], [false, posts]] as const)
    for (const p of list) if (p.createdAt >= now - STORY_DAYS * 86400) put(p.org, { post: p }, cast, 'p' + p.id);
  for (const e of events)
    if (e.status === 'published' && (e.publishedAt ?? 0) >= now - EVENT_DAYS * 86400 && (e.endsAt ?? e.startsAt + 3 * 3600) > now) put(e.org, { ev: e }, false, 'e' + e.id);
  const newest = (g: StoryGroup) => Math.max(...g.items.map(at));
  for (const g of by.values()) g.items.sort((a, b) => at(a) - at(b));
  return [...by.values()].sort((a, b) => +b.cast - +a.cast || +b.unread - +a.unread || newest(b) - newest(a));
}
/** where a club's stories open: its first unseen, else its newest */
export const storyStart = (g: StoryGroup, seen: ReadonlySet<number> = new Set()): number => { const i = g.items.findIndex((s) => unseen(s, seen)); return i < 0 ? g.items.length - 1 : i; };

// the events seen in the circles, on this device (a per-viewer convenience); reactive, so a circle's ring goes at once
const SEEN = 'kbtu.seenEvents';
export const seenEv = new SvelteSet<number>((() => { try { return JSON.parse(localStorage.getItem(SEEN) ?? '[]') as number[]; } catch { return []; } })());
export function markSeen(id: number): void {
  if (seenEv.has(id)) return;
  seenEv.add(id);
  try { localStorage.setItem(SEEN, JSON.stringify([...seenEv].slice(-300))); } catch { /* blocked */ }
}
