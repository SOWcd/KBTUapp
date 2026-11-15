// Each label's room on the plan (owner, Nov 15: labels pasted over walls; they must be printed inside their own room):
// the free space round a label's point on the plan as drawn (without its words), read off a picture of it. A label
// gets, for a few half-heights h of a band through its point, how far the band runs free left and right of it:
// [l, r] a band, in units of a 1000-wide frame (along the words: a turned label's band is turned with it). The app
// sizes each label to the biggest that fits (lib/mapgl.ts). Writes src/assets/map/boxes.json; by hand, after the
// plans or their labels change (map.test.ts checks every label has its box):
//   PW=<path to playwright-core> CHROME=<chrome binary> node tools/map/boxes.mjs
import fs from 'node:fs';
import path from 'node:path';
import { allLabels } from './labels.mjs';
import { chrome, name, OLD, shafts, tier } from './tiles.mjs';

export const BANDS = [3, 5, 8, 12, 18];
const here = path.dirname(new URL(import.meta.url).pathname), SVG = path.join(here, '../../src/assets/map');
const read = (f) => fs.readFileSync(path.join(SVG, f), 'utf8');
const PX = 3000; // a drawn plan's picture: 3 px a unit
const svgPic = (svg, css) => `data:image/svg+xml;base64,${Buffer.from(svg.replace(/<svg ([^>]*)>/, (_, at) => `<svg width="${PX}" height="${PX}" ${at}><style>text{display:none}</style>${css}`)).toString('base64')}`;

/** In the page: a picture's free runs. pts: [x, y, turn, ink] in its pixels; ink: the room's colour is the one under
 *  the point (ours: every room has its own), else white paper (Uni-Q's, 2023's: black on white). unit: px a unit;
 *  skip: [dx, dy] px round the point not read (Uni-Q's printed number under ours) */
async function runs(p, src, w, h, pts, unit, skip) {
  return p.evaluate(async ([src, w, h, pts, unit, skip, bands]) => {
    const im = new Image(); im.src = src; await im.decode();
    const c = new OffscreenCanvas(w, h), g = c.getContext('2d', { willReadFrequently: true });
    g.fillStyle = '#fff'; g.fillRect(0, 0, w, h); g.drawImage(im, 0, 0, w, h);
    const d = g.getImageData(0, 0, w, h).data, max = Math.round(400 * unit);
    return pts.map(([x0, y0, turn, own]) => {
      x0 = Math.round(x0); y0 = Math.round(y0);
      let ref = [255, 255, 255];
      if (own) { // the commonest colour round the point
        const n = new Map(), r = Math.round(3 * unit);
        for (let y = y0 - r; y <= y0 + r; y++) for (let x = x0 - r; x <= x0 + r; x++) {
          const i = (y * w + x) * 4, k = (d[i] >> 3) << 10 | (d[i + 1] >> 3) << 5 | d[i + 2] >> 3;
          n.set(k, (n.get(k) ?? 0) + 1);
        }
        const k = [...n].sort((a, b) => b[1] - a[1])[0][0];
        ref = [(k >> 10) << 3, ((k >> 5) & 31) << 3, (k & 31) << 3];
      }
      const tol = own ? 30 : 60;
      const wall = (x, y) => {
        if (x < 0 || y < 0 || x >= w || y >= h) return false; // past the sheet: nothing drawn there
        if (skip && Math.abs(x - x0) <= skip[0] && Math.abs(y - y0) <= skip[1]) return false;
        const i = (y * w + x) * 4;
        return Math.max(Math.abs(d[i] - ref[0]), Math.abs(d[i + 1] - ref[1]), Math.abs(d[i + 2] - ref[2])) > tol;
      };
      const side = Math.abs(turn) === 90; // the words run down the plan: the band is a column
      const at = (a, b) => (side ? wall(x0 + b, y0 + a) : wall(x0 + a, y0 + b)); // a along the words, b across
      return bands.flatMap((hb) => {
        const hp = Math.round(hb * unit), run = (dir) => {
          for (let a = 0; a <= max; a++) for (let b = -hp; b <= hp; b++) if (at(dir * a, b)) return a;
          return max;
        };
        return [run(-1), run(1)].map((n) => Math.round((n / unit) * 10) / 10);
      });
    });
  }, [src, w, h, pts, unit, skip, BANDS]);
}

const { b, p } = await chrome();
const out = { kbtu: {}, old: {}, main: {} }, labels = allLabels(read);
for (let f = 1; f <= 5; f++) {
  // ours far off: no small things (the tiles' first level), so a room's furniture never fences its name in
  const k = labels.kbtu[f].map(([u, v, , , , turn]) => [u * PX, v * PX, turn, 1]);
  out.kbtu[f] = await runs(p, svgPic(read(`kbtu-${f}.svg`), tier(0)), PX, PX, k, PX / 1000, null);
  const o = labels.old[f].map(([u, v, , , , turn]) => [u * PX, v * PX, turn, 0]);
  out.old[f] = await runs(p, svgPic(shafts(read(`floor-${f}.svg`)), OLD), PX, PX, o, PX / 1000, null);
  console.log('floor', f);
}
// Uni-Q's: their tiles one level under the finest (3307 px across), put together
const meta = JSON.parse(read('uniq-tiles.json')), rooms = JSON.parse(read('uniq-rooms.json')), L = 3, T = 512;
const W = Math.ceil(meta.w / 2), H = Math.ceil(meta.h / 2);
for (let f = 0; f <= 5; f++) {
  const parts = [];
  for (let r = 0; r * T < H; r++) for (let c = 0; c * T < W; c++) {
    const file = name('u2', f, L, c, r);
    if (fs.existsSync(file)) parts.push(`<image href="data:image/webp;base64,${fs.readFileSync(file).toString('base64')}" x="${c * T}" y="${r * T}" width="${T}" height="${T}"/>`);
  }
  const src = `data:image/svg+xml;base64,${Buffer.from(`<svg xmlns="http://www.w3.org/2000/svg" width="${W}" height="${H}">${parts.join('')}</svg>`).toString('base64')}`;
  const list = Object.entries(rooms[f]).flatMap(([room, at]) => at.map(([u, v]) => [room, u, v]));
  const unit = W / 1000, got = await runs(p, src, W, H, list.map(([, u, v]) => [u * W, v * H, 0, 0]), unit, [10 * unit, 5.5 * unit]);
  out.main[f] = {};
  list.forEach(([room], i) => (out.main[f][room] ??= []).push(got[i]));
  console.log('uniq floor', f);
}
await b.close();
// plain ASCII (Uni-Q's rooms with a Cyrillic letter as escapes), as labels.json
fs.writeFileSync(path.join(SVG, 'boxes.json'), JSON.stringify(out).replace(/[^\x20-\x7e]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`) + '\n');
