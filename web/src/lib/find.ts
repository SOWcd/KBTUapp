// The global search (screens/afisha/Everything): every kind of thing the app holds, ranked by lib/search.ts's one
// matcher (any language, a Latin-typed Russian word, the wrong keyboard layout, a typo). Pure, so it is tested alone.
import { score } from './search';

export const KINDS = ['event', 'club', 'person', 'news', 'forum', 'place', 'subject'] as const;
export type Kind = typeof KINDS[number];
export type Found<T> = { item: T; score: number };
type Names = (string | null | undefined)[];

/** A long text's words: a typo alone is too loose there (every post has a word one letter off), so only prefixes count. */
export const textScore = (q: string, text: string | null | undefined): number => { const s = score(q, [text]); return s >= 2 ? s : 0; };

/** The matches of `items`, best first; equal ones keep the source's order (upcoming events soonest, as the lists do). */
export function rank<T>(q: string, items: Iterable<T>, of: (x: T) => number | Names, cap = 5): Found<T>[] {
  const out: Found<T>[] = [];
  for (const item of items) {
    const n = of(item), s = typeof n === 'number' ? n : score(q, n);
    if (s > 0) out.push({ item, score: s });
  }
  return out.sort((a, b) => b.score - a.score).slice(0, cap);
}

/** The groups in the order to show: the best match's group first, then by their best; a tie keeps KINDS' order. */
export function order<G extends Partial<Record<Kind, Found<unknown>[]>>>(groups: G): Kind[] {
  return KINDS.filter((k) => groups[k]?.length).sort((a, b) => groups[b]![0].score - groups[a]![0].score);
}

/** Once per item, the first copy kept (the same post in two feeds, a friend also suggested). */
export function once<T>(items: Iterable<T>, key: (x: T) => unknown): T[] {
  const seen = new Set<unknown>(), out: T[] = [];
  for (const x of items) if (!seen.has(key(x))) { seen.add(key(x)); out.push(x); }
  return out;
}
