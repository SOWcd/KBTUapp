// The crop's math (PhotoCrop): a w×h photo under a box-px square window. Zoom 1 fills the window with the photo's
// short side; x, y: the photo's centre off the window's, screen px. The photo never leaves the window.
export type View = { zoom: number; x: number; y: number };
export const MAX_ZOOM = 5;

/** screen px per photo px */
export const scaleOf = (w: number, h: number, box: number, zoom: number) => (box / Math.min(w, h)) * zoom;

/** the view with the photo covering the window: zoom in [1, MAX_ZOOM], the offset held at the edges */
export function clampView(w: number, h: number, box: number, v: View): View {
  const zoom = Math.min(MAX_ZOOM, Math.max(1, v.zoom)), s = scaleOf(w, h, box, zoom);
  const mx = Math.max(0, (w * s - box) / 2), my = Math.max(0, (h * s - box) / 2);
  return { zoom, x: Math.min(mx, Math.max(-mx, v.x)) + 0, y: Math.min(my, Math.max(-my, v.y)) + 0 };  // + 0: no -0
}

/** zoomed by `f` around the point (px, py) off the window's centre: what's under the fingers stays there */
export function zoomAt(w: number, h: number, box: number, v: View, f: number, px = 0, py = 0): View {
  const zoom = Math.min(MAX_ZOOM, Math.max(1, v.zoom * f)), r = zoom / v.zoom;
  return clampView(w, h, box, { zoom, x: px - (px - v.x) * r, y: py - (py - v.y) * r });
}

/** the window in photo px: the square to draw on the canvas */
export function cropRect(w: number, h: number, box: number, v: View) {
  const s = scaleOf(w, h, box, v.zoom), side = box / s;
  return { sx: w / 2 - (box / 2 + v.x) / s, sy: h / 2 - (box / 2 + v.y) / s, side };
}
