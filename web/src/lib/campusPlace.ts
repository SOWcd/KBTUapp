// Main-building sides. Keep the aliases in sync with the server's campus_place parser.
export const CAMPUS_SIDES = {
  tole: { min: 0, max: 5, aliases: /^(?:\u0442\u0431|tb|t[oö]le(?: bi)?|\u0442[\u043e\u04e9]\u043b\u0435(?: \u0431\u0438)?)$/i },
  abylai: { min: 0, max: 4, aliases: /^(?:\u0430\u0431|ab|ab[yi]la[yi](?: khan)?|\u0430\u0431\u044b\u043b\u0430\u0439(?: \u0445\u0430\u043d\u0430?)?)$/i },
  panfilov: { min: 0, max: 4, aliases: /^(?:\u043f\u0444|pf|panfilov(?:a)?|\u043f\u0430\u043d\u0444\u0438\u043b\u043e\u0432\u0430?)$/i },
  kazybek: { min: 1, max: 4, aliases: /^(?:\u043a\u0431|kb|[kq]azybek(?: bi)?|[\u043a\u049b]\u0430\u0437\u044b\u0431\u0435\u043a(?: \u0431\u0438)?)$/i },
} as const;

export type CampusSide = keyof typeof CAMPUS_SIDES;
export const campusSides = Object.keys(CAMPUS_SIDES) as CampusSide[];
export type CampusPlace = { side: CampusSide; floor: number; room: string };

const SIDE_FLOOR = /^([^0-9·,]+?)\s*(?:[·,]\s*)?(?:floor\s+)?([0-9])(?:st|nd|rd|th)?(?:\s*-?\s*(?:floor|\u044d\u0442\u0430\u0436|\u049b\u0430\u0431\u0430\u0442))?(?:\s*·\s*(.+))?$/i;

export function campusPlace(place: string | null | undefined): CampusPlace | null {
  const m = place?.trim().replace(/\s+/g, ' ').match(SIDE_FLOOR);
  if (!m) return null;
  const floor = Number(m[2]);
  const side = campusSides.find((key) => {
    const { min, max, aliases } = CAMPUS_SIDES[key];
    return floor >= min && floor <= max && aliases.test(m[1]);
  });
  return side ? { side, floor, room: m[3] ?? '' } : null;
}
