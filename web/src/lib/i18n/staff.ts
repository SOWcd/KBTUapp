// sw() and swn(), "staff words": t() and tn() that also know the staff and organizer screens' words (staff.ru.ts).
// Those ~500 entries stay out of the start bundle: a screen that imports this module carries them in its own chunk, so
// they are in memory before any of its sw() calls run. Every other key falls through to t()/tn().
import { i18n, show, t, tn, type Key } from './index.svelte';
import ru, { type StaffKey } from './staff.ru';
import kk from './staff.kk';
import en from './staff.en';

export type { StaffKey };
const STAFF = { ru, kk, en };
const staff = (key: Key | StaffKey): key is StaffKey => key in ru;

export function sw(key: Key | StaffKey, vars?: Record<string, string | number>): string {
  return staff(key) ? show(STAFF[i18n.lang][key] ?? ru[key], undefined, vars) : t(key, vars);
}

export function swn(key: Key | StaffKey, n: number, vars?: Record<string, string | number>): string {
  return staff(key) ? show(STAFF[i18n.lang][key] ?? ru[key], n, vars) : tn(key, n, vars);
}
