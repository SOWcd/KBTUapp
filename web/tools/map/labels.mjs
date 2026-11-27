// The words of the drawn maps (the 2023 redraw, ours) as data: the app's map (MapLibre) draws the plans as pictures
// without their <text> and the words as its own labels, at a size one can read at any zoom, never one over another.
// `node tools/map/labels.mjs` writes src/assets/map/labels.json from the SVGs; map.test.ts fails while it is stale.
// A label: [u, v, text, key, size, turn, anchor, tier, fill, darkFill, halo, darkHalo, spacing, opacity]
//   u, v: its middle (anchor 0) or its left end (1) as fractions of the frame; size: in the plan's units of a
//   1000-wide frame; turn: degrees clockwise; key: its kmap.* word in the i18n files ('' when the text is as is);
//   tier: 0 always, 1 from mid zoom, 2 up close, 3 an area's name (class "area": big over its rooms, never in their
//   way); colours '' where the map's own theme picks them.

const num = (s, k) => { const m = new RegExp(`(?:^|\\s)${k}="([^"]*)"`).exec(s); return m ? m[1] : null; };
const plain = (s) => s.replace(/&#(\d+);/g, (_, n) => String.fromCodePoint(+n)).replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&');
const r4 = (n) => Math.round(n * 1e4) / 1e4;

/** Every <text> of an SVG with what it inherits from the groups round it: [{ at, text, ... }] in the SVG's own units */
function texts(svg) {
  const out = [], stack = [];
  const re = /<(\/?)(g|text)\b([^>]*)>([^<]*)/g;
  for (let m; (m = re.exec(svg));) {
    const [, end, tag, at, body] = m;
    if (tag === 'g') { if (end) stack.pop(); else if (!at.endsWith('/')) stack.push(at); continue; }
    if (end) continue;
    const round = [...stack].reverse(); // the groups it sits in, the nearest first
    const up = (k) => num(at, k) ?? round.map((g) => num(g, k)).find((v) => v != null) ?? null;
    const cls = [num(at, 'class'), ...round.map((g) => num(g, 'class'))].filter(Boolean).join(' ');
    out.push({ at, cls, text: plain(body), up });
  }
  return out;
}

/** One floor's labels. box: the frame in the SVG's units [x, y, width]; dark: the same floor's dark SVG, for its colours */
export function labelsOf(svg, box, dark = null) {
  const night = dark ? texts(dark) : null, k = 1000 / box[2];
  return texts(svg).map((t, i) => {
    const size = +t.up('font-size'), x = +num(t.at, 'x'), y0 = +num(t.at, 'y') - size * 0.36; // the middle of the capitals
    const rot = /rotate\((-?[\d.]+)(?:[ ,]+(-?[\d.]+)[ ,]+(-?[\d.]+))?\)/.exec(num(t.at, 'transform') ?? '');
    let px = x, py = y0, turn = 0;
    if (rot) {
      turn = +rot[1];
      const a = (turn * Math.PI) / 180, cx = +(rot[2] ?? 0), cy = +(rot[3] ?? 0);
      px = cx + (x - cx) * Math.cos(a) - (y0 - cy) * Math.sin(a); py = cy + (x - cx) * Math.sin(a) + (y0 - cy) * Math.cos(a);
    }
    const d = night?.[i], ink = (s, key) => (dark ? num(s.at, key) ?? '' : '');
    return [r4((px - box[0]) / box[2]), r4((py - box[1]) / box[2]), t.text, num(t.at, 'data-t') ?? '', Math.round(size * k * 10) / 10, turn,
      (t.up('text-anchor') ?? 'start') === 'middle' ? 0 : 1, /\barea\b/.test(t.cls) ? 3 : /\bfine\b/.test(t.cls) ? 2 : /\bmid\b/.test(t.cls) ? 1 : 0,
      ink(t, 'fill'), d ? ink(d, 'fill') : '', ink(t, 'stroke'), d ? ink(d, 'stroke') : '',
      +(num(t.at, 'letter-spacing') ?? 0) / size || 0, +(num(t.at, 'fill-opacity') ?? 1)];
  });
}

/** The frames: the 2023 plan whole, ours a 1000-unit cut of it */
export const BOX = { old: [0, 0, 1240], kbtu: [120, 130, 1000] };

/** Both drawn maps' labels by floor, from the SVGs' text: read(name) gives a file of src/assets/map */
export function allLabels(read) {
  const old = {}, kbtu = {};
  for (let n = 1; n <= 5; n++) {
    old[n] = labelsOf(read(`floor-${n}.svg`), BOX.old);
    kbtu[n] = labelsOf(read(`kbtu-${n}.svg`), BOX.kbtu, read(`kbtu-${n}-dark.svg`));
  }
  return { old, kbtu };
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const fs = await import('node:fs'), dir = new URL('../../src/assets/map/', import.meta.url);
  // plain ASCII (the plans' own letters as escapes): the repo keeps Cyrillic to the UI strings
  const json = JSON.stringify(allLabels((f) => fs.readFileSync(new URL(f, dir), 'utf8'))).replace(/[^\x20-\x7e]/g, (c) => `\\u${c.charCodeAt(0).toString(16).padStart(4, '0')}`);
  fs.writeFileSync(new URL('labels.json', dir), json + '\n');
}
