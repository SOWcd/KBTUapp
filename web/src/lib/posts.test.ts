import { describe, expect, it } from 'vitest';
import type { EventCard, Post } from './api';
import { storyGroups, storyStart } from './posts';

const p = (id: number, org: number, at: number, read = false) => ({ id, org: { id: org }, createdAt: at, read }) as unknown as Post;

describe('storyGroups', () => {
  it('broadcasts first, then unread clubs, newest first; posts oldest first; old ones left out', () => {
    const now = 100 * 86400;
    const g = storyGroups([p(1, 9, now - 50, true)], [p(2, 5, now - 10, true), p(3, 6, now - 400), p(4, 6, now - 300, true), p(5, 7, now - 40 * 86400)], now);
    expect(g.map((x) => x.org.id)).toEqual([9, 6, 5]);
    expect(g[1].items.map((x) => x.post!.id)).toEqual([3, 4]);
    expect(g[1].unread).toBe(true);
    expect(storyStart(g[1])).toBe(0);
    expect(storyStart(g[2])).toBe(0); // all read: the newest
  });
  it("a club's new event joins its circle, unseen until seen; old or over events stay out", () => {
    const now = 100 * 86400;
    const e = (id: number, org: number, pub: number, starts: number) => ({ id, org: { id: org }, status: 'published', publishedAt: pub, startsAt: starts, endsAt: null }) as unknown as EventCard;
    const g = storyGroups([], [p(2, 5, now - 10, true)], now, [e(7, 5, now - 5, now + 3600), e(8, 6, now - 20 * 86400, now + 3600), e(9, 6, now - 60, now - 4 * 3600)]);
    expect(g.map((x) => x.org.id)).toEqual([5]);
    expect(g[0].items.map((x) => x.ev?.id ?? x.post!.id)).toEqual([2, 7]);
    expect(g[0].unread).toBe(true);
    expect(storyStart(g[0])).toBe(1);
    expect(storyGroups([], [p(2, 5, now - 10, true)], now, [e(7, 5, now - 5, now + 3600)], new Set([7]))[0].unread).toBe(false);
  });
});
