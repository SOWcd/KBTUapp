// Keep the matching rules in step with server/kbtu/logic/search.py.
const KK = '\u0451\u04d9\u0493\u049b\u04a3\u04e9\u04b1\u04af\u04bb\u0456';
const RU = '\u0435\u0430\u0433\u043a\u043d\u043e\u0443\u0443\u0445\u0438';
const lower = (s: string) => s.normalize('NFKC').toLowerCase();
const words = (s: string) => s.match(/[\p{L}\p{N}]+/gu) ?? [];
const fold = (s: string) => s.replace(/[\u0451\u04d9\u0493\u049b\u04a3\u04e9\u04b1\u04af\u04bb\u0456]/g, (c) => RU[KK.indexOf(c)]);

// The same physical keys on US QWERTY, Russian and standard Kazakh Cyrillic.
const EN_KEYS = "`qwertyuiop[]asdfghjkl;'zxcvbnm,.";
const RU_KEYS = '\u0451\u0439\u0446\u0443\u043a\u0435\u043d\u0433\u0448\u0449\u0437\u0445\u044a\u0444\u044b\u0432\u0430\u043f\u0440\u043e\u043b\u0434\u0436\u044d\u044f\u0447\u0441\u043c\u0438\u0442\u044c\u0431\u044e';
const KK_ROW = '\u04d9\u0456\u04a3\u0493\u04af\u04b1\u049b\u04e9\u04bb';
const EN_ROW = '2345890-=';
const SHIFTED = '~{}:"<>@#$%*()_+';
const UNSHIFTED = "`[];',." + EN_ROW;
const layouts = [
  [EN_KEYS, RU_KEYS],
  [EN_KEYS + EN_ROW, RU_KEYS + KK_ROW],
  [RU_KEYS + KK_ROW, EN_KEYS + EN_ROW],
  [RU_KEYS + EN_ROW, RU_KEYS + KK_ROW],
  [RU_KEYS + KK_ROW, RU_KEYS + EN_ROW],
];

const LAT: Record<string, string> = {
  '\u0430': 'a', '\u0431': 'b', '\u0432': 'v', '\u0433': 'g', '\u0434': 'd', '\u0435': 'e', '\u0436': 'zh', '\u0437': 'z',
  '\u0438': 'i', '\u0439': 'y', '\u043a': 'k', '\u043b': 'l', '\u043c': 'm', '\u043d': 'n', '\u043e': 'o', '\u043f': 'p',
  '\u0440': 'r', '\u0441': 's', '\u0442': 't', '\u0443': 'u', '\u0444': 'f', '\u0445': 'h', '\u0446': 'ts', '\u0447': 'ch',
  '\u0448': 'sh', '\u0449': 'sh', '\u044a': '', '\u044b': 'y', '\u044c': '', '\u044d': 'e', '\u044e': 'yu', '\u044f': 'ya',
  '\u00e4': 'a', '\u00e1': 'a', '\u011f': 'g', '\u01f5': 'g', '\u0131': 'i', '\u00ed': 'i', '\u00f1': 'n', '\u0144': 'n',
  '\u00f6': 'o', '\u00f3': 'o', '\u00fc': 'u', '\u016b': 'u', '\u00fa': 'u', '\u00fd': 'u', '\u015f': 'sh', '\u015b': 'sh',
  '\u00e7': 'ch', '\u0107': 'ch', '\u010d': 'ch', '\u017e': 'zh', j: 'zh', q: 'k',
};
const latinChars = new RegExp(`[${Object.keys(LAT).join('')}]`, 'g');
// LAT turned around for sorting names: a Latin letter becomes its Cyrillic one (m, i, q to the Cyrillic em, i, ka), so "Misgarli"
// sorts among the Cyrillic M names instead of before all Cyrillic ones.
// ponytail: single letters only; c, w, x, j stay Latin (no one-letter Cyrillic in LAT), add them there if lists ask
const CYR: Record<string, string> = {};
for (const [k, v] of Object.entries(LAT)) if (k >= '\u0400' && v.length === 1) CYR[v] ??= k;
for (const [k, v] of Object.entries(LAT)) if (k < '\u0400' && CYR[v]) CYR[k] ??= CYR[v];
/** A name's sort key: lower case, Latin letters as Cyrillic. */
export const cyrKey = (s: string) => lower(s).replace(/./gu, (c) => CYR[c] ?? c);
const aliases: Record<string, string> = { shch: 'sh', kh: 'h', gh: 'g', ng: 'n', yu: 'iu', ye: 'e', y: 'i' };
const undouble = (s: string) => s.replace(/(\p{L})\1+/gu, '$1');
const skeleton = (s: string) => undouble(undouble(s).replace(latinChars, (c) => LAT[c])
  .replace(/shch|kh|gh|ng|[yi]+a|yu|ye|y/g, (s) => aliases[s] ?? 'a'));

// Most names use only BMP characters. Split only when a word needs code point indexing.
const chars = (s: string) => /[\ud800-\udbff]/.test(s) ? Array.from(s) : s;
type Chars = ReturnType<typeof chars>;
type Word = { text: string; latin: string; rawChars: Chars; latinChars: Chars; rawMask: number; latinMask: number };
type QueryWord = Word & { edits: number; latinEdits: number };
type Form = { words: QueryWord[]; prefix: number };
type Group = { forms: Form[]; split: Group[] };

function word(s: string): Word {
  const text = fold(s).replace(/\u00df/g, 'ss').replace(/\u03c2/g, '\u03c3'), latin = skeleton(text);
  const rawChars = chars(text), rawMask = letterMask(text);
  return { text, latin, rawChars, rawMask, latinChars: latin === text ? rawChars : chars(latin),
    latinMask: latin === text ? rawMask : letterMask(latin) };
}

function letterMask(s: string): number {
  let mask = 0;
  for (let i = 0; i < s.length; i++) {
    const code = s.codePointAt(i)!;
    mask |= 1 << (code & 31);
    if (code > 0xffff) i++;
  }
  return mask;
}

const nameCache = new Map<string, Word[]>();
function nameWords(name: string): Word[] {
  const cached = nameCache.get(name);
  if (cached) return cached;
  const terms = words(lower(name)).map(word);
  // A bounded cache keyed by text also works for callers that build a fresh names array on each keystroke.
  if (name.length <= 256) {
    if (nameCache.size === 16384) nameCache.delete(nameCache.keys().next().value!);
    nameCache.set(name, terms);
  }
  return terms;
}

const queryWords = (terms: string[]) => terms.map((s): QueryWord => {
  const w = word(s);
  const edits = /^\p{L}+$/u.test(s) ? Math.min(3, Math.floor(chars(s).length / 4)) : 0;
  return { ...w, edits, latinEdits: Math.min(edits, Math.floor(w.latinChars.length / 4)) };
});

function group(part: string, literal: string[]): Group {
  const forms: Form[] = [{ words: queryWords(literal), prefix: 3 }];
  const split = literal.length > 1 ? literal.map((s) => group(s, [s])) : [];
  if (/^\p{N}+$/u.test(part)) return { forms, split };
  let previous = part;
  for (const [from, to] of layouts) {
    let fixed = '';
    for (const c of part) {
      const key = UNSHIFTED[SHIFTED.indexOf(c)] ?? c;
      const i = from.indexOf(key);
      if (i < 0) {
        fixed = '';
        break;
      }
      fixed += to[i];
    }
    if (!fixed || fixed === part || fixed === previous) continue;
    previous = fixed;
    const terms = words(fixed);
    if (terms.length) forms.push({ words: queryWords(terms), prefix: 2 });
  }
  return { forms, split };
}

let lastQuery: string | undefined;
let groups: Group[] = [];
function prepare(q: string): Group[] {
  if (q === lastQuery) return groups;
  lastQuery = q;
  // Keep potential letter keys until after layout correction, even when they are punctuation in English.
  groups = (lower(q).match(/[\p{L}\p{N}`\[\];',.=~{}:"<>@#$%*()_+-]+/gu) ?? []).flatMap((part) => {
    const literal = words(part);
    return literal.length ? [group(part, literal)] : [];
  });
  return groups;
}

// Banded edit distance to a word prefix, with adjacent transpositions. Reuse the three rows across comparisons.
const scratch: number[][] = [[], [], []];
function near(w: Chars, t: Chars, max: number, missing: number): boolean {
  if (t.length + max < w.length) return false;
  // Every distinct missing letter costs at least one edit. Mask collisions can only skip this shortcut.
  for (let i = 0; missing; i++, missing &= missing - 1) {
    if (i === max) return false;
  }
  if (max === 1) return nearOne(w, t);
  let older = scratch[0], prev = scratch[1], cur = scratch[2];
  const end = Math.min(w.length + max, t.length), stop = max + 1;
  for (let j = 0; j <= max; j++) prev[j] = j;
  prev[max + 1] = stop;
  for (let i = 1; i <= w.length; i++) {
    const lo = Math.max(1, i - max), hi = Math.min(end, i + max);
    cur[lo - 1] = lo === 1 ? i : stop;
    cur[hi + 1] = stop;
    let best = cur[lo - 1];
    for (let j = lo; j <= hi; j++) {
      let distance = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + Number(w[i - 1] !== t[j - 1]));
      if (i > 1 && j > 1 && w[i - 1] === t[j - 2] && w[i - 2] === t[j - 1]) {
        distance = Math.min(distance, older[j - 2] + 1);
      }
      cur[j] = distance;
      if (distance < best) best = distance;
    }
    if (best > max) return false;
    const next = older;
    older = prev;
    prev = cur;
    cur = next;
  }
  return true;
}

function sameTail(w: Chars, t: Chars, i: number, j: number): boolean {
  for (; i < w.length; i++, j++) if (w[i] !== t[j]) return false;
  return true;
}

function nearOne(w: Chars, t: Chars): boolean {
  let i = 0;
  while (i < w.length && w[i] === t[i]) i++;
  if (i >= w.length - 1) return true;
  return sameTail(w, t, i + 1, i + 1) || sameTail(w, t, i + 1, i) || sameTail(w, t, i, i + 1) ||
    (w[i] === t[i + 1] && w[i + 1] === t[i] && sameTail(w, t, i + 2, i + 2));
}

function wordScore(w: QueryWord, terms: Word[], prefix: number, best: number): number {
  let result = 0;
  for (const t of terms) {
    if (t.text.startsWith(w.text)) return prefix;
    if (prefix === 3 && w.latin && t.latin.startsWith(w.latin)) result = 2;
  }
  if (result || best >= 1 || !w.edits) return result;
  for (const t of terms) {
    if (near(w.rawChars, t.rawChars, w.edits, w.rawMask & ~t.rawMask)) return 1;
    if (prefix === 3 && w.latinEdits && (w.rawChars !== w.latinChars || t.rawChars !== t.latinChars) &&
        near(w.latinChars, t.latinChars, w.latinEdits, w.latinMask & ~t.latinMask)) return 1;
  }
  return 0;
}

function nameScore(query: Group[], terms: Word[]): number {
  let level = 3;
  for (const { forms, split } of query) {
    let best = 0;
    for (const form of forms) {
      if (form.prefix <= best) continue;
      let match = form.prefix;
      for (const w of form.words) {
        match = Math.min(match, wordScore(w, terms, form.prefix, best));
        if (match <= best) break;
      }
      if (match > best) best = match;
    }
    if (best < 2 && split.length) best = Math.max(best, nameScore(split, terms));
    if (!best) return 0;
    level = Math.min(level, best);
  }
  return level;
}

/** Higher is better: exact prefix (3), transliterated or layout-corrected prefix (2), typo (1), no match (0). */
export function score(q: string, names: (string | null | undefined)[]): number {
  const query = prepare(q);
  if (!query.length) return 0;
  let best = 0;
  for (const name of names) {
    if (!name) continue;
    best = Math.max(best, nameScore(query, nameWords(name)));
    if (best === 3) break;
  }
  return best;
}

export function hit(q: string, names: (string | null | undefined)[]): boolean {
  return score(q, names) > 0;
}

type Named = { orig?: Record<string, string>; i18n?: Partial<Record<string, Record<string, string | undefined> | undefined>> };
/** A club's or an event's `keys` as shown, as typed (`orig`) and in each language the AI wrote (`i18n`). */
export const namesOf = (x: Named, ...keys: string[]): (string | undefined)[] =>
  keys.flatMap((k) => [(x as Record<string, unknown>)[k] as string | undefined, x.orig?.[k], ...Object.values(x.i18n ?? {}).map((t) => t?.[k])]);
