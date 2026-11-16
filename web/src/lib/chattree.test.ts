import { describe, expect, it } from 'vitest';
import { moved, treeRows } from './chattree';
import type { ChatTree, TreeChat } from './api';

const c = (id: number): TreeChat => ({ id, title: `g${id}`, members: 1, forum: false, bot: true, sync: 'off', at: null, by: 'hand', place: 'other', tag: null });
const tree = (over: Partial<ChatTree> = {}): ChatTree => ({ org: {} as ChatTree['org'], groups: 0, kept: 0, last: null, main: c(1),
  depts: [{ id: 5, name: 'Media', color: '#f00', chats: [c(2), c(3)] }, { id: 6, name: 'Events', color: '#0f0', chats: [] }], other: [c(4)], loose: [], ...over });

describe('treeRows', () => {
  it('main, its departments and their groups, the lines that run past', () => {
    const r = treeRows(tree());
    expect(r.map((x) => [x.key, x.depth, x.rails.join(), x.last])).toEqual([
      ['main', 0, '', true], ['d5', 1, '', false], ['d5c2', 2, 'true', false], ['d5c3', 2, 'true', true],
      ['d6', 1, '', false], ['other', 1, '', true], ['oc4', 2, 'false', true]]);
  });
  it('loose groups last, under an organisation row (DMP)', () => {
    const r = treeRows(tree({ main: null, other: [], loose: [c(9)] }), 1);
    expect(r[0]).toMatchObject({ kind: 'main', chat: null, depth: 1 });
    expect(r.at(-1)).toMatchObject({ key: 'lc9', depth: 3, rails: [false], loose: true });
  });
  it('a placed group moves at once; the old main goes loose', () => {
    const t = moved(tree(), c(4), 'main');
    expect([t.main?.id, t.other.length, t.loose.map((x) => x.id)]).toEqual([4, 0, [1]]);
    expect(moved(t, c(4), 'dept', 6).depts[1].chats.map((x) => x.id)).toEqual([4]);
  });
});
