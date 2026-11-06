// The lanyard card's drawn layers as pictures (perf round 3). Each layer the card draws (src/assets/lanyards/
// {scenes,schools}/*-card.svg from the round generators, KBTU's rosette and colonnade) rendered once at its own size on a
// 3x phone, 3% over for the tilt's overscan (base.css .z --zs), saved beside it as .webp. The card, its back, the ticket
// draw the .webp: a phone decodes a picture once, off the main thread, where the SVG (thousands of path points, blur
// filters) was recorded and rasterised again on every paint at 3x: the profile's open, each flip, each new layer.
// The SVG stays the source; scene-rasters.json holds each one's hash and lib/rasters.test.ts fails on a stale picture.
// Then the picker's minis (SettingsList): every lanyard's whole card art at the swatch's 74 x 48, one small picture each
// (tools/minis draws them as the picker drew them live: 20+ full scenes mounted at once for the creator, all their
// layers decoded at full size for a thumbnail). Their sources' hash is the manifest's "minis".
// usage: node tools/scene-rasters.mjs [--all]   (from web/; Playwright's Chromium, as the QA tools use)
import { readFileSync, writeFileSync, readdirSync, mkdirSync } from 'node:fs';
import { createHash } from 'node:crypto';
import { createRequire } from 'node:module';
import { createServer } from 'vite';

const { chromium } = createRequire(import.meta.url)('playwright');
const ROOT = new URL('../src/assets/lanyards/', import.meta.url);
const MANIFEST = new URL('./scene-rasters.json', import.meta.url);
// each picture at the scale it is shown on a 3x phone: 3 x its layer's overscan (--zs: 1.03 for the far and near layers,
// the others below), so a still card maps one picture pixel to one screen pixel; q .85: mean error 0.3/255
const Q = 0.85, ZS = 1.03;
const OVERSCAN = { 'scenes/mk-sky-card.svg': 1.04, 'kbtu-rosette.svg': 1.04, 'kbtu-facade.svg': 1.02, 'scenes/ch-shield-card.svg': 1.02, 'scenes/sx-cap-card.svg': 1.02,
  // layers that stand still on the card (no --zs): ClubScene's mid ridge, skyline, windows, ground, hill, flask, Faces'
  // ribbons; SchoolScene's unclassed and wave layers
  ...Object.fromEntries(['mk-mid', 'bcl-city', 'bcl-win', 'spe-ground', 'qa-hill', 'ai-flask', 'fc-neon', 'en-mid', 'cs-mid', 'knl-mid', 'lit-mid', 'tm-mid', 'w3-mid', 'zh-mid'].map((n) => [`scenes/${n}-card.svg`, 1])),
  ...Object.fromEntries(['geo-strata', 'bs-board', 'law-desk', 'kma-waves'].map((n) => [`schools/${n}-card.svg`, 1])) };

const files = [...['scenes', 'schools'].flatMap((d) => readdirSync(new URL(d + '/', ROOT)).filter((f) => f.endsWith('-card.svg')).map((f) => `${d}/${f}`)),
  'kbtu-rosette.svg', 'kbtu-facade.svg', 'sower-rosette.svg'];
// SOWER's rosette is a mask (ui/SowerArt) the tilt moved, re-rasterised on every frame: 1200 px holds its biggest crisp
// use (330 css px at 3x); the far copy, 580 px at a third of the opacity, takes it a little soft
const SIZE = { 'sower-rosette.svg': 1200 / 400 };
// perf round 4: each layer at the lowest quality, and a smooth one (sky, glow, gradient) at a smaller size, that keeps it
// within a quarter of an 8-bit step of the q .85 picture on average and its 99.9th percentile within 6 (12 at least) of
// it, both against the lossless render at the shown size: 2715 -> 2167 KB. q .65 for most; [quality, size] here.
const ENC = { 'schools/ise-earth-card.svg': [0.75, 1], 'schools/smsgt-field-card.svg': [0.75, 1], 'scenes/ch-crest-card.svg': [Q, 1],
  'scenes/kn-jersey-card.svg': [Q, 1], 'sower-rosette.svg': [Q, 1], 'scenes/bcl-bokeh-card.svg': [Q, 0.67], 'schools/seogi-dusk-card.svg': [Q, 0.75],
  ...Object.fromEntries(['scenes/cr-spectrum', 'schools/kma-moon', 'schools/law-shelf', 'schools/sce-sky', 'schools/sss-sky'].map((n) => [`${n}-card.svg`, [0.75, 0.75]])) };
const [quality, less] = [(f) => ENC[f]?.[0] ?? 0.65, (f) => ENC[f]?.[1] ?? 1];
const scale = (f) => (SIZE[f] ?? 3 * (OVERSCAN[f] ?? ZS)) * less(f);
const old = (() => { try { return JSON.parse(readFileSync(MANIFEST, 'utf8')); } catch { return {}; } })();
const sha = (b) => createHash('sha1').update(b).digest('hex').slice(0, 12);
const b = await chromium.launch();
const page = await b.newPage();
const out = {};
for (const f of files) {
  const src = readFileSync(new URL(f, ROOT));
  out[f] = sha(src);
  if (!process.argv.includes('--all') && old[f] === out[f]) continue;
  const [, , , w, h] = /viewBox="([\d.]+) ([\d.]+) ([\d.]+) ([\d.]+)"/.exec(src.toString()).map(Number);
  const data = await page.evaluate(async ({ svg, W, H, Q }) => {
    const img = new Image();
    img.src = 'data:image/svg+xml;base64,' + svg;
    await img.decode();
    const c = document.createElement('canvas');
    c.width = W; c.height = H;
    c.getContext('2d').drawImage(img, 0, 0, W, H);
    const blob = await new Promise((r) => c.toBlob(r, 'image/webp', Q));
    return [...new Uint8Array(await blob.arrayBuffer())];
  }, { svg: src.toString('base64'), W: Math.round(w * scale(f)), H: Math.round(h * scale(f)), Q: quality(f) });
  writeFileSync(new URL(f.replace(/\.svg$/, '.webp'), ROOT), Buffer.from(data));
  console.log(f, (src.length / 1024).toFixed(1), 'KB svg ->', (data.length / 1024).toFixed(1), 'KB webp');
}

// the minis: the art as the picker shows it, so their sources are every lanyard file, the card's components and the looks
const MINI_SRC = ['src/ui/LanyardBand.svelte', 'src/ui/ClubScene.svelte', 'src/ui/SchoolScene.svelte', 'src/ui/KbtuMark.svelte', 'src/lib/awards.ts', 'tools/minis/Minis.svelte'];
const WEB = new URL('../', import.meta.url);
const svgs = (d) => readdirSync(new URL(d, ROOT), { recursive: true }).filter((f) => f.endsWith('.svg')).map((f) => new URL(d + f, ROOT));
out.minis = sha(Buffer.concat([...MINI_SRC.map((f) => new URL(f, WEB)), ...svgs('').sort((a, b) => (a.href < b.href ? -1 : 1))].map((u) => readFileSync(u))));
if (process.argv.includes('--all') || old.minis !== out.minis) {
  const vite = await createServer({ root: WEB.pathname, logLevel: 'error', server: { port: 0 } });
  await vite.listen();
  const ctx = await b.newContext({ deviceScaleFactor: 3, viewport: { width: 400, height: 2000 } });
  const p = await ctx.newPage();
  await p.goto(`${vite.resolvedUrls.local[0]}tools/minis/index.html`);
  await p.waitForSelector('.cell');
  await p.evaluate(() => Promise.all([document.fonts.ready, ...[...document.images].map((i) => i.decode().catch(() => {}))]));
  const dir = new URL('minis/', ROOT);
  mkdirSync(dir, { recursive: true });
  for (const cell of await p.$$('.cell')) {
    const look = await cell.getAttribute('data-look');
    const png = await cell.screenshot({ omitBackground: true, animations: 'disabled' });
    const data = await p.evaluate(async (png) => {
      const img = new Image(); img.src = 'data:image/png;base64,' + png; await img.decode();
      const c = document.createElement('canvas'); c.width = img.width; c.height = img.height; c.getContext('2d').drawImage(img, 0, 0);
      const blob = await new Promise((r) => c.toBlob(r, 'image/webp', 0.9));
      return [...new Uint8Array(await blob.arrayBuffer())];
    }, png.toString('base64'));
    writeFileSync(new URL(`${look}.webp`, dir), Buffer.from(data));
  }
  console.log('minis:', (await p.$$('.cell')).length);
  await vite.close();
}
await b.close();
writeFileSync(MANIFEST, JSON.stringify(out, null, 1) + '\n');
