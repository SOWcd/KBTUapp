// Language: the person's explicit choice → their Telegram language → Russian.
// `i18n.lang` is reactive state, so every t() in a template re-renders when it changes —
// no reload (a reload looks like a crash).
import ru, { type Dict, type Key, type Plural } from './ru';
import kk from './kk';
import en from './en';
import { tg } from '../tg';

export type Lang = 'ru' | 'kk' | 'en';
export const LANGS: Lang[] = ['ru', 'kk', 'en'];
// each language by its own short name, the same whatever the app's language is
export const LANG_NAMES: Record<Lang, string> = { ru: 'Рус', kk: 'Қаз', en: 'Eng' };
export type { Key };

const DICTS: Record<Lang, Dict> = { ru, kk, en };
const KEY = 'kb-lang';

function detect(): Lang {
  try {
    const saved = localStorage.getItem(KEY) as Lang | null;
    if (saved && DICTS[saved]) return saved;
  } catch { /* storage blocked */ }
  const code = (tg.user?.language_code || '').slice(0, 2) as Lang;
  return DICTS[code] ? code : 'ru';
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
  const e = DICTS[i18n.lang][key] ?? ru[key];
  return fill(typeof e === 'string' ? e : e.other, vars);
}

/** Counted string: picks one / few / many / other by the language's own rules; {n} is the count. */
export function tn(key: Key, n: number, vars?: Record<string, string | number>): string {
  const e = DICTS[i18n.lang][key] ?? ru[key];
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
/** A class's subject in the app's language when the sign-in brought it (Oct 11), else as it came */
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
