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
//     legend IX); gold grows laurels, legend a full wreath, an iridescent bezel and a crown star.
//   The others (rg, st, fi, so, tm, se, bg, cr): <p>-field (its enamel), <p>-art-<metal> and <p>-near-<metal> (the
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
FACE.l = FACE.g;
const METAL = {
  b: { rim: FACE.b, lit: '#FFD9B3', glow: '#FF9D57' },
  s: { rim: FACE.s, lit: '#F2F6FF', glow: '#9CC4FF' },
  g: { rim: FACE.g, lit: '#FFF0B8', glow: '#FFC94A' },
  l: { rim: FACE.g, iri: ['#FF6BD6', '#7C4DFF', '#35D0FF', '#2FD3A0', '#FFD23F', '#FF6BD6'], lit: '#FFFFFF', glow: '#E59BFF' },
};
// the Recruiter's enamel per metal (its constellation glows on it)
const RC_FIELD = { b: ['#1F4E6E', '#0C2438', '#04101C'], s: ['#2C55D6', '#142A85', '#070F3C'], g: ['#3A2A8C', '#1A1050', '#08051F'], l: ['#7A3BE0', '#3A1290', '#12043A'] };
const metalOf = (l) => (l === 9 ? 'l' : l >= 7 ? 'g' : l >= 4 ? 's' : 'b');

// Struck relief: the part's own outline blurred is its height; a distant light from the upper left shades it (diffuse,
// multiplied into the metal) and glints on its slopes (specular, added); then its shadow falls down and right.
// blur: how round the bevel; depth: how high; sh: the shadow's reach (0: none)
const relief = (id, blur, depth, sh = 1) => `<filter id="${id}" x="-25%" y="-25%" width="150%" height="160%" color-interpolation-filters="sRGB">
<feGaussianBlur in="SourceAlpha" stdDeviation="${blur}" result="h"/>
<feDiffuseLighting in="h" surfaceScale="${depth}" diffuseConstant="1" lighting-color="#FFFFFF" result="d"><feDistantLight azimuth="235" elevation="52"/></feDiffuseLighting>
<feComposite in="SourceGraphic" in2="d" operator="arithmetic" k1="1.3" result="l"/>
<feSpecularLighting in="h" surfaceScale="${depth}" specularConstant="1.15" specularExponent="22" lighting-color="#FFFFFF" result="s"><feDistantLight azimuth="235" elevation="38"/></feSpecularLighting>
<feComposite in="s" in2="SourceAlpha" operator="in" result="s2"/>
<feComposite in="l" in2="s2" operator="arithmetic" k2="1" k3=".85" result="m"/>
<feComposite in="m" in2="SourceAlpha" operator="in" result="o"/>${sh ? `
<feGaussianBlur in="SourceAlpha" stdDeviation="${f(sh * 5)}"/><feOffset dx="${f(sh * 3)}" dy="${f(sh * 7)}"/><feComponentTransfer><feFuncA type="linear" slope=".62"/></feComponentTransfer>
<feMerge><feMergeNode/><feMergeNode in="o"/></feMerge>` : ''}</filter>`;
// three heights: a main part, a raised detail, a fine one
const RELIEFS = relief('r1', 6, 7) + relief('r2', 3.5, 5, 0.6) + relief('r3', 1.8, 3, 0.35);
// the metal's fills: across the part, the other way, and a sphere's
const metals = (k) => lin('mg', FACE[k], 1, 1) + lin('mh', [FACE[k][3], FACE[k][1], FACE[k][2], FACE[k][0], FACE[k][4]], 0, 1, 1, 0) + rad('ms', [FACE[k][0], FACE[k][1], FACE[k][2], FACE[k][5]], 0.36, 0.3, 0.8);
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
${m.iri ? lin('iri', m.iri, 1, 1) : ''}
<radialGradient id="sink" cx=".5" cy=".5" r=".5"><stop offset=".88" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".55"/></radialGradient>`,
  `<circle cx="${C}" cy="${C}" r="${FIELD + 1}" fill="url(#sink)"/>
<path d="M${C - 200} ${C - 30}A${FIELD} ${FIELD} 0 0 1 ${C + 170} ${C - 120}Q${C} ${C - 120} ${C - 200} ${C - 30}z" fill="url(#gloss)"/>
${part('re', 'mh', ring(238, 255))}
<path d="${knurl}" stroke="${m.rim[5]}" stroke-width="1.6" opacity=".5"/>
${part('rr', 'mg', ring(220, 240))}
${m.iri ? `<circle cx="${C}" cy="${C}" r="226" fill="none" stroke="url(#iri)" stroke-width="13" opacity=".9"/>` : ''}
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


// ---- the other medals (awards plan, Nov 3): one subject each, struck in the level's metal on its own enamel, under
// the shared rim of that metal (rc-rim-*): <p>-field (far), <p>-art-<m> (the subject), <p>-near-<m> (its nearest part,
// floats most). Every subject keeps inside r 165 above the laurels (gold and legend rims grow them low on both sides).
// The enamels laid into the metal are the subject's own colour (the ticket's red star, the flame's heart, the room's
// light...), the same at every level: the metal tells the level, the enamel and the shape tell the medal.
const ENAMELS = lin('er', ['#FF7A6A', '#D6283A', '#8A0E22'], 0.3, 1) + lin('eo', ['#FFE08A', '#FF9A2A', '#E0441C', '#9E1420'], 0, 1)
  + lin('ew', ['#FFFFF4', '#FFF0B8', '#FFC864'], 0, 1) + lin('ek', ['#3A3448', '#141019'], 0, 1) + lin('ey', ['#FFF6B0', '#FFD23A', '#F09A1A'], 0, 1)
  + lin('ec', ['#FF9C80', '#E2573A', '#A8341E'], 0, 1) + lin('eb', ['#B8E6FF', '#4AA8F0', '#1A5EB8'], 0, 1) + lin('esn', ['#FFFFFF', '#E4ECFA', '#9FB4E2', '#6E86C4'], 0.4, 1);
const pic = (p, fieldColors, light, art, near, rays = 0.3) => {
  files[`${p}-field`] = field(fieldColors, p.charCodeAt(0) * 31 + p.charCodeAt(1), light, rays);
  for (const k of 'bsgl') {
    const head = metals(k) + RELIEFS + ENAMELS + GLINT;
    files[`${p}-art-${k}`] = svg(head, art(k));
    files[`${p}-near-${k}`] = svg(head, near(k));
  }
};

// Regular: an admission ticket, its notches and perforation, the star punched through it raised in red enamel
const TICKET = 'M136 180H376Q394 180 394 198V234A22 22 0 0 0 394 278V314Q394 332 376 332H136Q118 332 118 314V278A22 22 0 0 0 118 234V198Q118 180 136 180z';
pic('rg', ['#8E1F3E', '#4A0A20', '#1C030C'], [C, 250],
  (k) => `<g transform="rotate(-14 256 256)">${part('r1', 'mg', `<path d="${TICKET}"/>`)}
${cut('M150 204Q150 196 158 196H366Q378 196 378 204V308Q378 316 370 316H158Q150 316 150 308z', 3, k)}
<g fill="${FACE[k][5]}" opacity=".8">${[0, 1, 2, 3, 4, 5, 6, 7, 8].map((i) => `<circle cx="318" cy="${200 + i * 14}" r="3.2"/>`).join('')}</g>
${cut('M340 226h26M340 246h26M340 266h18M340 286h26', 5, k)}</g>`,
  (k) => `<g transform="rotate(-14 256 256)">${part('r2', 'mg', `<path d="${star5(226, 258, 54, 25)}"/>`)}
${enamel(star5(226, 258, 36, 16), 'er')}</g>${glint(368, 176, 22)}`);

// Streak: a flame burning on, tongue in tongue: the metal flame, its heart in fire enamel, the white-hot core raised
pic('st', ['#4A2296', '#200C52', '#0A0420'], [C, 340],
  (k) => `${part('r1', 'mg', '<path d="M262 92C276 150 352 180 360 268C368 350 316 404 256 404C190 404 146 356 152 288C156 240 184 214 196 172C206 206 214 222 232 234C230 184 236 136 262 92z"/>')}
${enamel('M266 176C276 222 326 246 326 306C326 356 296 384 256 384C214 384 186 354 188 314C190 282 208 262 218 236C226 260 236 270 248 276C246 240 250 206 266 176z', 'eo')}`,
  (k) => `${part('r2', 'ms', '<path d="M260 266C268 294 296 310 294 342C292 368 276 382 256 382C234 382 220 366 220 344C220 318 240 302 248 282C252 292 256 296 260 298z"/>')}
${part('r3', 'mg', [[358, 168, 9], [388, 214, 6], [140, 196, 7], [168, 146, 5]].map(([x, y, r]) => `<path d="M${x} ${y - r * 1.6}L${x + r} ${y}L${x} ${y + r * 1.6}L${x - r} ${y}z"/>`).join(''))}`);

// First in: an arched doorway, the room's light in it, the door swung open, a star over it
pic('fi', ['#2346A8', '#0F2260', '#050B26'], [C, 236],
  (k) => `<path d="M150 404L192 360H320L362 404z" fill="#FFE7A6" opacity=".22"/>
${enamel('M192 356V202Q192 144 256 144Q320 144 320 202V356z', 'ew')}
${part('r1', 'mg', '<path fill-rule="evenodd" d="M168 356V196Q168 120 256 120Q344 120 344 196V356zM192 356V202Q192 144 256 144Q320 144 320 202V356z"/>')}
${part('r2', 'mh', '<rect x="148" y="352" width="216" height="20" rx="5"/>')}
${part('r2', 'mh', '<path d="M192 352V202Q192 166 206 154L144 182Q134 188 134 202V376Q134 388 146 384z"/>')}
${cut('M150 214L178 200V262L150 274zM150 300L178 290V344L150 356z', 3, k)}
${part('r3', 'ms', '<circle cx="176" cy="282" r="7"/>')}`,
  (k) => `${part('r2', 'mg', `<path d="${star5(352, 124, 36, 16)}"/>`)}${glint(352, 124, 30)}${glint(398, 196, 13)}`, 0.42);

// Life of the party: a mirror ball on its chain: each facet its own small plate of metal, a few flashing white
const ball = (k) => {
  const cx = 256, cy = 244, R = 104, rnd = rng(77);
  let tiles = '', lights = '';
  for (let lat = -84; lat < 84; lat += 14) {
    const y0 = cy + R * Math.sin((lat * Math.PI) / 180), y1 = cy + R * Math.sin(((lat + 14) * Math.PI) / 180);
    const w = R * Math.cos(((lat + 7) * Math.PI) / 180), n = Math.max(4, Math.round((2 * w) / 20));
    for (let i = 0; i < n; i++) {
      const x0 = cx - w + (2 * w * i) / n, ww = (2 * w) / n, r = rnd();
      tiles += `<rect x="${f(x0 + 1.4)}" y="${f(y0 + 1.4)}" width="${f(ww - 2.8)}" height="${f(y1 - y0 - 2.8)}" rx="1.5"/>`;
      if (r < 0.07) lights += `<rect x="${f(x0 + 1.4)}" y="${f(y0 + 1.4)}" width="${f(ww - 2.8)}" height="${f(y1 - y0 - 2.8)}" rx="1.5" fill="#FFFFFF" opacity=".55"/>`;
    }
  }
  return `${part('r3', 'mh', '<rect x="252" y="54" width="8" height="86" rx="4"/>')}${part('r2', 'mg', '<rect x="238" y="126" width="36" height="20" rx="5"/>')}
${part('r1', 'ms', `<circle cx="${cx}" cy="${cy}" r="${R}"/>`)}
<g fill="${FACE[k][5]}" opacity=".55"><circle cx="${cx}" cy="${cy}" r="${R - 1}"/></g>
<radialGradient id="mb" gradientUnits="userSpaceOnUse" cx="${cx - 38}" cy="${cy - 44}" r="${R * 1.6}">${stops([FACE[k][0], FACE[k][3], FACE[k][1], FACE[k][2], FACE[k][5]])}</radialGradient>
<clipPath id="bc"><circle cx="${cx}" cy="${cy}" r="${R - 2}"/></clipPath><g clip-path="url(#bc)">${part('r3', 'mb', tiles)}${lights}</g>`;
};
pic('so', ['#8A1F78', '#45093E', '#1A0318'], [C, 236], ball,
  (k) => `${glint(212, 196, 34)}${glint(300, 290, 16)}${part('r3', 'mg', `<path d="${star5(372, 316, 18, 7)}"/><path d="${star5(138, 330, 14, 6)}"/><path d="${star5(368, 150, 11, 5)}"/>`)}`, 0.5);

// Teambuilding thunder: a storm cloud, its rain, the bolt out of it
const CLOUD = 'M150 300Q114 300 114 264Q114 230 150 226Q152 186 196 182Q216 136 266 136Q322 136 336 188Q394 188 398 244Q400 300 344 300z';
pic('tm', ['#1F5C8A', '#0C2C4C', '#04121F'], [C, 220],
  (k) => `${part('r3', 'mh', '<path d="M178 326l-14 34M218 334l-14 34M298 334l-14 34M338 326l-14 34" fill="none" stroke="url(#mh)" stroke-width="9" stroke-linecap="round"/>')}
${part('r1', 'mg', `<path d="${CLOUD}"/>`)}
${cut('M196 182Q216 136 266 136Q306 136 324 170M150 226Q170 222 186 236M336 188Q318 192 308 210', 4, k)}`,
  (k) => `${part('r1', 'mh', '<path d="M272 258L220 354H260L236 440L322 322H278L306 258z"/>')}
${enamel('M276 270L236 342H272L258 396L304 334H264L286 270z', 'ey')}`);

// Season: a desk calendar, a term's days ticked off in red enamel, an autumn leaf against it
pic('se', ['#9A4A16', '#4E1F06', '#1E0A02'], [C, 240],
  (k) => {
    let cells = '', ticks = '';
    const on = [0, 1, 2, 4, 5, 7, 8, 10, 11, 12, 14];
    for (let r = 0; r < 4; r++) for (let c = 0; c < 5; c++) {
      const i = r * 5 + c, x = 172 + c * 36, y = 236 + r * 34;
      if (on.includes(i)) { cells += `<path d="M${x + 12} ${y}a12 12 0 1 0 0.01 0z"/>`; ticks += `<path d="M${x + 6} ${y + 12}l5 5l9 -10"/>`; }
      else cells += '';
    }
    const grid = Array.from({ length: 20 }, (_, i) => (on.includes(i) ? '' : `M${174 + (i % 5) * 36} ${238 + Math.floor(i / 5) * 34}h20v20h-20z`)).join('');
    return `${part('r1', 'mg', '<rect x="150" y="146" width="212" height="232" rx="24"/>')}
${enamel('M174 160H338Q348 160 348 170V208H164V170Q164 160 174 160z', 'er')}
${cut(grid, 2.5, k)}
<g fill="url(#er)">${cells}</g><g fill="none" stroke="#FFFFFF" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round">${ticks}</g>
${part('r2', 'mh', '<rect x="196" y="122" width="16" height="48" rx="8"/><rect x="300" y="122" width="16" height="48" rx="8"/>')}`;
  },
  (k) => `<g transform="rotate(-28 372 340)">${part('r2', 'mg', '<path d="M372 288Q416 318 372 396Q328 318 372 288z"/>')}${cut('M372 300V386M372 330l14 -10M372 354l-14 -10', 3, k)}</g>`);

// Bug hunter: a ladybird on its leaf: the leaf struck in metal, the bird's wing cases red enamel, its spots black
pic('bg', ['#1F7A44', '#0B3D22', '#03170C'], [C, 230],
  (k) => `${part('r1', 'mg', '<path d="M120 380Q130 200 300 130Q400 100 404 116Q414 240 300 330Q220 392 120 380z"/>')}
${cut('M126 374Q250 260 396 124', 5, k)}
${cut([[180, 316, 150, 270], [230, 270, 196, 214], [280, 224, 262, 168], [210, 292, 252, 330], [262, 246, 312, 280], [312, 200, 352, 226]].map(([a, b, c, d]) => `M${a} ${b}Q${(a + c) / 2 + 8} ${(b + d) / 2} ${c} ${d}`).join(''), 3, k)}`,
  (k) => `<g transform="rotate(-24 262 262)">
${part('r3', 'mh', '<path d="M206 236l-30 -14M200 270l-34 2M208 304l-28 18M318 236l30 -14M324 270l34 2M316 304l28 18M246 168Q236 140 214 134M278 168Q288 140 310 134" fill="none" stroke="url(#mh)" stroke-width="8" stroke-linecap="round"/><circle cx="213" cy="133" r="9"/><circle cx="311" cy="133" r="9"/>')}
${part('r2', 'ms', '<ellipse cx="262" cy="186" rx="46" ry="32"/>')}
${part('r1', 'mg', '<ellipse cx="262" cy="272" rx="84" ry="96"/>')}
${enamel('M256 186Q190 192 186 268Q186 340 256 362z', 'er')}${enamel('M268 186Q334 192 338 268Q338 340 268 362z', 'er')}
<g fill="url(#ek)"><circle cx="226" cy="236" r="15"/><circle cx="298" cy="236" r="15"/><circle cx="214" cy="292" r="13"/><circle cx="310" cy="292" r="13"/><circle cx="238" cy="334" r="10"/><circle cx="286" cy="334" r="10"/></g>
<ellipse cx="222" cy="220" rx="20" ry="9" fill="#FFFFFF" opacity=".5" transform="rotate(-36 222 220)"/></g>`);

// Couch critic: a deep sofa in coral upholstery set in its metal frame, a speech bubble over it with its three dots
pic('cr', ['#167A80', '#0A3E44', '#021A1D'], [C, 200],
  (k) => `${part('r3', 'mh', '<rect x="146" y="368" width="16" height="26" rx="4"/><rect x="350" y="368" width="16" height="26" rx="4"/>')}
${part('r1', 'mg', '<rect x="146" y="222" width="220" height="96" rx="30"/>')}
${enamel('M176 238H336Q350 238 350 252V300H162V252Q162 238 176 238z', 'ec')}
${part('r2', 'mh', '<rect x="128" y="344" width="256" height="30" rx="10"/>')}
${part('r2', 'mg', '<rect x="164" y="290" width="184" height="62" rx="18"/>')}
${enamel('M182 302H330Q338 302 338 310V336Q338 342 330 342H182Q174 342 174 336V310Q174 302 182 302z', 'ec')}${cut('M256 304V340', 3, k)}
${part('r2', 'mg', '<rect x="112" y="258" width="62" height="114" rx="28"/><rect x="338" y="258" width="62" height="114" rx="28"/>')}`,
  (k) => `${part('r1', 'mh', '<path d="M196 98H316Q346 98 346 128V170Q346 200 316 200H286L262 228L254 200H196Q166 200 166 170V128Q166 98 196 98z"/>')}
<g fill="url(#ek)"><circle cx="218" cy="149" r="12"/><circle cx="256" cy="149" r="12"/><circle cx="294" cy="149" r="12"/></g>`);

// a medal's ribbon at 96 px and up (ui/Medal): two tails behind the disc, cut in a V: dark navy grosgrain, the level's
// metal woven in as two stripes (legend: the iridescent one), shaded where it folds behind the disc
for (const k of 'bsgl') {
  const m = METAL[k], tail = (side) => `<g transform="translate(256 360) rotate(${side * 24})"><path d="M-62 0H62V240L0 200L-62 240z" fill="url(#rb)"/>
<path d="M-40 0H-28V226L-40 233zM28 0H40V233L28 226z" fill="url(#st)"/>
<path d="M-8 0H8V205L0 200L-8 205z" fill="${k === 'l' ? 'url(#iri)' : 'url(#st)'}" opacity="${k === 'l' ? 0.95 : 0.6}"/>
<path d="M-62 0H62V40H-62z" fill="url(#fold)"/></g>`;
  files[`ribbon-${k}`] = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 640"><defs>${lin('rb', ['#0C1438', '#22306E', '#2E3E86', '#1A2558', '#0A1030'], 1, 0)}${lin('st', [m.rim[0], m.rim[1], m.rim[2]], 1, 0)}${lin('fold', ['#000000AA', '#00000000'], 0, 1)}${m.iri ? lin('iri', m.iri, 0, 1) : ''}</defs>${tail(-1)}${tail(1)}</svg>\n`;
}

// ---- pins: the one-time awards are enamel shields (ui/Pin): the enamel (Pin fills SHIELD with the colour), its
// guilloche (zn-enamel, over the colour), one glyph struck in the frame's metal (zn-<glyph>-<metal>, floats with the
// tilt), the bevelled metal frame on top (zn-frame-<metal>, still). SHIELD is lib/awards.ts SHIELD: the two stay equal.
const SHIELD = 'M100 78Q256 44 412 78Q440 84 440 112V268Q440 398 256 480Q72 398 72 268V112Q72 84 100 78Z';
files['zn-enamel'] = (() => {
  let fine = '', guil = '';
  for (let i = 0; i < 180; i++) { const a = (i * 2 * Math.PI) / 180; fine += `M256 250L${f(256 + 300 * Math.sin(a))} ${f(250 - 300 * Math.cos(a))}`; }
  for (let i = 0; i < 24; i++) guil += `<ellipse cx="256" cy="250" rx="190" ry="72" transform="rotate(${f(i * 7.5)} 256 250)"/>`;
  return svg(`<clipPath id="in"><path d="${SHIELD}"/></clipPath>${rad('lt', ['#FFFFFF33', '#FFFFFF00'], 0.42, 0.32, 0.6)}<radialGradient id="vig" cx=".5" cy=".46" r=".6"><stop offset=".55" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".5"/></radialGradient>`,
    `<g clip-path="url(#in)"><path d="${fine}" stroke="#FFFFFF" stroke-width="1" opacity=".07"/><g fill="none" stroke="#FFFFFF" stroke-width="1" opacity=".09">${guil}</g>
<rect width="512" height="512" fill="url(#lt)"/><rect width="512" height="512" fill="url(#vig)"/></g>`);
})();
for (const k of 'gsr') {
  files[`zn-frame-${k}`] = svg(metals(k) + relief('rr', 6, 8, 0.4) + lin('gl', ['#FFFFFF40', '#FFFFFF00'], 0.6, 1) + `<clipPath id="in"><path d="${SHIELD}"/></clipPath>`,
    `<g clip-path="url(#in)"><path d="M60 40H460V130Q300 104 60 230z" fill="url(#gl)"/></g>
<g filter="url(#rr)"><path d="${SHIELD}" fill="none" stroke="url(#mg)" stroke-width="30" stroke-linejoin="round"/></g>
<path d="${SHIELD}" fill="none" stroke="#000" stroke-opacity=".4" stroke-width="2.5" transform="translate(256 262) scale(.928) translate(-256 -262)"/>`);
}
const glyph = (name, body) => { for (const k of 'gsr') files[`zn-${name}-${k}`] = svg(metals(k) + RELIEFS + ENAMELS + GLINT, body(k)); };
// First 500: the number struck big
glyph('500', (k) => {
  const five = (x, y) => `M${x + 58} ${y}H${x + 12}L${x + 8} ${y + 52}C${x + 30} ${y + 40} ${x + 70} ${y + 46} ${x + 70} ${y + 84}C${x + 70} ${y + 122} ${x + 22} ${y + 126} ${x + 4} ${y + 104}`;
  const d = `${five(130, 176)}M248 236m-30 0a30 58 0 1 0 60 0a30 58 0 1 0 -60 0M338 236m-30 0a30 58 0 1 0 60 0a30 58 0 1 0 -60 0`;
  return `${part('r1', 'mg', `<path d="${d}" fill="none" stroke="url(#mg)" stroke-width="32" stroke-linecap="round" stroke-linejoin="round"/>`)}
${part('r3', 'mh', `<path d="${star5(256, 350, 18, 8)}"/><path d="${star5(204, 354, 9, 4)}"/><path d="${star5(308, 354, 9, 4)}"/>`)}`;
});
// the 2026 initiation: the Alatau's snow over the dome it was held under
glyph('init26', (k) => `${part('r2', 'esn', '<path d="M104 252L166 174L202 212L262 128L324 204L354 176L408 252z"/>')}
<path d="M166 174L186 200L172 196L158 212zM262 128L292 172L270 166L254 188L240 162zM354 176L370 198L352 196z" fill="#6E86C4" opacity=".45" transform="translate(10 4)"/>
${part('r1', 'mg', '<path d="M146 300Q146 222 256 212Q366 222 366 300z"/>')}
${cut('M164 272Q256 248 348 272M188 240Q256 228 324 240', 4, k)}
${part('r1', 'mh', '<rect x="134" y="296" width="244" height="58" rx="6"/>')}
<g fill="${FACE[k][5]}" opacity=".7">${[0, 1, 2, 3, 4, 5, 6].map((i) => `<rect x="${152 + i * 31}" y="308" width="15" height="36" rx="3"/>`).join('')}</g>
${part('r2', 'mg', '<rect x="118" y="350" width="276" height="18" rx="5"/>')}`);
// Anthem: KBTU's colonnade, two notes over it
glyph('anthem', (k) => `${part('r2', 'mg', '<path d="M150 214L256 160L362 214z"/>')}${part('r2', 'mh', '<rect x="140" y="212" width="232" height="20" rx="4"/>')}
${part('r1', 'mg', [0, 1, 2, 3].map((i) => `<rect x="${164 + i * 52}" y="236" width="30" height="100" rx="3"/>`).join(''))}
${cut([0, 1, 2, 3].map((i) => `M${174 + i * 52} 246V326M${184 + i * 52} 246V326`).join(''), 2, k)}
${part('r2', 'mh', '<rect x="132" y="338" width="248" height="16" rx="4"/><rect x="116" y="356" width="280" height="16" rx="4"/>')}
${part('r2', 'ms', '<ellipse cx="330" cy="140" rx="16" ry="12" transform="rotate(-22 330 140)"/><ellipse cx="380" cy="126" rx="16" ry="12" transform="rotate(-22 380 126)"/><path d="M338 138V82L396 66V124H388V84L346 96V138z"/>')}`);
// Made the creator laugh: a face laughing to tears
glyph('laugh', (k) => `${part('r1', 'ms', '<circle cx="256" cy="250" r="106"/>')}
${cut('M196 226Q214 204 232 226M280 226Q298 204 316 226', 9, k)}
${enamel('M186 262Q256 274 326 262Q320 332 256 336Q192 332 186 262z', 'ek')}
${part('r3', 'mh', '<path d="M196 266Q256 276 316 266L312 282Q256 290 200 282z"/>')}
${part('r3', 'mg', '<path d="M168 230Q128 262 150 292Q174 302 178 268z"/><path d="M344 230Q384 262 362 292Q338 302 334 268z"/>')}
${enamel('M164 244Q138 266 152 286Q168 292 170 268z', 'eb')}${enamel('M348 244Q374 266 360 286Q344 292 342 268z', 'eb')}`);
// Found the creator: a hand waving hello
glyph('wave', (k) => `<g transform="rotate(-16 256 270)">${part('r1', 'mg', '<rect x="178" y="236" width="150" height="140" rx="56"/>')}
${part('r2', 'mh', [[184, 140, 150], [222, 112, 170], [260, 118, 166], [296, 146, 140]].map(([x, y, h]) => `<rect x="${x}" y="${y}" width="34" height="${h}" rx="17"/>`).join(''))}
${part('r2', 'mg', '<rect x="300" y="250" width="34" height="104" rx="17" transform="rotate(42 318 300)"/>')}</g>
${part('r3', 'mh', '<path d="M120 170Q108 210 122 248M394 170Q406 210 392 248M146 150Q130 200 146 246M368 150Q384 200 368 246" fill="none" stroke="url(#mh)" stroke-width="8" stroke-linecap="round"/>')}`);

// the files this tool owns are rewritten whole: drop the ones a rename left behind
for (const n of readdirSync(out)) if (/\.svg$/.test(n) && !(n.slice(0, -4) in files)) unlinkSync(new URL(n, out));
for (const [n, s] of Object.entries(files)) writeFileSync(new URL(`${n}.svg`, out), s);
console.log(Object.keys(files).length, 'files');
