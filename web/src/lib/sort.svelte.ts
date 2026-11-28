// Sorting for every long list of people: a list names itself and declares its orders, the engine remembers the
// choice per list (this device) and sorts. The control is ui/SortChip.svelte. A new list needs only its orders:
//   const ORDERS: Order<Row>[] = [usual(), byName((r) => r.fullName)];
//   const rows = $derived(sorted('friends', ORDERS, list));  +  <SortChip list="friends" orders={ORDERS} />
import type { Key } from './i18n/index.svelte';
import { cyrKey } from './search';

/** One way to order a list. The first of a list's orders is its default; without `by` the rows stay as they came
 *  (the server's order). `desc`: biggest first. Rows without a value go last either way. */
export type Order<T> = { id: string; label: Key; by?: (row: T) => string | number | null | undefined; desc?: boolean };

/** The orders most lists share. */
export const usual = <T>(label: Key = 'sort.usual'): Order<T> => ({ id: 'usual', label });
// Latin and Cyrillic names mixed: "Misgarli" among the Cyrillic M names (cyrKey), not before them all
export const byName = <T>(by: (row: T) => string): Order<T> => ({ id: 'name', label: 'sort.name', by: (row) => cyrKey(by(row) ?? '') });
export const newest = <T>(by: (row: T) => number | null | undefined, label: Key = 'sort.new'): Order<T> => ({ id: 'new', label, by, desc: true });

const KEY = 'kbtu.sort';
const kept = $state<Record<string, string>>((() => { try { return JSON.parse(localStorage.getItem(KEY) ?? '{}') || {}; } catch { return {}; } })());

/** The order a list shows in now: the remembered one, else its first. */
export const orderOf = <T>(list: string, orders: Order<T>[]): Order<T> => orders.find((o) => o.id === kept[list]) ?? orders[0];
export function setOrder(list: string, id: string) {
  kept[list] = id;
  try { localStorage.setItem(KEY, JSON.stringify(kept)); } catch { /* blocked: this visit only */ }
}

const text = new Intl.Collator(undefined, { numeric: true, sensitivity: 'base' });
const none = (v: unknown) => v == null || v === '';
/** `rows` in the list's chosen order (a copy; the sort is stable, so ties keep the order they came in). */
export function sorted<T>(list: string, orders: Order<T>[], rows: T[]): T[] {
  const { by, desc } = orderOf(list, orders);
  if (!by) return rows;
  const dir = desc ? -1 : 1;
  return rows.map((row) => ({ row, v: by(row) })).sort((a, b) => {
    if (none(a.v) || none(b.v)) return +none(a.v) - +none(b.v);
    return dir * (typeof a.v === 'string' || typeof b.v === 'string' ? text.compare(String(a.v), String(b.v)) : (a.v as number) - (b.v as number));
  }).map((x) => x.row);
}
