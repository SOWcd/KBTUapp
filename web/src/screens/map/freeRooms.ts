// "Free now" on the campus map (CampusMap.svelte), by the timetable (lib/rooms): which rooms of a floor get a tint
// where their number is printed, and the line a room's card says about it.
import { roomNow, type RoomWeek } from '../../lib/rooms';
import { t } from '../../lib/i18n/index.svelte';

// Office-hour rooms and rooms 310-318 stay on the map but must not be advertised as free.
const noFreeHighlight = new Set([
  '0', '5', '9', '15', '45', '47', '58', '69', '77', '87', '102', '112',
  '120', '140', '178', '179', '180', '181', '184', '215', '216a', '216b', '217', '218',
  '219', '220', '228', '249', '251', '251a', '251b', '257', '268', '270', '271', '272',
  '274', '275', '277', '278', '279', '281', '283', '284', '310', '311', '312', '313',
  '314', '315', '316', '317', '318', '319', '321', '324', '325', '327', '328', '331',
  '335', '336', '337', '345', '346', '348', '349', '355', '356', '357', '359', '365',
  '372', '376', '377', '381a', '381b', '383', '384', '385', '386', '388', '389', '400a',
  '403', '406', '409', '410', '410a', '411', '419', '420', '422', '427', '432', '433',
  '436', '447', '454', '456', '458', '459', '473', '509', '513',
]);

/** the tints of a floor's rooms (room → where its number is printed): free or busy now; an office is never "free" */
export function freeTints(rooms: Record<string, number[][]> | undefined, week: Record<string, RoomWeek>, clock: number) {
  return Object.entries(rooms ?? {}).flatMap(([r, ps]) => {
    if (!week[r]) return [];
    const free = roomNow(week[r], clock).free;
    return free && noFreeHighlight.has(r) ? [] : ps.map(([u, v]) => ({ r, u, v, free }));
  });
}

/** what a room's card says: free until when, or busy until when, by the timetable; '' when it can't say */
export function roomLine(room: string | null, week: Record<string, RoomWeek> | null, clock: number): string {
  const w = room && week?.[room];
  if (!w) return '';
  const n = roomNow(w, clock), time = `${String(n.until).padStart(2, '0')}:00`;
  if (n.free && noFreeHighlight.has(room as string)) return ''; // an office: its card doesn't say "free" either
  return (n.free ? (n.until == null ? t('map.freeEvening') : t('map.freeUntil', { time })) : t('map.busyUntil', { time })) + ' \u00b7 ' + t('map.byTimetable');
}
