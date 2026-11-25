// The Afisha's Today hero, personal (owner, Nov 25): its goal is to be tapped. Candidates come from what the app already
// holds (screens/afisha/List.svelte builds them); each kind has a fixed base, times what this person taps, learned on
// this phone only: the server gets anonymous totals per kind (logic/stats.py HERO), never who or which item.

/** In the base's order. The server's stats.HERO_KINDS has the same names (a test checks). */
export const KINDS = ['ticket', 'friends', 'club', 'news', 'forum', 'class', 'next'] as const;
export type Kind = (typeof KINDS)[number];
const BASE: Record<Kind, number> = { ticket: 7, friends: 6, club: 5, news: 4, forum: 3, class: 2, next: 1 };

/** key: the item (e12, p7, f3, c...), the same whatever kind it is now; today: my ticket for today, always first. */
export type Pick = { key: string; kind: Kind; today?: boolean };

/** s, t: shows and taps per kind; d, k, hit: today's first card and whether it was tapped; pd, pk, phit: the day before's;
 *  seen, tk: the items shown and tapped today (each counts once a day). */
export type Mem = { s: Partial<Record<Kind, number>>; t: Partial<Record<Kind, number>>; d: number; k: string; hit: boolean;
  pd: number; pk: string; phit: boolean; seen: string[]; tk: string[] };
export const fresh = (): Mem => ({ s: {}, t: {}, d: 0, k: '', hit: false, pd: 0, pk: '', phit: false, seen: [], tk: [] });

export const score = (kind: Kind, m: Mem): number => (((m.t[kind] ?? 0) + 1) / ((m.s[kind] ?? 0) + 3)) * BASE[kind];

/** Yesterday's first card, if it went untapped: never the hero two days running. */
export function stale(m: Mem, today: number): string {
  if (m.d === today) return m.pd === today - 1 && !m.phit ? m.pk : '';
  return m.d === today - 1 && !m.hit ? m.k : '';
}

/** Up to n cards: per kind its first item (items come in the kind's own order) that no other kind took and that isn't
 *  yesterday's untapped hero; my ticket for today first, then by score. */
export function rank<T extends Pick>(items: T[], m: Mem, today: number, n = 3): T[] {
  const no = stale(m, today), best = new Map<Kind, T>(), used = new Set<string>();
  for (const x of items) {
    if (best.has(x.kind) || used.has(x.key) || (x.key === no && !x.today)) continue;
    best.set(x.kind, x); used.add(x.key);
  }
  return [...best.values()].sort((a, b) => +!!b.today - +!!a.today || score(b.kind, m) - score(a.kind, m)).slice(0, n);
}

/** A new day: today's first card becomes the day before's. */
function roll(m: Mem, day: number): void {
  if (m.d !== day) Object.assign(m, { pd: m.d, pk: m.k, phit: m.hit, d: day, k: '', hit: false, seen: [], tk: [] });
}

/** A card came into view (first: as the hero, not swiped to). true: its first show today, to count. */
export function shown(m: Mem, x: Pick, day: number, first: boolean): boolean {
  roll(m, day);
  if (first && !m.k) m.k = x.key;
  if (m.seen.includes(x.key)) return false;
  m.seen.push(x.key);
  m.s[x.kind] = (m.s[x.kind] ?? 0) + 1;
  return true;
}

/** A card was tapped (anywhere on it). true: its first tap today, to count. */
export function tapped(m: Mem, x: Pick, day: number): boolean {
  roll(m, day);
  if (x.key === m.k) m.hit = true;
  if (m.tk.includes(x.key)) return false;
  m.tk.push(x.key);
  m.t[x.kind] = (m.t[x.kind] ?? 0) + 1;
  return true;
}

// On this phone only; a blocked or broken storage starts over (the base order).
const KEY = 'kbtu.hero';
export function load(): Mem {
  try {
    const j = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (j && typeof j.d === 'number' && Array.isArray(j.seen) && Array.isArray(j.tk)) return { ...fresh(), ...j };
  } catch { /* blocked or corrupted */ }
  return fresh();
}
export function save(m: Mem): void {
  try { localStorage.setItem(KEY, JSON.stringify(m)); } catch { /* blocked */ }
}
