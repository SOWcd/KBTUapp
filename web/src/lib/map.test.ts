// floorOf: a main-building room at the start of a place gives its floor; street addresses and other numbers never do.
// The Russian inputs are written as escapes (\u0410\u0443\u0434 = "Aud", \u0410\u0431\u0430\u044f = "Abaya") to keep the source English.
import { describe, expect, it } from 'vitest';
import ru from './i18n/ru';
import { BLDG2_2GIS, DORM_2GIS, eventPlace, atBldg2, awayOf, bldg2Room, floorOf, nearRooms, roomOf, spotOf, adminZone, locate, tapAt } from './map';
import uniqRooms from '../assets/map/uniq-rooms.json';

it('opens campus sides and known rooms on the selected floor', () => {
  const rooms = uniqRooms as unknown as Record<string, number[][]>[];
  const kazybek = '\u049a\u0430\u0437\u044b\u0431\u0435\u043a \u0431\u0438 1';
  expect(floorOf(kazybek)).toBe(1);
  expect(floorOf(' KB  0 ')).toBeNull();
  expect(floorOf(' PF  0 ')).toBe(0);
  expect(locate(kazybek, rooms, [], 1)).toMatchObject({ f: 1, room: '', u: 0.234, v: 0.269 });
  expect(locate('KB · floor 1 · 158', rooms, [], 1)).toMatchObject({ f: 1, room: '158' });
  expect(locate('KB · floor 2 · 158', rooms, [], 1)).toMatchObject({ f: 2, room: '' });
});

it('finds the floor of a room, never of an address', () => {
  const cases: [string, number | null][] = [
    ['\u0410\u0443\u0434. 305', 3], ['\u0430\u0443\u0434 112', 1], ['\u041a\u0430\u0431\u0438\u043d\u0435\u0442 251', 2], ['305', 3], ['Room 412', 4],
    ['\u0410\u0431\u0430\u044f 150', null], ['1203', null], ['612', null], ['Atrium', null],
  ];
  for (const [place, floor] of cases) expect(floorOf(place), place).toBe(floor);
  expect(roomOf('\u0410\u0443\u0434. 305')).toBe('305');  // the number the map circles
  // a letter after the number is another room (251a is not 251), Latin or Cyrillic; a word after it is not a letter
  expect(roomOf('251a')).toBe('251a');
  expect(roomOf('Room: 372')).toBe('372'); // a colon after the word (owner, Nov 21)
  expect(roomOf('251\u0431')).toBe('251b');
  expect(roomOf('305 \u0438 306')).toBe('305');
  expect(roomOf('305\u043a\u0430\u0431')).toBe('305');
  expect(floorOf('251a')).toBe(2);
  // Independence Hall's wing is 7xx on floor 2; the basement's 70 stays below
  expect(floorOf('728')).toBe(2);
  expect(roomOf('Independence Hall')).toBe(null); // the round hall, a place without a number
  expect(floorOf('Independence Hall')).toBe(2);
  expect(floorOf('Halyk Arena')).toBe(null); // an arena in town, not the co-working's floor
  expect(roomOf('Kunaev Hall')).toBe('400a');
  expect(spotOf('\u0411\u0438\u0431\u043b\u0438\u043e\u0442\u0435\u043a\u0430')?.room).toBe('158'); // Uni-Q's names, any language
  expect(spotOf('Library')?.room).toBe('158');
  expect(adminZone('466')).toBe(true);
  expect(adminZone('470')).toBe(false);
  expect(roomOf('Al-Farabi Hall')).toBe('470');
  expect(spotOf('Halyk Co-working')?.f).toBe(1);
  expect(spotOf('Canteen 5')).toBe(null);
  expect(floorOf('70')).toBe(0);
  // a hall by its name (the Kunaev hall, Russian and Kazakh), never the street of the same name
  expect(roomOf('\u0438\u043c. \u0414.\u0410. \u041a\u0443\u043d\u0430\u0435\u0432\u0430')).toBe('400a');
  expect(floorOf('\u0414.\u0410. \u049a\u043e\u043d\u0430\u0435\u0432 \u0430\u0442\u044b\u043d\u0434\u0430\u0493\u044b')).toBe(4);
  expect(roomOf('\u041a\u0443\u043d\u0430\u0435\u0432\u0430 21')).toBe(null);
  // the basement's 1-99 as the whole place, a letter kept; never a short number in an address
  expect(floorOf('45')).toBe(0);
  expect(roomOf('045')).toBe('45');
  expect(roomOf('43\u0430')).toBe('43a');
  expect(floorOf('12 \u043c\u043a\u0440')).toBe(null);
});

describe('nearRooms', () => {
  const floor = { '434': [[0.30, 0.40]], '436': [[0.32, 0.40]], '450': [[0.9, 0.9]] };
  it('a room off the plan: its numbered neighbours', () => {
    expect(nearRooms(floor, '435', 1).map(([k]) => k)).toEqual(['434', '436']); // close together: both
    expect(nearRooms(floor, '445', 1).map(([k]) => k)).toEqual(['450']); // 436 is 9 below, 450 5 above, far apart: the nearer
    expect(nearRooms(floor, '470', 1)).toEqual([]);
  });
});

// the second building: its 312 is not the main one's; it opens 2GIS with its own number
it('the second building', () => {
  const p = '312 (\u041a\u043e\u0440\u043f\u0443\u0441 \u21162, \u0443\u043b. \u0422\u043e\u043b\u0435 \u0431\u0438)'; // "312 (Korpus No2, Tole bi st.)"
  expect(atBldg2(p)).toBe(true);
  expect(roomOf(p)).toBe(null);
  expect(floorOf(p)).toBe(null);
  expect(bldg2Room(p)).toBe('312');
  expect(atBldg2('2 \u043a\u043e\u0440\u043f\u0443\u0441, 105')).toBe(true);
  expect(bldg2Room('2 \u043a\u043e\u0440\u043f\u0443\u0441, 105')).toBe('105');            // the room, not the building's 2
  expect(bldg2Room('\u041a\u043e\u0440\u043f\u0443\u0441 \u21162, 312')).toBe('312');
  expect(bldg2Room('\u041a\u043e\u0440\u043f\u0443\u0441 \u21162, \u0443\u043b. \u0422\u043e\u043b\u0435 \u0431\u0438 59')).toBe(null); // a street's number is no room
  expect(atBldg2('\u041a\u043e\u0440\u043f\u0443\u0441 \u211612')).toBe(false); // building 12 is another
  expect(atBldg2('312')).toBe(false);
  expect(roomOf('312')).toBe('312');
});

// the two institutes off campus: their room numbers are not the main building's
it('the institutes off campus', () => {
  const a = awayOf('\u0418\u0422\u041a\u0438\u042d \u043a\u0430\u0431 \u21161(\u0443\u043b\u0438\u0446\u0430 \u041a\u0443\u043d\u0430\u0435\u0432\u0430 142)'); // "ITKiE kab No1(Kunaeva st. 142)"
  expect(a?.k).toBe('itkie');
  expect(a?.room).toBe('1'); // not the street's 142
  const b = '\u0418\u0425\u041d\u2116314'; // "IHN No314"
  expect(awayOf(b)).toMatchObject({ k: 'ihn', room: '314' });
  expect(roomOf(b)).toBe(null);
  expect(floorOf(b)).toBe(null);
  expect(awayOf('314')).toBe(null);
});

it('opens the campus map or 2GIS for every event venue', () => {
  const link = 'https://2gis.kz/almaty/geo/1';
  expect(eventPlace('Room 412', link)).toEqual({ kind: 'room', floor: 4 });
  expect(eventPlace('45')).toEqual({ kind: 'room', floor: 0 });
  expect(eventPlace(' KB  1 ', link)).toEqual({ kind: 'room', floor: 1 });
  expect(eventPlace('312 (\u041a\u043e\u0440\u043f\u0443\u0441 \u21162)', link)).toEqual({ kind: 'bldg2', url: BLDG2_2GIS });
  expect(eventPlace('\u041e\u0431\u0449\u0430\u0433\u0430', link)).toEqual({ kind: 'dorm', url: DORM_2GIS });
  expect(eventPlace('  PlatformA  ')).toEqual({ kind: 'elsewhere', url: 'https://2gis.kz/almaty/search/PlatformA' });
  expect(eventPlace('\u0410\u0431\u0430\u044f 157/3 #2')?.url).toBe('https://2gis.kz/almaty/search/%D0%90%D0%B1%D0%B0%D1%8F%20157%2F3%20%232');
  expect(eventPlace('PlatformA', 'https://2gis.kz.example.org/path')?.url).toBe('https://2gis.kz/almaty/search/PlatformA');
  expect(eventPlace('PlatformA', link)?.url).toBe(link);
  expect(eventPlace('', link)?.url).toBe(link);
  expect(eventPlace(' ')).toBeNull();
  // the campus's own places the map can't point at stay plain, never a search across Almaty
  for (const p of ['Atrium', '\u0410\u043a\u0442\u043e\u0432\u044b\u0439 \u0437\u0430\u043b', 'KBTU Atrium', 'Main Hall']) expect(eventPlace(p)).toEqual({ kind: 'campus' });
});

// Our map's SVGs are made from a floor's geometry and one style (tools/map): an edit to either without building
// again would leave the old picture in the app.
it("our map's SVGs are built from the geometry and the style as they are now", async () => {
  const { render } = await import('../../tools/map/build.mjs' as string);
  const geo = import.meta.glob('/tools/map/floor-*.svg', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
  const made = import.meta.glob('/src/assets/map/kbtu-*.svg', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
  expect(Object.keys(geo).length).toBeGreaterThan(0);
  for (const [path, src] of Object.entries(geo)) {
    const n = /floor-(\d)/.exec(path)![1];
    for (const k of src.match(/data-t="\w+"/g) ?? []) expect(ru, `floor ${n}: no ${k} in the i18n files`).toHaveProperty([`kmap.${k.slice(8, -1)}`]);
    for (const dark of [0, 1]) expect(made[`/src/assets/map/kbtu-${n}${dark ? '-dark' : ''}.svg`] === render(src, dark), `floor ${n}: run node tools/map/build.mjs`).toBe(true);
  }
});

// The map on MapLibre (lib/mapgl.ts): a plan's (u, v) to the library's degrees and back, sizes as zooms, the labels.
describe('the map frame', () => {
  it('a point of a plan goes to MapLibre and back, on every map', async () => {
    const { FRAMES, lngLat, uvOf, zoomFor, widthAt, Z0 } = await import('./mapgl');
    for (const f of Object.values(FRAMES)) {
      for (const [u, v] of [[0, 0], [1, 1], [0.485, 0.5], [0.8054, 0.199]]) {
        const [u2, v2] = uvOf(f, ...lngLat(f, u, v));
        expect(u2).toBeCloseTo(u, 9); expect(v2).toBeCloseTo(v, 9);
      }
      expect(lngLat(f, 0, 0)).toEqual([0, 0]); // the sheet hangs from the world's middle: its tiles start at a tile's corner
      expect(widthAt(f, zoomFor(f, 487.5))).toBeCloseTo(487.5, 9);
    }
    expect(widthAt(FRAMES.old, Z0)).toBe(512); // the whole sheet is one tile at its coarsest level
    expect(widthAt(FRAMES.main, Z0 + 4)).toBeCloseTo(6613, 6); // Uni-Q's finest level is its own pixels
  });
  it('a floor is a pyramid of tiles named as web-mercator ones; a screen with more pixels takes smaller tiles', async () => {
    const { tilesOf, overview, tileSize } = await import('./mapgl');
    expect(tilesOf('kbtu', true, 2)).toMatch(/map\/k2d\/f2\/\{z\}\/\{x\}_\{y\}\.webp$/);
    expect(overview('main', true, 0)).toMatch(/map\/u2\/f0\/6\/32_32\.webp$/); // inverted in the dark look, not another cut
    expect(tileSize(3)).toBeLessThan(tileSize(2));
    expect(512 / tileSize(3)).toBeGreaterThan(3 / 1.5); // at least 2/3 of a picture's pixel a screen pixel
  });
  it("the drawn maps' labels are their SVGs' words as they are now", async () => {
    const { allLabels } = await import('../../tools/map/labels.mjs' as string);
    const svgs = import.meta.glob('/src/assets/map/*.svg', { query: '?raw', import: 'default', eager: true }) as Record<string, string>;
    const made = (await import('../assets/map/labels.json')).default;
    expect(JSON.stringify(made) === JSON.stringify(allLabels((f: string) => svgs[`/src/assets/map/${f}`])), 'run node tools/map/labels.mjs').toBe(true);
  });
  it('room numbers are labels on every map: found by the room, sized to it, halls first', async () => {
    const { roomAt, labelsOf } = await import('./mapgl');
    for (const ver of ['main', 'old', 'kbtu'] as const) expect(roomAt(ver, 3, '303'), ver).toHaveLength(1);
    expect(roomAt('kbtu', 3, '349b')).toHaveLength(1); // the label says it in the UI's language, the room is the same
    expect(roomAt('old', 3, '999')).toEqual([]);
    const word = (k: string) => `<${k}>`;
    const main = labelsOf('main', 4, true, word), hall = main.find((l) => l.t === '400a')!, any = main.find((l) => l.t === '412')!;
    expect(main.every((l) => l.s > 5 && l.s <= 30 && l.plate && l.tier === 0)).toBe(true);
    expect(hall.rank).toBeLessThan(any.rank);
    const ours = labelsOf('kbtu', 1, false, word);
    expect(ours.find((l) => l.t === '<canteen>')).toBeTruthy(); // its words come from the i18n files
    const nums = ours.filter((l) => /^\d{3}$/.test(l.t));
    expect(nums.every((l) => l.s > 0 && l.tier === 0)).toBe(true);
    expect(nums.filter((l) => l.s >= 12).length).toBeGreaterThan(nums.length * 0.7); // most read zoomed out, the rest come closer
    expect(labelsOf('old', 1, false, word).some((l) => l.t === 'Tole bi street')).toBe(true);
  });
  it('a label is printed inside its own room: never wider than the free run round it, two lines when that is bigger', async () => {
    const { fit, ems } = await import('./mapgl');
    const labels = (await import('../assets/map/labels.json')).default as unknown as Record<string, Record<string, unknown[]>>;
    const boxes = (await import('../assets/map/boxes.json')).default as unknown as Record<string, Record<string, unknown>>;
    for (const ver of ['kbtu', 'old']) for (const f of ['1', '2', '3', '4', '5']) expect((boxes[ver][f] as unknown[]).length, `${ver} ${f}: node tools/map/boxes.mjs`).toBe(labels[ver][f].length);
    const box = [20, 24, 20, 24, 20, 24, 0, 0, 0, 0]; // a room 44 wide, 16 tall round the point
    const [s, t] = fit('100', box, false);
    expect(t).toBe('100');
    expect(s * ems('100')).toBeLessThanOrEqual(40);
    expect(s * 0.5).toBeLessThanOrEqual(8);
    const wide = [100, 100, 100, 100, 100, 100, 100, 100, 100, 100], narrow = [30, 30, 30, 30, 30, 30, 30, 30, 30, 30];
    expect(fit('Halyk Co-working', wide, false)[1]).toBe('Halyk Co-working');
    expect(fit('Halyk Co-working', narrow, false)[1]).toBe('Halyk\nCo-working');
    expect(fit('Canteen', [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], true)[0]).toBe(0); // a wall right at it: it waits forever
  });
});

// locate: the room-code resolver behind a route's ends and "Show on map" (a code typed in, or from the timetable)
describe('locate', () => {
  const rooms: Record<string, number[][]>[] = [{ '45': [[0.1, 0.1]] }, { '158': [[0.2, 0.7]] }, {}, { '305': [[0.8, 0.2]], '377': [[0.5, 0.5]] }, {}, {}];
  const doors = [{ f: 1, u: 0.4, v: 0.9, k: 'x', name: 'Tole bi' }, { f: 3, u: 0.6, v: 0.6, r: ['312'] }];
  const at = (text: string) => locate(text, rooms, doors, 1);
  it('puts a typed room where its number is printed, whatever the prefix', () => {
    expect(at('\u0410\u0443\u0434. 305')).toEqual({ f: 3, u: 0.8, v: 0.2, room: '305' });
    expect(at('Room 305')).toMatchObject({ f: 3, room: '305' });
    expect(at('045')).toMatchObject({ f: 0, u: 0.1, room: '45' }); // the basement, the leading zero dropped
  });
  it('falls back to the door on the graph, then to the nearest numbered neighbour', () => {
    expect(at('312')).toEqual({ f: 3, u: 0.6, v: 0.6, room: '312' });
    expect(at('376')).toEqual({ f: 3, u: 0.5, v: 0.5, room: '377', near: '376' });
  });
  it('knows entrances and named places by name', () => {
    expect(at('Tole bi')).toEqual({ f: 1, u: 0.4, v: 0.9, room: 'Tole bi' });
    expect(at(ru['route.spot.canteen'])).toMatchObject({ f: 0, spot: 'canteen' });
    expect(at(ru['route.spot.library'])).toMatchObject({ f: 1, room: '158' }); // a named room: its number
  });
  it('resolves nothing for what is not on the main map', () => {
    for (const text of ['\u0410\u0431\u0430\u044f 150', '1203', '999', '312 (\u043a\u043e\u0440\u043f\u0443\u0441 \u2116 2)', '', 'hello']) expect(at(text), text).toBeNull();
  });
  it('resolves every room the real plan prints', () => {
    const real = uniqRooms as unknown as Record<string, number[][]>[];
    expect(locate('305', real, [], 1)).toMatchObject({ f: 3, room: '305' });
    expect(locate('\u0430\u0443\u0434 158', real, [], 1)).toMatchObject({ f: 1, room: '158' });
  });
});

// tapAt: what a tap on the map means for a route's end
describe('tapAt', () => {
  const rooms: Record<string, number[][]>[] = [{}, { '120': [[0.3, 0.3]], '121': [[0.35, 0.3]] }];
  const doors = [{ f: 1, u: 0.5, v: 0.5, k: 'x', name: 'Panfilov' }, { f: 1, u: 0.31, v: 0.31 }];
  it('takes the nearest room number within reach, on the floor tapped', () => {
    expect(tapAt({ f: 1, u: 0.34, v: 0.3 }, rooms, doors, 1, 0.03)).toEqual({ room: '121' });
    expect(tapAt({ f: 1, u: 0.31, v: 0.3 }, rooms, doors, 1, 0.03)).toEqual({ room: '120' });
    expect(tapAt({ f: 2, u: 0.3, v: 0.3 }, rooms, doors, 1, 0.03)).toBeNull();
  });
  it('an entrance or a named place before a room; nothing near: the point itself', () => {
    expect(tapAt({ f: 1, u: 0.51, v: 0.5 }, rooms, doors, 1, 0.03)).toEqual({ exit: 'Panfilov' });
    expect(tapAt({ f: 0, u: 0.55, v: 0.6 }, rooms, doors, 1, 0.03)).toEqual({ spot: 'canteen' });
    expect(tapAt({ f: 1, u: 0.9, v: 0.9 }, rooms, doors, 1, 0.03)).toBeNull();
  });
});
