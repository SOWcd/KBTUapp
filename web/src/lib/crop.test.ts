// The crop window never shows past the photo, and what it frames is the square that gets drawn.
import { expect, it } from 'vitest';
import { clampView, cropRect, zoomAt } from './crop';

it('holds the photo over the window', () => {
  // 2000×1000 in a 300 px window: zoom 1 is 600×300 on screen, so it slides 150 px sideways and not at all up or down
  expect(clampView(2000, 1000, 300, { zoom: 1, x: 999, y: -50 })).toEqual({ zoom: 1, x: 150, y: 0 });
  expect(clampView(2000, 1000, 300, { zoom: 0.2, x: -999, y: 0 })).toEqual({ zoom: 1, x: -150, y: 0 });
  expect(clampView(2000, 1000, 300, { zoom: 99, x: 0, y: 0 }).zoom).toBe(5);
});

it('zooms around the fingers and stays inside', () => {
  const v = zoomAt(1000, 1000, 300, { zoom: 1, x: 0, y: 0 }, 2, 75, 0);  // 2× at a point right of centre
  expect(v).toEqual({ zoom: 2, x: -75, y: 0 });
  expect(zoomAt(1000, 1000, 300, v, 0.5, 75, 0)).toEqual({ zoom: 1, x: 0, y: 0 });  // back out: no offset left
});

it('crops the square the window shows', () => {
  expect(cropRect(2000, 1000, 300, { zoom: 1, x: 0, y: 0 })).toEqual({ sx: 500, sy: 0, side: 1000 });
  expect(cropRect(2000, 1000, 300, { zoom: 1, x: 150, y: 0 })).toEqual({ sx: 0, sy: 0, side: 1000 });   // the left edge
  expect(cropRect(2000, 1000, 300, { zoom: 2, x: 0, y: 0 })).toEqual({ sx: 750, sy: 250, side: 500 });
  const r = cropRect(3000, 4000, 320, clampView(3000, 4000, 320, { zoom: 3.3, x: -1e4, y: 1e4 }));     // pinned to a corner
  expect(r.sx + r.side).toBeCloseTo(3000); expect(r.sy).toBeCloseTo(0);
});
