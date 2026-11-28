// aw() and awn(), "admissions words": t() and tn() that also know the admissions' words (ako.ru.ts), for the applicant's
// page and the team's desk. Like staff.ts, they stay out of the start bundle: the screens that import this carry them.
// Every other key falls through to t()/tn().
import { i18n, show, t, tn, type Key } from './index.svelte';
import ru, { type AkoKey } from './ako.ru';
import main from './ru';
import kk from './ako.kk';
import en from './ako.en';

export type { AkoKey };
const AKO = { ru, kk, en };
const ours = (key: Key | AkoKey): key is AkoKey => key in ru;
// a key neither dictionary has comes back as itself: a document's optional how-to or link (ako.docHow.<doc>) is asked for by name
const known = (key: Key | AkoKey): key is Key => key in main;

export function aw(key: Key | AkoKey, vars?: Record<string, string | number>): string {
  return ours(key) ? show(AKO[i18n.lang][key] ?? ru[key], undefined, vars) : known(key) ? t(key, vars) : key;
}

export function awn(key: Key | AkoKey, n: number, vars?: Record<string, string | number>): string {
  return ours(key) ? show(AKO[i18n.lang][key] ?? ru[key], n, vars) : known(key) ? tn(key, n, vars) : key;
}
