import { describe, expect, it } from 'vitest';
import type { Post } from './api';
import { storyGroups, storyStart } from './posts';

const p = (id: number, org: number, at: number, read = false) => ({ id, org: { id: org }, createdAt: at, read }) as unknown as Post;

describe('storyGroups', () => {
  it('broadcasts first, then unread clubs, newest first; posts oldest first; old ones left out', () => {
    const now = 100 * 86400;
    const g = storyGroups([p(1, 9, now - 50, true)], [p(2, 5, now - 10, true), p(3, 6, now - 400), p(4, 6, now - 300, true), p(5, 7, now - 40 * 86400)], now);
    expect(g.map((x) => x.org.id)).toEqual([9, 6, 5]);
    expect(g[1].posts.map((x) => x.id)).toEqual([3, 4]);
    expect(g[1].unread).toBe(true);
    expect(storyStart(g[1])).toBe(0);
    expect(storyStart(g[2])).toBe(0); // all read: the newest
  });
});
