// The orb's grains (ui/Orb.svelte): points on a sphere seen from the front, drawn once as two small SVGs, the near half
// and the far half, which the CSS turns slowly against each other. Each is three paths of zero-length round-capped
// strokes (dust, grains, a few bright ones): 7 and 4 KB, under 3 KB gzipped.
//   node tools/orb-dots.mjs   ->   src/assets/orb/near.svg, src/assets/orb/far.svg
import fs from 'node:fs';
let s = 7; const rnd = () => (s = (s * 16807) % 2147483647) / 2147483647; // seeded: the same picture every run
const layer = (n, near) => {
  const d = ['', '', ''];
  for (let i = 0; i < n; i++) {
    const z = rnd(), a = rnd() * 6.2832, r = Math.sqrt(1 - z * z) * 0.965; // z: towards the eye
    const k = rnd(), cls = k < 0.05 ? 2 : k < 0.3 ? 1 : 0;
    d[cls] += `M${(100 + Math.cos(a) * r * 100).toFixed(1)} ${(100 + Math.sin(a) * r * 100).toFixed(1)}h0`;
  }
  const w = near ? [0.55, 0.95, 1.7] : [0.45, 0.7, 1.1], o = near ? [0.5, 0.8, 1] : [0.3, 0.42, 0.55];
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 200 200" fill="none" stroke="#fff" stroke-linecap="round">${d.map((p, i) => `<path stroke-width="${w[i]}" opacity="${o[i]}" d="${p}"/>`).join('')}</svg>`;
};
fs.writeFileSync(new URL('../src/assets/orb/near.svg', import.meta.url), layer(520, true));
fs.writeFileSync(new URL('../src/assets/orb/far.svg', import.meta.url), layer(300, false));
