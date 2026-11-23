// The home-screen app's launch pictures (iOS: apple-touch-startup-image). iOS shows one from the tap on the icon until
// the page paints, so each is the boot screen's still first frame, drawn from index.html's own #boot markup and CSS at
// each iPhone's size, dark and light: the picture turns into the live boot screen without a jump.
// Writes public/splash/*.png and the <link> lines between index.html's splash markers.
// iOS keeps a launch picture by its URL: when the first frame changes, raise V (and install.html's ?v=) so it fetches the new ones.
// usage: node tools/splash.mjs   (from web/, after changing #boot or its CSS; Playwright's Chromium, as the QA tools use)
import { readFileSync, writeFileSync, mkdirSync, rmSync } from 'node:fs';
import { createRequire } from 'node:module';

const { chromium } = createRequire(import.meta.url)('playwright');
const V = 3;
const INDEX = new URL('../index.html', import.meta.url), OUT = new URL('../public/splash/', import.meta.url);
// portrait iPhones by CSS size and pixel ratio (iOS takes a picture only at its exact size)
const PHONES = [
  [440, 956, 3], // 16 Pro Max, 17 Pro Max
  [430, 932, 3], // 14 Pro Max, 15 / 16 Plus, 15 Pro Max
  [428, 926, 3], // 12 / 13 Pro Max, 14 Plus
  [420, 912, 3], // Air
  [414, 896, 3], // XS Max, 11 Pro Max
  [414, 896, 2], // XR, 11
  [402, 874, 3], // 16 Pro, 17, 17 Pro
  [393, 852, 3], // 14 Pro, 15, 15 Pro, 16
  [390, 844, 3], // 12, 13, 14, 16e
  [375, 812, 3], // X, XS, 11 Pro, 12 / 13 mini
  [375, 667, 2], // SE
];

const html = readFileSync(INDEX, 'utf8');
const css = html.match(/<style id="boot-css">[\s\S]*?<\/style>/)?.[0], boot = html.match(/<div id="boot"[\s\S]*?(?=<div id="app")/)?.[0];
if (!css || !boot || !html.includes('<!-- splash:start -->')) throw new Error('splash: #boot, its CSS or the markers are missing in index.html');

rmSync(OUT, { recursive: true, force: true });
mkdirSync(OUT, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.CHROME }); // CHROME: another Chromium than Playwright's own
const links = [];
for (const [w, h, dpr] of PHONES) {
  const page = await browser.newPage({ viewport: { width: w, height: h }, deviceScaleFactor: dpr });
  for (const theme of ['dark', 'light']) {
    // the first frame: every animation held at its start (paused from the first style, so none ever runs a frame)
    await page.setContent(`<!doctype html><html data-boot="${theme}"><head>${css}<style>#boot *{animation-play-state:paused!important}</style></head><body>${boot}</body></html>`);
    const name = `${w}x${h}-${dpr}x-${theme}.png`;
    await page.screenshot({ path: new URL(name, OUT).pathname });
    links.push(`<link rel="apple-touch-startup-image" href="/splash/${name}?v=${V}" media="(prefers-color-scheme: ${theme}) and (device-width: ${w}px) and (device-height: ${h}px) and (-webkit-device-pixel-ratio: ${dpr}) and (orientation: portrait)">`);
  }
  await page.close();
}
await browser.close();
writeFileSync(INDEX, html.replace(/<!-- splash:start -->[\s\S]*?<!-- splash:end -->/, `<!-- splash:start -->\n${links.join('\n')}\n<!-- splash:end -->`));
console.log(`${links.length} launch pictures in public/splash`);
