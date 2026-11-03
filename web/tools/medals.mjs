// The drawn achievement medals, in layers (public/medals/*.svg): vector, so crisp at any size and pixel ratio, and
// layered, so the field, the art and the near art float with the phone's tilt under a still rim (ui/Medal.svelte,
// lib/awards.ts layersOf). Every layer is the same 512 box centred on the medal; the field overscans under the rim.
//   Recruiter (rc-*): a constellation. I am the star in the middle; each level one more friend lights up on the
//     orbit, tied to me and to each other. The rim is the level's metal (bronze I-III, silver IV-VI, gold VII-VIII,
//     legend IX); gold grows laurels, legend a full wreath, an iridescent bezel and a crown star.
//   The others (rg, st, fi, so, tm, se, bg, cr): one picture each on its own enamel field under the rc rims; the
//     ribbons; the pins (zn-*): the shield frames and their glyphs (the anthem keeps its colonnade there).
// usage: node tools/medals.mjs   (from web/)
import { writeFileSync, mkdirSync } from 'node:fs';
const out = new URL('../public/medals/', import.meta.url);
mkdirSync(out, { recursive: true });
const C = 256, FIELD = 212, f = (n) => +n.toFixed(2);
const pt = (r, deg) => [f(C + r * Math.sin((deg * Math.PI) / 180)), f(C - r * Math.cos((deg * Math.PI) / 180))];
const svg = (defs, body) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs>${defs}</defs>${body}</svg>\n`;
// a stop's colour, #RRGGBBAA as its colour and opacity (stop-color takes no alpha in older WebKit)
const stops = (cs) => cs.map((c, i) => `<stop offset="${f(i / (cs.length - 1))}" stop-color="${c.slice(0, 7)}"${c.length === 9 ? ` stop-opacity="${f(parseInt(c.slice(7), 16) / 255)}"` : ''}/>`).join('');

const METAL = {
  b: { rim: ['#FFE0C2', '#E9A36A', '#9A5524', '#5E2C0E', '#D88E52'], lit: '#FFD9B3', glow: '#FF9D57', field: ['#1F4E6E', '#0C2438', '#04101C'] },
  s: { rim: ['#FFFFFF', '#DCE3F0', '#8B96AE', '#4A5368', '#C9D2E4'], lit: '#F2F6FF', glow: '#9CC4FF', field: ['#2C55D6', '#142A85', '#070F3C'] },
  g: { rim: ['#FFF6CC', '#FFD45E', '#C98A0E', '#6E4304', '#F5C040'], lit: '#FFF0B8', glow: '#FFC94A', field: ['#3A2A8C', '#1A1050', '#08051F'] },
  l: { rim: ['#FFF6CC', '#FFD45E', '#C98A0E', '#6E4304', '#F5C040'], iri: ['#FF6BD6', '#7C4DFF', '#35D0FF', '#2FD3A0', '#FFD23F', '#FF6BD6'], lit: '#FFFFFF', glow: '#E59BFF', field: ['#7A3BE0', '#3A1290', '#12043A'] },
};
const metalOf = (l) => (l === 9 ? 'l' : l >= 7 ? 'g' : l >= 4 ? 's' : 'b');

// a four-point sparkle
const star = (x, y, r, w, fill) =>
  `<path d="M${x} ${f(y - r)}Q${f(x + w)} ${f(y - w)} ${f(x + r)} ${y}Q${f(x + w)} ${f(y + w)} ${x} ${f(y + r)}Q${f(x - w)} ${f(y + w)} ${f(x - r)} ${y}Q${f(x - w)} ${f(y - w)} ${x} ${f(y - r)}z" fill="${fill}"/>`;
const rng = (seed) => () => ((seed = (seed * 16807) % 2147483647) / 2147483647);

// a laurel branch inside the rim, from the bottom up one side: paired leaves leaning along the growth
function laurel(side, span, stem) {
  let s = '';
  const R = 194, n = Math.round(span / 11);
  for (let i = 0; i < n; i++) {
    const a = 180 + side * (14 + i * 11), r = (a * Math.PI) / 180;
    const [x, y] = pt(R, a), th = (Math.atan2(side * Math.cos(r), -side * Math.sin(r)) * 180) / Math.PI, k = 1 - i * 0.025;
    for (const lean of [-40, 40]) s += `<path d="M0 0Q10 -15 0 -31Q-10 -15 0 0z" transform="translate(${x} ${y}) rotate(${f(th + lean)}) scale(${f(k)})" fill="url(#leaf)" stroke="${stem}" stroke-width="1" stroke-opacity=".6"/>`;
  }
  const [x0, y0] = pt(R, 180 + side * 6), [x1, y1] = pt(R, 180 + side * (14 + (n - 1) * 11));
  return `<path d="M${x0} ${y0}A${R} ${R} 0 0 ${side > 0 ? 1 : 0} ${x1} ${y1}" fill="none" stroke="${stem}" stroke-width="3.5" stroke-linecap="round"/>` + s;
}

// the rim: a ring round the field's hole (milled edge, bevels, a bead row), the field's sunk edge, a static gloss
function rim(m, extra = '') {
  let knurl = '', beads = '';
  for (let i = 0; i < 144; i++) { const [a, b] = pt(250, i * 2.5), [c, d] = pt(240, i * 2.5); knurl += `M${a} ${b}L${c} ${d}`; }
  for (let i = 0; i < 60; i++) { const [x, y] = pt(226, i * 6); beads += `<circle cx="${x}" cy="${y}" r="2.1"/>`; }
  return svg(`<linearGradient id="rim" x1="0" y1="0" x2="1" y2="1">${stops(m.rim)}</linearGradient>
<linearGradient id="rimIn" x1="1" y1="1" x2="0" y2="0">${stops(m.rim)}</linearGradient>
<linearGradient id="leaf" x1="0" y1="0" x2="1" y2="1">${stops(m.rim.slice(0, 3))}</linearGradient>
<linearGradient id="gloss" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFFFFF" stop-opacity=".24"/><stop offset="1" stop-color="#FFFFFF" stop-opacity="0"/></linearGradient>
<radialGradient id="halo" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="${m.glow}" stop-opacity=".75"/><stop offset="1" stop-color="${m.glow}" stop-opacity="0"/></radialGradient>
${m.iri ? `<linearGradient id="iri" x1="0" y1="0" x2="1" y2="1">${stops(m.iri)}</linearGradient>` : ''}
<radialGradient id="sink" cx=".5" cy=".5" r=".5"><stop offset=".9" stop-color="#000" stop-opacity="0"/><stop offset="1" stop-color="#000" stop-opacity=".45"/></radialGradient>
<mask id="hole"><circle cx="${C}" cy="${C}" r="256" fill="#fff"/><circle cx="${C}" cy="${C}" r="${FIELD}" fill="#000"/></mask>`,
  `<circle cx="${C}" cy="${C}" r="${FIELD + 1}" fill="url(#sink)"/>
<path d="M${C - 200} ${C - 30}A${FIELD} ${FIELD} 0 0 1 ${C + 170} ${C - 120}Q${C} ${C - 120} ${C - 200} ${C - 30}z" fill="url(#gloss)"/>
<g mask="url(#hole)"><circle cx="${C}" cy="${C}" r="252" fill="url(#rim)"/>
<path d="${knurl}" stroke="${m.rim[3]}" stroke-width="1.6" opacity=".45"/>
<circle cx="${C}" cy="${C}" r="238" fill="url(#rimIn)"/><circle cx="${C}" cy="${C}" r="232" fill="url(#rim)"/>
<g fill="${m.rim[3]}" opacity=".55">${beads}</g>
<circle cx="${C}" cy="${C}" r="216" fill="url(#rimIn)"/>
${m.iri ? `<circle cx="${C}" cy="${C}" r="226" fill="none" stroke="url(#iri)" stroke-width="12"/>` : ''}</g>
<circle cx="${C}" cy="${C}" r="${FIELD}" fill="none" stroke="#000" stroke-opacity=".35" stroke-width="3"/>
<path d="M${C - 236} ${C - 40}A240 240 0 0 1 ${C + 120} ${C - 207}" fill="none" stroke="#FFFFFF" stroke-opacity=".55" stroke-width="3" stroke-linecap="round"/>
${extra}`);
}

// the field: enamel, the banknote guilloche the KBTU lanyard uses, rays from a light, far stars; r 236: it overscans
function field(colors, lit, seed, light = [C, C], rayAlpha = 0.38) {
  let rays = '', guil = '', dust = '';
  for (let i = 0; i < 32; i++) {
    const a = (i * 11.25 * Math.PI) / 180, b = 0.028;
    rays += `M${light[0]} ${light[1]}L${f(light[0] + 330 * Math.sin(a - b))} ${f(light[1] - 330 * Math.cos(a - b))}L${f(light[0] + 330 * Math.sin(a + b))} ${f(light[1] - 330 * Math.cos(a + b))}z`;
  }
  for (let i = 0; i < 24; i++) guil += `<ellipse cx="${C}" cy="${C}" rx="210" ry="78" transform="rotate(${f(i * 7.5)} ${C} ${C})"/>`;
  const rnd = rng(seed);
  for (let i = 0; i < 52; i++) { const [x, y] = pt(50 + rnd() * 180, rnd() * 360); dust += `<circle cx="${x}" cy="${y}" r="${f(0.8 + rnd() * 1.6)}" opacity="${f(0.25 + rnd() * 0.5)}"/>`; }
  return svg(`<radialGradient id="field" cx=".42" cy=".34" r=".75">${stops(colors)}</radialGradient>
<radialGradient id="rays" cx="${f(light[0] / 512)}" cy="${f(light[1] / 512)}" r=".5"><stop offset="0" stop-color="${lit}" stop-opacity=".5"/><stop offset="1" stop-color="${lit}" stop-opacity="0"/></radialGradient>
<clipPath id="in"><circle cx="${C}" cy="${C}" r="236"/></clipPath>`,
  `<circle cx="${C}" cy="${C}" r="236" fill="url(#field)"/><g clip-path="url(#in)">
<g fill="none" stroke="#FFFFFF" stroke-width="1" opacity=".07">${guil}</g>
<path d="${rays}" fill="url(#rays)" opacity="${rayAlpha}"/>
<g fill="#FFFFFF">${dust}</g></g>`);
}

// ---- Recruiter
function nodes(level) {
  if (level === 9) return [...[0, 90, 180, 270].map((a) => [104, a + 45, 17]), ...Array.from({ length: 8 }, (_, i) => [160, i * 45, 15])];
  const start = level === 1 ? 45 : level === 2 ? -60 : 0;
  return Array.from({ length: level }, (_, i) => [146, start + (i * 360) / level, 19]);
}
const bust = (x, y, s, fill) =>
  `<g fill="${fill}" opacity=".55"><circle cx="${x}" cy="${f(y - s * 0.28)}" r="${f(s * 0.26)}"/><path d="M${f(x - s * 0.5)} ${f(y + s * 0.5)}a${f(s * 0.5)} ${f(s * 0.46)} 0 0 1 ${f(s)} 0z"/></g>`;

function net(level) {
  const m = METAL[metalOf(level)], ns = nodes(level), pos = ns.map(([r, a, s]) => [...pt(r, a), s, r]);
  let ties = '', web = '';
  for (const [x, y] of pos) ties += `M${C} ${C}L${x} ${y}`;
  const ring = (list) => { for (let i = 0; i < list.length && list.length > 1; i++) { if (list.length === 2 && i === 1) break; const [x, y] = list[i], [u, v] = list[(i + 1) % list.length]; web += `M${x} ${y}L${u} ${v}`; } };
  ring(pos.filter((p) => p[3] === pos[0][3])); ring(pos.filter((p) => p[3] !== pos[0][3]));
  if (level === 9) for (let i = 0; i < 4; i++) for (const j of [0, 1, 2]) { const a = pos[i], b = pos[4 + ((i * 2 + j) % 8)]; web += `M${a[0]} ${a[1]}L${b[0]} ${b[1]}`; }
  return svg(`<linearGradient id="tie" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="${m.lit}"/><stop offset="1" stop-color="${m.glow}"/></linearGradient>
<radialGradient id="orb" cx=".38" cy=".32" r=".7"><stop offset="0" stop-color="#FFFFFF"/><stop offset=".45" stop-color="${m.lit}"/><stop offset="1" stop-color="${m.glow}"/></radialGradient>
<radialGradient id="halo" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="${m.glow}" stop-opacity=".75"/><stop offset="1" stop-color="${m.glow}" stop-opacity="0"/></radialGradient>`,
  `${[...new Set(ns.map((n) => n[0]))].map((r) => `<circle cx="${C}" cy="${C}" r="${r}" fill="none" stroke="${m.lit}" stroke-width="1.6" stroke-dasharray="2 7" stroke-linecap="round" opacity=".45"/>`).join('')}
<path d="${web}" stroke="${m.lit}" stroke-width="3" stroke-linecap="round" opacity=".35" fill="none"/>
<path d="${ties}" stroke="url(#tie)" stroke-width="9" stroke-linecap="round" opacity=".18" fill="none"/>
<path d="${ties}" stroke="${m.lit}" stroke-width="3.2" stroke-linecap="round" opacity=".85" fill="none"/>
${pos.map(([x, y, s]) => `<circle cx="${x}" cy="${y}" r="${f(s * 2)}" fill="url(#halo)"/>`).join('')}
${pos.map(([x, y, s]) => `<circle cx="${x}" cy="${y}" r="${s}" fill="url(#orb)"/>${bust(x, y + 1, s * 1.15, m.field[1])}<circle cx="${x}" cy="${y}" r="${s}" fill="none" stroke="#FFFFFF" stroke-opacity=".7" stroke-width="1.5"/>`).join('')}`);
}

const core = (m) => svg(`<radialGradient id="core" cx=".5" cy=".5" r=".5"><stop offset="0" stop-color="#FFFFFF"/><stop offset=".35" stop-color="${m.lit}"/><stop offset=".7" stop-color="${m.glow}" stop-opacity=".55"/><stop offset="1" stop-color="${m.glow}" stop-opacity="0"/></radialGradient>`,
  `<circle cx="${C}" cy="${C}" r="96" fill="url(#core)"/>${star(C, C, 70, 9, m.lit)}${star(C, C, 46, 5, '#FFFFFF')}<g transform="rotate(45 ${C} ${C})" opacity=".8">${star(C, C, 30, 4, '#FFFFFF')}</g><circle cx="${C}" cy="${C}" r="11" fill="#FFFFFF"/>`);

const files = {};
for (const k of 'bsgl') {
  const m = METAL[k];
  files[`rc-field-${k}`] = field(m.field, m.lit, 'bsgl'.indexOf(k) * 97 + 13);
  files[`rc-core-${k}`] = core(m);
  const wreath = k === 'g' || k === 'l' ? laurel(1, k === 'l' ? 140 : 66, m.rim[3]) + laurel(-1, k === 'l' ? 140 : 66, m.rim[3]) : '';
  files[`rc-rim-${k}`] = rim(m, wreath + (k === 'l' ? `<circle cx="${C}" cy="26" r="34" fill="url(#halo)"/>${star(C, 26, 30, 5, '#FFFFFF')}<circle cx="${C}" cy="26" r="5" fill="#FFFFFF"/>` : ''));
}
for (let l = 1; l <= 9; l++) files[`rc-net-${l}`] = net(l);


// ---- the other medals (awards plan, Nov 3): one picture each on its own enamel field, under the shared rim of the
// level's metal (rc-rim-*): <p>-field (far), <p>-art (the picture), <p>-near (its nearest part, floats most). Every
// picture keeps inside r 165 above the laurels (gold and legend rims grow them low on both sides) and casts a soft shadow.
const SHADOW = '<filter id="sh" x="-30%" y="-30%" width="160%" height="170%"><feGaussianBlur in="SourceAlpha" stdDeviation="7"/><feOffset dy="9"/><feComponentTransfer><feFuncA type="linear" slope=".5"/></feComponentTransfer><feMerge><feMergeNode/><feMergeNode in="SourceGraphic"/></feMerge></filter>';
const lin = (id, cs, x2 = 0, y2 = 1, x1 = 0, y1 = 0) => `<linearGradient id="${id}" x1="${x1}" y1="${y1}" x2="${x2}" y2="${y2}">${stops(cs)}</linearGradient>`;
const rad = (id, cs, cx = 0.38, cy = 0.3, r = 0.75) => `<radialGradient id="${id}" cx="${cx}" cy="${cy}" r="${r}">${stops(cs)}</radialGradient>`;
const GOLDS = ['#FFF6CC', '#FFD45E', '#C98A0E'];
const sparks = (list) => list.map(([x, y, r]) => star(x, y, r, r / 6, '#FFFFFF')).join('');
const star5 = (x, y, R, r = R * 0.45, rot = 0) => 'M' + Array.from({ length: 10 }, (_, i) => { const a = ((i * 36 + rot) * Math.PI) / 180, k = i % 2 ? r : R; return `${f(x + k * Math.sin(a))} ${f(y - k * Math.cos(a))}`; }).join('L') + 'z';
const pic = (p, fieldColors, light, art, near = null, rays = 0.3) => {
  files[`${p}-field`] = field(fieldColors, '#FFFFFF', p.charCodeAt(0) * 31 + p.charCodeAt(1), light, rays);
  files[`${p}-art`] = svg(SHADOW + art[0], `<g filter="url(#sh)">${art[1]}</g>`);
  if (near) files[`${p}-near`] = svg(SHADOW + near[0], `<g filter="url(#sh)">${near[1]}</g>`);
};

// Regular: a golden ticket, a star punched in it, the stub torn along its perforation
pic('rg', ['#B4284E', '#5E0C2A', '#22030F'], [C, 250], [
  lin('tk', GOLDS, 1, 1) + lin('tk2', ['#FFE9A0', '#E2A72A'], 0, 1) + '<mask id="cut"><rect width="512" height="512" fill="#fff"/><circle cx="118" cy="256" r="22" fill="#000"/><circle cx="394" cy="256" r="22" fill="#000"/><circle cx="318" cy="180" r="11" fill="#000"/><circle cx="318" cy="332" r="11" fill="#000"/></mask>',
  `<g transform="rotate(-14 256 256)"><g mask="url(#cut)"><rect x="118" y="180" width="276" height="152" rx="18" fill="url(#tk)"/>
<rect x="134" y="196" width="244" height="120" rx="10" fill="none" stroke="#8A5606" stroke-opacity=".5" stroke-width="3"/></g>
<path d="M318 196V316" stroke="#8A5606" stroke-opacity=".55" stroke-width="4" stroke-dasharray="2 9" stroke-linecap="round"/>
<path d="${star5(222, 258, 46, 20)}" fill="#7A1030"/><path d="${star5(222, 254, 40, 17)}" fill="#B4284E"/>
<path d="M342 226h30M342 246h30M342 266h22M342 286h30" stroke="#8A5606" stroke-opacity=".55" stroke-width="6" stroke-linecap="round"/>
<path d="M136 192Q250 182 384 194" stroke="#FFFFFF" stroke-opacity=".65" stroke-width="3" fill="none" stroke-linecap="round"/></g>`],
  ['', sparks([[392, 150, 20], [138, 352, 14], [370, 372, 10]])]);

// Streak: a flame burning on, tongue in tongue, sparks flying off it
pic('st', ['#4A2296', '#200C52', '#0A0420'], [C, 340], [
  lin('f1', ['#FFB23A', '#FF5A1F', '#C21A2A'], 0, 1) + lin('f2', ['#FFF2A8', '#FFC23A', '#FF7A1F'], 0, 1) + lin('f3', ['#FFFFFF', '#FFF2B8'], 0, 1) + rad('fg', ['#FF9A3A', '#FF9A3A00'], 0.5, 0.62, 0.5),
  `<circle cx="256" cy="300" r="150" fill="url(#fg)" opacity=".55"/>
<path d="M262 92C276 150 352 180 360 268C368 350 316 404 256 404C190 404 146 356 152 288C156 240 184 214 196 172C206 206 214 222 232 234C230 184 236 136 262 92z" fill="url(#f1)"/>
<path d="M266 176C276 222 326 246 326 306C326 356 296 384 256 384C214 384 186 354 188 314C190 282 208 262 218 236C226 260 236 270 248 276C246 240 250 206 266 176z" fill="url(#f2)"/>
<path d="M260 262C268 290 296 306 294 340C292 366 276 380 256 380C234 380 220 364 220 342C220 316 240 300 248 280C252 290 256 294 260 296z" fill="url(#f3)"/>`],
  ['', `<g fill="#FFD27A">${[[356, 170, 7], [384, 214, 5], [140, 196, 6], [168, 146, 4.5], [330, 120, 4]].map(([x, y, r]) => `<path d="M${x} ${y - r * 1.6}L${x + r} ${y}L${x} ${y + r * 1.6}L${x - r} ${y}z"/>`).join('')}</g>`]);

// First in: an open door with the light of the room spilling out of it, a star over it
pic('fi', ['#2A4FA8', '#11245C', '#050C24'], [C, 236], [
  lin('lt', ['#FFFBEA', '#FFE7A6', '#FFC45A'], 0, 1) + lin('fr', GOLDS, 1, 1) + lin('dr', ['#E2A72A', '#8A5606'], 1, 0) + lin('fl', ['#FFE7A6', '#FFE7A600'], 0, 1),
  `<path d="M150 404L196 340H316L362 404z" fill="url(#fl)" opacity=".85"/>
<path d="M178 340V196Q178 130 256 130Q334 130 334 196V340z" fill="url(#fr)"/>
<path d="M196 340V200Q196 148 256 148Q316 148 316 200V340z" fill="url(#lt)"/>
<path d="M196 340V200Q196 158 214 150L150 176Q140 182 140 196V372Q140 382 150 380z" fill="url(#dr)"/>
<circle cx="158" cy="272" r="6" fill="#FFF6CC"/>
<path d="M164 342H348" stroke="#FFF6CC" stroke-width="6" stroke-linecap="round"/>`],
  ['', `${star(332, 128, 34, 6, '#FFFFFF')}<circle cx="332" cy="128" r="5" fill="#FFFFFF"/>${sparks([[384, 196, 12]])}`], 0.45);

// Life of the party: a mirror ball on its string throwing light round the room
const ball = (() => {
  const cx = 256, cy = 236, R = 98, rnd = rng(77);
  const tones = ['#FFFFFF', '#E6ECFA', '#B9C3E0', '#8C97BC', '#FFC2EC', '#A6ECFF', '#6B7499'];
  let tiles = '';
  for (let lat = -80; lat < 80; lat += 16) {
    const y0 = cy + R * Math.sin((lat * Math.PI) / 180), y1 = cy + R * Math.sin(((lat + 16) * Math.PI) / 180);
    const w = R * Math.cos(((lat + 8) * Math.PI) / 180), n = Math.max(4, Math.round((2 * w) / 19));
    for (let i = 0; i < n; i++) {
      const x0 = cx - w + (2 * w * i) / n, ww = (2 * w) / n, lit = (x0 - cx) / R * -0.5 + (y0 - cy) / R * -0.6;
      const tone = tones[Math.min(tones.length - 1, Math.max(0, Math.floor(3 - lit * 3 + rnd() * 2.2)))];
      tiles += `<rect x="${f(x0 + 1)}" y="${f(y0 + 1)}" width="${f(ww - 2)}" height="${f(y1 - y0 - 2)}" rx="2" fill="${rnd() < 0.08 ? (rnd() < 0.5 ? '#FFC2EC' : '#A6ECFF') : tone}"/>`;
    }
  }
  return [rad('bl', ['#FFFFFF', '#AEB8D8', '#3A4268'], 0.36, 0.3, 0.8) + `<clipPath id="bc"><circle cx="${cx}" cy="${cy}" r="${R}"/></clipPath>` + rad('gl', ['#FFFFFF', '#FFFFFF00'], 0.5, 0.5, 0.5),
    `<path d="M256 52V140" stroke="#E6ECFA" stroke-width="4"/><rect x="246" y="128" width="20" height="14" rx="3" fill="#C9D2E4"/>
<circle cx="${cx}" cy="${cy}" r="${R}" fill="url(#bl)"/><g clip-path="url(#bc)">${tiles}<circle cx="${cx}" cy="${cy}" r="${R}" fill="url(#bl)" opacity=".25"/></g>
<circle cx="${cx}" cy="${cy}" r="${R}" fill="none" stroke="#2A2F4A" stroke-opacity=".5" stroke-width="2"/>`];
})();
pic('so', ['#C0308C', '#5E0F52', '#22041E'], [C, 236], ball,
  ['', `${star(214, 190, 30, 4, '#FFFFFF')}<circle cx="214" cy="190" r="5" fill="#FFFFFF"/>${sparks([[372, 300, 18], [140, 316, 14], [362, 150, 11], [150, 140, 9]])}
<g stroke="#FFC2EC" stroke-width="3" stroke-linecap="round" opacity=".8"><path d="M176 372l-14 18M336 372l14 18M256 388v22"/></g>`], 0.5);

// Teambuilding thunder: a storm cloud with its rain and the bolt out of it
pic('tm', ['#3E6AB8', '#1A3366', '#08142C'], [C, 220], [
  lin('cl', ['#FFFFFF', '#DCE4F6', '#9AA9CC'], 0, 1) + lin('cd', ['#8E9CC4', '#5C6A94'], 0, 1),
  `<g stroke="#9CC4FF" stroke-width="7" stroke-linecap="round" opacity=".75"><path d="M178 322l-14 34M218 330l-14 34M298 330l-14 34M338 322l-14 34"/></g>
<path d="M150 300Q114 300 114 264Q114 230 150 226Q152 186 196 182Q216 136 266 136Q322 136 336 188Q394 188 398 244Q400 300 344 300z" fill="url(#cd)" transform="translate(0 14)"/>
<path d="M150 300Q114 300 114 264Q114 230 150 226Q152 186 196 182Q216 136 266 136Q322 136 336 188Q394 188 398 244Q400 300 344 300z" fill="url(#cl)"/>
<path d="M196 182Q216 136 266 136Q306 136 324 170Q300 152 266 156Q226 156 210 190z" fill="#FFFFFF" opacity=".8"/>`],
  [lin('bo', ['#FFF6B8', '#FFD23A', '#FF9A1F'], 0, 1),
   `<path d="M270 262L222 352H260L238 432L318 324H276L302 262z" fill="url(#bo)" stroke="#FFF6CC" stroke-width="3" stroke-linejoin="round"/>`]);

// Season: a desk calendar, a term's days ticked off in it
pic('se', ['#E07A2A', '#8A3A0E', '#341404'], [C, 240], [
  lin('pg', ['#FFFFFF', '#F4ECDC'], 0, 1) + lin('hd', ['#FF7A62', '#D23A2C'], 0, 1) + lin('rg', GOLDS, 1, 0),
  (() => {
    let cells = '';
    const on = [0, 1, 2, 4, 5, 7, 8, 10, 11, 12, 14];
    for (let r = 0; r < 4; r++) for (let c = 0; c < 5; c++) {
      const i = r * 5 + c, x = 172 + c * 36, y = 236 + r * 34;
      cells += on.includes(i) ? `<circle cx="${x + 12}" cy="${y + 12}" r="13" fill="#D23A2C"/><path d="M${x + 6} ${y + 12}l5 5l9 -10" stroke="#FFFFFF" stroke-width="3.5" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`
        : `<rect x="${x + 2}" y="${y + 2}" width="20" height="20" rx="5" fill="#E2D6C0"/>`;
    }
    return `<rect x="150" y="146" width="212" height="232" rx="24" fill="url(#pg)"/>
<path d="M150 170Q150 146 174 146H338Q362 146 362 170V212H150z" fill="url(#hd)"/>
${cells}
<rect x="196" y="122" width="16" height="46" rx="8" fill="url(#rg)"/><rect x="300" y="122" width="16" height="46" rx="8" fill="url(#rg)"/>`;
  })()],
  [lin('lf', ['#FFD45E', '#E2672A'], 1, 1),
   `<g transform="rotate(-28 372 340)"><path d="M372 292Q412 318 372 392Q332 318 372 292z" fill="url(#lf)"/><path d="M372 300V386" stroke="#9A3A0E" stroke-width="3" opacity=".6"/></g>`]);

// Bug hunter: a ladybird on its leaf
pic('bg', ['#3C9A48', '#185226', '#06200C'], [C, 230], [
  lin('lv', ['#9AE07A', '#3E9A3A', '#1E6624'], 1, 1),
  `<path d="M120 380Q130 200 300 130Q400 100 404 116Q414 240 300 330Q220 392 120 380z" fill="url(#lv)"/>
<path d="M126 374Q250 260 396 124" stroke="#1A5A20" stroke-width="5" fill="none" stroke-linecap="round" opacity=".6"/>
<g stroke="#1A5A20" stroke-width="3" fill="none" opacity=".45">${[[180, 316, 150, 270], [230, 270, 196, 214], [280, 224, 262, 168], [210, 292, 252, 330], [262, 246, 312, 280], [312, 200, 352, 226]].map(([a, b, c, d]) => `<path d="M${a} ${b}Q${(a + c) / 2 + 8} ${(b + d) / 2} ${c} ${d}"/>`).join('')}</g>`],
  [lin('el', ['#FF7A5A', '#E3242B', '#9E0E16'], 1, 1),
   `<g transform="rotate(-24 262 262)">
<g stroke="#1A1416" stroke-width="7" stroke-linecap="round" fill="none"><path d="M206 236l-30 -14M200 270l-34 2M208 304l-28 18M318 236l30 -14M324 270l34 2M316 304l28 18"/><path d="M246 168Q236 140 214 134M278 168Q288 140 310 134"/></g>
<circle cx="213" cy="133" r="8" fill="#1A1416"/><circle cx="311" cy="133" r="8" fill="#1A1416"/>
<path d="M222 186Q262 140 302 186z" fill="#1A1416"/><ellipse cx="262" cy="186" rx="44" ry="30" fill="#1A1416"/>
<circle cx="244" cy="180" r="7" fill="#FFFFFF"/><circle cx="280" cy="180" r="7" fill="#FFFFFF"/>
<ellipse cx="262" cy="270" rx="78" ry="90" fill="url(#el)"/>
<path d="M262 186V360" stroke="#1A1416" stroke-width="5"/>
<g fill="#1A1416"><circle cx="226" cy="236" r="15"/><circle cx="298" cy="236" r="15"/><circle cx="214" cy="292" r="13"/><circle cx="310" cy="292" r="13"/><circle cx="240" cy="334" r="11"/><circle cx="284" cy="334" r="11"/></g>
<ellipse cx="226" cy="214" rx="20" ry="10" fill="#FFFFFF" opacity=".55" transform="rotate(-30 226 214)"/></g>`]);

// Couch critic: an armchair-deep sofa, a speech bubble over it with its three dots
pic('cr', ['#1E8C92', '#0A4A52', '#021E22'], [C, 200], [
  lin('sb', ['#FF9A78', '#E2573A', '#A8341E'], 0, 1) + lin('ss', ['#FFB49A', '#F0704E'], 0, 1) + lin('sa', ['#F07A5A', '#B8432C'], 1, 0),
  `<rect x="150" y="226" width="212" height="88" rx="30" fill="url(#sb)"/>
<rect x="170" y="290" width="172" height="52" rx="16" fill="url(#ss)"/><path d="M256 296V340" stroke="#B8432C" stroke-width="4" opacity=".6"/>
<rect x="118" y="262" width="58" height="104" rx="26" fill="url(#sa)"/><rect x="336" y="262" width="58" height="104" rx="26" fill="url(#sa)" transform="scale(-1 1) translate(-730 0)"/>
<rect x="128" y="350" width="256" height="24" rx="10" fill="#8A2E1A"/>
<g fill="#5A2412"><rect x="146" y="372" width="14" height="22" rx="4"/><rect x="352" y="372" width="14" height="22" rx="4"/></g>
<path d="M164 236Q256 222 348 236" stroke="#FFFFFF" stroke-opacity=".5" stroke-width="4" fill="none" stroke-linecap="round"/>`],
  [lin('bb', ['#FFFFFF', '#E2EAF6'], 0, 1),
   `<path d="M196 104H316Q344 104 344 132V170Q344 198 316 198H284L262 222L256 198H196Q168 198 168 170V132Q168 104 196 104z" fill="url(#bb)"/>
<g fill="#0A4A52"><circle cx="220" cy="151" r="11"/><circle cx="256" cy="151" r="11"/><circle cx="292" cy="151" r="11"/></g>`]);

// a medal's ribbon at 96 px and up (ui/Medal): two tails behind the disc, the rim's metal with a darker band, cut in a V
for (const k of 'bsgl') {
  const m = METAL[k], tail = (side) => `<g transform="translate(256 360) rotate(${side * 24})"><path d="M-62 0H62V240L0 200L-62 240z" fill="url(#rb)"/>
<path d="M-20 0H20V214L0 200L-20 214z" fill="${k === 'l' ? 'url(#iri)' : m.rim[3]}" opacity="${k === 'l' ? 0.9 : 0.55}"/><path d="M-62 0H62V24H-62z" fill="#000" opacity=".25"/></g>`;
  files[`ribbon-${k}`] = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 640"><defs>${lin('rb', [m.rim[1], m.rim[0], m.rim[2]], 1, 0)}${m.iri ? lin('iri', m.iri, 0, 1) : ''}</defs>${tail(-1)}${tail(1)}</svg>\n`;
}

// ---- pins: the one-time awards are enamel shields (ui/Pin): a flat enamel field (Pin fills SHIELD with the colour),
// one glyph over it (zn-<glyph>, floats with the tilt), a thin metal frame with the enamel's gloss on top (zn-frame-<metal>,
// still). SHIELD is lib/awards.ts SHIELD: the two must stay equal.
const SHIELD = 'M100 78Q256 44 412 78Q440 84 440 112V268Q440 398 256 480Q72 398 72 268V112Q72 84 100 78Z';
const ROSE = ['#FFE4D6', '#F0B49C', '#A8604A', '#5E2C1E', '#D8907A'];
for (const [k, rimc] of [['g', METAL.g.rim], ['s', METAL.s.rim], ['r', ROSE]]) {
  files[`zn-frame-${k}`] = svg(lin('fr', rimc, 1, 1) + lin('gl', ['#FFFFFF66', '#FFFFFF00'], 0.6, 1) + `<clipPath id="in"><path d="${SHIELD}"/></clipPath>`,
    `<g clip-path="url(#in)"><path d="M60 40H460V150Q300 120 60 260z" fill="url(#gl)"/></g>
<path d="${SHIELD}" fill="none" stroke="url(#fr)" stroke-width="26" stroke-linejoin="round"/>
<path d="${SHIELD}" fill="none" stroke="${rimc[3]}" stroke-opacity=".6" stroke-width="3" transform="translate(256 262) scale(.9) translate(-256 -262)"/>
<path d="M104 70Q256 36 408 70" fill="none" stroke="#FFFFFF" stroke-opacity=".7" stroke-width="3" stroke-linecap="round"/>`);
}
const glyph = (name, defs, body) => (files[`zn-${name}`] = svg(SHADOW.replace('stdDeviation="7"', 'stdDeviation="4"').replace('dy="9"', 'dy="5"') + defs, `<g filter="url(#sh)">${body}</g>`));
// First 500: the number struck in gold
glyph('500', lin('gd', GOLDS, 0, 1), (() => {
  const five = (x, y) => `M${x + 58} ${y}H${x + 12}L${x + 8} ${y + 52}C${x + 30} ${y + 40} ${x + 70} ${y + 46} ${x + 70} ${y + 84}C${x + 70} ${y + 122} ${x + 22} ${y + 126} ${x + 4} ${y + 104}`;
  const d = `${five(132, 182)}M${248 - 0} 240m-30 0a30 56 0 1 0 60 0a30 56 0 1 0 -60 0M${336} 240m-30 0a30 56 0 1 0 60 0a30 56 0 1 0 -60 0`;
  return `<path d="${d}" fill="none" stroke="#5E3A04" stroke-width="34" stroke-linecap="round" stroke-linejoin="round"/><path d="${d}" fill="none" stroke="url(#gd)" stroke-width="22" stroke-linecap="round" stroke-linejoin="round"/>
${star(256, 352, 18, 3, '#FFE9A0')}${star(200, 356, 9, 1.6, '#FFE9A0')}${star(312, 356, 9, 1.6, '#FFE9A0')}`;
})());
// the 2026 initiation: the mountains and the dome it was held under
glyph('init26', lin('gd', GOLDS, 0, 1) + lin('sn', ['#FFFFFF', '#C8D6F2'], 0, 1),
  `<path d="M108 250L168 176L204 214L262 132L322 206L352 180L404 250z" fill="#8FA8E6"/>
<path d="M168 176L186 198L174 196L160 210zM262 132L290 172L270 166L254 186L242 162zM352 180L366 198L350 196z" fill="url(#sn)"/>
<path d="M146 300Q146 224 256 214Q366 224 366 300z" fill="url(#gd)" stroke="#8A5606" stroke-width="4"/>
<path d="M164 270Q256 246 348 270M190 238Q256 226 322 238" fill="none" stroke="#8A5606" stroke-width="4" opacity=".7"/>
<rect x="136" y="298" width="240" height="56" rx="6" fill="url(#gd)" stroke="#8A5606" stroke-width="4"/>
<g fill="#8A5606" opacity=".75">${[0, 1, 2, 3, 4, 5, 6].map((i) => `<rect x="${154 + i * 30}" y="310" width="14" height="34" rx="3"/>`).join('')}</g>
<rect x="120" y="352" width="272" height="16" rx="5" fill="url(#gd)" stroke="#8A5606" stroke-width="4"/>`);
// Anthem: KBTU's colonnade, two notes over it
glyph('anthem', lin('gd', GOLDS, 0, 1),
  `<path d="M150 214L256 160L362 214z" fill="url(#gd)" stroke="#8A5606" stroke-width="4" stroke-linejoin="round"/>
<rect x="140" y="212" width="232" height="18" rx="4" fill="url(#gd)" stroke="#8A5606" stroke-width="4"/>
${[0, 1, 2, 3].map((i) => `<rect x="${164 + i * 52}" y="236" width="28" height="100" rx="3" fill="url(#gd)" stroke="#8A5606" stroke-width="4"/>`).join('')}
<rect x="132" y="338" width="248" height="16" rx="4" fill="url(#gd)" stroke="#8A5606" stroke-width="4"/><rect x="116" y="356" width="280" height="16" rx="4" fill="url(#gd)" stroke="#8A5606" stroke-width="4"/>
<g fill="#FFFFFF"><ellipse cx="330" cy="140" rx="15" ry="11" transform="rotate(-22 330 140)"/><ellipse cx="380" cy="126" rx="15" ry="11" transform="rotate(-22 380 126)"/>
<path d="M342 136V84L392 70V122" fill="none" stroke="#FFFFFF" stroke-width="7" stroke-linejoin="round"/><path d="M342 84L392 70V86L342 100z"/></g>`);
// Made the creator laugh: a face laughing to tears
glyph('laugh', rad('fc', ['#FFF2A8', '#FFD23A', '#F0A01E'], 0.4, 0.3, 0.8),
  `<circle cx="256" cy="250" r="104" fill="url(#fc)" stroke="#8A5606" stroke-width="5"/>
<path d="M196 226Q214 204 232 226M280 226Q298 204 316 226" fill="none" stroke="#5A3A10" stroke-width="10" stroke-linecap="round"/>
<path d="M186 262Q256 274 326 262Q320 330 256 334Q192 330 186 262z" fill="#5A1E14"/><path d="M220 314Q256 296 292 314Q276 332 256 332Q236 332 220 314z" fill="#F0606A"/><path d="M196 266Q256 276 316 266L312 280Q256 288 200 280z" fill="#FFFFFF"/>
<g fill="#5AC8FF" stroke="#FFFFFF" stroke-width="3"><path d="M168 230Q130 262 150 290Q172 300 176 268z"/><path d="M344 230Q382 262 362 290Q340 300 336 268z"/></g>`);
// Found the creator: a hand waving hello
glyph('wave', lin('hd', ['#FFE08A', '#FFC23A', '#E8961E'], 1, 1),
  `<g transform="rotate(-16 256 270)" fill="url(#hd)" stroke="#8A5606" stroke-width="5" stroke-linejoin="round">
<rect x="178" y="236" width="150" height="140" rx="56"/>
${[[184, 140, 150], [222, 112, 170], [260, 118, 166], [296, 146, 140]].map(([x, y, h]) => `<rect x="${x}" y="${y}" width="34" height="${h}" rx="17"/>`).join('')}
<rect x="300" y="250" width="34" height="104" rx="17" transform="rotate(42 318 300)"/>
<path d="M190 300Q256 330 324 296" fill="none" stroke-width="0"/></g>
<g fill="none" stroke="#FFFFFF" stroke-width="7" stroke-linecap="round" opacity=".9"><path d="M120 170Q108 210 122 248"/><path d="M146 150Q130 200 146 246" opacity=".6"/><path d="M394 170Q406 210 392 248"/><path d="M368 150Q384 200 368 246" opacity=".6"/></g>`);

for (const [n, s] of Object.entries(files)) writeFileSync(new URL(`${n}.svg`, out), s);
console.log(Object.keys(files).length, 'files');
