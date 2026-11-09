// The drawn achievement medals, in layers (public/medals/*.svg): vector, so crisp at any size and pixel ratio, and
// layered, so the field, the art and the near art float with the phone's tilt under a still rim (ui/Medal.svelte,
// lib/awards.ts layersOf). Every layer is the same 512 box centred on the medal; the field overscans under the rim.
// One look for all of them, the owner's struck coins (First 500, the 2026 initiation): a polished metal rim with a
// rolled bevel, a deep enamel field with an engine-turned guilloche, and the picture struck in relief in the level's
// metal, enamel laid into it where a colour tells it apart. The relief is real light, not paint: SVG lighting filters
// (relief() below) bevel every part from its own outline, so each part catches the light on its upper left, shades on
// its lower right and throws a shadow on what lies under it (owner, Nov 3: the flat pictures read childish).
//   Recruiter (rc-*): a constellation. I am the star in the middle; each level one more friend lights up on the
//     orbit, tied to me and to each other. The rim is the level's metal (bronze I-III, silver IV-VI, gold VII-VIII,
//     legend IX); gold grows laurels, legend a full wreath, the whole metal holographic foil and a crown star.
//   The others (rg, st, fi, so, tm, se, bg, dm, cr): <p>-field (its enamel), <p>-art-<metal> and <p>-near-<metal> (the
//     relief in the level's metal) under the rc rims; the ribbons; the pins (zn-*): the shield frames, the enamel's
//     guilloche, and the glyphs in the frame's metal (zn-<glyph>-<metal>).
// usage: node tools/medals.mjs   (from web/)
import { writeFileSync, mkdirSync, readdirSync, unlinkSync } from 'node:fs';
const out = new URL('../public/medals/', import.meta.url);
mkdirSync(out, { recursive: true });
const C = 256, FIELD = 212, f = (n) => +n.toFixed(2);
const pt = (r, deg) => [f(C + r * Math.sin((deg * Math.PI) / 180)), f(C - r * Math.cos((deg * Math.PI) / 180))];
const svg = (defs, body) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs>${defs}</defs>${body}</svg>\n`;
// a stop's colour, #RRGGBBAA as its colour and opacity (stop-color takes no alpha in older WebKit)
const stops = (cs) => cs.map((c, i) => `<stop offset="${f(i / (cs.length - 1))}" stop-color="${c.slice(0, 7)}"${c.length === 9 ? ` stop-opacity="${f(parseInt(c.slice(7), 16) / 255)}"` : ''}/>`).join('');
const lin = (id, cs, x2 = 0, y2 = 1, x1 = 0, y1 = 0) => `<linearGradient id="${id}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}">${stops(cs)}</linearGradient>`;
const rad = (id, cs, cx = 0.38, cy = 0.3, r = 0.75) => `<radialGradient id="${id}" cx="${cx}" cy="${cy}" r="${r}">${stops(cs)}</radialGradient>`;
const rng = (seed) => () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

// polished metal, as a struck face reflects a room: bright, a band of its body colour, a second highlight, its shade
const FACE = {
  g: ['#FFF7D6', '#F7D774', '#D29C2C', '#FFEDAE', '#C2861A', '#7A4C08'],
  s: ['#FFFFFF', '#E8EDF6', '#A8B1C4', '#F8FAFE', '#8E98AE', '#535C72'],
  b: ['#FFE8D2', '#EEB07A', '#B26A3C', '#F9D2AC', '#9C5828', '#5E2E12'],
  r: ['#FFEFE6', '#F5C3AE', '#BE7862', '#FCDACC', '#A8624C', '#64301F'],
};
// legend: holographic foil (owner, Nov 9: "just gold with rainbow edges"). The hues run through the part as a foil's do,
// a bright stop beside each deep one so it still reads as metal under relief()'s light; FACE.l for what wants
// single stops (the mirror ball's sphere, the cut lines' deep violet)
FACE.l = ['#FFF2FB', '#7FE8FF', '#B08CFF', '#FFE3A0', '#F050C8', '#3A1480'];
const HOLO = ['#E0249A', '#FF8AE0', '#FFE8FB', '#9A6BFF', '#4A38D8', '#3FC0FF', '#E2FBFF', '#2FD9AE', '#129A6E', '#C4F566', '#FFFCD8', '#FFB036', '#E2513A', '#E0249A'];
const METAL = {
  b: { rim: FACE.b, lit: '#FFD9B3', glow: '#FF9D57' },
  s: { rim: FACE.s, lit: '#F2F6FF', glow: '#9CC4FF' },
  g: { rim: FACE.g, lit: '#FFF0B8', glow: '#FFC94A' },
  l: { rim: FACE.l, iri: ['#FF6BD6', '#7C4DFF', '#35D0FF', '#2FD3A0', '#FFD23F', '#FF6BD6'], lit: '#FFFFFF', glow: '#E59BFF' },
};
// the Recruiter's enamel per metal (its constellation glows on it)
const RC_FIELD = { b: ['#1F4E6E', '#0C2438', '#04101C'], s: ['#2C55D6', '#142A85', '#070F3C'], g: ['#3A2A8C', '#1A1050', '#08051F'], l: ['#7A3BE0', '#3A1290', '#12043A'] };
const metalOf = (l) => (l === 9 ? 'l' : l >= 7 ? 'g' : l >= 4 ? 's' : 'b');

// Struck relief: the part's own outline blurred is its height; a distant light from the upper left shades it (diffuse,
// multiplied into the metal) and glints on its slopes (specular, added); then its shadow falls down and right.
// blur: how round the bevel; depth: how high; sh: the shadow's reach (0: none)
const relief = (id, blur, depth, sh = 1, spec = 1.15, exp = 22) => `<filter id="${id}" x="-25%" y="-25%" width="150%" height="160%" color-interpolation-filters="sRGB">
<feGaussianBlur in="SourceAlpha" stdDeviation="${blur}" result="h"/>
<feDiffuseLighting in="h" surfaceScale="${depth}" diffuseConstant="1" lighting-color="#FFFFFF" result="d"><feDistantLight azimuth="235" elevation="52"/></feDiffuseLighting>
<feComposite in="SourceGraphic" in2="d" operator="arithmetic" k1="1.3" result="l"/>
<feSpecularLighting in="h" surfaceScale="${depth}" specularConstant="${spec}" specularExponent="${exp}" lighting-color="#FFFFFF" result="s"><feDistantLight azimuth="235" elevation="38"/></feSpecularLighting>
<feComposite in="s" in2="SourceAlpha" operator="in" result="s2"/>
<feComposite in="l" in2="s2" operator="arithmetic" k2="1" k3=".85" result="m"/>
<feComposite in="m" in2="SourceAlpha" operator="in" result="o"/>${sh ? `
<feGaussianBlur in="SourceAlpha" stdDeviation="${f(sh * 5)}"/><feOffset dx="${f(sh * 3)}" dy="${f(sh * 7)}"/><feComponentTransfer><feFuncA type="linear" slope=".62"/></feComponentTransfer>
<feMerge><feMergeNode/><feMergeNode in="o"/></feMerge>` : ''}</filter>`;
// three heights: a main part, a raised detail, a fine one
const RELIEFS = relief('r1', 6, 7) + relief('r2', 3.5, 5, 0.6) + relief('r3', 1.8, 3, 0.35);
// the metal's fills: across the part, the other way, and a sphere's
const metals = (k) => k === 'l' ? lin('mg', HOLO, 1, 1) + lin('mh', [...HOLO.slice(6), ...HOLO.slice(1, 7)], 0, 1, 1, 0) + rad('ms', ['#FFFFFF', '#FFC8F4', '#9A6BFF', '#3FC0FF', '#2FD9AE', '#FFB036', '#7A1E9E'], 0.36, 0.3, 0.85) : lin('mg', FACE[k], 1, 1) + lin('mh', [FACE[k][3], FACE[k][1], FACE[k][2], FACE[k][0], FACE[k][4]], 0, 1, 1, 0) + rad('ms', [FACE[k][0], FACE[k][1], FACE[k][2], FACE[k][5]], 0.36, 0.3, 0.8);
const part = (filter, fill, body) => `<g filter="url(#${filter})" fill="url(#${fill})">${body}</g>`;
// a line cut into the metal: its upper left wall in shadow, its lower right one catching the light
const cut = (d, w = 5, k = 'g') => `<path d="${d}" fill="none" stroke="${FACE[k][5]}" stroke-opacity=".75" stroke-width="${w}" stroke-linecap="round" stroke-linejoin="round"/><path d="${d}" fill="none" stroke="#FFFFFF" stroke-opacity=".5" stroke-width="${f(w * 0.4)}" stroke-linecap="round" stroke-linejoin="round" transform="translate(${f(w * 0.3)} ${f(w * 0.3)})"/>`;
// enamel laid into a cell of the metal: its glossy colour, the cell's wall shading its top edge, the glaze's light
const enamel = (d, fill, extra = '') => `<path d="${d}" fill="url(#${fill})"/><path d="${d}" fill="none" stroke="#000" stroke-opacity=".4" stroke-width="3" transform="translate(-1 -1.5)"/>${extra}`;
// a glint of light off the polish: a thin four-point flare in a soft halo
const star4 = (x, y, r, w, fill) =>
  `<path d="M${x} ${f(y - r)}Q${f(x + w)} ${f(y - w)} ${f(x + r)} ${y}Q${f(x + w)} ${f(y + w)} ${x} ${f(y + r)}Q${f(x - w)} ${f(y + w)} ${f(x - r)} ${y}Q${f(x - w)} ${f(y - w)} ${x} ${f(y - r)}z" fill="${fill}"/>`;
const GLINT = rad('gh', ['#FFFFFFCC', '#FFFFFF00'], 0.5, 0.5, 0.5);
const glint = (x, y, r) => `<circle cx="${x}" cy="${y}" r="${f(r * 0.7)}" fill="url(#gh)"/>${star4(x, y, r, r / 9, '#FFFFFF')}`;
const star5 = (x, y, R, r = R * 0.45, rot = 0) => 'M' + Array.from({ length: 10 }, (_, i) => { const a = ((i * 36 + rot) * Math.PI) / 180, k = i % 2 ? r : R; return `${f(x + k * Math.sin(a))} ${f(y - k * Math.cos(a))}`; }).join('L') + 'z';

// a laurel branch inside the rim, from the bottom up one side: paired leaves leaning along the growth
function laurel(side, span) {
  let s = '';
  const R = 194, n = Math.round(span / 11);
  for (let i = 0; i < n; i++) {
    const a = 180 + side * (14 + i * 11), r = (a * Math.PI) / 180;
    const [x, y] = pt(R, a), th = (Math.atan2(side * Math.cos(r), -side * Math.sin(r)) * 180) / Math.PI, k = 1 - i * 0.025;
    for (const lean of [-40, 40]) s += `<path d="M0 0Q11 -15 0 -32Q-11 -15 0 0z" transform="translate(${x} ${y}) rotate(${f(th + lean)}) scale(${f(k)})"/>`;
  }
  const [x0, y0] = pt(R, 180 + side * 6), [x1, y1] = pt(R, 180 + side * (14 + (n - 1) * 11));
  return `<path d="M${x0} ${y0}A${R} ${R} 0 0 ${side > 0 ? 1 : 0} ${x1} ${y1}" fill="none" stroke="url(#mg)" stroke-width="5" stroke-linecap="round"/>` + s;
}

// the rim: a milled outer edge, a broad polished band rolled at both edges, a thin raised lip, a step down into
// the field; the field's sunk edge shadowed under it, the glaze's gloss across the enamel
function rim(k, extra = '') {
  const m = METAL[k];
  let knurl = '';
  for (let i = 0; i < 160; i++) { const [a, b] = pt(253, i * 2.25), [c, d] = pt(242, i * 2.25); knurl += `M${a} ${b}L${c} ${d}`; }
  const ring = (r0, r1) => `<path fill-rule="evenodd" d="M${C - r1} ${C}a${r1} ${r1} 0 1 0 ${2 * r1} 0a${r1} ${r1} 0 1 0 ${-2 * r1} 0zM${C - r0} ${C}a${r0} ${r0} 0 1 0 ${2 * r0} 0a${r0} ${r0} 0 1 0 ${-2 * r0} 0z"/>`;
  return svg(`${metals(k)}${relief('rr', 10, 11, 0.5)}${relief('re', 3, 6, 0)}${RELIEFS}
<linearGradient id="gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".2"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>
<radialGradient id="halo" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="${m.glow}" stop-opacity=".75"/><stop offset="1" stop-color="${m.glow}" stop-opacity="0"/></radialGradient>

<radialGradient id="sink" cx=".5" cy=".5" r=".5"><stop offset=".88" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".55"/></radialGradient>`,
  `<circle cx="${C}" cy="${C}" r="${FIELD + 1}" fill="url(#sink)"/>
<path d="M${C - 200} ${C - 30}A${FIELD} ${FIELD} 0 0 1 ${C + 170} ${C - 120}Q${C} ${C - 120} ${C - 200} ${C - 30}z" fill="url(#gloss)"/>
${part('re', 'mh', ring(238, 255))}
<path d="${knurl}" stroke="${m.rim[5]}" stroke-width="1.6" opacity=".5"/>
${part('rr', 'mg', ring(220, 240))}

${part('r3', 'mh', ring(FIELD, 221))}
<circle cx="${C}" cy="${C}" r="${FIELD}" fill="none" stroke="#000" stroke-opacity=".45" stroke-width="2.5"/>
${extra}`);
}

// the field: deep enamel over an engine-turned ground (a fine sunburst and the banknote rosette the KBTU lanyard uses),
// a soft light in it, darker to its edge; r 236: it overscans under the rim. `dust`: the Recruiter's far stars
function field(colors, seed, light = [C, C], rayAlpha = 0.3, dust = false) {
  let rays = '', guil = '', fine = '', specks = '';
  for (let i = 0; i < 32; i++) {
    const a = (i * 11.25 * Math.PI) / 180, b = 0.026;
    rays += `M${light[0]} ${light[1]}L${f(light[0] + 330 * Math.sin(a - b))} ${f(light[1] - 330 * Math.cos(a - b))}L${f(light[0] + 330 * Math.sin(a + b))} ${f(light[1] - 330 * Math.cos(a + b))}z`;
  }
  for (let i = 0; i < 180; i++) { const [a, b] = pt(236, i * 2), [c, d] = pt(30, i * 2); fine += `M${c} ${d}L${a} ${b}`; }
  for (let i = 0; i < 24; i++) guil += `<ellipse cx="${C}" cy="${C}" rx="212" ry="80" transform="rotate(${f(i * 7.5)} ${C} ${C})"/>`;
  if (dust) { const rnd = rng(seed); for (let i = 0; i < 52; i++) { const [x, y] = pt(50 + rnd() * 180, rnd() * 360); specks += `<circle cx="${x}" cy="${y}" r="${f(0.8 + rnd() * 1.6)}" opacity="${f(0.25 + rnd() * 0.5)}"/>`; } }
  return svg(`<radialGradient id="field" cx=".42" cy=".34" r=".75">${stops(colors)}</radialGradient>
<radialGradient id="rays" cx="${f(light[0] / 512)}" cy="${f(light[1] / 512)}" r=".5"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".5"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></radialGradient>
<radialGradient id="vig" cx=".5" cy=".5" r=".5"><stop offset=".6" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".45"/></radialGradient>
<clipPath id="in"><circle cx="${C}" cy="${C}" r="236"/></clipPath>`,
  `<circle cx="${C}" cy="${C}" r="236" fill="url(#field)"/><g clip-path="url(#in)">
<path d="${fine}" stroke="#FFFFFF" stroke-width="1" opacity=".06"/>
<g fill="none" stroke="#FFFFFF" stroke-width="1" opacity=".08">${guil}</g>
<path d="${rays}" fill="url(#rays)" opacity="${rayAlpha}"/>
<g fill="#FFFFFF">${specks}</g>
<circle cx="${C}" cy="${C}" r="236" fill="url(#vig)"/></g>`);
}

// ---- Recruiter
function nodes(level) {
  if (level === 9) return [...[0, 90, 180, 270].map((a) => [104, a + 45, 17]), ...Array.from({ length: 8 }, (_, i) => [160, i * 45, 15])];
  const start = level === 1 ? 45 : level === 2 ? -60 : 0;
  return Array.from({ length: level }, (_, i) => [146, start + (i * 360) / level, 19]);
}
const bust = (x, y, s, fill) =>
  `<g fill="${fill}" opacity=".85"><circle cx="${x}" cy="${f(y - s * 0.28)}" r="${f(s * 0.26)}"/><path d="M${f(x - s * 0.5)} ${f(y + s * 0.5)}a${f(s * 0.5)} ${f(s * 0.46)} 0 0 1 ${f(s)} 0z"/></g>`;

function net(level) {
  const k = metalOf(level), m = METAL[k], ns = nodes(level), pos = ns.map(([r, a, s]) => [...pt(r, a), s, r]);
  let ties = '', web = '';
  for (const [x, y] of pos) ties += `M${C} ${C}L${x} ${y}`;
  const ring = (list) => { for (let i = 0; i < list.length && list.length > 1; i++) { if (list.length === 2 && i === 1) break; const [x, y] = list[i], [u, v] = list[(i + 1) % list.length]; web += `M${x} ${y}L${u} ${v}`; } };
  ring(pos.filter((p) => p[3] === pos[0][3])); ring(pos.filter((p) => p[3] !== pos[0][3]));
  if (level === 9) for (let i = 0; i < 4; i++) for (const j of [0, 1, 2]) { const a = pos[i], b = pos[4 + ((i * 2 + j) % 8)]; web += `M${a[0]} ${a[1]}L${b[0]} ${b[1]}`; }
  // the friends are struck metal studs now (their busts cut in), the ties light
  return svg(`<linearGradient id="tie" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${m.lit}"/><stop offset="1" stop-color="${m.glow}"/></linearGradient>
<radialGradient id="halo" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="${m.glow}" stop-opacity=".75"/><stop offset="1" stop-color="${m.glow}" stop-opacity="0"/></radialGradient>${metals(k)}${RELIEFS}`,
  `${[...new Set(ns.map((n) => n[0]))].map((r) => `<circle cx="${C}" cy="${C}" r="${r}" fill="none" stroke="${m.lit}" stroke-width="1.6" stroke-dasharray="2 7" stroke-linecap="round" opacity=".45"/>`).join('')}
<path d="${web}" stroke="${m.lit}" stroke-width="3" stroke-linecap="round" opacity=".35" fill="none"/>
<path d="${ties}" stroke="url(#tie)" stroke-width="9" stroke-linecap="round" opacity=".18" fill="none"/>
<path d="${ties}" stroke="${m.lit}" stroke-width="3.2" stroke-linecap="round" opacity=".85" fill="none"/>
${pos.map(([x, y, s]) => `<circle cx="${x}" cy="${y}" r="${f(s * 2)}" fill="url(#halo)"/>`).join('')}
${part('r2', 'ms', pos.map(([x, y, s]) => `<circle cx="${x}" cy="${y}" r="${s}"/>`).join(''))}
${pos.map(([x, y, s]) => bust(x, y + 1, s * 1.15, FACE[k][5])).join('')}`);
}

const core = (m) => svg(`<radialGradient id="core" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#FFFFFF"/><stop offset=".35" stop-color="${m.lit}"/><stop offset=".7" stop-color="${m.glow}" stop-opacity=".55"/><stop offset="1" stop-color="${m.glow}" stop-opacity="0"/></radialGradient>`,
  `<circle cx="${C}" cy="${C}" r="96" fill="url(#core)"/>${star4(C, C, 70, 9, m.lit)}${star4(C, C, 46, 5, '#FFFFFF')}<g transform="rotate(45 ${C} ${C})" opacity=".8">${star4(C, C, 30, 4, '#FFFFFF')}</g><circle cx="${C}" cy="${C}" r="11" fill="#FFFFFF"/>`);

const files = {};
for (const k of 'bsgl') {
  const m = METAL[k];
  files[`rc-field-${k}`] = field(RC_FIELD[k], 'bsgl'.indexOf(k) * 97 + 13, [C, C], 0.38, true);
  files[`rc-core-${k}`] = core(m);
  const wreath = k === 'g' || k === 'l' ? part('r3', 'mg', laurel(1, k === 'l' ? 140 : 66) + laurel(-1, k === 'l' ? 140 : 66)) : '';
  files[`rc-rim-${k}`] = rim(k, wreath + (k === 'l' ? `<circle cx="${C}" cy="26" r="34" fill="url(#halo)"/>${star4(C, 26, 30, 5, '#FFFFFF')}<circle cx="${C}" cy="26" r="5" fill="#FFFFFF"/>` : ''));
}
for (let l = 1; l <= 9; l++) files[`rc-net-${l}`] = net(l);


// ---- the other medals (round 3, owner Nov 3: "the same as my coins"): one bold subject each, struck in heavy relief
// in the level's metal and filling its field the way the 2026 dome fills his coin, enamel laid into it where a colour
// tells it apart, few small details (it reads at 34 px). A calm enamel field (engine-turned, a soft light behind the
// subject, no rays) inside a wide polished band (md-rim-<m>, no laurels: the band's metal is the level, legend's a
// holographic foil), which carries the medal's name engraved round its top at full size (<p>-legend-<m>, ui/Medal from
// 160 px, as his coins carry theirs). Layers: <p>-field (far), <p>-art-<m> (the subject), <p>-near-<m> (its nearest
// part, floats most). Every subject keeps inside r 180.
const ENAMELS = lin('er', ['#FF7A6A', '#D6283A', '#8A0E22'], 0.3, 1) + lin('eo', ['#FFE08A', '#FF9A2A', '#E0441C', '#9E1420'], 0, 1)
  + lin('ew', ['#FFFFF4', '#FFF0B8', '#FFC864'], 0, 1) + lin('ek', ['#3A3448', '#141019'], 0, 1) + lin('ey', ['#FFF6B0', '#FFD23A', '#F09A1A'], 0, 1)
  + lin('ec', ['#FF9C80', '#E2573A', '#A8341E'], 0, 1) + lin('eb', ['#B8E6FF', '#4AA8F0', '#1A5EB8'], 0, 1);
const MR = 188; // the medals' field radius
// the heavy strike: a deep, round bevel and a strong glint, its shadow long
const R0 = relief('r0', 9, 15, 1.4, 1.5, 16);
// a subject drawn round (cx, cy), scaled to the field
const fit = (s, cx, cy, body) => `<g transform="translate(256 256) scale(${s}) translate(${-cx} ${-cy})">${body}</g>`;

function mdRim(k) {
  const m = METAL[k];
  let knurl = '';
  for (let i = 0; i < 160; i++) { const [a, b] = pt(254, i * 2.25), [c, d] = pt(244, i * 2.25); knurl += `M${a} ${b}L${c} ${d}`; }
  const ring = (r0, r1) => `<path fill-rule="evenodd" d="M${C - r1} ${C}a${r1} ${r1} 0 1 0 ${2 * r1} 0a${r1} ${r1} 0 1 0 ${-2 * r1} 0zM${C - r0} ${C}a${r0} ${r0} 0 1 0 ${2 * r0} 0a${r0} ${r0} 0 1 0 ${-2 * r0} 0z"/>`;
  return svg(`${metals(k)}${relief('rr', 7, 8, 0.5, 1.3, 18)}${lin('band', k === 'l' ? HOLO : [FACE[k][4], FACE[k][1], FACE[k][3], FACE[k][2], FACE[k][5], FACE[k][2], FACE[k][1], FACE[k][3], FACE[k][4]], 1, 1)}${relief('re', 3, 6, 0)}${RELIEFS}
<linearGradient id="gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".16"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>

<radialGradient id="sink" cx=".5" cy=".5" r=".5"><stop offset=".86" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".6"/></radialGradient>`,
  `<circle cx="${C}" cy="${C}" r="${MR + 1}" fill="url(#sink)"/>
<path d="M${C - 176} ${C - 30}A${MR} ${MR} 0 0 1 ${C + 150} ${C - 112}Q${C} ${C - 104} ${C - 176} ${C - 30}z" fill="url(#gloss)"/>
${part('re', 'mh', ring(240, 255))}
<path d="${knurl}" stroke="${m.rim[5]}" stroke-width="1.6" opacity=".5"/>
${part('rr', 'band', ring(MR + 4, 242))}

${part('r3', 'mh', ring(MR, MR + 6))}
<circle cx="${C}" cy="${C}" r="${MR}" fill="none" stroke="#000" stroke-opacity=".5" stroke-width="2.5"/>`);
}
for (const k of 'bsgl') files[`md-rim-${k}`] = mdRim(k);

// the medal's name engraved round the band's top: each letter's upper left wall in shadow, its lower right lit
const legendSvg = (k, words) => {
  const arc = `<path id="arc" d="M${C - 207} ${C}A207 207 0 0 1 ${C + 207} ${C}" fill="none"/>`;
  const txt = (fill, op, dx) => `<text font-family="Georgia, 'Times New Roman', serif" font-size="22" font-weight="700" letter-spacing="2.5" text-anchor="middle" fill="${fill}" fill-opacity="${op}"${dx ? ` transform="translate(${dx} ${dx})"` : ''}><textPath href="#arc" xlink:href="#arc" startOffset="50%">${words}</textPath></text>`;
  return `<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 512 512"><defs>${arc}</defs>${txt('#FFFFFF', 0.55, 1.3)}${txt(FACE[k][5], 0.85, 0)}</svg>\n`;
};

// the field: calm deep enamel over a guilloche, as his 500 coin's: two engine-turned rosettes of a wave turned round the
// centre (one curve, its turned copies by <use>: a few hundred bytes), each line cut fine into the ground (its shadow
// side dark, its lit side catching the light from the upper left), a soft light behind the subject
const wave = (r, a, n) => 'M' + Array.from({ length: 145 }, (_, i) => { const t = (i * 2.5 * Math.PI) / 180, k = r + a * Math.sin(n * t); return `${f(C + k * Math.sin(t))} ${f(C - k * Math.cos(t))}`; }).join('L') + 'z';
function mfield(colors) {
  const turn = (id, copies, period) => Array.from({ length: copies }, (_, i) => `<use href="#${id}" transform="rotate(${f((i * period) / copies)} ${C} ${C})"/>`).join('');
  const lines = turn('w1', 22, 360 / 7) + turn('w2', 30, 360 / 12);
  return svg(`<radialGradient id="field" cx=".42" cy=".36" r=".72">${stops(colors)}</radialGradient>
<radialGradient id="lt" cx=".5" cy=".47" r=".34"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".2"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></radialGradient>
<radialGradient id="vig" cx=".5" cy=".5" r=".5"><stop offset=".62" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".5"/></radialGradient>
<linearGradient id="gl" gradientUnits="userSpaceOnUse" x1="60" y1="40" x2="452" y2="472"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".36"/><stop offset=".5" stop-color="#FFFFFF" stop-opacity=".14"/><stop offset="1" stop-color="#FFFFFF" stop-opacity=".05"/></linearGradient>
<path id="w1" d="${wave(110, 36, 7)}" fill="none"/><path id="w2" d="${wave(166, 18, 12)}" fill="none"/>`,
  `<circle cx="${C}" cy="${C}" r="236" fill="url(#field)"/>
<g stroke="#000000" stroke-opacity=".22" stroke-width="1.1">${lines}</g>
<g stroke="url(#gl)" stroke-width=".8" transform="translate(.8 .8)">${lines}</g>
<circle cx="${C}" cy="${C}" r="236" fill="url(#lt)"/><circle cx="${C}" cy="${C}" r="236" fill="url(#vig)"/>`);
}

const pic = (p, fieldColors, words, art, near) => {
  files[`${p}-field`] = mfield(fieldColors);
  for (const k of 'bsgl') {
    const head = metals(k) + RELIEFS + R0 + ENAMELS + GLINT;
    files[`${p}-art-${k}`] = svg(head, art(k));
    files[`${p}-near-${k}`] = svg(head, near(k));
    files[`${p}-legend-${k}`] = legendSvg(k, words);
  }
};
const DOT = ' · ';

// Regular: an admission ticket, notched and perforated, the star punched through it raised in red enamel
const TICKET = 'M136 180H376Q394 180 394 198V234A22 22 0 0 0 394 278V314Q394 332 376 332H136Q118 332 118 314V278A22 22 0 0 0 118 234V198Q118 180 136 180z';
const TK = (body) => fit(1.18, 256, 256, `<g transform="rotate(-14 256 256)">${body}</g>`);
pic('rg', ['#9A2244', '#4E0B22', '#1C030C'], 'REGULAR' + DOT + 'KBTU APP',
  (k) => TK(`${part('r0', 'mg', `<path d="${TICKET}"/>`)}
${cut('M150 206Q150 196 160 196H362Q378 196 378 206V306Q378 316 368 316H160Q150 316 150 306z', 4, k)}
<g fill="${FACE[k][5]}" opacity=".85">${[0, 1, 2, 3, 4, 5].map((i) => `<circle cx="324" cy="${211 + i * 18}" r="4.5"/>`).join('')}</g>`),
  (k) => TK(`${part('r1', 'mg', `<path d="${star5(232, 256, 60, 27)}"/>`)}${enamel(star5(232, 256, 38, 17), 'er')}`));

// Streak: a flame burning on: the metal flame, its heart in fire enamel, the white-hot core raised
pic('st', ['#4E2498', '#220C56', '#0A0420'], 'ON A STREAK' + DOT + 'KBTU APP',
  (k) => fit(1.06, 256, 248, `${part('r0', 'mg', '<path d="M262 92C276 150 352 180 360 268C368 350 316 404 256 404C190 404 146 356 152 288C156 240 184 214 196 172C206 206 214 222 232 234C230 184 236 136 262 92z"/>')}
${enamel('M266 176C276 222 326 246 326 306C326 356 296 384 256 384C214 384 186 354 188 314C190 282 208 262 218 236C226 260 236 270 248 276C246 240 250 206 266 176z', 'eo')}`),
  (k) => fit(1.06, 256, 248, part('r1', 'ms', '<path d="M260 262C268 292 298 308 296 342C294 370 278 384 256 384C232 384 218 368 218 344C218 318 238 300 248 278C252 290 256 294 260 296z"/>')));

// First in: an arched doorway full of the room's light, the door swung open toward me
pic('fi', ['#2448AC', '#0F2260', '#050B26'], 'FIRST IN' + DOT + 'KBTU APP',
  (k) => fit(1.16, 250, 252, `${enamel('M192 356V202Q192 144 256 144Q320 144 320 202V356z', 'ew')}
${part('r0', 'mg', '<path fill-rule="evenodd" d="M168 356V196Q168 120 256 120Q344 120 344 196V356zM192 356V202Q192 144 256 144Q320 144 320 202V356z"/>')}
${part('r1', 'mh', '<rect x="160" y="352" width="192" height="20" rx="6"/>')}`),
  (k) => fit(1.16, 250, 252, `${part('r1', 'mh', '<path d="M192 352V202Q192 166 206 154L156 178Q148 184 148 196V366Q148 378 160 374z"/>')}
${cut('M162 212L182 202V262L162 270zM162 298L182 290V340L162 348z', 3, k)}${part('r3', 'ms', '<circle cx="178" cy="282" r="7"/>')}`));

// Life of the party: a mirror ball hanging from the rim, each facet its own small plate of metal, a few flashing
const ball = (k) => {
  const cx = 256, cy = 270, R = 128, rnd = rng(77);
  let tiles = '', lights = '';
  for (let lat = -84; lat < 84; lat += 15) {
    const y0 = cy + R * Math.sin((lat * Math.PI) / 180), y1 = cy + R * Math.sin(((lat + 15) * Math.PI) / 180);
    const w = R * Math.cos(((lat + 7.5) * Math.PI) / 180), n = Math.max(4, Math.round((2 * w) / 26));
    for (let i = 0; i < n; i++) {
      const x0 = cx - w + (2 * w * i) / n, ww = (2 * w) / n, r = rnd(), cell = `x="${f(x0 + 1.8)}" y="${f(y0 + 1.8)}" width="${f(ww - 3.6)}" height="${f(y1 - y0 - 3.6)}" rx="2"`;
      tiles += `<rect ${cell}/>`;
      if (r < 0.06) lights += `<rect ${cell} fill="#FFFFFF" opacity=".6"/>`;
    }
  }
  return `${part('r3', 'mh', '<rect x="251" y="40" width="10" height="110" rx="5"/>')}${part('r1', 'mg', '<rect x="234" y="128" width="44" height="22" rx="6"/>')}
${part('r0', 'ms', `<circle cx="${cx}" cy="${cy}" r="${R}"/>`)}
<circle cx="${cx}" cy="${cy}" r="${R - 1}" fill="${FACE[k][5]}" opacity=".6"/>
<radialGradient id="mb" gradientUnits="userSpaceOnUse" cx="${cx - 46}" cy="${cy - 54}" r="${R * 1.6}">${stops([FACE[k][0], FACE[k][3], FACE[k][1], FACE[k][2], FACE[k][5]])}</radialGradient>
<clipPath id="bc"><circle cx="${cx}" cy="${cy}" r="${R - 2}"/></clipPath><g clip-path="url(#bc)">${part('r3', 'mb', tiles)}${lights}</g>`;
};
pic('so', ['#92207E', '#480A40', '#1A0318'], 'LIFE OF THE PARTY' + DOT + 'KBTU APP', ball, () => `${glint(206, 214, 44)}${glint(318, 330, 18)}`);

// Teambuilding thunder: a storm cloud and the bolt out of it, in yellow enamel
pic('tm', ['#22609A', '#0C2C4C', '#04121F'], 'TEAMBUILDING' + DOT + 'KBTU APP',
  (k) => fit(1.12, 256, 270, `${part('r0', 'mg', '<path d="M150 300Q114 300 114 264Q114 230 150 226Q152 186 196 182Q216 136 266 136Q322 136 336 188Q394 188 398 244Q400 300 344 300z"/>')}
${cut('M200 186Q218 150 264 150Q302 150 318 180', 4, k)}`),
  (k) => fit(1.12, 256, 270, `${part('r0', 'mh', '<path d="M272 258L220 354H260L244 420L322 322H278L306 258z"/>')}
${enamel('M276 270L236 342H272L262 386L304 334H264L286 270z', 'ey')}`));

// Season: a desk calendar, a term's days ticked off in red enamel, its binder rings over the top
pic('se', ['#A2501A', '#521F06', '#1E0A02'], 'SEASON' + DOT + 'KBTU APP',
  (k) => {
    const on = [0, 1, 2, 4, 5, 6, 8];
    let cells = '', ticks = '', empty = '';
    for (let i = 0; i < 12; i++) {
      const x = 176 + (i % 4) * 42, y = 230 + Math.floor(i / 4) * 46;
      if (on.includes(i)) { cells += `<circle cx="${x + 16}" cy="${y + 16}" r="16"/>`; ticks += `M${x + 8} ${y + 16}l6 6l11 -12`; }
      else empty += `M${x + 4} ${y + 4}h24v24h-24z`;
    }
    return fit(1.12, 256, 250, `${part('r0', 'mg', '<rect x="150" y="146" width="212" height="232" rx="24"/>')}
${enamel('M176 160H336Q348 160 348 172V210H164V172Q164 160 176 160z', 'er')}
${cut(empty, 3, k)}<g fill="url(#er)">${cells}</g><path d="${ticks}" fill="none" stroke="#FFFFFF" stroke-width="4.5" stroke-linecap="round" stroke-linejoin="round"/>`);
  },
  (k) => fit(1.12, 256, 250, part('r1', 'mh', '<rect x="194" y="122" width="20" height="52" rx="10"/><rect x="298" y="122" width="20" height="52" rx="10"/>')));

// Bug hunter: a ladybird, big: struck legs and head, its wing cases red enamel with their black spots
const LB = (body) => fit(1.16, 262, 250, `<g transform="rotate(-24 262 262)">${body}</g>`);
pic('bg', ['#22804A', '#0B3D22', '#03170C'], 'BUG HUNTER' + DOT + 'KBTU APP',
  (k) => LB(`${part('r1', 'mh', '<path d="M206 236l-30 -14M200 270l-34 2M208 304l-28 18M318 236l30 -14M324 270l34 2M316 304l28 18M246 168Q236 140 214 134M278 168Q288 140 310 134" fill="none" stroke="url(#mh)" stroke-width="9" stroke-linecap="round"/><circle cx="213" cy="133" r="10"/><circle cx="311" cy="133" r="10"/>')}
${part('r0', 'ms', '<ellipse cx="262" cy="188" rx="48" ry="34"/>')}`),
  (k) => LB(`${part('r0', 'mg', '<ellipse cx="262" cy="272" rx="86" ry="98"/>')}
${enamel('M256 186Q188 192 184 268Q184 342 256 364z', 'er')}${enamel('M268 186Q336 192 340 268Q340 342 268 364z', 'er')}
<g fill="url(#ek)"><circle cx="224" cy="236" r="16"/><circle cx="300" cy="236" r="16"/><circle cx="212" cy="296" r="14"/><circle cx="312" cy="296" r="14"/><circle cx="238" cy="338" r="10"/><circle cx="286" cy="338" r="10"/></g>
<ellipse cx="220" cy="218" rx="22" ry="10" fill="#FFFFFF" opacity=".45" transform="rotate(-36 220 218)"/>`));

// Attendance required: a raised open hand, the "I'm here" of a roll call, one silhouette so the bevel runs round it all;
// a tick in enamel on the palm, as Season's days
const FINGER = (cx, top, rot, w = 50, base = 300) => `<rect x="${cx - w / 2}" y="${top}" width="${w}" height="${base - top}" rx="${w / 2}" transform="rotate(${rot} ${cx} ${base})"/>`;
pic('dm', ['#8E2438', '#470C1C', '#1A040A'], 'ATTENDANCE' + DOT + 'KBTU APP',
  () => fit(1.12, 240, 258, part('r0', 'mg', `<path d="M164 256H350Q356 330 334 376Q322 402 290 402H222Q190 402 178 376Q158 330 164 256z"/>${FINGER(190, 150, -9)}${FINGER(240, 118, -3)}${FINGER(290, 130, 3)}${FINGER(338, 176, 10, 44)}${FINGER(182, 234, -38, 50, 350)}`)),
  () => fit(1.12, 240, 258, `${part('r1', 'mh', '<circle cx="256" cy="328" r="46"/>')}<circle cx="256" cy="328" r="35" fill="url(#er)"/><path d="M238 329l13 13l23 -26" fill="none" stroke="#FFFFFF" stroke-width="9" stroke-linecap="round" stroke-linejoin="round"/>`));

// Couch critic: a deep sofa in coral upholstery in its metal frame, a speech bubble over it with its three dots
pic('cr', ['#18848A', '#0A3E44', '#021A1D'], 'COUCH CRITIC' + DOT + 'KBTU APP',
  (k) => fit(1.08, 256, 250, `${part('r3', 'mh', '<rect x="150" y="360" width="18" height="26" rx="5"/><rect x="344" y="360" width="18" height="26" rx="5"/>')}
${part('r0', 'mg', '<rect x="150" y="224" width="212" height="94" rx="30"/>')}
${enamel('M178 240H334Q346 240 346 252V300H166V252Q166 240 178 240z', 'ec')}
${part('r1', 'mh', '<rect x="136" y="340" width="240" height="28" rx="10"/>')}
${part('r1', 'mg', '<rect x="166" y="290" width="180" height="60" rx="18"/>')}
${enamel('M184 302H328Q336 302 336 310V334Q336 340 328 340H184Q176 340 176 334V310Q176 302 184 302z', 'ec')}
${part('r1', 'mg', '<rect x="120" y="260" width="58" height="108" rx="27"/><rect x="334" y="260" width="58" height="108" rx="27"/>')}`),
  (k) => fit(1.08, 256, 250, `${part('r0', 'mh', '<path d="M200 102H312Q342 102 342 132V164Q342 194 312 194H286L262 220L256 194H200Q170 194 170 164V132Q170 102 200 102z"/>')}
<g fill="url(#ek)"><circle cx="220" cy="148" r="13"/><circle cx="256" cy="148" r="13"/><circle cx="292" cy="148" r="13"/></g>`));

// a medal's ribbon at 96 px and up (ui/Medal): two tails behind the disc, cut in a V: dark navy grosgrain, the level's
// metal woven in as two stripes (legend: the iridescent one), shaded where it folds behind the disc
for (const k of 'bsgl') {
  const m = METAL[k], tail = (side) => `<g transform="translate(256 360) rotate(${side * 24})"><path d="M-62 0H62V240L0 200L-62 240z" fill="url(#rb)"/>
<path d="M-40 0H-28V226L-40 233zM28 0H40V233L28 226z" fill="url(#st)"/>
<path d="M-8 0H8V205L0 200L-8 205z" fill="${k === 'l' ? 'url(#iri)' : 'url(#st)'}" opacity="${k === 'l' ? 0.95 : 0.6}"/>
<path d="M-62 0H62V40H-62z" fill="url(#fold)"/></g>`;
  files[`ribbon-${k}`] = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 640"><defs>${lin('rb', ['#0C1438', '#22306E', '#2E3E86', '#1A2558', '#0A1030'], 1, 0)}${lin('st', [m.rim[0], m.rim[1], m.rim[2]], 1, 0)}${lin('fold', ['#000000AA', '#00000000'], 0, 1)}${m.iri ? lin('iri', m.iri, 0, 1) : ''}</defs>${tail(-1)}${tail(1)}</svg>\n`;
}

// ---- pins: an event's pin is a shield (ui/Pin): its emoji on its colour, zn-enamel's guilloche over it, the milled
// metal frame (zn-frame-<m>). SHIELD is lib/awards.ts SHIELD: the two stay equal. The app's own drawn pins are round
// medals as Recruiter's (below).
const SHIELD = 'M100 78Q256 44 412 78Q440 84 440 112V268Q440 398 256 480Q72 398 72 268V112Q72 84 100 78Z';
const SC = [256, 262]; // the shield's middle, for scaling it
const scaled = (s) => `translate(${SC[0]} ${SC[1]}) scale(${s}) translate(${-SC[0]} ${-SC[1]})`;
files['zn-enamel'] = (() => {
  let fine = '', guil = '';
  for (let i = 0; i < 180; i++) { const a = (i * 2 * Math.PI) / 180; fine += `M256 250L${f(256 + 300 * Math.sin(a))} ${f(250 - 300 * Math.cos(a))}`; }
  for (let i = 0; i < 24; i++) guil += `<ellipse cx="256" cy="250" rx="190" ry="72" transform="rotate(${f(i * 7.5)} 256 250)"/>`;
  return svg(`<clipPath id="in"><path d="${SHIELD}"/></clipPath>${rad('lt', ['#FFFFFF33', '#FFFFFF00'], 0.42, 0.32, 0.6)}<radialGradient id="vig" cx=".5" cy=".46" r=".6"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".5"/></radialGradient>`,
    `<g clip-path="url(#in)"><path d="${fine}" stroke="#FFFFFF" stroke-width="1" opacity=".07"/><g fill="none" stroke="#FFFFFF" stroke-width="1" opacity=".09">${guil}</g>
<rect width="512" height="512" fill="url(#lt)"/><rect width="512" height="512" fill="url(#vig)"/></g>`);
})();
// the frame: rc-rim's craft round the shield: a milled outer edge, a rolled polished band, a fine bright lip inside it
for (const k of 'gsr') {
  files[`zn-frame-${k}`] = svg(metals(k) + relief('rr', 7, 9, 0.4, 1.3, 18) + lin('gl', ['#FFFFFF30', '#FFFFFF00'], 0.6, 1) + `<clipPath id="in"><path d="${SHIELD}"/></clipPath>`,
    `<g clip-path="url(#in)"><path d="M60 40H460V120Q300 96 60 214z" fill="url(#gl)"/></g>
<g filter="url(#rr)"><path d="${SHIELD}" fill="none" stroke="url(#mg)" stroke-width="30" stroke-linejoin="round"/></g>
<path d="${SHIELD}" fill="none" stroke="${FACE[k][5]}" stroke-opacity=".55" stroke-width="7" stroke-dasharray="1.6 4" transform="${scaled(1.03)}"/>
<path d="${SHIELD}" fill="none" stroke="#000" stroke-opacity=".45" stroke-width="2.5" transform="${scaled(0.93)}"/>
<path d="${SHIELD}" fill="none" stroke="#FFFFFF" stroke-opacity=".45" stroke-width="1.5" transform="translate(1 1.5) ${scaled(0.93)}"/>`);
}
// the app's own drawn pins (owner, Nov 4: the shields looked terrible, Recruiter's medal "looks great"): round medals
// built exactly as Recruiter's, layer for layer (lib/awards layersOf): zn-<g>-field (its field, in the pin's own
// enamel), zn-<g>-net (the symbol as a constellation: a few glowing studs joined by thin light, abstract, never a
// drawing), Recruiter's own light (rc-core-<m>) and a plain rim of its metal (zn-rim-<m>: rim() without laurels).
for (const k of 'gs') files[`zn-rim-${k}`] = rim(k);
function constellation(k, nodes, ties, web, orbits) {
  const m = METAL[k];
  return svg(`<linearGradient id="tie" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${m.lit}"/><stop offset="1" stop-color="${m.glow}"/></linearGradient>
<radialGradient id="halo" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="${m.glow}" stop-opacity=".75"/><stop offset="1" stop-color="${m.glow}" stop-opacity="0"/></radialGradient>${metals(k)}${RELIEFS}`,
  `<g fill="none" stroke="${m.lit}" stroke-width="1.6" stroke-dasharray="2 7" stroke-linecap="round" opacity=".45">${orbits}</g>
<path d="${web}" stroke="${m.lit}" stroke-width="3" stroke-linecap="round" opacity=".35" fill="none"/>
<path d="${ties}" stroke="url(#tie)" stroke-width="9" stroke-linecap="round" stroke-linejoin="round" opacity=".18" fill="none"/>
<path d="${ties}" stroke="${m.lit}" stroke-width="3.2" stroke-linecap="round" stroke-linejoin="round" opacity=".85" fill="none"/>
${nodes.map(([x, y, s]) => `<circle cx="${x}" cy="${y}" r="${f(s * 2)}" fill="url(#halo)"/>`).join('')}
${part('r2', 'ms', nodes.map(([x, y, s]) => `<circle cx="${x}" cy="${y}" r="${s}"/>`).join(''))}`);
}
const arc = (r, a0, a1) => { const [x0, y0] = pt(r, a0), [x1, y1] = pt(r, a1); return `M${x0} ${y0}A${r} ${r} 0 0 ${a1 > a0 ? 1 : 0} ${x1} ${y1}`; };
// Variant B (lib/awards PIN_SHAPE 'shield', owner, Nov 4: "the shields at the medals' level, or better"): the same pin
// in the shield, built as the coin is: the coin's rim along the shield's outline (a milled outer band, the broad band
// rolled by the same relief light, a raised lip, the field's edge sunk under it, the glaze's gloss), the same field and
// constellation inside (zn-<g>-sfield: the field clipped to the shield; zn-<g>-snet: the constellation a little smaller
// to clear the narrower sides), Recruiter's light in the middle. Each band is the outline scaled round the shield's
// middle, in the coin's proportions (knurl 1-.935, band .94-.86, lip .865-.83: the coin's 255/238/240/220/221/212).
const SH_PTS = [['M', 100, 78], ['Q', 256, 44, 412, 78], ['Q', 440, 84, 440, 112], ['L', 440, 268], ['Q', 440, 398, 256, 480], ['Q', 72, 398, 72, 268], ['L', 72, 112], ['Q', 72, 84, 100, 78]];
const SHC = [256, 262];
const SH_FILL = 1.12; // the shield fills the box as the coin does (its outline in lib/awards SHIELD keeps the shield pins of events)
const shieldD = (k) => { const s = k * SH_FILL; return SH_PTS.map(([c, ...v]) => c + v.map((n, i) => f(SHC[i % 2] + (n - SHC[i % 2]) * s)).join(' ')).join('') + 'Z'; };
const sring = (s0, s1) => `<path fill-rule="evenodd" d="${shieldD(s0)}${shieldD(s1)}"/>`;
function shieldRim(k) {
  const m = METAL[k];
  return svg(`${metals(k)}${relief('rr', 10, 11, 0.5)}${relief('re', 3, 6, 0)}${RELIEFS}
<linearGradient id="gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".22"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>
<clipPath id="fd"><path d="${shieldD(0.83)}"/></clipPath>
<filter id="sb" x="-10%" y="-10%" width="120%" height="120%"><feGaussianBlur stdDeviation="7"/></filter>`,
  `<g clip-path="url(#fd)"><path d="${shieldD(0.83)}" fill="none" stroke="#000" stroke-opacity=".55" stroke-width="22" filter="url(#sb)"/>
<path d="M90 ${f(230)}Q150 96 256 92Q362 96 420 150Q300 120 90 230z" fill="url(#gloss)"/></g>
${part('re', 'mh', sring(1, 0.935))}
<path d="${shieldD(0.968)}" fill="none" stroke="${m.rim[5]}" stroke-width="16" stroke-dasharray="1.6 3.4" opacity=".5"/>
${part('rr', 'mg', sring(0.94, 0.86))}
${part('r3', 'mh', sring(0.865, 0.83))}
<path d="${shieldD(0.83)}" fill="none" stroke="#000" stroke-opacity=".45" stroke-width="2.5"/>`);
}
for (const k of 'gs') files[`zn-srim-${k}`] = shieldRim(k);
// a file's drawing clipped to the shield (the field overscans under the rim, as the coin's does)
const clipShield = (s, scale) => s.replace('<defs>', `<defs><clipPath id="shc"><path d="${shieldD(scale)}"/></clipPath>`).replace('</defs>', '</defs><g clip-path="url(#shc)">').replace(/<\/svg>\n$/, '</g></svg>\n');
// the constellation smaller round the shield's light, to clear its narrower sides and point
const shrink = (s, k) => s.replace('</defs>', `</defs><g transform="translate(${C} ${C}) scale(${k}) translate(${-C} ${-C})">`).replace(/<\/svg>\n$/, '</g></svg>\n');
const zpin = (name, k, colors, nodes, ties, web, orbits) => {
  files[`zn-${name}-field`] = field(colors, name.charCodeAt(0) * 37 + name.length, [C, C], 0.38, true);
  files[`zn-${name}-net`] = constellation(k, nodes, ties, web, orbits);
  files[`zn-${name}-sfield`] = clipShield(files[`zn-${name}-field`], 0.9);
  files[`zn-${name}-snet`] = shrink(files[`zn-${name}-net`], 0.92);
};
// Anthem: a melody rising through the light, its notes on a faint staff
(() => {
  const n = [[110, 304, 16], [172, 222, 16], [340, 214, 16], [394, 140, 14]];
  const staff = [196, 226, 256, 286, 316].map((y) => { const w = Math.sqrt(176 * 176 - (y - C) ** 2); return `<path d="M${f(C - w)} ${y}H${f(C + w)}"/>`; }).join('');
  zpin('anthem', 'g', ['#5A3AD0', '#2A168A', '#0C0638'], n,
    `M110 304L172 222L${C} ${C}L340 214L394 140`, `M110 304L340 214M172 222L394 140`, staff);
})();
// Made the creator laugh: a smile of five stars under two, the eyes tied to the light
(() => {
  const smile = [125, 152.5, 180, 207.5, 235].map((a) => [...pt(140, a), 15]), eyes = [-34, 34].map((a) => [...pt(124, a), 16]);
  zpin('laugh', 'g', ['#1AA0A8', '#0A5058', '#021E24'], [...smile, ...eyes],
    `${arc(140, 125, 235)}${eyes.map(([x, y]) => `M${C} ${C}L${x} ${y}`).join('')}`, `M${eyes[0][0]} ${eyes[0][1]}L${eyes[1][0]} ${eyes[1][1]}`,
    `<circle cx="${C}" cy="${C}" r="140"/>`);
})();
// Found the creator: a hello going out both ways, waves of light from the middle
(() => {
  const near = [90, 270].map((a) => [...pt(108, a), 15]), far = [62, 118, 242, 298].map((a) => [...pt(166, a), 14]);
  zpin('wave', 'g', ['#C8384A', '#6A1028', '#24040E'], [...near, ...far],
    `${near.map(([x, y]) => `M${C} ${C}L${x} ${y}`).join('')}${arc(108, 62, 118)}${arc(108, 242, 298)}${arc(166, 62, 118)}${arc(166, 242, 298)}`,
    `M${near[0][0]} ${near[0][1]}L${far[0][0]} ${far[0][1]}M${near[0][0]} ${near[0][1]}L${far[1][0]} ${far[1][1]}M${near[1][0]} ${near[1][1]}L${far[2][0]} ${far[2][1]}M${near[1][0]} ${near[1][1]}L${far[3][0]} ${far[3][1]}`,
    `<circle cx="${C}" cy="${C}" r="108"/><circle cx="${C}" cy="${C}" r="166"/>`);
})();

// the files this tool owns are rewritten whole: drop the ones a rename left behind
for (const n of readdirSync(out)) if (/\.svg$/.test(n) && !n.startsWith("vb-") && !(n.slice(0, -4) in files)) unlinkSync(new URL(n, out));
for (const [n, s] of Object.entries(files)) writeFileSync(new URL(`${n}.svg`, out), s);
console.log(Object.keys(files).length, 'files');
