// The drawn achievement medals, in layers (public/medals/*.svg): vector, so crisp at any size and pixel ratio, and
// layered, so the field, the art and the near art float with the phone's tilt under a still rim (ui/Medal.svelte,
// lib/awards.ts layersOf). Every layer is the same 512 box centred on the medal; the field overscans under the rim.
//   Recruiter (rc-*): a constellation. I am the star in the middle; each level one more friend lights up on the
//     orbit, tied to me and to each other. The rim is the level's metal (bronze I-III, silver IV-VI, gold VII-VIII,
//     legend IX); gold grows laurels, legend a full wreath, an iridescent bezel and a crown star.
//   Anthem (an-*): KBTU's colonnade in gold at sunrise, the anthem's staff flowing over it with its notes.
// usage: node tools/medals.mjs   (from web/)
import { writeFileSync, mkdirSync } from 'node:fs';
const out = new URL('../public/medals/', import.meta.url);
mkdirSync(out, { recursive: true });
const C = 256, FIELD = 212, f = (n) => +n.toFixed(2);
const pt = (r, deg) => [f(C + r * Math.sin((deg * Math.PI) / 180)), f(C - r * Math.cos((deg * Math.PI) / 180))];
const svg = (defs, body) => `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512"><defs>${defs}</defs>${body}</svg>\n`;
const stops = (cs) => cs.map((c, i) => `<stop offset="${f(i / (cs.length - 1))}" stop-color="${c}"/>`).join('');

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

// ---- Anthem: sunrise behind the colonnade, the staff of the anthem flowing over it
const AN = { ...METAL.g, field: ['#5A4CF0', '#2A1A9A', '#0B0640'] };
const SUN = [C, 330];
files['an-field'] = svg(`<radialGradient id="field" cx=".5" cy=".34" r=".8">${stops(AN.field)}</radialGradient>
<radialGradient id="dawn" cx="${f(SUN[0] / 512)}" cy="${f(SUN[1] / 512)}" r=".42"><stop offset="0" stop-color="#FFE7A6"/><stop offset=".25" stop-color="#FFB45A" stop-opacity=".85"/><stop offset=".6" stop-color="#E0508A" stop-opacity=".35"/><stop offset="1" stop-color="#E0508A" stop-opacity="0"/></radialGradient>
<radialGradient id="rays" cx="${f(SUN[0] / 512)}" cy="${f(SUN[1] / 512)}" r=".55"><stop offset="0" stop-color="#FFE7A6" stop-opacity=".55"/><stop offset="1" stop-color="#FFE7A6" stop-opacity="0"/></radialGradient>
<clipPath id="in"><circle cx="${C}" cy="${C}" r="236"/></clipPath>`,
  (() => {
    let rays = '', guil = '', dust = '';
    for (let i = 0; i < 40; i++) { const a = (i * 9 * Math.PI) / 180, b = 0.022; rays += `M${SUN[0]} ${SUN[1]}L${f(SUN[0] + 340 * Math.sin(a - b))} ${f(SUN[1] - 340 * Math.cos(a - b))}L${f(SUN[0] + 340 * Math.sin(a + b))} ${f(SUN[1] - 340 * Math.cos(a + b))}z`; }
    for (let i = 0; i < 24; i++) guil += `<ellipse cx="${C}" cy="${C}" rx="210" ry="78" transform="rotate(${f(i * 7.5)} ${C} ${C})"/>`;
    const rnd = rng(4242);
    for (let i = 0; i < 40; i++) { const x = 40 + rnd() * 432, y = 40 + rnd() * 200; dust += `<circle cx="${f(x)}" cy="${f(y)}" r="${f(0.8 + rnd() * 1.5)}" opacity="${f(0.25 + rnd() * 0.5)}"/>`; }
    return `<circle cx="${C}" cy="${C}" r="236" fill="url(#field)"/><g clip-path="url(#in)">
<g fill="none" stroke="#FFFFFF" stroke-width="1" opacity=".06">${guil}</g>
<g fill="#FFFFFF">${dust}</g>
<circle cx="${SUN[0]}" cy="${SUN[1]}" r="215" fill="url(#dawn)"/>
<path d="${rays}" fill="url(#rays)" opacity=".7"/>
<circle cx="${SUN[0]}" cy="${SUN[1] - 6}" r="46" fill="#FFF3CF" opacity=".9"/></g>`;
  })());

// the staff: five lines along one gentle wave, from low left to high right; notes ride it
const wave = (x, k) => 196 - (x - C) * 0.3 + Math.sin((x - 40) / 70) * 22 + k * 15;
const staffPath = (k) => { let d = ''; for (let x = 20; x <= 492; x += 8) d += `${x === 20 ? 'M' : 'L'}${x} ${f(wave(x, k))}`; return d; };
function note(x, k, flag) {
  const y = wave(x, k), sl = Math.atan(-0.32 + Math.cos((x - 40) / 70) * 22 / 70) * 180 / Math.PI;
  return `<g transform="translate(${x} ${f(y)}) scale(1.4)"><ellipse rx="10.5" ry="7.4" transform="rotate(${f(sl - 22)})" fill="url(#ink)"/>
<path d="M9 -2V-50" stroke="url(#ink)" stroke-width="3.2" stroke-linecap="round"/>${flag ? '<path d="M9 -50q4 14 17 20q6 6 1 18q2 -16 -18 -22z" fill="url(#ink)"/>' : ''}</g>`;
}
files['an-staff'] = svg(`<linearGradient id="ink" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#FFF6CC"/><stop offset=".55" stop-color="#FFD45E"/><stop offset="1" stop-color="#E7A21E"/></linearGradient>
<clipPath id="in"><circle cx="${C}" cy="${C}" r="230"/></clipPath>
<linearGradient id="fade" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#FFE7A6" stop-opacity="0"/><stop offset=".25" stop-color="#FFE7A6" stop-opacity=".8"/><stop offset=".75" stop-color="#FFE7A6" stop-opacity=".8"/><stop offset="1" stop-color="#FFE7A6" stop-opacity="0"/></linearGradient>`,
  `<g clip-path="url(#in)"><g fill="none" stroke="url(#fade)" stroke-width="3">${[-2, -1, 0, 1, 2].map((k) => `<path d="${staffPath(k)}"/>`).join('')}</g>
${note(112, 1.5, false)}${note(178, -0.5, true)}${note(256, 1, false)}${note(330, -1.5, true)}${note(400, 0, false)}
${star(96, 120, 12, 2, '#FFFFFF')}${star(420, 236, 9, 1.6, '#FFFFFF')}</g>`);

// the colonnade (the app's mark): an architrave, five columns with capitals, the steps; struck gold, lit from the left
files['an-hall'] = svg(`<linearGradient id="g" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#FFF6CC"/><stop offset=".35" stop-color="#FFD45E"/><stop offset=".7" stop-color="#C98A0E"/><stop offset="1" stop-color="#8A5606"/></linearGradient>
<linearGradient id="v" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#FFF6CC"/><stop offset=".5" stop-color="#FFC940"/><stop offset="1" stop-color="#A96C08"/></linearGradient>
<filter id="sh" x="-20%" y="-20%" width="140%" height="160%"><feGaussianBlur stdDeviation="5"/></filter>`,
  (() => {
    const x0 = 136, w = 240, top = 282, colTop = 316, colBot = 392;
    const cols = [0, 1, 2, 3, 4].map((i) => x0 + 14 + i * ((w - 28 - 22) / 4));
    const body = `<path d="M${x0 - 6} ${top + 22}L${C} ${top - 26}L${x0 + w + 6} ${top + 22}z" fill="url(#v)"/>
<path d="M${x0 + 26} ${top + 14}L${C} ${top - 11}L${x0 + w - 26} ${top + 14}z" fill="#8A5606" opacity=".45"/>
<rect x="${x0 - 8}" y="${top + 20}" width="${w + 16}" height="12" rx="3" fill="url(#v)"/>
${cols.map((x) => `<rect x="${f(x - 3)}" y="${colTop - 4}" width="30" height="8" rx="2" fill="url(#v)"/><rect x="${f(x)}" y="${colTop}" width="24" height="${colBot - colTop}" fill="url(#g)"/><path d="M${f(x + 7.3)} ${colTop + 4}V${colBot - 3}M${f(x + 14.6)} ${colTop + 4}V${colBot - 3}" stroke="#8A5606" stroke-opacity=".35" stroke-width="1.4"/>`).join('')}
<rect x="${x0 - 10}" y="${colBot}" width="${w + 20}" height="10" rx="2" fill="url(#v)"/>
<rect x="${x0 - 24}" y="${colBot + 10}" width="${w + 48}" height="10" rx="2" fill="url(#v)"/>
<path d="M${x0 - 8} ${top + 21}H${x0 + w + 8}M${x0 - 10} ${colBot + 1}H${x0 + w + 10}M${x0 - 24} ${colBot + 11}H${x0 + w + 24}" stroke="#FFFFFF" stroke-opacity=".7" stroke-width="1.6"/>`;
    return `<g filter="url(#sh)" opacity=".55" transform="translate(0 8)">${body.replace(/url\(#[gv]\)/g, '#1A0A30')}</g>${body}`;
  })());
files['an-rim'] = rim(AN);

for (const [n, s] of Object.entries(files)) writeFileSync(new URL(`${n}.svg`, out), s);
console.log(Object.keys(files).length, 'files');
