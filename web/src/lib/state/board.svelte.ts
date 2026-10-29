// The student forum's feed (screens/forum/Board): asked for as soon as the app knows a student is here (the speed
// rule: a page never waits for its data when it opens), refreshed quietly when the tab comes into view, one topic or
// all. In memory only: it holds other students' words, so it stays out of the launch copy.
import { api, type Thread, type Topic } from '../api';

export const PAGE = 40; // the server's page
export const board = $state({ topic: null as Topic | null, list: null as Thread[] | null, more: false });
let seq = 0;

export async function loadBoard(): Promise<void> {
  const mine = ++seq, topic = board.topic;
  try {
    const l = await api.threads(topic);
    if (mine === seq) { board.list = l; board.more = l.length >= PAGE; }
  } catch { if (mine === seq && !board.list) board.list = []; }
}

/** The next page down (older bumps). */
export async function moreBoard(): Promise<void> {
  const last = board.list?.at(-1);
  if (!last || !board.more) return;
  const mine = seq, topic = board.topic;
  try {
    const l = await api.threads(topic, last.bumpedAt, last.id);
    if (mine === seq) { board.list = [...(board.list ?? []), ...l.filter((x) => !board.list!.some((y) => y.id === x.id))]; board.more = l.length >= PAGE; }
  } catch { /* the button stays: try again */ }
}

/** A thread changed in its sheet (a reply, "I'm in"): the feed's card follows; gone (deleted) when null. */
export function putThread(id: number, t: Thread | null): void {
  if (!board.list) return;
  board.list = t ? board.list.map((x) => (x.id === id ? { ...x, ...t } : x)) : board.list.filter((x) => x.id !== id);
}
