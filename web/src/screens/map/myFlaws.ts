// "Something's wrong here" on the campus map (CampusMap.svelte): a long press in place marks the spot (the map's
// flaws marked in the app, not by screenshots), with a line of text, to the admin's list with its floor and the plan's
// units. Only my own open ones show, as small pins; never anyone else's (the admin's list has all of them).
import { api } from '../../lib/api';
import { t } from '../../lib/i18n/index.svelte';
import { haptic } from '../../lib/tg';
import { say } from '../../lib/state/ui.svelte';
import { sheets } from '../../lib/state/sheets';
import type { Ver } from '../../lib/mapgl';
import { fromPlan } from './planUnits';

export type Flaw = { id: number; ver: string; floor: number; u: number; v: number; px: number | null; py: number | null; body: string };

/** mine on this floor of this map: its own spot, or on another map through the 2023 plan's units */
export function flawsOn(mine: Flaw[], cur: number, ver: Ver) {
  return mine.flatMap((m) => {
    if (m.floor !== cur) return [];
    const [u, v] = m.ver === ver ? [m.u, m.v] : m.px != null && m.py != null ? fromPlan(ver, m.px, m.py) : [-1, -1];
    return u >= 0 && u <= 1 && v >= 0 && v <= 1 ? [{ id: m.id, u, v, body: m.body }] : [];
  });
}

/** the note's sheet, then the spot sent: the flaw as mine (the server answers 204: a negative id until the next visit
 *  lists it with its own), or null when cancelled or it failed (said) */
export function sendFlaw(spot: { ver: Ver; floor: number; u: number; v: number; px: number; py: number }): Promise<Flaw | null> {
  return sheets.askText({ title: t('map.flawTitle'), text: t('map.flawText', { floor: spot.floor }), ok: t('map.flawSend'), cancel: t('common.cancel'), placeholder: t('map.flawPh'), max: 300 })
    .then((body) => body ? api.mapFlaw({ ...spot, body }).then(() => {
      haptic.ok(); say(t('map.flawThanks'), 'sparkles_3d');
      return { id: -Date.now(), ...spot, body };
    }) : null)
    .catch(() => { say(t('common.error'), 'warning_3d'); return null; });
}
