// The one search's match, the server's (server/kbtu/logic/search.py) for lists already held: any case in any script,
// Russian yo as ye, every word of the query starting a word of one of the names, in any order.
// Kazakh letters as the Russian ones a Russian keyboard types for them (the server's table, search.py _KK)
const KK = '\u0451\u04d9\u0493\u049b\u04a3\u04e9\u04b1\u04af\u04bb\u0456', RU = '\u0435\u0430\u0433\u043a\u043d\u043e\u0443\u0443\u0445\u0438';
const words = (s: string) => s.normalize('NFKC').toLowerCase().replace(/[\u0451\u04d9\u0493\u049b\u04a3\u04e9\u04b1\u04af\u04bb\u0456]/g, (c) => RU[KK.indexOf(c)]).match(/[\p{L}\p{N}]+/gu) ?? [];

export function hit(q: string, names: (string | null | undefined)[]): boolean {
  const ws = words(q);
  return ws.length > 0 && names.some((n) => {
    const ts = words(n ?? '');
    return ws.every((w) => ts.some((t) => t.startsWith(w)));
  });
}

type Named = { orig?: Record<string, string>; i18n?: Partial<Record<string, Record<string, string | undefined> | undefined>> };
/** A club's or an event's `keys` as shown, as typed (`orig`) and in each language the AI wrote (`i18n`). */
export const namesOf = (x: Named, ...keys: string[]): (string | undefined)[] =>
  keys.flatMap((k) => [(x as Record<string, unknown>)[k] as string | undefined, x.orig?.[k], ...Object.values(x.i18n ?? {}).map((t) => t?.[k])]);
