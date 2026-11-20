// floorOf: a main-building room at the start of a place gives its floor; street addresses and other numbers never do.
// The Russian inputs are written as escapes (\u0410\u0443\u0434 = "Aud", \u0410\u0431\u0430\u044f = "Abaya") to keep the source English.
import { describe, expect, it } from 'vitest';
import ru from './i18n/ru';
import { addressGis, atBldg2, awayOf, bldg2Room, floorOf, nearRooms, roomOf, spotOf, adminZone } from './map';

it('finds the floor of a room, never of an address', () => {
  const cases: [string, number | null][] = [
    ['\u0410\u0443\u0434. 305', 3], ['\u0430\u0443\u0434 112', 1], ['\u041a\u0430\u0431\u0438\u043d\u0435\u0442 251', 2], ['305', 3], ['Room 412', 4],
    ['\u0410\u0431\u0430\u044f 150', null], ['1203', null], ['612', null], ['Atrium', null],
  ];
  for (const [place, floor] of cases) expect(floorOf(place), place).toBe(floor);
  expect(roomOf('\u0410\u0443\u0434. 305')).toBe('305');  // the number the map circles
  // a letter after the number is another room (251a is not 251), Latin or Cyrillic; a word after it is not a letter
  expect(roomOf('251a')).toBe('251a');
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
  expect(addressGis('\u0418\u0422\u041a\u0438\u042d \u043a\u0430\u0431 \u21161(\u0443\u043b\u0438\u0446\u0430 \u041a\u0443\u043d\u0430\u0435\u0432\u0430 142)')).toBe(null);
  expect(awayOf('314')).toBe(null);
});

it('a typed street address becomes a 2GIS search; rooms and campus places never do', () => {
  expect(addressGis('Gogolya 157')).toBe('https://2gis.kz/almaty/search/Gogolya%20157');
  expect(addressGis('\u0443\u043b. \u0410\u0431\u0430\u044f 150, 2 \u044d\u0442\u0430\u0436')).toContain('2gis.kz/almaty/search/');
  for (const p of ['305', 'Room 412', '251a', '\u0430\u0443\u0434. 305', 'Hall', '']) expect(addressGis(p)).toBeNull();
  // a named venue off campus is searched too (owner, Nov 20); the campus's own places never are
  expect(addressGis("Mad Murphy's Irish Pub")).toBe("https://2gis.kz/almaty/search/Mad%20Murphy's%20Irish%20Pub");
  for (const p of ['\u0410\u043a\u0442\u043e\u0432\u044b\u0439 \u0437\u0430\u043b', 'KBTU Atrium', '\u041a\u0411\u0422\u0423, \u0445\u043e\u043b\u043b', 'Main Hall', '\u0423\u0442\u043e\u0447\u043d\u044f\u0435\u0442\u0441\u044f']) expect(addressGis(p)).toBeNull();
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
