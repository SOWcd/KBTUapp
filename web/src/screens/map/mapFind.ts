// Finding a place on the campus map (CampusMap.svelte, its keypad MapPad): a room by its number, a named place
// (canteen, Independence Hall; lib/map SPOTS), or an entrance by its name on the route graph. What the keypad says
// while one types, and the names the map shows for floors and rooms.
import { t } from '../../lib/i18n/index.svelte';
import { SPOTS, roomOf, floorOf, spotOf } from '../../lib/map';
import type { Graph } from '../../lib/route';
import { doorHint, adminNote, type PadCheck } from './MapPad.svelte';

export const floorName = (n: number) => (n ? t('route.floor', { n }) : t('route.basement'));
// The graph also gives the keypad the entrances on the basement floor.
export const doorNamed = (graph: Graph | null, text: string) => graph?.n.find((n) => n.k === 'x' && n.name === text) ?? null;

/** what the keypad says of the text so far: found (its floor), near a numbered room, or not a room */
export function checkFind(text: string, graph: Graph | null, rooms: Record<string, number[][]>[]): PadCheck {
  const dn = doorNamed(graph, text);
  if (dn) return { ok: true, tone: 'ok', hint: doorHint(dn, floorName(dn.f)) };
  const sp = spotOf(text);
  if (sp) return { ok: true, tone: 'ok', hint: floorName(sp.f ?? floorOf(sp.room) ?? 0) + adminNote(sp.room) };
  const r = roomOf(text), f = floorOf(r);
  if (!r || f == null) return text.length >= 3 || /[^\d\u0430-\u0433]/.test(text) ? { ok: false, tone: 'no', hint: t('pad.noRoom') } : { ok: false, hint: t('pad.roomHint') };
  return rooms[f]?.[r] ? { ok: true, tone: 'ok', hint: floorName(f) + adminNote(r) } : { ok: true, hint: t('pad.near', { room: r }) };
}

/** a room's name on its card: a named place's own name (Uni-Q's library is 158), else "Room 305" */
export function roomTitle(room: string): string {
  const sp = SPOTS.find((x) => x.room === room);
  return sp ? t(`route.spot.${sp.k}` as 'route.spot.canteen') : t('map.roomTitle', { room });
}
