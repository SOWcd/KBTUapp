// Language: the person's explicit choice → their Telegram language → Russian.
// `i18n.lang` is reactive state, so every t() in a template re-renders when it changes —
// no reload (a reload looks like a crash).
import ru, { type Dict, type Key, type Plural } from './ru';
import { tg } from '../tg';

export type Lang = 'ru' | 'kk' | 'en';
export const LANGS: Lang[] = ['ru', 'kk', 'en'];
// each language by its own short name, the same whatever the app's language is
export const LANG_NAMES: Record<Lang, string> = { ru: 'Рус', kk: 'Қаз', en: 'Eng' };
export type { Key };

// Russian is every missing key's fallback, so it ships in the boot bundle; the other two are their own chunks (a quarter
// of what the app loaded at start): the app's language is loaded before the first render (main.ts), the rest when idle
const DICTS: Partial<Record<Lang, Dict>> = { ru };
const LOAD: Record<Exclude<Lang, 'ru'>, () => Promise<{ default: Dict }>> = { kk: () => import('./kk'), en: () => import('./en') };
const KEY = 'kb-lang';

/** Resolves once the language's dictionary is in memory (at once for one already there). */
export function loadLang(lang: Lang): Promise<void> {
  if (lang === 'ru' || DICTS[lang]) return Promise.resolve();
  return LOAD[lang]().then((m) => { DICTS[lang] = m.default; });
}

function detect(): Lang {
  try {
    const saved = localStorage.getItem(KEY) as Lang | null;
    if (saved && LANGS.includes(saved)) return saved;
  } catch { /* storage blocked */ }
  const code = (tg.user?.language_code || '').slice(0, 2) as Lang;
  return LANGS.includes(code) ? code : 'ru';
}

export const i18n = $state({ lang: detect() });

export function setLang(lang: Lang): void {
  i18n.lang = lang;
  try { localStorage.setItem(KEY, lang); } catch { /* storage blocked */ }
  document.documentElement.lang = lang;
}

const rules: Record<Lang, Intl.PluralRules> = {
  ru: new Intl.PluralRules('ru'),
  kk: new Intl.PluralRules('kk'),
  en: new Intl.PluralRules('en'),
};

function fill(s: string, vars?: Record<string, string | number>): string {
  return vars ? s.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? String(vars[k]) : m)) : s;
}

/** Plain string. Plural entries need tn(). */
export function t(key: Key, vars?: Record<string, string | number>): string {
  const e = DICTS[i18n.lang]?.[key] ?? ru[key];
  return fill(typeof e === 'string' ? e : e.other, vars);
}

/** Counted string: picks one / few / many / other by the language's own rules; {n} is the count. */
export function tn(key: Key, n: number, vars?: Record<string, string | number>): string {
  const e = DICTS[i18n.lang]?.[key] ?? ru[key];
  if (typeof e === 'string') return fill(e, { n, ...vars });
  const cat = rules[i18n.lang].select(n) as keyof Plural;
  return fill(e[cat] ?? e.other, { n: fmtNum(n), ...vars });
}

const nums: Partial<Record<Lang, Intl.NumberFormat>> = {};
/** 3 000, 12 400 — grouped the local way. */
export function fmtNum(n: number): string {
  const f = (nums[i18n.lang] ??= new Intl.NumberFormat(i18n.lang === 'en' ? 'en-US' : i18n.lang));
  return f.format(n);
}

/** Tenge amount: «3 000 ₸». */
/** An event's place as shown; empty while it's to be confirmed (a room asked of DMP by memo) */
export const placeOf = (place: string): string => place || t('event.placeTba');
/** A class's subject in the app's language when the sign-in brought it, else as it came */
export const subjectOf = (c: { subject: string; names?: Partial<Record<Lang, string>> | null }): string => c.names?.[i18n.lang] || c.subject;

export function money(n: number): string {
  // always grouped with a no-break space: «1 500 ₸» (Russian rules leave 4-digit numbers ungrouped)
  return String(Math.round(n)).replace(/\B(?=(\d{3})+(?!\d))/g, '\u00a0') + '\u00a0₸';
}

/** "Dana is going" · "Dana, Arman are going" · "Dana, Arman and 3 more". */
export function friendsLine(names: string[], past = false): string {
  if (past) return t('event.friendsWent', { names: names.length > 2 ? t('event.goingWith', { names: names.slice(0, 2).join(', '), n: names.length - 2 }) : names.join(', ') });
  if (names.length === 1) return t('event.friendGoes', { name: names[0] });
  if (names.length === 2) return t('event.friendsGo', { names: names.join(', ') });
  return t('event.goingWith', { names: names.slice(0, 2).join(', '), n: names.length - 2 });
}
