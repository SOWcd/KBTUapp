// A cover per format: which picture a format shows, where a drag leaves its crop, and where a new photo's subject is.
import { expect, it } from 'vitest';
import { coverFor, panFocus, smartFocus } from './photo';

it('gives a format its own photo or crop, else the one cover', () => {
  const cover = { id: 1, url: 'a.webp', thumb: 'a.t.webp', focus: [0.5, 0.2] as [number, number],
    formats: { feed: { focus: [0.1, 0.9] as [number, number] }, list: { id: 2, url: 'b.webp', thumb: 'b.t.webp', focus: null } } };
  expect(coverFor(cover, 'card')).toBe(cover);
  expect(coverFor(cover, 'feed')).toMatchObject({ id: 1, url: 'a.webp', focus: [0.1, 0.9] });
  expect(coverFor(cover, 'list')).toMatchObject({ id: 2, url: 'b.webp', focus: null }); // its own photo: never the cover's point
  expect(coverFor(null, 'feed')).toBeNull();
});

it('moves the crop with the finger and stops at the edges', () => {
  // 2000x1000 in a 100x100 frame: 200x100 on screen, 100 px to slide sideways and nowhere up or down
  const photo = { w: 2000, h: 1000 }, frame = { w: 100, h: 100 };
  expect(panFocus([0.5, 0.5], -25, 40, photo, frame)).toEqual([0.75, 0.5]); // dragged left: what was right of it comes in
  expect(panFocus([0.5, 0.5], 999, 0, photo, frame)).toEqual([0, 0.5]);
  expect(panFocus(null, -999, 0, photo, frame)).toEqual([1, 0.5]);
  expect(panFocus([0.3, 0.3], 10, 10, { w: 500, h: 500 }, frame)).toEqual([0.3, 0.3]); // the same shape: nothing to move
});

it('aims a new photo at its detail, the middle when there is none', () => {
  const n = 32, flat = new Uint8ClampedArray(n * n * 4).fill(128);
  expect(smartFocus(flat)).toEqual([0.5, 0.5]);
  const busy = flat.slice(); // a checkered patch in the top right corner
  for (let y = 2; y < 10; y++) for (let x = 22; x < 30; x++) busy.fill((x + y) % 2 ? 255 : 0, (y * n + x) * 4, (y * n + x) * 4 + 3);
  const [x, y] = smartFocus(busy);
  expect(x).toBeGreaterThan(0.7); expect(y).toBeLessThan(0.3);
});
