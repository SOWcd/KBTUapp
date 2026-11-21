// The one search's match, the server's (server/kbtu/logic/search.py) for lists already held: any case in any script,
// Russian yo as ye, every word of the query starting a word of one of the names, in any order.
// Kazakh letters as the Russian ones a Russian keyboard types for them (the server's table, search.py _KK)
const KK = '\u0451\u04d9\u0493\u049b\u04a3\u04e9\u04b1\u04af\u04bb\u0456', RU = '\u0435\u0430\u0433\u043a\u043d\u043e\u0443\u0443\u0445\u0438';
const words = (s: string) => s.normalize('NFKC').toLowerCase().replace(/[\u0451\u04d9\u0493\u049b\u04a3\u04e9\u04b1\u04af\u04bb\u0456]/g, (c) => RU[KK.indexOf(c)]).match(/[\p{L}\p{N}]+/gu) ?? [];

// Russian letters spelled in Latin, then the sounds people swap: Aigerim typed in either script, Zhansaya as well
const LAT: Record<string, string> = {
  '\u0430': 'a', '\u0431': 'b', '\u0432': 'v', '\u0433': 'g', '\u0434': 'd', '\u0435': 'e', '\u0436': 'zh', '\u0437': 'z', '\u0438': 'i',
  '\u0439': 'i', '\u043a': 'k', '\u043b': 'l', '\u043c': 'm', '\u043d': 'n', '\u043e': 'o', '\u043f': 'p', '\u0440': 'r', '\u0441': 's',
  '\u0442': 't', '\u0443': 'u', '\u0444': 'f', '\u0445': 'h', '\u0446': 'ts', '\u0447': 'ch', '\u0448': 'sh', '\u0449': 'sh', '\u044a': '',
  '\u044b': 'y', '\u044c': '', '\u044d': 'e', '\u044e': 'iu', '\u044f': 'ia',
};
const skel = (w: string) => [...w].map((c) => LAT[c] ?? c).join('').replace(/kh/g, 'h').replace(/[jy]/g, 'i').replace(/ya/g, 'ia').replace(/yu/g, 'iu')
  .replace(/(.)\1/g, '$1');
// a typo or two: the query word against the start of a name's word, one edit per 3 letters typed
function near(w: string, t: string): boolean {
  if (w.length < 4) return false;
  const p = t.slice(0, w.length + 2), max = Math.floor(w.length / 3);
  let prev = Array.from({ length: p.length + 1 }, (_, j) => j);
  for (let i = 1; i <= w.length; i++) {
    const cur = [i];
    for (let j = 1; j <= p.length; j++) cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (w[i - 1] === p[j - 1] ? 0 : 1));
    prev = cur;
  }
  return Math.min(...prev.slice(Math.max(1, w.length - max))) <= max;
}

export function hit(q: string, names: (string | null | undefined)[]): boolean {
  const ws = words(q);
  if (!ws.length) return false;
  const sw = ws.map(skel);
  return names.some((n) => {
    const ts = words(n ?? '');
    if (ws.every((w) => ts.some((t) => t.startsWith(w)))) return true;
    const st = ts.map(skel); // ponytail: fuzzy over every name on each keystroke, fine for a few hundred rows
    return sw.every((w) => st.some((t) => t.startsWith(w) || near(w, t)));
  });
}

type Named = { orig?: Record<string, string>; i18n?: Partial<Record<string, Record<string, string | undefined> | undefined>> };
/** A club's or an event's `keys` as shown, as typed (`orig`) and in each language the AI wrote (`i18n`). */
export const namesOf = (x: Named, ...keys: string[]): (string | undefined)[] =>
  keys.flatMap((k) => [(x as Record<string, unknown>)[k] as string | undefined, x.orig?.[k], ...Object.values(x.i18n ?? {}).map((t) => t?.[k])]);
