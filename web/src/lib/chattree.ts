// A club's groups as tree rows (Studio → Chats, DMP): main → its departments → their groups, then other and loose ones.
// Each row knows its depth and which ancestors' lines run past it (rails), so the view draws the connectors in CSS.
import type { ChatTree, TreeChat } from './api';

type Bare =
  | { key: string; kind: 'main'; chat: TreeChat | null }
  | { key: string; kind: 'dept'; dept: ChatTree['depts'][number] }
  | { key: string; kind: 'head'; head: 'other' | 'loose'; n: number }
  | { key: string; kind: 'chat'; chat: TreeChat; loose: boolean };
export type TreeRow = Bare & { depth: number; rails: boolean[]; last: boolean };

type Item = { row: Bare; kids: Item[] };

const k = (c: TreeChat, i: number) => (c.id != null ? `c${c.id}` : `s${i}`);

/** The rows of one tree, `base` levels in (DMP: 1, under its organisation's row). */
export function treeRows(t: ChatTree, base = 0): TreeRow[] {
  const chats = (l: TreeChat[], loose = false, pre = ''): Item[] => l.map((c, i) => ({ row: { key: pre + k(c, i), kind: 'chat', chat: c, loose }, kids: [] }));
  const kids: Item[] = [
    ...t.depts.map((d) => ({ row: { key: `d${d.id}`, kind: 'dept' as const, dept: d }, kids: chats(d.chats, false, `d${d.id}`) })),
    ...(t.other.length ? [{ row: { key: 'other', kind: 'head' as const, head: 'other' as const, n: t.other.length }, kids: chats(t.other, false, 'o') }] : []),
    ...(t.loose.length ? [{ row: { key: 'loose', kind: 'head' as const, head: 'loose' as const, n: t.loose.length }, kids: chats(t.loose, true, 'l') }] : []),
  ];
  const out: TreeRow[] = [];
  const walk = (it: Item, depth: number, rails: boolean[], last: boolean) => {
    out.push({ ...it.row, depth, rails, last });
    it.kids.forEach((c, i) => walk(c, depth + 1, depth > base ? [...rails, !last] : rails, i === it.kids.length - 1));
  };
  walk({ row: { key: 'main', kind: 'main', chat: t.main }, kids }, base, [], true);
  return out;
}

/** The tree with group `c` placed (null: loose again), as the server will answer: the tap shows it at once. A main
 *  group placed by hand before goes loose. */
export function moved(tr: ChatTree, c: TreeChat, place: TreeChat['place'], tag?: number): ChatTree {
  const strip = (l: TreeChat[]) => l.filter((x) => x.id !== c.id);
  const n: TreeChat = { ...c, place, tag: place === 'dept' ? (tag ?? null) : null, by: place ? 'hand' : null, guess: null };
  const next: ChatTree = { ...tr, main: tr.main?.id === c.id ? null : tr.main, depts: tr.depts.map((d) => ({ ...d, chats: strip(d.chats) })),
    other: strip(tr.other), loose: strip(tr.loose) };
  if (place === 'main') {
    if (next.main) next.loose = [...next.loose, { ...next.main, by: null, place: null, tag: null }];
    next.main = n;
  } else if (place === 'dept') next.depts = next.depts.map((d) => (d.id === tag ? { ...d, chats: [...d.chats, n] } : d));
  else if (place === 'other') next.other = [...next.other, n];
  else next.loose = [...next.loose, n];
  return next;
}
