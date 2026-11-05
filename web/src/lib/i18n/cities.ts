// the cities the picker offers (Settings → Privacy → City; owner, Nov 3): Kazakhstan's big ones, as each language writes
// them; any other is typed in (the server takes letters, spaces, hyphens: account.CITY_RE)
export const CITIES: Record<'ru' | 'kk' | 'en', string>[] = [
  ['Алматы', 'Алматы', 'Almaty'],
  ['Астана', 'Астана', 'Astana'],
  ['Шымкент', 'Шымкент', 'Shymkent'],
  ['Актобе', 'Ақтөбе', 'Aktobe'],
  ['Актау', 'Ақтау', 'Aktau'],
  ['Атырау', 'Атырау', 'Atyrau'],
  ['Караганда', 'Қарағанды', 'Karaganda'],
  ['Тараз', 'Тараз', 'Taraz'],
  ['Уральск', 'Орал', 'Uralsk'],
  ['Кызылорда', 'Қызылорда', 'Kyzylorda'],
  ['Туркестан', 'Түркістан', 'Turkistan'],
  ['Талдыкорган', 'Талдықорған', 'Taldykorgan'],
  ['Конаев', 'Қонаев', 'Konaev'],
  ['Усть-Каменогорск', 'Өскемен', 'Oskemen'],
  ['Семей', 'Семей', 'Semey'],
  ['Павлодар', 'Павлодар', 'Pavlodar'],
  ['Костанай', 'Қостанай', 'Kostanay'],
  ['Кокшетау', 'Көкшетау', 'Kokshetau'],
  ['Петропавловск', 'Петропавл', 'Petropavl'],
  ['Жезказган', 'Жезқазған', 'Zhezkazgan'],
  ['Темиртау', 'Теміртау', 'Temirtau'],
].map(([ru, kk, en]) => ({ ru, kk, en }));

// smaller towns: never offered, but a typed or imported one still shows in my language
const MORE = [
  ['Каскелен', 'Қаскелең', 'Kaskelen'], ['Кульсары', 'Құлсары', 'Kulsary'], ['Кентау', 'Кентау', 'Kentau'],
  ['Аксай', 'Ақсай', 'Aksai'], ['Сатпаев', 'Сәтбаев', 'Satpaev'], ['Шардара', 'Шардара', 'Shardara'],
  ['Аягоз', 'Аягөз', 'Ayagoz'], ['Жетысай', 'Жетісай', 'Zhetisay'],
].map(([ru, kk, en]) => ({ ru, kk, en }));
// other spellings seen in the roster import (prod, Nov 5)
const ALSO: Record<string, string> = { qaragandy: 'Karaganda', karagandy: 'Karaganda', 'ust-kamenogorsk': 'Oskemen', oral: 'Uralsk',
  'петропавлск': 'Petropavl', 'талыдыкурган': 'Taldykorgan', 'чардара': 'Shardara', konaev: 'Konaev', 'конаев': 'Konaev' };
const key = (s: string) => s.toLowerCase().replace(/[^\p{L}-]/gu, '');
const BY = new Map<string, Record<'ru' | 'kk' | 'en', string>>();
for (const c of [...CITIES, ...MORE]) for (const n of [c.ru, c.kk, c.en]) BY.set(key(n), c);
for (const [a, en] of Object.entries(ALSO)) BY.set(key(a), BY.get(key(en))!);

/** A city as stored (any language, any known spelling) in the app's language; an unknown one as typed. */
export const cityName = (raw: string, lang: 'ru' | 'kk' | 'en') => BY.get(key(raw))?.[lang] ?? raw;
