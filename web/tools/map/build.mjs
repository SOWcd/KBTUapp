// Our map's floors: geometry (floor-N.svg, one tag a line, $tokens for the look) + style.mjs -> the two SVGs the app
// loads, src/assets/map/kbtu-N.svg and kbtu-N-dark.svg. Run `node tools/map/build.mjs` after editing either; map.test.ts
// fails while the SVGs are stale. The output is plain attributes only: no CSS, no variables, no <use>, nothing iOS
// WebKit hasn't drawn since the first version (the reverted perf pass, 341f0f57).
import { STYLE } from './style.mjs';

const fx = (n) => n.toFixed(1);

/** One floor's SVG for a theme (0 light, 1 dark) */
export function render(geo, dark, style = STYLE) {
  const pick = (v) => (Array.isArray(v) ? v[dark] : v);
  const val = (k) => {
    if (!(k in style)) throw new Error(`map: no $${k} in style.mjs`);
    return k === 'H' ? fx(style.H) : String(pick(style[k]));
  };
  const out = [];
  const lines = geo.split('\n').filter(Boolean);
  for (let i = 0; i < lines.length; i++) {
    if (lines[i] !== '<g walls>') { out.push(lines[i]); continue; }
    // the walls, drawn once in the floor file: side copies from the floor up, the top face, the dark's lit top
    const end = lines.indexOf('</g>', i), kids = lines.slice(i + 1, end), plain = kids.map((k) => k.replace(/ lit="[^"]*"/, ''));
    const paint = (c) => plain.map((k) => k.replace(/stroke="([^"]*)"/, (_, was) => `stroke="${c === '$side' && was === '$warmWall' ? '$warmSide' : c}"`));
    const g = (at, op, body) => [`<g transform="translate(${at})"${op < 1 ? ` opacity="${op}"` : ''}>`, ...body, '</g>'];
    for (const [dx, dy] of style.cast) out.push(...g(`${dx} ${dy}`, pick(style.oCast), paint('$shadow'))); // the contact shadow on the floor
    const step = style.H / style.layers;
    for (let n = 0; n < style.layers; n++) out.push(...g(`0 ${n ? '-' : ''}${fx(n * step)}`, pick(style.oSide), paint('$side')));
    out.push(...g('0 -$H', 1, plain));
    const lit = pick(style.lit);
    if (lit) out.push(...g(`0 -${fx(style.H + style.litRise)}`, style.oLit,
      kids.map((k) => k.replace(/stroke="[^"]*"/, `stroke="${lit}"`).replace(/stroke-width="[^"]*"(.*) lit="([^"]*)"/, 'stroke-width="$2"$1'))));
    i = end;
  }
  // words: none smaller than the style's least (it grows about its middle); a room's number sits in the middle of the
  // floor left in sight, and a wall's top hides `H` of it (the floor files are drawn for H = 4)
  const min = style.minText, up = (style.H - 4) / 2;
  for (let i = 0; i < out.length; i++) {
    if (!out[i].startsWith('<text')) continue;
    const num = out[i].includes('fill="$num"') && !out[i].includes('transform=');
    out[i] = out[i].replace(/^(.*?) y="([\d.]+)"(.*?) font-size="([\d.]+)"/, (_, a, y, b, fs) =>
      `${a} y="${fx(+y + Math.max(0, min - fs) * 0.36 - (num ? up : 0))}"${b} font-size="${Math.max(min, +fs)}"`);
  }
  return out.join('').replace(/\$([A-Za-z]\w*)/g, (_, k) => val(k));
}

// node tools/map/build.mjs: write every floor
if (import.meta.url === `file://${process.argv[1]}`) {
  const { readFileSync, writeFileSync, readdirSync } = await import('node:fs');
  const here = new URL('.', import.meta.url);
  for (const f of readdirSync(here)) {
    const n = /^floor-(\d)\.svg$/.exec(f)?.[1];
    if (!n) continue;
    const geo = readFileSync(new URL(f, here), 'utf8');
    for (const dark of [0, 1]) writeFileSync(new URL(`../../src/assets/map/kbtu-${n}${dark ? '-dark' : ''}.svg`, here), render(geo, dark));
  }
}
