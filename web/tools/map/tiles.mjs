// The map's pictures as tiles for MapLibre (lib/mapgl.ts has the frame): every map is a square sheet, 8192 px at its
// finest level, cut in 512 px tiles over five levels (512 px ... 8192 px across), named as web-mercator tiles
// f<floor>/<z>/<x>_<y>.webp under public/map/<cut>/ (the server caches map/ for a year: a new cut gets a new folder).
//   u2   Uni-Q's plans, from their own finest tiles (PREV: the cut before, public/map/u1 in git until Nov 15: f<n>/2/<c>_<r>.webp of 6613 x 5930)
//   o2   the 2023 redraw (src/assets/map/floor-N.svg) without its words, every wall one ink
//   k2, k2d  our map, light and dark (kbtu-N.svg), without its words; details come in with the levels
//   p1   the 2023 plan as it was given to us, a picture a floor (SCAN: the folder with floor-00N.jpg), by ImageMagick
// By hand, with a Chromium to draw (Q: WebP quality, the cuts in the app are 0.85; 1 is lossless, four times the size):
//   Q=0.85 PW=<path to playwright-core> CHROME=<chrome binary> node tools/map/tiles.mjs u2|o2|k2|p1 ...
import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { createRequire } from 'node:module';

const here = path.dirname(new URL(import.meta.url).pathname), web = path.join(here, '../..');
const OUT = path.join(web, 'public/map'), SVG = path.join(web, 'src/assets/map');
const Z0 = 6, TOP = 4, T = 512; // the sheet is one tile at zoom Z0; TOP levels finer
export const name = (cut, f, l, c, r) => { const o = 2 ** (Z0 + l - 1); return path.join(OUT, cut, `f${f}`, String(Z0 + l), `${o + c}_${o + r}.webp`); };

/** The 2023 redraw for the app: no words (they are labels), every wall one ink and one weight (owner, Nov 15: red and
 *  black walls look the same in the building), a free-standing column with its shaft in it, as the plan draws them
 *  (they were empty rings) */
export const OLD = `<style>.t{display:none}.w{fill:#1c1c1e;stroke:#1c1c1e;stroke-width:.5}.lr{stroke:#1c1c1e;stroke-width:1.5}.lk{stroke:#1c1c1e}
.lg{stroke:#9a9aa0}.c{fill:#d4d4d8;stroke:#1c1c1e}.o{fill:#c7c7cc;stroke:#1c1c1e}.oo{fill:#fff}</style>`;
export const shafts = (svg) => svg.replace(/<circle class="oo"[^>]*cx="([\d.]+)" cy="([\d.]+)" r="([\d.]+)"\/>/g,
  (m, x, y, r) => `${m}<circle cx="${x}" cy="${y}" r="${(r * 0.5).toFixed(1)}"/>`);
/** ours by level: far off no small things (the classes the SVG marks them with), then all of it; never its words */
export const tier = (l) => `<style>text{display:none}${l < 1 ? '.mid{display:none}' : ''}${l < 2 ? '.fine{display:none}' : ''}</style>`;
const sized = (svg, css) => svg.replace(/<svg ([^>]*)>/, (_, at) => `<svg width="${T * 2 ** TOP}" height="${T * 2 ** TOP}" ${at}>${css}`);

export async function chrome() {
  const { chromium } = createRequire(import.meta.url)(process.env.PW ?? 'playwright-core');
  const b = await chromium.launch({ executablePath: process.env.CHROME || undefined });
  const p = await b.newPage();
  await p.goto('about:blank');
  // a tile of a picture: the square (x, y, size) of it drawn into 512 px; lossless WebP, or lossy at q
  await p.evaluate(() => {
    const pics = new Map();
    window.pic = async (id, src) => { const im = new Image(); im.src = src; await im.decode(); pics.set(id, im); };
    window.drop = (id) => pics.delete(id);
    window.cut = async (parts, q, paper) => {
      const c = new OffscreenCanvas(512, 512), g = c.getContext('2d');
      g.fillStyle = paper; g.fillRect(0, 0, 512, 512); g.imageSmoothingQuality = 'high';
      for (const [id, sx, sy, sw, sh, dx, dy, dw, dh] of parts) g.drawImage(pics.get(id), sx, sy, sw, sh, dx, dy, dw, dh);
      const b = await c.convertToBlob({ type: 'image/webp', quality: q });
      return new Promise((done) => { const r = new FileReader(); r.onload = () => done(r.result.split(',')[1]); r.readAsDataURL(b); });
    };
  });
  return { b, p };
}
const save = (file, b64) => { fs.mkdirSync(path.dirname(file), { recursive: true }); fs.writeFileSync(file, Buffer.from(b64, 'base64')); };
const url = (file, type) => `data:${type};base64,${fs.readFileSync(file).toString('base64')}`;

/** a drawn map: each level straight from the vectors */
async function drawn(p, cut, file, css, q, paper) {
  for (let f = 1; f <= 5; f++) {
    const svg = fs.readFileSync(path.join(SVG, file(f)), 'utf8');
    for (let l = 0; l <= TOP; l++) {
      await p.evaluate(([id, src]) => window.pic(id, src), ['s', `data:image/svg+xml;base64,${Buffer.from(sized(css.pre ? css.pre(svg) : svg, css.at(l))).toString('base64')}`]);
      const n = 2 ** l, size = (T * 2 ** TOP) / n;
      for (let r = 0; r < n; r++) for (let c = 0; c < n; c++)
        save(name(cut, f, l, c, r), await p.evaluate(([parts, q, paper]) => window.cut(parts, q, paper), [[['s', c * size, r * size, size, size, 0, 0, T, T]], q, paper]));
    }
    console.log(cut, 'floor', f);
  }
}

/** Uni-Q's: the finest level is their tiles as they are, each coarser one its four finer tiles at half size */
async function uniq(p, prev) {
  const meta = JSON.parse(fs.readFileSync(path.join(SVG, 'uniq-tiles.json'), 'utf8')), cols = Math.ceil(meta.w / T), rows = Math.ceil(meta.h / T);
  for (let f = 0; f <= 5; f++) {
    for (let l = TOP; l >= 0; l--) {
      const k = 2 ** (TOP - l), nc = Math.ceil(cols / k), nr = Math.ceil(rows / k);
      for (let r = 0; r < nr; r++) for (let c = 0; c < nc; c++) {
        const kids = l === TOP ? [[path.join(prev, `f${f}/2/${c}_${r}.webp`), 0, 0, T, T, 0, 0, T, T]]
          : [0, 1, 2, 3].map((i) => [name('u2', f, l + 1, c * 2 + (i & 1), r * 2 + (i >> 1)), 0, 0, T, T, (i & 1) * 256, (i >> 1) * 256, 256, 256]);
        const parts = [];
        for (const [file, ...at] of kids) if (fs.existsSync(file)) { // none: blank paper
          const id = `k${parts.length}`;
          await p.evaluate(([id, src]) => window.pic(id, src), [id, url(file, 'image/webp')]);
          parts.push([id, ...at]);
        }
        save(name('u2', f, l, c, r), await p.evaluate(([parts]) => window.cut(parts, 1, '#fff'), [parts]));
      }
    }
    console.log('u2 floor', f);
  }
  // the levels were made from each other without loss; now each tile once through the lossy encoder (Q)
  const q = +(process.env.Q ?? 1);
  if (q < 1) for (const file of fs.globSync(path.join(OUT, 'u2/f*/*/*.webp'))) {
    await p.evaluate(([src]) => window.pic('k0', src), [url(file, 'image/webp')]);
    save(file, await p.evaluate(([q]) => window.cut([['k0', 0, 0, 512, 512, 0, 0, 512, 512]], q, '#fff'), [q]));
  }
}

const cuts = process.argv.slice(2);
if (cuts.includes('p1')) {
  for (let f = 1; f <= 5; f++) {
    fs.mkdirSync(path.join(OUT, 'p1'), { recursive: true });
    execFileSync('magick', [path.join(process.env.SCAN, `floor-00${f - 1}.jpg`), '-resize', '1240x1240', '-quality', '82', path.join(OUT, 'p1', `f${f}.webp`)]);
  }
}
if (cuts.some((c) => c !== 'p1')) {
  const { b, p } = await chrome();
  if (cuts.includes('u2')) await uniq(p, process.env.PREV);
  if (cuts.includes('o2')) await drawn(p, 'o2', (f) => `floor-${f}.svg`, { pre: shafts, at: () => OLD }, +(process.env.Q ?? 1), '#fff');
  if (cuts.includes('k2')) {
    await drawn(p, 'k2', (f) => `kbtu-${f}.svg`, { at: tier }, +(process.env.Q ?? 1), '#DCE0EA');
    await drawn(p, 'k2d', (f) => `kbtu-${f}-dark.svg`, { at: tier }, +(process.env.Q ?? 1), '#0A0B10');
  }
  await b.close();
}
